"""
embed_pipeline.py — chunk, embed, and load the UTD corpus into Neon.

Documents come from corpus_prep.prepare_documents(): catalog pages (with combined and
copied certificate pages cut down to their own section), one catalog overview page, and
the Crawl4AI web pages. A document is re-embedded only when its content hash changed.
Identical chunks are stored once; the other sources are recorded in chunk_metadata.

Usage (crawl4ai-env activated):
    python backend/embed_pipeline.py --dry-run   # show what would change, no writes
    python backend/embed_pipeline.py

Settings:
    CHUNK_SIZE    = 512 tokens  (cl100k_base)
    CHUNK_OVERLAP = 64  tokens
    EMBED_MODEL   = text-embedding-3-small  (1536-dim)
    BATCH_SIZE    = 100 chunks per OpenAI call
"""

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import tiktoken
from dotenv import load_dotenv
from openai import OpenAI

from corpus_prep import prepare_documents, text_hash

# ── Config ────────────────────────────────────────────────────────────────────

CHUNK_SIZE    = 512
CHUNK_OVERLAP = 64
BATCH_SIZE    = 100
MIN_WORDS     = 30   # skip files with fewer words (footer-only scraping failures)
ENV_PATH      = Path(__file__).parent / ".env"
DUP_LOG       = Path(__file__).parent / "ingest_duplicates.log"
PRICE_PER_M   = 0.02  # USD per million tokens, text-embedding-3-small

load_dotenv(ENV_PATH)

DATABASE_URL  = os.environ["DATABASE_URL"]
OPENAI_KEY    = os.environ["OPENAI_API_KEY"]
EMBED_MODEL   = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
EMBED_DIMS    = 1536  # text-embedding-3-small native dimension

client = OpenAI(api_key=OPENAI_KEY)
enc    = tiktoken.get_encoding("cl100k_base")

# ── Helpers ───────────────────────────────────────────────────────────────────

def doc_id(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def chunk_text(text: str) -> list[str]:
    tokens = enc.encode(text)
    chunks = []
    start  = 0
    while start < len(tokens):
        end = min(start + CHUNK_SIZE, len(tokens))
        chunks.append(enc.decode(tokens[start:end]))
        if end == len(tokens):
            break
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def embed_batch(texts: list[str]) -> list[list[float]]:
    resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [item.embedding for item in sorted(resp.data, key=lambda x: x.index)]


def migrate_column(cur):
    """Alter vector column to 1536-dim and clear incompatible old rows."""
    cur.execute(
        "SELECT pg_catalog.format_type(atttypid, atttypmod) "
        "FROM pg_attribute JOIN pg_class ON attrelid = pg_class.oid "
        "WHERE relname = 'embeddings' AND attname = 'vector';"
    )
    col_type = cur.fetchone()[0]
    if col_type != f"vector({EMBED_DIMS})":
        print(f"  Altering embeddings.vector from {col_type} → vector({EMBED_DIMS})")
        cur.execute("DELETE FROM embeddings;")
        cur.execute("DELETE FROM chunks;")
        cur.execute("DELETE FROM documents;")
        cur.execute(f"ALTER TABLE embeddings ALTER COLUMN vector TYPE vector({EMBED_DIMS}) USING NULL;")
        print("  Column altered, old rows cleared.")
    else:
        print(f"  Column already vector({EMBED_DIMS}), no migration needed.")


def delete_doc(cur, did: str):
    cur.execute("DELETE FROM embeddings WHERE chunk_id IN (SELECT id FROM chunks WHERE document_id = %s);", (did,))
    cur.execute("DELETE FROM chunks WHERE document_id = %s;", (did,))


def log_dup(line: str):
    with open(DUP_LOG, "a") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat()} {line}\n")


# ── Planning ──────────────────────────────────────────────────────────────────

