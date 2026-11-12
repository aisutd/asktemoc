# Retrieval eval after corpus dedupe (2026-11-11)

Same 30 questions as the Week 3 review (`eval_questions.md` at `d8e03ee`), same harness (`feat/retrieval-eval`, read-only against Neon). Only the corpus changed: 192 documents / 885 chunks before, 202 documents / 892 chunks after.

Dense (`text-embedding-3-small`), document level:

| metric | before strict | before dup-aware | after (strict = dup-aware) |
|---|---:|---:|---:|
| Recall@1 | 0.578 | 0.667 | 0.689 |
| Recall@3 | 0.706 | 0.794 | 0.900 |
| Recall@5 | 0.761 | 0.889 | 0.928 |
| Recall@10 | 0.967 | 0.967 | 1.000 |
| MRR@10 | 0.769 | 0.838 | 0.883 |

First relevant rank for the review's worst questions (dense, strict): Q6 6 -> 1, Q8 8 -> 1, Q19 6 -> 2, Q30 5 -> 3, Q5 4 -> 2, Q10 6 -> 6.

Not fixed by the dedupe: Q10 (sibling programs outrank the target), repeated chunks from one document (27/30 questions), and BM25 favouring a few hub documents, including the single catalog overview page (top 5 for 8 questions).

Full harness output follows.

---

# Retrieval evaluation — 2026-11-11

- Questions: 30 from `/private/tmp/claude-501/-Users-sahilpatil-AskTemoc/f30d68e9-29fd-4d03-adca-7784f4641190/scratchpad/eval_questions_30.md`; parsed copy in `eval/eval_set.json`
- Corpus: 202 documents, 892 chunks (Neon, read-only)
- Code: `b56f7c4 (with uncommitted changes)`
- Questions source commit: none (read from a local file)
- Dense: `text-embedding-3-small` query embedding, pgvector cosine distance, exact scan
- BM25: rank_bm25 BM25Okapi, lowercase + `[a-z0-9]+` tokens, no stemming or stopwords
- Each method returns the top 50 chunks; these are collapsed to a document ranking (first chunk of each document counts) and metrics are computed on documents.
- STRICT: only the exact target titles are relevant. DUPLICATE-AWARE: documents with identical text (`exact`) or difflib ratio ≥ 0.99 to a target (`near (ratio)`) also count. Recall counts each target once, credited to the first document that matches it.

## Summary (document level)

Headline metrics: Recall@k and MRR@k over the document ranking.

**Recall@k**

| method | mode | @1 | @3 | @5 | @10 |
|---|---|---:|---:|---:|---:|
| dense | strict | 0.689 | 0.900 | 0.928 | 1.000 |
| dense | duplicate-aware | 0.689 | 0.900 | 0.928 | 1.000 |
| bm25 | strict | 0.472 | 0.711 | 0.811 | 0.911 |
| bm25 | duplicate-aware | 0.472 | 0.711 | 0.811 | 0.911 |

**MRR@k**

| method | mode | @1 | @3 | @5 | @10 |
|---|---|---:|---:|---:|---:|
| dense | strict | 0.800 | 0.878 | 0.878 | 0.883 |
| dense | duplicate-aware | 0.800 | 0.878 | 0.878 | 0.883 |
| bm25 | strict | 0.567 | 0.644 | 0.658 | 0.673 |
| bm25 | duplicate-aware | 0.567 | 0.644 | 0.658 | 0.673 |

**Precision@k (strict)**

| method | mode | @1 | @3 | @5 | @10 |
|---|---|---:|---:|---:|---:|
| dense | strict | 0.800 | 0.378 | 0.240 | 0.133 |
| bm25 | strict | 0.567 | 0.289 | 0.200 | 0.110 |

**Precision@k (duplicate-aware)**: counts identical copies as separate hits, so it rewards redundancy; not comparable to strict precision.

| method | mode | @1 | @3 | @5 | @10 |
|---|---|---:|---:|---:|---:|
| dense | duplicate-aware | 0.800 | 0.389 | 0.253 | 0.140 |
| bm25 | duplicate-aware | 0.567 | 0.289 | 0.207 | 0.117 |

## Chunk budget (what generation receives)

Recall and MRR over the raw first k chunks, with no document-level dedup: repeated chunks of one document use up the budget, and MRR uses the position of the first relevant chunk.

**Recall within the first k chunks**

