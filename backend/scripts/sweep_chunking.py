"""
Chunk-size sweep over the local deduped corpus (no Neon).

    python scripts/sweep_chunking.py --dry-run     # chunk counts and cost only, no API calls

Builds the corpus with corpus_prep.prepare_documents(), skips documents under
MIN_WORDS (as embed_pipeline.py does), chunks each with tiktoken cl100k_base at
each (size, overlap) config, then merges identical chunks: across all documents,
in corpus_prep order, the first document containing a chunk keeps it (the same
rule embed_pipeline.py applies, but over the whole corpus at once, so it is
not order-of-ingestion dependent like Neon).
"""
import argparse
import sys
from pathlib import Path

import tiktoken

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import corpus_prep  # noqa: E402
from corpus_prep import prepare_documents, text_hash  # noqa: E402

ENC = tiktoken.get_encoding("cl100k_base")
CONFIGS = [(256, 32), (384, 48), (512, 64), (768, 96), (1024, 128)]
MIN_WORDS = 30          # same filter as embed_pipeline.py
PRICE_SMALL = 0.02      # USD per 1M tokens, text-embedding-3-small
PRICE_LARGE = 0.13      # USD per 1M tokens, text-embedding-3-large


def chunk_text(text, size, overlap):
    """Same token windows as embed_pipeline.chunk_text, with size/overlap as arguments."""
    tokens = ENC.encode(text)
    chunks, start = [], 0
    while start < len(tokens):
        end = min(start + size, len(tokens))
        chunks.append(ENC.decode(tokens[start:end]))
        if end == len(tokens):
            break
        start += size - overlap
    return chunks


def load_documents(corpus_dir=None, web_dir=None):
    """Documents to chunk. corpus_dir / web_dir override corpus_prep's folders."""
    if corpus_dir:
        corpus_prep.CORPUS_DIR = Path(corpus_dir).resolve()
    if web_dir:
        corpus_prep.WEB_DIR = Path(web_dir).resolve()
    docs, _, _ = prepare_documents()
    return [d for d in docs if len(d["text"].split()) >= MIN_WORDS]


def build_chunks(docs, size, overlap):
    """Chunks for one config, identical chunks merged. Returns (chunks, merged_count)."""
    seen, out, merged = set(), [], 0
    for d in docs:
        for i, text in enumerate(chunk_text(d["text"], size, overlap)):
            h = text_hash(text)
            if h in seen:
                merged += 1
                continue
            seen.add(h)
            out.append({"doc_title": d["title"], "chunk_index": i, "text": text,
                        "tokens": len(ENC.encode(text))})
    return out, merged


def main():
    p = argparse.ArgumentParser(description="Chunk-size sweep over the local corpus.")
    p.add_argument("--dry-run", action="store_true", help="print chunk counts and cost, no API calls")
    p.add_argument("--corpus-dir", help="catalog folder to read (default: corpus_prep.CORPUS_DIR)")
    p.add_argument("--web-dir", help="Crawl4AI folder to read (default: corpus_prep.WEB_DIR)")
    args = p.parse_args()

    docs = load_documents(args.corpus_dir, args.web_dir)
    print(f"catalog: {corpus_prep.CORPUS_DIR}\nweb:     {corpus_prep.WEB_DIR}")
    print(f"{len(docs)} documents after the {MIN_WORDS}-word filter\n")
    print(f"{'config':>9} {'docs':>5} {'chunks':>7} {'merged':>7} {'tokens':>9} "
          f"{'avg tok':>8} {'small $':>8} {'large $':>8}")
    for size, overlap in CONFIGS:
        chunks, merged = build_chunks(docs, size, overlap)
        tokens = sum(c["tokens"] for c in chunks)
        n_docs = len({c["doc_title"] for c in chunks})
        print(f"{size:>4}/{overlap:<4} {n_docs:>5} {len(chunks):>7} {merged:>7} {tokens:>9,} "
              f"{tokens / len(chunks):>8.0f} {tokens / 1e6 * PRICE_SMALL:>8.4f} "
              f"{tokens / 1e6 * PRICE_LARGE:>8.4f}")
    if not args.dry_run:
        print("\nEmbedding is not implemented yet; run with --dry-run.")


if __name__ == "__main__":
    main()
