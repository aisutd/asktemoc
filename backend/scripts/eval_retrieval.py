"""
Evaluate dense (pgvector) and BM25 retrieval on the 30 eval questions.

    cd backend && python scripts/eval_retrieval.py

1. Reads eval_questions.md (by default from origin/feat/crawl4ai-scraper via
   git show; --questions-file to use a local copy), parses it, and writes the
   parsed set to eval/eval_set.json for checking. Labels are never modified.
2. For each question and method, takes a pool of top chunks and collapses it
   to a document ranking (first chunk of each document counts; later chunks of
   the same document are repeats and are tallied).
3. Scores Precision@k, Recall@k, MRR@k for k in 1, 3, 5, 10 in two modes:
   STRICT (only exact target titles) and DUPLICATE-AWARE (documents with
   identical text, or difflib ratio >= 0.99 to a target, also count).
4. Writes eval/results/retrieval_eval_<date>.md and .csv.

    python scripts/eval_retrieval.py --large

adds "dense-large": text-embedding-3-large over the local chunk vectors from
scripts/embed_chunks_large.py (queries embedded with the large model too), and
writes retrieval_eval_<date>_small-vs-large.md/.csv with a small-vs-large
section. Without --large the output is the dense + BM25 report alone.

Neon is only read. Query embeddings are cached in backend/.cache/ so reruns
make no OpenAI calls for questions already seen.
"""

import argparse
import csv
import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from retrieval.bm25 import bm25_search, get_index  # noqa: E402
from retrieval.db import connect  # noqa: E402
from retrieval.dense import EMBED_MODEL, openai_embed, retrieve  # noqa: E402
from retrieval.local_dense import LARGE_MODEL, load_index, local_retrieve  # noqa: E402
from retrieval.evaluate import (  # noqa: E402
    KS, NEAR_THRESHOLD, doc_ranking, duplicate_classes, parse_questions,
    repeat_stats, score, strict_classes,
)

QUESTIONS_REF = "origin/feat/crawl4ai-scraper"
QUESTIONS_PATH = "backend/eval_questions.md"
EVAL_DIR = BACKEND / "eval"
CACHE_DIR = BACKEND / ".cache"
# Query embeddings per model. The small model keeps its original file name so
# earlier runs reuse the exact same vectors.
EMBED_CACHES = {EMBED_MODEL: CACHE_DIR / "query_embeddings.json",
                LARGE_MODEL: CACHE_DIR / f"query_embeddings_{LARGE_MODEL}.json"}
INDEX_PAGES = {"1/requirements", "2/requirements", "3/requirements"}
METHODS = ("dense", "bm25")
LARGE_METHODS = ("dense", "dense-large", "bm25")
METHOD_LABELS = {
    "dense": ("Dense", f"`{EMBED_MODEL}` query embedding, pgvector cosine distance, exact scan"),
    "dense-large": ("Dense-large", f"`{LARGE_MODEL}` for chunks and queries, exact cosine in numpy "
                                   "over locally cached chunk vectors (same 885 chunks as Neon)"),
    "bm25": ("BM25", "rank_bm25 BM25Okapi, lowercase + `[a-z0-9]+` tokens, no stemming or stopwords"),
}
MODES = ("strict", "duplicate-aware")
# Chunk budgets: what the generation step would receive with k chunks of context.
CHUNK_BUDGETS = (3, 5, 8)


def git(*args):
    return subprocess.run(["git", *args], cwd=BACKEND.parent, capture_output=True,
                          text=True, encoding="utf-8", check=True).stdout


def load_questions_md(path):
    if path:
        return Path(path).read_text(encoding="utf-8"), {"file": str(path)}
    spec = f"{QUESTIONS_REF}:{QUESTIONS_PATH}"
    return git("show", spec), {
        "git": spec,
        "blob": git("rev-parse", spec).strip(),
        # last commit on the ref that touched the file, and the ref's tip when read
        "commit": git("log", "-1", "--format=%H", QUESTIONS_REF, "--", QUESTIONS_PATH).strip(),
        "ref_tip": git("rev-parse", QUESTIONS_REF).strip(),
    }