| method | mode | 3 chunks | 5 chunks | 8 chunks |
|---|---|---:|---:|---:|
| dense | strict | 0.883 | 0.928 | 0.961 |
| dense | duplicate-aware | 0.883 | 0.928 | 0.961 |
| bm25 | strict | 0.711 | 0.794 | 0.878 |
| bm25 | duplicate-aware | 0.711 | 0.794 | 0.878 |

**MRR within the first k chunks**

| method | mode | 3 chunks | 5 chunks | 8 chunks |
|---|---|---:|---:|---:|
| dense | strict | 0.872 | 0.872 | 0.876 |
| dense | duplicate-aware | 0.872 | 0.872 | 0.876 |
| bm25 | strict | 0.644 | 0.658 | 0.668 |
| bm25 | duplicate-aware | 0.644 | 0.658 | 0.668 |

## Per question: rank of first relevant document (top 10, – = none)

| Q | targets | dense strict | dense dup-aware | bm25 strict | bm25 dup-aware | question |
|---|---:|---:|---:|---:|---:|---|
| Q1 | 1 | 1 | 1 | 5 | 5 | What are the core requirements for the BS in Computer Science at UTD? |
| Q2 | 1 | 1 | 1 | 3 | 3 | How many total credit hours are required to complete the BS in Computer Science? |
| Q3 | 1 | 2 | 2 | 1 | 1 | What math courses are required for the BS in Electrical Engineering? |
| Q4 | 1 | 1 | 1 | 1 | 1 | What is the Certificate in Quantum Information and what courses does it require? |
| Q5 | 1 | 2 | 2 | 6 | 6 | What are the requirements for the BS in Biology and Healthcare Management double major? |
| Q6 | 1 | 1 | 1 | 1 | 1 | What courses are listed under the Certificate in Intercultural Communication? |
| Q7 | 1 | 1 | 1 | 1 | 1 | What does the Certificate in Military Science Leadership require, and who is eligible? |
| Q8 | 1 | 1 | 1 | 1 | 1 | What courses make up the Certificate in Applied Experience Design and Research? |
| Q9 | 1 | 1 | 1 | 2 | 2 | What are the upper-division elective options for the BS in Computer Science? |
| Q10 | 1 | 6 | 6 | 6 | 6 | What are the requirements for the standalone BS in Healthcare Management at UTD? |
| Q11 | 1 | 1 | 1 | 1 | 1 | What science or lab courses are required in the BS in Electrical Engineering? |
| Q12 | 1 | 2 | 2 | 3 | 3 | What courses are required for the BS in Accounting at UTD? |
| Q13 | 3 | 1 | 1 | 1 | 1 | What certificates at UTD focus on communication, design, or user experience? |
| Q14 | 2 | 1 | 1 | 1 | 1 | What is the difference in core requirements between a BS in Computer Science and a BS in Electrical Engineering at UTD? |
| Q15 | 1 | 1 | 1 | 1 | 1 | What are the course requirements for the BA in Animation and Games at UTD? |
| Q16 | 1 | 1 | 1 | 2 | 2 | What does the BS in Business Analytics and Artificial Intelligence require? |
| Q17 | 1 | 1 | 1 | 1 | 1 | What courses are required for the BS in Cybersecurity and Risk Management? |
| Q18 | 2 | 1 | 1 | 1 | 1 | How do the core requirements for the BS in Software Engineering compare to those for the BS in Computer Science? |
| Q19 | 1 | 2 | 2 | 3 | 3 | What are the requirements for the Certificate in Cyber Defense? |
| Q20 | 1 | 1 | 1 | 1 | 1 | What courses does the BS in Biomedical Engineering require? |
| Q21 | 1 | 1 | 1 | 3 | 3 | What is required for the BS in Neuroscience at UTD? |
| Q22 | 2 | 1 | 1 | 1 | 1 | How do the requirements differ between the BA in Economics and the BS in Finance and Economics double major? |
| Q23 | 1 | 1 | 1 | 5 | 5 | What courses make up the Certificate in Data Science? |
| Q24 | 1 | 1 | 1 | 1 | 1 | What are the requirements for the BS in Mechanical Engineering? |
| Q25 | 3 | 1 | 1 | 1 | 1 | What programs at UTD focus on sustainability or environmental topics? |
| Q26 | 1 | 1 | 1 | 8 | 8 | What is the BS in Marketing and what courses does it require? |
| Q27 | 1 | 1 | 1 | 1 | 1 | What are the requirements for the Certificate in Innovation and Entrepreneurship? |
| Q28 | 2 | 1 | 1 | – | – | Does UTD have a pre-law program or certificate, and what does it cover? |
| Q29 | 1 | 1 | 1 | 1 | 1 | What are the requirements for the BA in Visual and Performing Arts — Film concentration? |
| Q30 | 3 | 3 | 3 | – | – | What programs at UTD combine business with another discipline as a prescribed double major? |

