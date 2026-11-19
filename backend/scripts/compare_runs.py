"""
Compare two retrieval eval CSVs side by side (strict mode), as a markdown table.

    python scripts/compare_runs.py OLD.csv NEW.csv [--method dense]
"""
import argparse
import csv
import math

COLS = [("R@3", "Recall@3 (docs)"), ("R@5", "Recall@5 (docs)"), ("R@10", "Recall@10 (docs)"),
        ("MRR@10", "MRR@10"), ("nDCG@10", "nDCG@10"),
        ("R@3chunks", "Recall within 3 chunks"), ("R@5chunks", "Recall within 5 chunks"),
        ("R@8chunks", "Recall within 8 chunks"),
        ("CP@3chunks", "Context precision, 3 chunks"), ("CP@5chunks", "Context precision, 5 chunks")]


def ndcg10(r):
    ranks = [int(h.split()[0][1:]) for h in r["hits_at_10"].split("; ") if h.strip()]
    n = int(r["n_targets"])
    ideal = sum(1 / math.log2(i + 1) for i in range(1, min(n, 10) + 1))
    return sum(1 / math.log2(k + 1) for k in ranks) / ideal


def means(path, method):
    rows = [r for r in csv.DictReader(open(path, encoding="utf-8"))
            if r["mode"] == "strict" and r["method"] == method]
    out = {"n": len(rows)}
    for col, _ in COLS:
        if col == "nDCG@10":
            out[col] = sum(ndcg10(r) for r in rows) / len(rows)
        elif col in rows[0]:
            out[col] = sum(float(r[col]) for r in rows) / len(rows)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("old")
    p.add_argument("new")
    p.add_argument("--method", default="dense")
    a = p.parse_args()
    o, n = means(a.old, a.method), means(a.new, a.method)
    print(f"{a.method}, strict ({o['n']} vs {n['n']} questions)\n")
    print("| Metric | Old | New | Change |")
    print("|---|---:|---:|---:|")
    for col, label in COLS:
        ov, nv = o.get(col), n.get(col)
        f = lambda v: "n/a" if v is None else f"{v:.3f}"
        d = "" if ov is None or nv is None else f"{nv - ov:+.3f}"
        print(f"| {label} | {f(ov)} | {f(nv)} | {d} |")


if __name__ == "__main__":
    main()