class CachedEmbedder:
    """Query embeddings keyed by exact text, persisted as JSON (gitignored)."""

    def __init__(self, model, path=None):
        self.model, self.path, self.misses = model, path or EMBED_CACHES[model], 0
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.vectors = data["vectors"] if data.get("model") == model else {}
        except (OSError, ValueError, KeyError):
            self.vectors = {}

    def __call__(self, text):
        if text not in self.vectors:
            self.vectors[text] = openai_embed(text, self.model)
            self.misses += 1
        return self.vectors[text]

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"model": self.model, "vectors": self.vectors}), encoding="utf-8")


def fmt(x):
    return f"{x:.3f}"


def first_hit(s):
    return s["relevant"][0]["rank"] if s["relevant"] else None


def hits_str(s, duplicates_only=False):
    """
    Relevant documents in rank order. A non-target document is shown as
    "#rank doc -> target [exact|near (ratio)]", plus ", rescued" when it is the
    first document credited to that target (so it raised recall or MRR, not
    just precision).
    """
    out = []
    for r in s["relevant"]:
        if "target" in r["matches"].values():
            if not duplicates_only:
                out.append(f"#{r['rank']} {r['doc']}")
            continue
        via = ", ".join(
            f"{t} [{label}{', rescued' if s['credited'][t]['doc'] == r['doc'] else ''}]"
            for t, label in r["matches"].items())
        out.append(f"#{r['rank']} {r['doc']} -> {via}")
    return "; ".join(out)