## Strict vs duplicate-aware: what changed

4 question/method pairs change. The last column lists every non-target document that counted in the top 10, as `#rank doc -> target [exact|near (ratio)]`. `rescued` marks the first document credited to that target, which raised recall or MRR; the others only raised precision.

| Q | method | changed at k | R@10 strict → dup | MRR@10 strict → dup | P@10 strict → dup (dup counts copies) | duplicate documents counted (top 10) |
|---|---|---|---|---|---|---|
| Q5 | dense | 5, 10 | 1.000 → 1.000 | 0.500 → 0.500 | 0.100 → 0.200 | #5 bs_in_healthcare_management_and_biology_double_major/requirements -> bs_in_biology_and_healthcare_management_double_major/requirements [near (0.992)] |
| Q5 | bm25 | 10 | 1.000 → 1.000 | 0.167 → 0.167 | 0.100 → 0.200 | #7 bs_in_healthcare_management_and_biology_double_major/requirements -> bs_in_biology_and_healthcare_management_double_major/requirements [near (0.992)] |
| Q22 | dense | 3, 5, 10 | 1.000 → 1.000 | 1.000 → 1.000 | 0.200 → 0.300 | #2 bs_in_finance_and_economics_double_major/requirements -> bs_in_economics_and_finance_double_major/requirements [near (0.994)] |
| Q22 | bm25 | 5, 10 | 1.000 → 1.000 | 1.000 → 1.000 | 0.200 → 0.300 | #5 bs_in_finance_and_economics_double_major/requirements -> bs_in_economics_and_finance_double_major/requirements [near (0.994)] |

### Equivalence sets used for targets (targets with at least one duplicate)

- `bs_in_biology_and_healthcare_management_double_major/requirements`: `bs_in_healthcare_management_and_biology_double_major/requirements` (near (0.992))
- `bs_in_economics_and_finance_double_major/requirements`: `bs_in_finance_and_economics_double_major/requirements` (near (0.994))

## Repeated documents in chunk rankings

| method | questions with a repeat in top 10 chunks | mean repeats in top 10 chunks | max | mean chunks needed for 10 distinct docs | max |
|---|---:|---:|---:|---:|---:|
| dense | 27/30 | 2.97 | 6 | 14.9 | 24 |
| bm25 | 26/30 | 1.90 | 6 | 12.7 | 19 |

## Catalog index pages (`1/`, `2/`, `3/requirements`) in the top 5

These three documents are identical copies of the catalog's program index page.

| method | questions with ≥1 in top 5 docs | slots taken in top 5 docs | questions with ≥1 in top 5 chunks | slots taken in top 5 chunks |
|---|---:|---:|---:|---:|
| dense | 0/30 | 0/150 | 0/30 | 0/150 |
| bm25 | 0/30 | 0/150 | 0/30 | 0/150 |

## Documents that appear in the top 5 most often

A document in many unrelated top-5 lists is crowding out targets. Count = questions (of 30) with that document in the top 5.

**dense**: `bachelor_of_science_in_software_engineering/requirements` 8 (a target), `bachelor_of_science_in_computer_science/requirements` 6 (a target), `bachelor_of_science_in_computer_engineering/requirements` 6, `bachelor_of_science_in_systems_engineering/requirements` 5, `bachelor_of_science_in_cybersecurity_and_risk_management/requirements` 5 (a target), `bachelor_of_science_in_cognitive_science/requirements` 5

**bm25**: `bachelor_of_arts_in_economics/requirements` 23 (a target), `bachelor_of_arts_in_sociology/requirements` 17, `bachelor_of_arts_in_political_science/requirements` 8, `undergraduate_catalog_overview/requirements` 8, `certificate_in_neural_net_math/requirements` 7, `bachelor_of_science_in_computer_science/requirements` 7 (a target)

## Method comparison (MRR@10)

**strict**: dense better on 12, BM25 better on 1, tied on 17.

- BM25 beats dense: Q3 (1.000 vs 0.500)
- Both miss in top 10: none
- Both miss in top 5: Q10

**duplicate-aware**: dense better on 12, BM25 better on 1, tied on 17.

- BM25 beats dense: Q3 (1.000 vs 0.500)
- Both miss in top 10: none
- Both miss in top 5: Q10

