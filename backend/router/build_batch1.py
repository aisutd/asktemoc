"""
Build the first labeled query-router batch from the two hand-written sources.

    python -m router.build_batch1        (from backend/)

Reads router/data/corpus_grounded.csv and router/data/seed_synthetic.csv, and
writes router/data/labels_batch1.csv with an 80/20 train/test split stratified
by label and source (seed 42). Also writes router/data/eval_set_check.csv from eval/eval_set.json.
The test rows are frozen: later batches go in new files, never back into this
one, so rerunning this script must reproduce the same split.
"""

import csv
import json
import random
from collections import defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
DATA = BACKEND / "router" / "data"
SOURCES = [DATA / "corpus_grounded.csv", DATA / "seed_synthetic.csv"]
EVAL_SET = BACKEND / "eval" / "eval_set.json"

COLUMNS = ["id", "query", "label", "in_corpus", "confidence", "source", "note"]
SEED = 42
TEST_FRACTION = 0.2


def read_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_rows(path, rows, columns):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def split(rows):
    """
    Assign split=test to round(20%) of each (label, source) group, chosen with a
    seeded shuffle, so off-corpus academics questions are held out too.
    """
    rng = random.Random(SEED)
    groups = defaultdict(list)
    for row in rows:
        groups[(row["label"], row["source"])].append(row["id"])
    test = set()
    for key in sorted(groups):
        ids = sorted(groups[key])
        rng.shuffle(ids)
        test.update(ids[:round(len(ids) * TEST_FRACTION)])
    return [{**row, "split": "test" if row["id"] in test else "train"} for row in rows]


def main():
    rows = [row for path in SOURCES for row in read_rows(path)]
    seen = set()
    for row in rows:
        key = row["query"].strip().lower()
        if key in seen:
            raise ValueError(f"duplicate query: {row['query']!r}")
        seen.add(key)
    write_rows(DATA / "labels_batch1.csv", split(rows), COLUMNS + ["split"])

    questions = json.loads(EVAL_SET.read_text(encoding="utf-8"))["questions"]
    check = [{"id": q["id"], "query": q["question"], "label": "academics", "in_corpus": "yes",
              "confidence": "high", "source": "eval_set", "note": "sanity check only"}
             for q in questions]
    write_rows(DATA / "eval_set_check.csv", check, COLUMNS)


if __name__ == "__main__":
    main()