def plan(cur, docs, dropped):
    cur.execute("SELECT id, doc_metadata FROM documents WHERE is_deleted IS NOT TRUE;")
    existing = {r[0]: (r[1] or {}) for r in cur.fetchall()}
    cur.execute(
        "SELECT d.id FROM documents d LEFT JOIN chunks c ON c.document_id = d.id "
        "WHERE d.is_deleted IS NOT TRUE AND c.id IS NULL;"
    )
    empty_ids = {r[0] for r in cur.fetchall()}

    delete_ids = [doc_id(k) for k in dropped if doc_id(k) in existing]
    insert, replace, backfill, skip = [], [], [], []
    for d in docs:
        did = doc_id(d["key"])
        d["id"] = did
        if len(d["text"].split()) < MIN_WORDS:
            print(f"  [skip] {d['key']} ({len(d['text'].split())} words)")
            if did in existing:
                delete_ids.append(did)
            continue
        if did not in existing:
            insert.append(d)
            continue
        stored = existing[did].get("content_hash")
        if did in empty_ids:
            replace.append(d)
        elif stored == d["metadata"]["content_hash"]:
            skip.append(d)
        elif stored is None and d["kind"] == "catalog":
            backfill.append(d)
        else:
            replace.append(d)
    return existing, delete_ids, insert, replace, backfill, skip


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="show the plan, write nothing")
    args = ap.parse_args()

    docs, dropped, flagged = prepare_documents()
    for k in flagged:
        print(f"  [needs re-scrape] {k}: no certificate section found on its page")

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur  = conn.cursor()

    print(f"Model:  {EMBED_MODEL}  ({EMBED_DIMS}-dim)")
    print(f"Chunks: size={CHUNK_SIZE} tokens, overlap={CHUNK_OVERLAP} tokens")
    if not args.dry_run:
        migrate_column(cur)
        conn.commit()

    existing, delete_ids, insert, replace, backfill, skip = plan(cur, docs, dropped)
    to_build = insert + replace
    est_tokens = sum(len(enc.encode(d["text"])) for d in to_build)

    print(f"\nPrepared documents: {len(docs)}   in Neon now: {len(existing)}")
    print(f"  delete (dropped duplicates/junk): {len(delete_ids)}")
    print(f"  insert new:                       {len(insert)}")
    print(f"  replace (content changed):        {len(replace)}")
    print(f"  backfill hash only:               {len(backfill)}")
    print(f"  unchanged:                        {len(skip)}")
    print(f"  ~{est_tokens:,} tokens to embed  (≈ ${est_tokens / 1e6 * PRICE_PER_M:.3f})")

    if args.dry_run:
        for label, items in (("DELETE", delete_ids), ("INSERT", [d["key"] for d in insert]),
                             ("REPLACE", [d["key"] for d in replace])):
            print(f"\n{label}:")
            for x in items:
                print("  ", x)
        conn.close()
        return

    # ── 1. Apply deletes, replacements, hash backfills ────────────────────────
    for did in delete_ids:
        delete_doc(cur, did)
        cur.execute("DELETE FROM documents WHERE id = %s;", (did,))
    for d in replace:
        delete_doc(cur, d["id"])
        cur.execute(
            "UPDATE documents SET title=%s, source=%s, doc_metadata=%s, updated_at=NOW() WHERE id=%s;",
            (d["title"], d["source"], json.dumps(d["metadata"]), d["id"]),
        )
    for d in backfill:
        cur.execute(
            "UPDATE documents SET doc_metadata=%s WHERE id=%s;",
            (json.dumps({**existing[d["id"]], **d["metadata"]}), d["id"]),
        )
    for d in insert:
        cur.execute(
            """
            INSERT INTO documents (id, title, source, doc_metadata, created_at, updated_at, is_deleted)
            VALUES (%s, %s, %s, %s, NOW(), NOW(), FALSE);
            """,
            (d["id"], d["title"], d["source"], json.dumps(d["metadata"])),
        )
    conn.commit()
    print("\nDocument changes applied.")

    # ── 2. Known chunk hashes (for merging identical chunks) ──────────────────
    cur.execute(
        "SELECT c.id, c.text, d.title FROM chunks c JOIN documents d ON d.id = c.document_id "
        "WHERE c.is_deleted IS NOT TRUE AND d.is_deleted IS NOT TRUE;"
    )
    known = {}
    for cid, text, title in cur.fetchall():
        known.setdefault(text_hash(text), (cid, title))

    # ── 3. Chunk new/changed documents ────────────────────────────────────────
    new_chunks: list[dict] = []
    also_in: dict[str, set] = {}
    merged = 0
    for d in to_build:
        for idx, chunk in enumerate(chunk_text(d["text"])):
            h = text_hash(chunk)
            if h in known:
                kept_id, kept_title = known[h]
                merged += 1
                if kept_title != d["title"]:
                    also_in.setdefault(kept_id, set()).add(d["title"])
                log_dup(f"chunk-duplicate doc={d['title']} idx={idx} kept_in={kept_title}")
                continue
            cid = hashlib.sha256(f"{d['id']}:{idx}".encode()).hexdigest()[:32]
            known[h] = (cid, d["title"])
            new_chunks.append({"chunk_id": cid, "doc_id": d["id"], "index": idx, "text": chunk})

    for cid, titles in also_in.items():
        cur.execute("SELECT chunk_metadata FROM chunks WHERE id = %s;", (cid,))
        row = cur.fetchone()
        meta = (row[0] if row and row[0] else {}) or {}
        meta["also_in"] = sorted(set(meta.get("also_in", [])) | titles)
        cur.execute("UPDATE chunks SET chunk_metadata = %s WHERE id = %s;", (json.dumps(meta), cid))
    conn.commit()
    print(f"New chunks to embed: {len(new_chunks)}   identical chunks merged: {merged}")

    # ── 4. Embed in batches and insert ────────────────────────────────────────
    total, done, t_start = len(new_chunks), 0, time.time()
    for i in range(0, total, BATCH_SIZE):
        batch = new_chunks[i : i + BATCH_SIZE]
        vecs  = embed_batch([c["text"] for c in batch])
        for c, vec in zip(batch, vecs):
            cur.execute(
                """
                INSERT INTO chunks (id, document_id, chunk_index, text, chunk_metadata, created_at, updated_at, is_deleted)
                VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), FALSE)
                ON CONFLICT (id) DO NOTHING;
                """,
                (c["chunk_id"], c["doc_id"], c["index"], c["text"], json.dumps({"chunk_index": c["index"]})),
            )
            eid = hashlib.sha256(f"emb:{c['chunk_id']}".encode()).hexdigest()[:32]
            cur.execute(
                """
                INSERT INTO embeddings (id, chunk_id, vector, model, is_synced, created_at, updated_at)
                VALUES (%s, %s, %s::vector, %s, FALSE, NOW(), NOW())
                ON CONFLICT (id) DO NOTHING;
                """,
                (eid, c["chunk_id"], str(vec), EMBED_MODEL),
            )
        conn.commit()
        done += len(batch)
        rate = done / (time.time() - t_start)
        print(f"  [{done}/{total}]  {rate:.1f} chunks/s")

    conn.close()
    print(f"\nDone. {done} chunks embedded, {merged} merged, model {EMBED_MODEL} ({EMBED_DIMS}-dim)")


if __name__ == "__main__":
    main()
