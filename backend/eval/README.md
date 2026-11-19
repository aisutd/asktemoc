# Retrieval evaluation: Weeks 4 to 6

| 2026-11-18 | | README; improved `compare_runs.py` table |

Owner: Sal (role B, retrieval and its metrics). Branch: `feat/week5-retrieval-router`.

This file records what was done on this branch, in order, with the results, so
anyone can follow it and reproduce every number. Newest results are at the
bottom of each section. If you change the corpus, the eval set or the harness,
add a dated entry to the log at the end.

## Contents

1. [Where this branch comes from](#1-where-this-branch-comes-from)
2. [Setup on Windows (PowerShell)](#2-setup-on-windows-powershell)
3. [The merge with Sahil's dedupe, and two bugs it exposed](#3-the-merge-with-sahils-dedupe-and-two-bugs-it-exposed)
4. [Baseline after the dedupe](#4-baseline-after-the-dedupe)
5. [Neon changed between two runs](#5-neon-changed-between-two-runs)
6. [Metrics: what each one measures](#6-metrics-what-each-one-measures)
7. [Context precision](#7-context-precision)
8. [Where retrieval loses context precision](#8-where-retrieval-loses-context-precision)
9. [Decisions so far](#9-decisions-so-far)
10. [Open issues for the team](#10-open-issues-for-the-team)
11. [Next steps](#11-next-steps)
12. [Log](#12-log)

## 1. Where this branch comes from

| Branch | Owner | What it holds |
|---|---|---|
| `feat/retrieval-eval` | Sal | Week 3: dense and BM25 retrieval over Neon, the eval harness (`scripts/eval_retrieval.py`), small vs large embedding comparison |
| `feat/query-router` | Sal | Week 3 review (`eval/results/week3_review.md`) and query-router batch 1 (`router/data/labels_batch1.csv`, 90 rows, 18 frozen test rows). This completed Week 4. |
| `fix/corpus-dedupe-and-sources` | Sahil | `corpus_prep.py`, `embed_pipeline.py`, 55 eval questions (`eval_questions.md`), after-dedupe eval (`analysis/retrieval_eval_after_dedupe.md`) |
| **`feat/week5-retrieval-router`** | Sal | This branch: `feat/query-router` + Sahil's fix, and the Week 5 work |

Sahil's fix split each school's combined certificates page into one document
per certificate and merged the three identical catalog index pages into one
overview page. On the original 30 questions, dense strict MRR@10 went from
0.769 (Week 3) to 0.867, and Recall@5 from 0.761 to 0.928. It fixed Q6, Q8 and
Q19 from the Week 3 worst-five list. It did not fix Q10 or chunk repetition.

## 2. Setup on Windows (PowerShell)

Work outside OneDrive (git and OneDrive fight over line endings and lock files).

```powershell
cd C:\dev
git clone https://github.com/aisutd/asktemoc.git
cd asktemoc
git checkout feat/week5-retrieval-router
cd backend
py -3.11 -m venv .venv
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned   # once, so Activate.ps1 can run
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt tiktoken scikit-learn joblib rich
```

`backend\.env` (gitignored, never commit it) needs two values:

```
OPENAI_API_KEY=sk-...
NEON_DATABASE_URL=postgresql://...neon.tech/...
```

`NEON_DATABASE_URL` is read only by the eval code (`retrieval/db.py`), which
opens a read-only session. The app itself uses `DATABASE_URL`. The team's
database is Postgres hosted on Neon, with the pgvector extension doing the
vector search.

Checks:

```powershell
pytest -q
python -c "import corpus_prep as c; d,_,f=c.prepare_documents(); print(len(d), f)"   # expect: 203 []
```

203 local documents matches Neon's 202: `embed_pipeline.py` skips one page with
fewer than 30 words.

PowerShell tips that cost time once:

- Multi-line Python: wrap it in `@'` ... `'@ | python -`. The closing `'@`
  must be first on its own line. Anything typed before it becomes part of the
  script.
- Writing files from PowerShell: use `Set-Content -Encoding ascii` (or utf8).
  The default in Windows PowerShell is UTF-16, which git and Python reject.
- `Get-Content` shows UTF-8 files garbled (`â€”`). Add `-Encoding utf8`; the
  file itself is fine.

## 3. The merge with Sahil's dedupe, and two bugs it exposed

```powershell
git checkout -b feat/week5-retrieval-router    # from feat/query-router
git merge origin/fix/corpus-dedupe-and-sources
```

Three conflicts, all resolved to this branch's side:

| File | Resolution | Why |
|---|---|---|
| `backend/requirements.txt` | ours | Sahil only added playwright and crawl4ai, already in `requirements-scrape.txt` |
| `backend/.env.example` | ours, plus `NEON_DATABASE_URL=` | ours is the documented version; the eval code needs that variable |
| `backend/.gitignore` | deleted | the root `.gitignore` covers `.env`, `*.log` and `.cache/` |

**Catalog location.** This branch moved the catalog to `data/catalog/` on
2026-10-05 (`6edd28b`). Sahil's branch still used `backend/test_output/`. Git
carried the move through for his existing files. His 7 new education folders
were moved by hand into `data/catalog/`, and `CORPUS_DIR` in `corpus_prep.py`
now points at `HERE.parent / "data" / "catalog"`. Without that edit,
`prepare_documents()` silently builds a corpus of only the 3 web pages. Merge
commit: `faaa668`.

**Bug 1, Windows paths (`d73de2f`).** `corpus_prep.py` built document keys with
`str(path)`, which uses backslashes on Windows, then split them on `/`. Fixed
with `.as_posix()`. This affects anyone running `embed_pipeline.py` on Windows.

**Bug 2, `.md` targets (`00c5747`).** Sahil's questions Q52 to Q55 target the
Crawl4AI web pages as `web/utd_tuition_rates.md`, but documents are titled
without the extension. `parse_questions` in `retrieval/evaluate.py` stripped
only `.txt`; it now strips `.txt` and `.md`.

## 4. Baseline after the dedupe

```powershell
python scripts/eval_retrieval.py --questions-file eval_questions.md --refresh-bm25
```

55 questions: Q1 to Q30 (the original set), Q31 to Q51 (new catalog questions,
many about the education programs), Q52 to Q55 (web pages). Dense is
`text-embedding-3-small` over Neon pgvector, 512-token chunks with 64 overlap.

Run 1 (2026-11-18 18:41 CT, 202 docs, 892 chunks), dense strict, by group:

| Group | MRR@10 | Recall@5 | nDCG@10 |
|---|---:|---:|---:|
| Q1-30 | 0.867 | 0.928 | 0.894 |
| Q31-51 | 0.767 | 0.833 | 0.801 |
| Q52-55 web | 0.750 | 0.750 | 0.750 |
| all 55 | 0.820 | 0.879 | 0.848 |

Q1 to Q30 reproduce Sahil's after-dedupe report (Recall@5 0.928 exactly;
MRR@10 0.867 vs 0.883 is one question moving from rank 1 to rank 2, likely
cached vs fresh query embeddings). BM25 beats dense only on the web pages
(4/4 vs 3/4).

Questions where dense's first hit is worse than rank 3: Q10, Q45, Q46, Q48,
Q49, Q50, Q54. Three failure types:

- sibling programs with near-identical text (Q10, Q46, Q48): a ranking problem
- small sections inside long documents (Q45 Fast Track, Q50 sample degree plan): a miss
- exact terms on long web pages (Q54): BM25 territory

Files: `eval/results/retrieval_eval_2026-11-18.{md,csv}`.

## 5. Neon changed between two runs

A second run at 19:47 CT gave different dense numbers with identical cached
query embeddings and identical BM25. Querying Neon showed why: at 18:48 to
18:51 CT (00:48 to 00:51 UTC), `embed_pipeline.py` re-ingested `web/utd_home`,
the 14 education documents and several other program pages. Sahil confirmed
he hashed and removed duplicate chunks: a chunk whose text appears in two
documents is now stored once. Chunks went from 892 to 874; documents stayed at
202.

Chunks per document that changed (before, after): most lost one shared
boilerplate chunk; `bs_in_finance_and_economics_double_major` went from 5 to 1
because four chunks are word-for-word copies of
`bs_in_economics_and_finance_double_major`; `bachelor_of_science_in_healthcare_management`
went from 5 to 6.

Run 2 (19:47 CT, 202 docs, 874 chunks) against run 1, dense strict:

| Metric | 892 chunks | 874 chunks | Change |
|---|---:|---:|---:|
| Recall@3 | 0.836 | 0.891 | +0.055 (+3.0 q) |
| Recall@5 | 0.879 | 0.906 | +0.027 (+1.5 q) |
| Recall@10 | 0.945 | 0.958 | +0.012 (+0.7 q) |
| MRR@10 | 0.820 | 0.827 | +0.007 (+0.4 q) |
| nDCG@10 | 0.848 | 0.853 | +0.006 (+0.3 q) |
| Recall, 3 chunks | 0.827 | 0.882 | +0.055 (+3.0 q) |
| Recall, 5 chunks | 0.879 | 0.906 | +0.027 (+1.5 q) |
| Recall, 8 chunks | 0.915 | 0.942 | +0.027 (+1.5 q) |

"q" is the change in questions (change x 55). BM25 was unchanged because it
reads the chunk cache on disk, not live Neon.

**Run 2 is the baseline from here on.** Gains on Q46, Q48 and Q50 come from
Sahil's re-ingestion and must not be credited to any Week 5 experiment.

Lessons: Week 5 tuning runs on a frozen local corpus (`scripts/sweep_chunking.py`),
not live Neon; and whoever re-ingests posts in the team chat first.

Files: `eval/results/retrieval_eval_2026-11-18_run2.{md,csv}`. Compare any two
runs with:

```powershell
python scripts/compare_runs.py OLD.csv NEW.csv --labels "892 chunks" "874 chunks"
python scripts/compare_runs.py OLD.csv NEW.csv --md    # markdown for notes
```

## 6. Metrics: what each one measures

All relevance is binary (a document is a target or not), strict mode unless
stated. Strict and duplicate-aware now agree, so strict is reported.

- **MRR@k**: 1 / rank of the first correct document, averaged. Rank 1 = 1.0,
  rank 2 = 0.5, miss = 0. Only the first hit counts.
- **Recall@k**: share of a question's targets in the top k. Recall@10 says
  whether the answer is reachable; Recall@5 is closer to what generation gets.
- **Precision@k**: share of the top k documents that are targets. Most
  questions have one target, so the best possible P@10 on this set is 0.127.
  Dense scores 0.122, 96% of that. Document precision is not a problem here.
- **nDCG@k**: every target in the top k earns 1 / log2(rank + 1), divided by
  the best possible. Rewards finding all targets and ranking them high. The
  best single number for comparing configs.
- **Recall within k chunks**: recall over the raw chunk list sent to
  generation, repeats included.
- **Context precision (CP@k chunks)**: share of the k chunks sent to
  generation that come from a target document. See section 7.

Headline metrics for Week 5 decisions: nDCG@10, recall within 3 and 5 chunks,
context precision at 3 and 5 chunks. Decision rule: a change counts only if
it moves a headline metric by at least 2 questions (about 0.035 on 55
questions) without dropping any question currently at rank 1.

## 7. Context precision

Added to the harness (`retrieval/evaluate.py`, `scripts/eval_retrieval.py`).
The existing `score()` already returned it as `precision` on the chunk list;
it is now written to the CSV (`CP@{3,5,8}chunks`) and the report. A
per-document cap (`cap_per_doc`, `DOC_CAP = 2`) was added as an option and
measured.

Run 2, dense strict:

| Chunks sent | Recall, no cap | Recall, cap 2 | CP, no cap | CP, cap 2 | Best possible CP |
|---|---:|---:|---:|---:|---:|
| 3 | 0.882 | 0.891 | 0.558 | 0.509 | 0.885 |
| 5 | 0.906 | 0.906 | 0.447 | 0.338 | 0.796 |
| 8 | 0.942 | 0.942 | 0.352 | 0.223 | 0.664 |

"Best possible" fills every slot with target chunks, limited by how many
chunks the targets have. It is slightly optimistic, since not every chunk of
a target contains the answer.

- Dense reaches about 60% of the best possible CP at every budget. At 3
  chunks, generation gets about 1.7 relevant chunks out of 3 where about 2.65
  are possible. This is a real retrieval gap.
- The per-document cap gains half a question of recall at 3 chunks and none at
  5 or 8, and lowers CP every time. **Rejected.** (An earlier note compared
  capped run 2 against uncapped run 1, which mixed corpora; that comparison
  was wrong.)
- CP at "k chunks" depends on chunk size. The chunk-size sweep must compare
  configs at equal token budgets, not equal chunk counts.

## 8. Where retrieval loses context precision

The 12 questions with the largest gap between actual and best possible CP at 3
chunks (run 2) show three patterns:

| Pattern | Questions | Example |
|---|---|---|
| Sibling programs take the slots | Q10, Q49, Q2, Q5, Q17, Q31, Q16, Q26 | healthcare studies for healthcare management; education 7-12 / 4-8 for EC-6; computational and geospatial science for CS |
| Hub document | Q5, Q30, Q45 | the catalog overview ranks first for specific programs, yet nowhere for Q45 (Fast Track), where it is the target |
| `/example` pages | Q12, Q26 | `accounting/example` and `marketing/example` take a slot and may actually be relevant |

In Q16, Q17, Q26 and Q31 the correct document ranks first but contributes only
1 of the 3 chunks: its other chunks score below a sibling's chunk that matches
the question's wording. A reranker fixes wrong-first cases (Q10, Q49, Q2) but
not this one, because it also scores chunk by chunk.

## 9. Decisions so far

| Decision | Status | Evidence |
|---|---|---|
| Keep `text-embedding-3-small` | kept (revisit large once in the sweep) | Week 3: large no better overall, worse repetition |
| Report strict mode only | adopted | strict and duplicate-aware agree after the dedupe |
| Per-document cap of 2 | rejected | section 7 |
| Precision@10 as a target | rejected | at 96% of its ceiling; context precision is the metric that matters |
| Reranking | Week 6, justified | section 8 |
| Hybrid search | Week 6, weak case | BM25 wins only on the 4 web questions and loses badly on catalog |

## 10. Open issues for the team

- **Housing is not in the corpus.** `data/housing/` (36 files) exists on this
  branch, but `corpus_prep.py` reads only `data/catalog/` and the 3 Crawl4AI
  pages. The router can send queries to housing, but retrieval has nothing
  there. Data role (Sahil).
- **Re-ingestion coordination.** Post in the team chat before running
  `embed_pipeline.py` against Neon (section 5).
- **Vector dimension mismatch.** On main, `app/db/models.py` declares
  `Vector(3072)` ("text-embedding-3-large dimension"), while Neon and
  `embed_pipeline.py` use 1536 (small). Backend (Davis).
- **Citations after chunk dedup.** Shared chunks are attached to one
  document, so a Finance and Economics question may cite the Economics and
  Finance page. Same content, different source label. Generation (Nithin).
- **`CORPUS_DIR` moved.** `embed_pipeline.py` imports `corpus_prep`, so
  ingestion from this branch reads `data/catalog/` (Sahil).

## 11. Next steps

Week 5:

1. **Chunk-size sweep** (`scripts/sweep_chunking.py`): build the corpus locally
   with `corpus_prep.py`, chunk at 256/32, 384/48, 512/64, 768/96, 1024/128,
   embed with small (plus 512/64 with large), search in numpy, score with
   `retrieval/evaluate.py`. Sanity check: local 512/64 small must match run 2.
   Compare at equal token budgets. Watch Q45 and Q50.
2. **Neighbor expansion** on the best config: fill remaining slots with the
   top document's other chunks. Check the two-target questions Q14, Q18, Q22.
3. **Title-match boost**: small score bonus when the document title contains
   the program named in the query. Targets the sibling-program pattern.
4. **Label review**: decide by hand whether `/example` pages answer Q12, Q26
   and similar; add them as extra targets in a separate questions file.
5. **Router**: label batch 2 (`router/data/labels_batch2.csv`, 100 to 150
   rows, 20% frozen as test), then train logistic regression on
   `text-embedding-3-small` embeddings, plus a TF-IDF baseline.

Week 6:

1. Router: classifier vs zero-shot `gpt-4o-mini` on the frozen test rows
   (accuracy, macro-F1, confusion matrix, p50/p95 latency, cost).
2. Reranker (cross-encoder) over the top 20, aimed at the sibling cases left
   after Week 5.
3. Hybrid (reciprocal rank fusion) only if it helps web questions without
   hurting catalog.
4. Lock the final config in `eval/results/week6_final_config.md` and
   re-embed it into Neon.

## 12. Log

| Date | Commit | What |
|---|---|---|
| 2026-10-05 | `6edd28b` | Catalog moved to `data/catalog/` |
| 2026-10-21 | `1a89404`, `0330a52` | Week 3 harness; small vs large |
| 2026-10-27 | `b161a8c`, `90eae2f` | Week 3 review; router batch 1 (Week 4) |
| 2026-11-11 | `c9644f0` (Sahil) | Corpus dedupe; 55 eval questions |
| 2026-11-18 | `faaa668` | Merge Sahil's fix; education pages into `data/catalog/` |
| 2026-11-18 | `d73de2f` | Windows path fix in `corpus_prep.py` |
| 2026-11-18 | `00c5747` | `.md` target fix; baseline run 1 (892 chunks) |
| 2026-11-18 | | Context precision, per-doc cap, `compare_runs.py`, run 2 (874 chunks), this README |

## Appendix: ad-hoc checks

These were run as one-off scripts. Turn them into files under `scripts/` if
they are needed again.

Best possible context precision (needs `NEON_DATABASE_URL`):

```python
import json, sys
sys.path.insert(0, ".")
from retrieval.db import connect
qs = json.load(open("eval/eval_set.json", encoding="utf-8"))["questions"]
with connect() as conn, conn.cursor() as cur:
    cur.execute("""SELECT d.title, count(c.id) FROM documents d JOIN chunks c ON c.document_id = d.id
                   WHERE NOT c.is_deleted AND NOT d.is_deleted GROUP BY d.title""")
    n_chunks = dict(cur.fetchall())
for k in (3, 5, 8):
    ceil = [min(sum(n_chunks.get(t, 0) for t in q["relevant"]), k) / k for q in qs]
    print(f"best possible context precision at {k} chunks: {sum(ceil) / len(ceil):.3f}")
```

When Neon last changed:

```python
import sys; sys.path.insert(0, ".")
from retrieval.db import connect
with connect() as conn, conn.cursor() as cur:
    for t in ("documents", "chunks", "embeddings"):
        cur.execute(f"SELECT count(*), max(created_at), max(updated_at) FROM {t}")
        print(t, cur.fetchone())
```
