"""
Print dense (pgvector) and BM25 top-k for one query side by side.

    cd backend && python scripts/compare_retrieval.py "What does the BS in Neuroscience require?" -k 5

Each column shows doc_title #chunk_index and score. Dense score is cosine
similarity (0..1); BM25 score is unbounded, so compare ranks, not numbers.
A "*" marks a document that appears in both lists. Long title prefixes are
abbreviated (see PREFIXES) so the distinguishing part of the name stays visible.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from retrieval import bm25_search, retrieve  # noqa: E402
from retrieval.bm25 import get_index  # noqa: E402

PREFIXES = [
    ("bachelor_of_science_in_", "bs:"),
    ("bachelor_of_arts_in_", "ba:"),
    ("certificate_in_", "cert:"),
    ("bs_in_", "bs2:"),
    ("ba_in_", "ba2:"),
]
SUFFIXES = [("/requirements", "/req"), ("/example", "/ex")]


def shorten(title, width):
    for long, short in PREFIXES:
        if title.startswith(long):
            title = short + title[len(long):]
            break
    for long, short in SUFFIXES:
        if title.endswith(long):
            title = title[: -len(long)] + short
    return title if len(title) <= width else title[: width - 1] + "…"


def cell(hit, shared, width):
    mark = "*" if hit["doc_title"] in shared else " "
    suffix = f" #{hit['chunk_index']}"
    label = shorten(hit["doc_title"], width - 10 - len(suffix)) + suffix
    return f"{mark}{label:<{width - 10}} {hit['score']:>8.4f}"


def main():
    parser = argparse.ArgumentParser(description="Dense vs BM25 top-k for one query.")
    parser.add_argument("query")
    parser.add_argument("-k", type=int, default=5, help="results per method (default 5)")
    parser.add_argument("--width", type=int, default=64, help="column width (default 64)")
    parser.add_argument("--refresh-bm25", action="store_true",
                        help="reload chunks from Neon instead of the local cache")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    dense = retrieve(args.query, args.k)
    sparse = bm25_search(args.query, args.k, index=get_index(refresh=args.refresh_bm25))
    shared = {h["doc_title"] for h in dense} & {h["doc_title"] for h in sparse}

    w = args.width
    print(f"query: {args.query}\nk={args.k}")
    legend = ", ".join(f"{short}={long}" for long, short in PREFIXES + SUFFIXES)
    print(f"legend: {legend}; * = document in both lists\n")
    print(f"{'#':>2}  {'DENSE (cosine)':<{w}}  {'BM25':<{w}}")
    print(f"{'':>2}  {'-' * w}  {'-' * w}")
    for i in range(args.k):
        left = cell(dense[i], shared, w) if i < len(dense) else ""
        right = cell(sparse[i], shared, w) if i < len(sparse) else ""
        print(f"{i + 1:>2}  {left:<{w}}  {right}")


if __name__ == "__main__":
    main()
