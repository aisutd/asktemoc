"""
embed_pipeline.py — chunk, embed, and load the UTD catalog corpus into Neon.

Reads all .txt files under backend/test_output/, chunks them with tiktoken,
embeds with text-embedding-3-small, and upserts into the Neon
documents / chunks / embeddings tables.

Usage (from repo root, with crawl4ai-env activated):
    python backend/embed_pipeline.py

Settings:
    CHUNK_SIZE    = 512 tokens  (cl100k_base)
    CHUNK_OVERLAP = 64  tokens
    EMBED_MODEL   = text-embedding-3-small  (1536-dim)
    BATCH_SIZE    = 100 chunks per OpenAI call
"""

import hashlib
import json
import os
import sys
import time
from pathlib import Path

import psycopg2
import tiktoken
from dotenv import load_dotenv
from openai import OpenAI

# ── Config ────────────────────────────────────────────────────────────────────

CHUNK_SIZE    = 512
CHUNK_OVERLAP = 64
BATCH_SIZE    = 100
CORPUS_DIR    = Path(__file__).parent / "test_output"
ENV_PATH      = Path(__file__).parent / ".env"

load_dotenv(ENV_PATH)

DATABASE_URL  = os.environ["DATABASE_URL"]
OPENAI_KEY    = os.environ["OPENAI_API_KEY"]
EMBED_MODEL   = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
EMBED_DIMS    = 1536  # text-embedding-3-small native dimension

client = OpenAI(api_key=OPENAI_KEY)
enc    = tiktoken.get_encoding("cl100k_base")

# ── Helpers ───────────────────────────────────────────────────────────────────

def doc_id(path: Path) -> str:
    return hashlib.sha256(str(path.relative_to(CORPUS_DIR)).encode()).hexdigest()[:32]


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


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    txt_files = sorted(CORPUS_DIR.rglob("*.txt"))
    if not txt_files:
        print(f"No .txt files found in {CORPUS_DIR}", file=sys.stderr)
        sys.exit(1)

    print(f"Corpus: {len(txt_files)} files in {CORPUS_DIR}")
    print(f"Model:  {EMBED_MODEL}  ({EMBED_DIMS}-dim)")
    print(f"Chunks: size={CHUNK_SIZE} tokens, overlap={CHUNK_OVERLAP} tokens")
    print()

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur  = conn.cursor()

    # ── 1. Migrate column if needed ───────────────────────────────────────────
    migrate_column(cur)
    conn.commit()

    # ── 2. Load existing doc IDs to skip duplicates ───────────────────────────
    cur.execute("SELECT id FROM documents;")
    existing_doc_ids = {row[0] for row in cur.fetchall()}
    print(f"Existing docs in DB: {len(existing_doc_ids)}")

    # ── 3. Parse corpus ───────────────────────────────────────────────────────
    all_chunks: list[dict] = []  # {doc_id, chunk_index, text, doc_meta}

    skipped = 0
    for path in txt_files:
        did  = doc_id(path)
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            continue

        program = path.parent.name  # e.g. "bs_in_computer_science"
        filename = path.stem        # e.g. "requirements"

        if did in existing_doc_ids:
            skipped += 1
            continue

        cur.execute(
            """
            INSERT INTO documents (id, title, source, doc_metadata, created_at, updated_at, is_deleted)
            VALUES (%s, %s, %s, %s, NOW(), NOW(), FALSE)
            ON CONFLICT (id) DO NOTHING;
            """,
            (did, f"{program}/{filename}", str(path), json.dumps({"program": program, "file": filename}))
        )

        for idx, chunk in enumerate(chunk_text(text)):
            cid = hashlib.sha256(f"{did}:{idx}".encode()).hexdigest()[:32]
            cur.execute(
                """
                INSERT INTO chunks (id, document_id, chunk_index, text, chunk_metadata, created_at, updated_at, is_deleted)
                VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), FALSE)
                ON CONFLICT (id) DO NOTHING;
                """,
                (cid, did, idx, chunk, json.dumps({"chunk_index": idx}))
            )
            all_chunks.append({"chunk_id": cid, "text": chunk})

    conn.commit()
    print(f"Skipped {skipped} already-embedded docs.")
    print(f"New chunks to embed: {len(all_chunks)}")

    if not all_chunks:
        print("Nothing new to embed.")
        conn.close()
        return

    # ── 4. Embed in batches and insert ────────────────────────────────────────
    total   = len(all_chunks)
    done    = 0
    t_start = time.time()

    for i in range(0, total, BATCH_SIZE):
        batch  = all_chunks[i : i + BATCH_SIZE]
        texts  = [c["text"] for c in batch]
        vecs   = embed_batch(texts)

        for c, vec in zip(batch, vecs):
            eid = hashlib.sha256(f"emb:{c['chunk_id']}".encode()).hexdigest()[:32]
            cur.execute(
                """
                INSERT INTO embeddings (id, chunk_id, vector, model, is_synced, created_at, updated_at)
                VALUES (%s, %s, %s::vector, %s, FALSE, NOW(), NOW())
                ON CONFLICT (id) DO NOTHING;
                """,
                (eid, c["chunk_id"], str(vec), EMBED_MODEL)
            )

        conn.commit()
        done += len(batch)
        elapsed = time.time() - t_start
        rate    = done / elapsed if elapsed > 0 else 0
        eta     = (total - done) / rate if rate > 0 else 0
        print(f"  [{done}/{total}]  {rate:.1f} chunks/s  ETA {eta:.0f}s")

    conn.close()

    # ── 5. Summary ────────────────────────────────────────────────────────────
    elapsed = time.time() - t_start
    print()
    print("=" * 60)
    print(f"Done.  {done} chunks embedded in {elapsed:.1f}s")
    print(f"Model: {EMBED_MODEL} ({EMBED_DIMS}-dim)")
    print("=" * 60)


if __name__ == "__main__":
    main()
