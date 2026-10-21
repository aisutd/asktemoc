"""
Embed every corpus chunk with text-embedding-3-large into a local, gitignored
cache (backend/.cache/chunk_embeddings_text-embedding-3-large.npz).

    cd backend && python scripts/embed_chunks_large.py --dry-run   # estimate only
    cd backend && python scripts/embed_chunks_large.py

Chunk texts come from the BM25 chunk cache (read from Neon once); nothing is
written to Neon. Only chunks without a cached vector for their current text are
embedded, so reruns are free and an interrupted run resumes. The estimate uses
tiktoken cl100k_base (the text-embedding-3 tokenizer), and the run aborts
before any API call if it exceeds --max-cost.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from retrieval.bm25 import get_index  # noqa: E402
from retrieval.local_dense import LARGE_MODEL, cache_path, embed_chunks, missing_chunks  # noqa: E402

# USD per 1M input tokens (OpenAI list price for text-embedding-3-large).
PRICE_PER_M = 0.13


def main():
    parser = argparse.ArgumentParser(description=f"Embed corpus chunks with {LARGE_MODEL}.")
    parser.add_argument("--dry-run", action="store_true", help="print the estimate and stop")
    parser.add_argument("--max-cost", type=float, default=0.50, help="abort above this estimate (USD)")
    parser.add_argument("--refresh-bm25", action="store_true", help="reload chunk texts from Neon first")
    args = parser.parse_args()

    import tiktoken

    chunks = get_index(refresh=args.refresh_bm25).chunks
    path = cache_path(LARGE_MODEL)
    todo = missing_chunks(chunks, path)
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = sum(len(enc.encode(c["text"])) for c in todo)
    cost = tokens / 1e6 * PRICE_PER_M
    print(f"{len(chunks)} chunks, {len(chunks) - len(todo)} cached, {len(todo)} to embed")
    print(f"estimate: {tokens} tokens -> ${cost:.4f} at ${PRICE_PER_M}/1M ({LARGE_MODEL})")
    if args.dry_run or not todo:
        return
    if cost > args.max_cost:
        sys.exit(f"estimate ${cost:.4f} is over --max-cost ${args.max_cost:.2f}; nothing embedded")

    n = embed_chunks(chunks, model=LARGE_MODEL, path=path,
                     on_batch=lambda done, total: print(f"  {done}/{total}"))
    print(f"embedded {n} chunks -> {path}")


if __name__ == "__main__":
    main()
