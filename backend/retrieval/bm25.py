"""
BM25 (rank_bm25.BM25Okapi) over the same Neon chunks as dense retrieval.

The chunk table is read from Neon once and cached to backend/.cache/ (gitignored)
as JSON; the index itself is rebuilt from that file on load, which takes well
under a second for ~900 chunks. Pass refresh=True after the corpus is re-ingested.
"""

import json
import re
from pathlib import Path

from retrieval.db import check_k, connect

CACHE_PATH = Path(__file__).resolve().parents[1] / ".cache" / "bm25_chunks.json"
CACHE_VERSION = 1

CHUNKS_SQL = """
    SELECT c.id, c.document_id, d.title, c.chunk_index, c.text
    FROM chunks c
    JOIN documents d ON d.id = c.document_id
    WHERE NOT c.is_deleted AND NOT d.is_deleted
    ORDER BY d.title, c.chunk_index
"""

# Tokenization: lowercase, then runs of ASCII letters/digits. Punctuation and
# whitespace split tokens, so "CS 1337" -> ["cs", "1337"] and "(UX)" -> ["ux"].
# No stemming and no stopword list: kept deliberately simple as a baseline, and
# BM25's IDF already down-weights words that appear in most chunks.
_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text):
    return _TOKEN.findall(text.lower())


def load_chunks(conn=None):
    """All live chunks from Neon as dicts (same keys as a result, minus score)."""
    own = conn is None
    conn = connect() if own else conn
    try:
        with conn.cursor() as cur:
            cur.execute(CHUNKS_SQL)
            rows = cur.fetchall()
    finally:
        if own:
            conn.close()
    return [
        {"chunk_id": cid, "document_id": did, "doc_title": title,
         "chunk_index": idx, "text": text}
        for cid, did, title, idx, text in rows
    ]


class BM25Index:
    def __init__(self, chunks):
        from rank_bm25 import BM25Okapi

        if not chunks:
            raise ValueError("cannot build a BM25 index over zero chunks")
        self.chunks = chunks
        self.bm25 = BM25Okapi([tokenize(c["text"]) for c in chunks])

    def search(self, query, k):
        check_k(k)
        scores = self.bm25.get_scores(tokenize(query))
        # Ties (including all-zero scores) fall back to corpus order, so runs are stable.
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))[:k]
        return [{**self.chunks[i], "score": float(scores[i])} for i in order]


def _read_cache(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if data.get("version") != CACHE_VERSION:
        return None
    return data["chunks"]


def _write_cache(path, chunks):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version": CACHE_VERSION, "chunks": chunks}), encoding="utf-8")
    tmp.replace(path)


_indexes = {}


def get_index(*, refresh=False, cache_path=CACHE_PATH, loader=load_chunks):
    """The BM25 index, built once per process from the cache file (or Neon if missing)."""
    key = str(cache_path)
    if refresh or key not in _indexes:
        chunks = None if refresh else _read_cache(cache_path)
        if chunks is None:
            chunks = loader()
            _write_cache(cache_path, chunks)
        _indexes[key] = BM25Index(chunks)
    return _indexes[key]


def bm25_search(query, k, *, index=None):
    """Top-k chunks for query by BM25 score. Same result shape as retrieve()."""
    return (index or get_index()).search(query, k)
