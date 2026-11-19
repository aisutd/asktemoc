"""
Compare two retrieval eval CSVs (strict mode) side by side.

    python scripts/compare_runs.py OLD.csv NEW.csv
    python scripts/compare_runs.py OLD.csv NEW.csv --labels "892 chunks" "874 chunks"
    python scripts/compare_runs.py OLD.csv NEW.csv --md        # markdown, for notes

Shows dense and BM25 next to each other, grouped into document-level metrics,
chunk-budget recall and context precision. "q" is the change expressed in
questions: change x number of questions (one question = 1/n of a mean).
Changes of at least --threshold questions (default 2) are colored.
"""
import argparse
import csv
import math

SECTIONS = [
    ("Document ranking", [("R@3", "Recall@3"), ("R@5", "Recall@5"), ("R@10", "Recall@10"),
                          ("MRR@10", "MRR@10"), ("nDCG@10", "nDCG@10")]),
    ("Recall in chunks sent", [("R@3chunks", "3 chunks"), ("R@5chunks", "5 chunks"),
                               ("R@8chunks", "8 chunks")]),
    ("Context precision", [("CP@3chunks", "3 chunks"), ("CP@5chunks", "5 chunks"),
                           ("CP@8chunks", "8 chunks")]),
]
METHODS = ("dense", "bm25")


def ndcg10(r):
    ranks = [int(h.split()[0][1:]) for h in r["hits_at_10"].split("; ") if h.strip()]
    ideal = sum(1 / math.log2(i + 1) for i in range(1, min(int(r["n_targets"]), 10) + 1))
    return sum(1 / math.log2(k + 1) for k in ranks) / ideal


def means(path):
    rows = [r for r in csv.DictReader(open(path, encoding="utf-8")) if r["mode"] == "strict"]
    out = {}
    for m in METHODS:
        g = [r for r in rows if r["method"] == m]
        if not g:
            continue
        vals = {"n": len(g)}
        for _, metrics in SECTIONS:
            for col, _ in metrics:
                if col == "nDCG@10":
                    vals[col] = sum(ndcg10(r) for r in g) / len(g)
                elif col in g[0]:
                    vals[col] = sum(float(r[col]) for r in g) / len(g)
        out[m] = vals
    return out


def cells(old, new, col):
    """(old, new, change, change in questions) as numbers or None."""
    o, n = old.get(col), new.get(col)
    if o is None or n is None:
        return o, n, None, None
    return o, n, n - o, (n - o) * new["n"]


def fmt(v):
    return "-" if v is None else f"{v:.3f}"


def print_md(old, new, labels, methods):
    print("| Metric | " + " | ".join(f"{m} {labels[0]} | {m} {labels[1]} | {m} change"
                                     for m in methods) + " |")
    print("|---|" + "---:|---:|---:|" * len(methods))
    for section, metrics in SECTIONS:
        print(f"| **{section}** |" + " |" * (3 * len(methods)))
        for col, label in metrics:
            row = [label]
            for m in methods:
                o, n, d, q = cells(old[m], new[m], col)
                row += [fmt(o), fmt(n), "-" if d is None else f"{d:+.3f} ({q:+.1f} q)"]
            print("| " + " | ".join(row) + " |")


def print_rich(old, new, labels, methods, threshold):
    from rich.console import Console
    from rich.table import Table

    t = Table(title=f"Retrieval eval, strict mode: {labels[0]} vs {labels[1]}",
              caption=f"q = change in questions ({new[methods[0]]['n']} questions); "
                      f"colored when |q| >= {threshold}",
              header_style="bold")
    t.add_column("Metric", style="bold")
    for m in methods:
        t.add_column(f"{m}\n{labels[0]}", justify="right")
        t.add_column(f"{m}\n{labels[1]}", justify="right")
        t.add_column(f"{m}\nchange", justify="right")
    for i, (section, metrics) in enumerate(SECTIONS):
        if i:
            t.add_section()
        t.add_row(f"[cyan]{section}[/cyan]", *[""] * (3 * len(methods)))
        for col, label in metrics:
            row = [f"  {label}"]
            for m in methods:
                o, n, d, q = cells(old[m], new[m], col)
                if d is None:
                    change = "[dim]-[/dim]"
                else:
                    change = f"{d:+.3f} ({q:+.1f} q)"
                    if abs(q) >= threshold:
                        change = f"[green]{change}[/green]" if d > 0 else f"[red]{change}[/red]"
                    elif abs(d) < 0.0005:
                        change = f"[dim]{change}[/dim]"
                row += [fmt(o), fmt(n), change]
            t.add_row(*row)
    Console().print(t)


def main():
    p = argparse.ArgumentParser(description="Compare two retrieval eval CSVs.")
    p.add_argument("old")
    p.add_argument("new")
    p.add_argument("--labels", nargs=2, default=["old", "new"], metavar=("OLD", "NEW"))
    p.add_argument("--method", choices=METHODS, help="show one method only")
    p.add_argument("--md", action="store_true", help="print a markdown table instead")
    p.add_argument("--threshold", type=float, default=2.0, help="questions needed to color a change")
    a = p.parse_args()
    old, new = means(a.old), means(a.new)
    methods = [a.method] if a.method else [m for m in METHODS if m in old and m in new]
    if a.md:
        print_md(old, new, a.labels, methods)
        return
    try:
        print_rich(old, new, a.labels, methods, a.threshold)
    except ImportError:
        print("rich is not installed (pip install rich); printing markdown instead.\n")
        print_md(old, new, a.labels, methods)


if __name__ == "__main__":
    main()