def evaluate(questions, retrievers, classes):
    """retrievers: {method: fn(question) -> chunk hits, best first}."""
    results = {}
    for q in questions:
        for method, fetch in retrievers.items():
            h = fetch(q["question"])
            ranking = [d["doc_title"] for d in doc_ranking(h)]
            results[q["id"], method] = {
                "ranking": ranking,
                "repeats": repeat_stats(h, 10),
                "index_docs_top5": sum(d in INDEX_PAGES for d in ranking[:5]),
                "index_chunks_top5": sum(x["doc_title"] in INDEX_PAGES for x in h[:5]),
                "scores": {mode: {k: score(ranking, q["relevant"], classes[mode], k) for k in KS}
                           for mode in MODES},
                # Raw chunk ranking, repeats kept: rank = chunk position.
                "budget": {mode: {b: score([x["doc_title"] for x in h], q["relevant"], classes[mode], b)
                                  for b in CHUNK_BUDGETS}
                           for mode in MODES},
            }
    return results


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def write_csv(path, questions, results, today, methods):
    metric_cols = [f"{m}@{k}" for m in ("R", "MRR", "P") for k in KS]
    budget_cols = [f"{m}@{b}chunks" for m in ("R", "MRR") for b in CHUNK_BUDGETS]
    cols = ["date", "question_id", "question", "method", "mode", "n_targets", "targets",
            *metric_cols, *budget_cols, "first_hit_rank_at_10", "hits_at_10", "duplicate_hits_at_10",
            "changed_vs_strict", "top5_docs", "index_pages_in_top5_docs",
            "repeats_in_top10_chunks", "chunks_to_fill_10_docs", "docs_in_pool"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for q in questions:
            for method in methods:
                r = results[q["id"], method]
                for mode in MODES:
                    s = r["scores"][mode]
                    row = {
                        "date": today, "question_id": q["id"], "question": q["question"],
                        "method": method, "mode": mode, "n_targets": len(q["relevant"]),
                        "targets": " | ".join(q["relevant"]),
                        "first_hit_rank_at_10": first_hit(s[10]) or "",
                        "hits_at_10": hits_str(s[10]),
                        "duplicate_hits_at_10": hits_str(s[10], duplicates_only=True),
                        "changed_vs_strict": mode != "strict" and changed(r),
                        "top5_docs": " | ".join(r["ranking"][:5]),
                        "index_pages_in_top5_docs": r["index_docs_top5"],
                        "repeats_in_top10_chunks": r["repeats"]["repeats_in_top_chunks"],
                        "chunks_to_fill_10_docs": r["repeats"]["chunks_to_fill"] or "",
                        "docs_in_pool": len(r["ranking"]),
                    }
                    for k in KS:
                        row[f"P@{k}"] = fmt(s[k]["precision"])
                        row[f"R@{k}"] = fmt(s[k]["recall"])
                        row[f"MRR@{k}"] = fmt(s[k]["rr"])
                    for b, sb in r["budget"][mode].items():
                        row[f"R@{b}chunks"] = fmt(sb["recall"])
                        row[f"MRR@{b}chunks"] = fmt(sb["rr"])
                    w.writerow(row)


def changed_ks(r):
    a, b = (r["scores"][m] for m in MODES)
    return [k for k in KS
            if (a[k]["precision"], a[k]["recall"], a[k]["rr"]) != (b[k]["precision"], b[k]["recall"], b[k]["rr"])]


def changed(r):
    return bool(changed_ks(r))


def rank_cell(s):
    rank = first_hit(s[10])
    return str(rank) if rank else "–"


def write_md(path, questions, results, classes, meta, methods):
    qids = [q["id"] for q in questions]
    n = len(qids)
    L = []
    add = L.append

    title = "Retrieval evaluation" + (" (small vs large vs BM25)" if "dense-large" in methods else "")
    add(f"# {title} — {meta['date']}\n")
    src = meta["source"]
    add(f"- Questions: {n} from `{src.get('git') or src.get('file')}`"
        + (f" (blob `{src['blob'][:12]}`)" if "blob" in src else "")
        + "; parsed copy in `eval/eval_set.json`")
    add(f"- Corpus: {meta['docs']} documents, {meta['chunks']} chunks (Neon, read-only)")
    add(f"- Code: `{meta['commit']}`")
    if "commit" in src:
        add(f"- Questions source commit: `{src['commit'][:12]}` (last commit touching the file on "
            f"`{QUESTIONS_REF}`; branch tip `{src['ref_tip'][:12]}`)")
    else:
        add("- Questions source commit: none (read from a local file)")
    for m in methods:
        add(f"- {METHOD_LABELS[m][0]}: {METHOD_LABELS[m][1]}")
    add(f"- Each method returns the top {meta['pool']} chunks; these are collapsed to a document "
        "ranking (first chunk of each document counts) and metrics are computed on documents.")
    add("- STRICT: only the exact target titles are relevant. DUPLICATE-AWARE: documents with "
        f"identical text (`exact`) or difflib ratio ≥ {NEAR_THRESHOLD} to a target (`near (ratio)`) "
        "also count. Recall counts each target once, credited to the first document that matches it.\n")

    def table(key, modes, source="scores", cols=KS, col_label="@{}"):
        add("| method | mode | " + " | ".join(col_label.format(c) for c in cols) + " |")
        add("|---|---|" + "---:|" * len(cols))
        for method in methods:
            for mode in modes:
                vals = [mean(results[q, method][source][mode][c][key] for q in qids) for c in cols]
                add(f"| {method} | {mode} | " + " | ".join(fmt(v) for v in vals) + " |")
        add("")

    add("## Summary (document level)\n")
    add("Headline metrics: Recall@k and MRR@k over the document ranking.\n")
    add("**Recall@k**\n")
    table("recall", MODES)
    add("**MRR@k**\n")
    table("rr", MODES)
    add("**Precision@k (strict)**\n")
    table("precision", ("strict",))
    add("**Precision@k (duplicate-aware)**: counts identical copies as separate hits, so it rewards "
        "redundancy; not comparable to strict precision.\n")
    table("precision", ("duplicate-aware",))

    add("## Chunk budget (what generation receives)\n")
    add("Recall and MRR over the raw first k chunks, with no document-level dedup: repeated chunks of "
        "one document use up the budget, and MRR uses the position of the first relevant chunk.\n")
    add("**Recall within the first k chunks**\n")
    table("recall", MODES, source="budget", cols=CHUNK_BUDGETS, col_label="{} chunks")
    add("**MRR within the first k chunks**\n")
    table("rr", MODES, source="budget", cols=CHUNK_BUDGETS, col_label="{} chunks")

    add("## Per question: rank of first relevant document (top 10, – = none)\n")
    add("| Q | targets | " + " | ".join(f"{m} {'strict' if mode == 'strict' else 'dup-aware'}"
                                     for m in methods for mode in MODES) + " | question |")
    add("|---|---:|" + "---:|" * (len(methods) * len(MODES)) + "---|")
    for q in questions:
        cells = [rank_cell(results[q["id"], m]["scores"][mode]) for m in methods for mode in MODES]
        add(f"| {q['id']} | {len(q['relevant'])} | " + " | ".join(cells) + f" | {q['question']} |")
    add("")

    add("## Strict vs duplicate-aware: what changed\n")
    rows = []
    for q in questions:
        for m in methods:
            r = results[q["id"], m]
            if changed(r):
                s, d = r["scores"]["strict"], r["scores"]["duplicate-aware"]
                ks = ", ".join(str(k) for k in changed_ks(r))
                rows.append(f"| {q['id']} | {m} | {ks} | "
                            f"{fmt(s[10]['recall'])} → {fmt(d[10]['recall'])} | "
                            f"{fmt(s[10]['rr'])} → {fmt(d[10]['rr'])} | "
                            f"{fmt(s[10]['precision'])} → {fmt(d[10]['precision'])} | "
                            f"{hits_str(d[10], duplicates_only=True)} |")
    if rows:
        add(f"{len(rows)} question/method pairs change. The last column lists every non-target document "
            "that counted in the top 10, as `#rank doc -> target [exact|near (ratio)]`. `rescued` marks "
            "the first document credited to that target, which raised recall or MRR; the others only "
            "raised precision.\n")
        add("| Q | method | changed at k | R@10 strict → dup | MRR@10 strict → dup "
            "| P@10 strict → dup (dup counts copies) | duplicate documents counted (top 10) |")
        add("|---|---|---|---|---|---|---|")
        L.extend(rows)
    else:
        add("No question changes.")
    add("")

    add("### Equivalence sets used for targets (targets with at least one duplicate)\n")
    for t, cls in sorted(classes["duplicate-aware"].items()):
        others = [f"`{d}` ({lab})" for d, lab in sorted(cls.items()) if lab != "target"]
        if others:
            add(f"- `{t}`: " + ", ".join(others))
    add("")

    add("## Repeated documents in chunk rankings\n")
    add("| method | questions with a repeat in top 10 chunks | mean repeats in top 10 chunks | "
        "max | mean chunks needed for 10 distinct docs | max |")
    add("|---|---:|---:|---:|---:|---:|")
    for m in methods:
        reps = [results[q, m]["repeats"]["repeats_in_top_chunks"] for q in qids]
        fill = [results[q, m]["repeats"]["chunks_to_fill"] for q in qids]
        filled = [f for f in fill if f]
        add(f"| {m} | {sum(r > 0 for r in reps)}/{n} | {mean(reps):.2f} | {max(reps)} | "
            f"{mean(filled):.1f} | {max(filled) if filled else '–'} |")
        unfilled = [q for q, f in zip(qids, fill) if not f]
        if unfilled:
            add(f"\n{m}: pool did not reach 10 distinct documents for {', '.join(unfilled)}.")
    add("")

    add("## Catalog index pages (`1/`, `2/`, `3/requirements`) in the top 5\n")
    add("These three documents are identical copies of the catalog's program index page.\n")
    add("| method | questions with ≥1 in top 5 docs | slots taken in top 5 docs | "
        "questions with ≥1 in top 5 chunks | slots taken in top 5 chunks |")
    add("|---|---:|---:|---:|---:|")
    for m in methods:
        d = [results[q, m]["index_docs_top5"] for q in qids]
        c = [results[q, m]["index_chunks_top5"] for q in qids]
        add(f"| {m} | {sum(x > 0 for x in d)}/{n} | {sum(d)}/{5 * n} | {sum(x > 0 for x in c)}/{n} | {sum(c)}/{5 * n} |")
    hit = [q for q in qids if results[q, "bm25"]["index_docs_top5"]]
    if hit:
        add("\nBM25 questions affected: " + ", ".join(
            f"{q} ({results[q, 'bm25']['index_docs_top5']})" for q in hit))
    add("")

    add("## Documents that appear in the top 5 most often\n")
    add("A document in many unrelated top-5 lists is crowding out targets. "
        "Count = questions (of {}) with that document in the top 5.\n".format(n))
    targets = {t for q in questions for t in q["relevant"]}
    for m in methods:
        counts = Counter(d for q in qids for d in results[q, m]["ranking"][:5])
        add(f"**{m}**: " + ", ".join(
            f"`{d}` {c}" + (" (a target)" if d in targets else "") for d, c in counts.most_common(6)))
        add("")

    def compare(a, b, both_directions):
        name = {"dense": "dense", "dense-large": "dense-large", "bm25": "BM25"}
        A, B = name[a], name[b]
        for mode in MODES:
            a_rr = {q: results[q, a]["scores"][mode][10]["rr"] for q in qids}
            b_rr = {q: results[q, b]["scores"][mode][10]["rr"] for q in qids}
            b_wins = [q for q in qids if b_rr[q] > a_rr[q]]
            a_wins = [q for q in qids if a_rr[q] > b_rr[q]]
            both_miss = [q for q in qids if a_rr[q] == b_rr[q] == 0]
            both_miss5 = [q for q in qids if results[q, a]["scores"][mode][5]["rr"]
                          == results[q, b]["scores"][mode][5]["rr"] == 0]
            add(f"**{mode}**: {A} better on {len(a_wins)}, {B} better on {len(b_wins)}, "
                f"tied on {n - len(a_wins) - len(b_wins)}.\n")
            if both_directions:
                add(f"- {A} beats {B}: "
                    f"{', '.join(f'{q} ({fmt(a_rr[q])} vs {fmt(b_rr[q])})' for q in a_wins) or 'none'}")
            add(f"- {B} beats {A}: {', '.join(f'{q} ({fmt(b_rr[q])} vs {fmt(a_rr[q])})' for q in b_wins) or 'none'}")
            add(f"- Both miss in top 10: {', '.join(both_miss) or 'none'}")
            add(f"- Both miss in top 5: {', '.join(both_miss5) or 'none'}\n")

    add("## Method comparison (MRR@10)\n")
    if "dense-large" not in methods:
        compare("dense", "bm25", both_directions=False)
    else:
        for a, b in (("dense-large", "dense"), ("dense", "bm25"), ("dense-large", "bm25")):
            add(f"### {a} vs {b}\n")
            compare(a, b, both_directions=True)
        small_vs_large(questions, results, add)

    path.write_text("\n".join(L) + "\n", encoding="utf-8")


ABBREV = [("bachelor_of_science_in_", "bs:"), ("bachelor_of_arts_in_", "ba:"), ("certificate_in_", "cert:"),
          ("bs_in_", "bs2:"), ("ba_in_", "ba2:")]


def abbrev(title):
    for long, short in ABBREV:
        if title.startswith(long):
            title = short + title[len(long):]
            break
    return title.removesuffix("/requirements").replace("/example", "/ex")


def small_vs_large(questions, results, add):
    """Questions where text-embedding-3-small (dense) and -large (dense-large) differ most."""

    def m(q, method, mode="duplicate-aware"):
        r = results[q, method]
        return {"rr": r["scores"][mode][10]["rr"], "first": first_hit(r["scores"][mode][10]),
                "r5c": r["budget"][mode][5]["recall"], "r5": r["scores"][mode][5]["recall"]}

    rows = []
    for q in questions:
        qid = q["id"]
        s, g = m(qid, "dense"), m(qid, "dense-large")
        ss, gs = m(qid, "dense", "strict"), m(qid, "dense-large", "strict")
        key = (abs(g["rr"] - s["rr"]), abs(g["r5c"] - s["r5c"]), abs(gs["rr"] - ss["rr"]),
               abs(gs["r5c"] - ss["r5c"]), abs(g["r5"] - s["r5"]))
        if any(key):
            rows.append((key, q, s, g, ss, gs))
    rows.sort(key=lambda r: r[0], reverse=True)

    def rk(x):
        return str(x["first"]) if x["first"] else "–"

    add("## Small vs large: questions that differ most\n")
    better = sum(m(q["id"], "dense-large")["rr"] > m(q["id"], "dense")["rr"] for q in questions)
    worse = sum(m(q["id"], "dense-large")["rr"] < m(q["id"], "dense")["rr"] for q in questions)
    add(f"Duplicate-aware MRR@10: large better on {better}, small better on {worse}, "
        f"tied on {len(questions) - better - worse}. The table lists the {len(rows)} questions where any of "
        "MRR@10, document Recall@5 or recall within the first 5 chunks differs between the models "
        f"(the other {len(questions) - len(rows)} score identically). Rows are sorted by the size of the "
        "difference: duplicate-aware MRR@10, then duplicate-aware recall within 5 chunks, then strict "
        "MRR@10. Titles are abbreviated: " + ", ".join(f"`{b}` = `{a}`" for a, b in ABBREV)
        + ", `/requirements` dropped, so `1`, `2`, `3` are the catalog index pages.\n")
    add("| Q | first hit small (strict / dup) | first hit large (strict / dup) | MRR@10 dup small → large "
        "| R in 5 chunks small → large (strict; dup) | top 3 docs small | top 3 docs large | question |")
    add("|---|---|---|---|---|---|---|---|")
    for _, q, s, g, ss, gs in rows:
        top = {meth: ", ".join(abbrev(d) for d in results[q["id"], meth]["ranking"][:3])
               for meth in ("dense", "dense-large")}
        add(f"| {q['id']} | {rk(ss)} / {rk(s)} | {rk(gs)} / {rk(g)} | {fmt(s['rr'])} → {fmt(g['rr'])} | "
            f"{fmt(ss['r5c'])} → {fmt(gs['r5c'])}; {fmt(s['r5c'])} → {fmt(g['r5c'])} | "
            f"{top['dense']} | {top['dense-large']} | {q['question']} |")
    if not rows:
        add("| – | | | | | | | no differences |")
    add("")


def main():
    parser = argparse.ArgumentParser(description="Evaluate dense and BM25 retrieval.")
    parser.add_argument("--questions-file", help=f"local eval_questions.md (default: git show {QUESTIONS_REF})")
    parser.add_argument("--pool", type=int, default=50, help="chunks retrieved per method (default 50)")
    parser.add_argument("--refresh-bm25", action="store_true", help="reload chunks from Neon")
    parser.add_argument("--large", action="store_true",
                        help=f"add {LARGE_MODEL} (local vectors) and write the small-vs-large report")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    md, source = load_questions_md(args.questions_file)
    questions = parse_questions(md)
    EVAL_DIR.mkdir(exist_ok=True)
    eval_set = EVAL_DIR / "eval_set.json"
    eval_set.write_text(json.dumps({"source": source, "count": len(questions), "questions": questions},
                                   indent=2) + "\n", encoding="utf-8")
    print(f"parsed {len(questions)} questions -> {eval_set.relative_to(BACKEND)}")

    index = get_index(refresh=args.refresh_bm25)
    texts = defaultdict(list)
    for c in index.chunks:  # ordered by title, chunk_index
        texts[c["doc_title"]].append(c["text"])
    doc_texts = {t: "".join(parts) for t, parts in texts.items()}

    targets = list(dict.fromkeys(t for q in questions for t in q["relevant"]))
    missing = [t for t in targets if t not in doc_texts]
    if missing:
        sys.exit(f"targets not found in documents.title: {missing}")
    classes = {"strict": strict_classes(targets), "duplicate-aware": duplicate_classes(doc_texts, targets)}

    methods = LARGE_METHODS if args.large else METHODS
    embedders = {EMBED_MODEL: CachedEmbedder(EMBED_MODEL)}
    large_index = None
    if args.large:
        large_index = load_index(index.chunks, model=LARGE_MODEL)
        embedders[LARGE_MODEL] = CachedEmbedder(LARGE_MODEL)

    conn = connect()
    retrievers = {
        "dense": lambda text: retrieve(text, args.pool, conn=conn, embed=embedders[EMBED_MODEL]),
        "dense-large": lambda text: local_retrieve(text, args.pool, index=large_index,
                                                   embed=embedders.get(LARGE_MODEL)),
        "bm25": lambda text: bm25_search(text, args.pool, index=index),
    }
    try:
        results = evaluate(questions, {m: retrievers[m] for m in methods}, classes)
    finally:
        conn.close()
        for e in embedders.values():
            e.save()
    for model, e in embedders.items():
        print(f"query embeddings ({model}): {e.misses} new OpenAI calls, {len(questions) - e.misses} cached")

    today = date.today().isoformat()
    dirty = " (with uncommitted changes)" if git("status", "--porcelain", "--", "backend").strip() else ""
    meta = {"date": today, "source": source, "pool": args.pool, "docs": len(doc_texts),
            "chunks": len(index.chunks), "commit": git("rev-parse", "--short", "HEAD").strip() + dirty}
    out = EVAL_DIR / "results"
    out.mkdir(exist_ok=True)
    stem = f"retrieval_eval_{today}" + ("_small-vs-large" if args.large else "")
    md_path, csv_path = out / f"{stem}.md", out / f"{stem}.csv"
    write_csv(csv_path, questions, results, today, methods)
    write_md(md_path, questions, results, classes, meta, methods)
    print(f"wrote {md_path.relative_to(BACKEND)} and {csv_path.relative_to(BACKEND)}")


if __name__ == "__main__":
    main()
