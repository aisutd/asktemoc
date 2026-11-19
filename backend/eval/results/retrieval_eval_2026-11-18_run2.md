# Retrieval evaluation — 2026-11-18

- Questions: 55 from `eval_questions.md`; parsed copy in `eval/eval_set.json`
- Corpus: 202 documents, 892 chunks (Neon, read-only)
- Code: `00c5747 (with uncommitted changes)`
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
| dense | strict | 0.639 | 0.891 | 0.906 | 0.958 |
| dense | duplicate-aware | 0.639 | 0.891 | 0.906 | 0.958 |
| bm25 | strict | 0.458 | 0.597 | 0.752 | 0.842 |
| bm25 | duplicate-aware | 0.458 | 0.597 | 0.752 | 0.842 |

**MRR@k**

| method | mode | @1 | @3 | @5 | @10 |
|---|---|---:|---:|---:|---:|
| dense | strict | 0.727 | 0.821 | 0.821 | 0.827 |
| dense | duplicate-aware | 0.727 | 0.821 | 0.821 | 0.827 |
| bm25 | strict | 0.527 | 0.570 | 0.602 | 0.616 |
| bm25 | duplicate-aware | 0.527 | 0.570 | 0.602 | 0.616 |

**Precision@k (strict)**

| method | mode | @1 | @3 | @5 | @10 |
|---|---|---:|---:|---:|---:|
| dense | strict | 0.727 | 0.370 | 0.229 | 0.122 |
| bm25 | strict | 0.527 | 0.236 | 0.182 | 0.102 |

**Precision@k (duplicate-aware)**: counts identical copies as separate hits, so it rewards redundancy; not comparable to strict precision.

| method | mode | @1 | @3 | @5 | @10 |
|---|---|---:|---:|---:|---:|
| dense | duplicate-aware | 0.727 | 0.370 | 0.233 | 0.124 |
| bm25 | duplicate-aware | 0.527 | 0.236 | 0.182 | 0.104 |

## Chunk budget (what generation receives)

Recall and MRR over the raw first k chunks, with no document-level dedup: repeated chunks of one document use up the budget, and MRR uses the position of the first relevant chunk.

**Recall within the first k chunks**

| method | mode | 3 chunks | 5 chunks | 8 chunks |
|---|---|---:|---:|---:|
| dense | strict | 0.882 | 0.906 | 0.942 |
| dense | duplicate-aware | 0.882 | 0.906 | 0.942 |
| bm25 | strict | 0.597 | 0.742 | 0.824 |
| bm25 | duplicate-aware | 0.597 | 0.742 | 0.824 |

**MRR within the first k chunks**

| method | mode | 3 chunks | 5 chunks | 8 chunks |
|---|---|---:|---:|---:|
| dense | strict | 0.818 | 0.818 | 0.823 |
| dense | duplicate-aware | 0.818 | 0.818 | 0.823 |
| bm25 | strict | 0.570 | 0.602 | 0.613 |
| bm25 | duplicate-aware | 0.570 | 0.602 | 0.613 |

**Context precision within the first k chunks**: the share of the k chunks sent to generation that come from a relevant document. Repeated chunks of a target count each time.

| method | mode | 3 chunks | 5 chunks | 8 chunks |
|---|---|---:|---:|---:|
| dense | strict | 0.558 | 0.447 | 0.352 |
| dense | duplicate-aware | 0.558 | 0.451 | 0.357 |
| bm25 | strict | 0.345 | 0.316 | 0.248 |
| bm25 | duplicate-aware | 0.345 | 0.316 | 0.250 |

**With a per-document cap of 2 chunks**: the same budgets after keeping at most 2 chunks from any one document.

Recall:

| method | mode | 3 chunks | 5 chunks | 8 chunks |
|---|---|---:|---:|---:|
| dense | strict | 0.891 | 0.906 | 0.942 |
| dense | duplicate-aware | 0.891 | 0.906 | 0.942 |
| bm25 | strict | 0.597 | 0.742 | 0.824 |
| bm25 | duplicate-aware | 0.597 | 0.742 | 0.824 |

Context precision:

| method | mode | 3 chunks | 5 chunks | 8 chunks |
|---|---|---:|---:|---:|
| dense | strict | 0.509 | 0.338 | 0.223 |
| dense | duplicate-aware | 0.509 | 0.342 | 0.227 |
| bm25 | strict | 0.303 | 0.258 | 0.182 |
| bm25 | duplicate-aware | 0.303 | 0.258 | 0.184 |

## Per question: rank of first relevant document (top 10, – = none)

| Q | targets | dense strict | dense dup-aware | bm25 strict | bm25 dup-aware | question |
|---|---:|---:|---:|---:|---:|---|
| Q1 | 1 | 1 | 1 | 5 | 5 | What are the core requirements for the BS in Computer Science at UTD? |
| Q2 | 1 | 2 | 2 | 3 | 3 | How many total credit hours are required to complete the BS in Computer Science? |
| Q3 | 1 | 2 | 2 | 1 | 1 | What math courses are required for the BS in Electrical Engineering? |
| Q4 | 1 | 1 | 1 | 1 | 1 | What is the Certificate in Quantum Information and what courses does it require? |
| Q5 | 1 | 3 | 3 | 6 | 6 | What are the requirements for the BS in Biology and Healthcare Management double major? |
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
| Q27 | 1 | 2 | 2 | 1 | 1 | What are the requirements for the Certificate in Innovation and Entrepreneurship? |
| Q28 | 2 | 1 | 1 | – | – | Does UTD have a pre-law program or certificate, and what does it cover? |
| Q29 | 1 | 1 | 1 | 1 | 1 | What are the requirements for the BA in Visual and Performing Arts — Film concentration? |
| Q30 | 3 | 3 | 3 | – | – | What programs at UTD combine business with another discipline as a prescribed double major? |
| Q31 | 1 | 1 | 1 | 1 | 1 | What does UT Dallas require to become a certified teacher through the BA in Education with 7-12 Social Studies (History)? |
| Q32 | 1 | 1 | 1 | 4 | 4 | What is the BS in Healthcare Studies and what courses does it require? |
| Q33 | 1 | 1 | 1 | 1 | 1 | Which Society of Actuaries exams does the BS in Actuarial Science prepare students to take? |
| Q34 | 1 | 1 | 1 | 1 | 1 | Which calculus and general chemistry courses are required for the BS in Biochemistry? |
| Q35 | 1 | 1 | 1 | 4 | 4 | What geology courses does the BS in Geosciences require, and what careers does it lead to? |
| Q36 | 2 | 2 | 2 | 1 | 1 | How do the requirements for the BA in Biology differ from the BS in Molecular Biology? |
| Q37 | 1 | 1 | 1 | – | – | What career paths does the BA in Criminology prepare students for? |
| Q38 | 2 | 1 | 1 | 1 | 1 | What is the difference between the BS in Public Policy and the BS in Public Affairs? |
| Q39 | 1 | 1 | 1 | 1 | 1 | What is the Certificate in Compassionate Law Enforcement Active Response (CLEAR) and how many credit hours is it? |
| Q40 | 1 | 1 | 1 | 1 | 1 | What are the requirements for the Music concentration in the BA in Visual and Performing Arts? |
| Q41 | 2 | 1 | 1 | 5 | 5 | What concentrations does the BA in Literature offer, and what does the Creative Writing concentration require? |
| Q42 | 1 | 1 | 1 | 5 | 5 | What are the degree requirements for the BA in History? |
| Q43 | 1 | 1 | 1 | – | – | What does the sample four-year degree plan for the BS in Psychology look like for the first fall semester? |
| Q44 | 1 | 1 | 1 | – | – | What does the sample four-year degree plan for the BS in Computer Science look like for the first year? |
| Q45 | 1 | – | – | – | – | Which undergraduate programs at UTD have a Fast Track option? |
| Q46 | 1 | 2 | 2 | 1 | 1 | How many credit hours and how many core curriculum hours does the BA in Education with EC-6 Core Subjects require? |
| Q47 | 1 | 1 | 1 | 4 | 4 | What are the degree requirements for the BS in Education with a 4-8 Mathematics focus? |
| Q48 | 2 | 1 | 1 | 4 | 4 | How does the BA in Education 4-8 English, Language Arts and Reading (ELAR) differ from the 4-8 Social Studies track? |
| Q49 | 1 | 7 | 7 | 8 | 8 | What are the two routes to teacher certification at UT Dallas, and which schools run them? |
| Q50 | 1 | 2 | 2 | – | – | What does the sample four-year degree plan for the BS in Education 4-8 Science look like? |
| Q51 | 2 | 2 | 2 | 7 | 7 | What is the difference between the BA in Education 4-8 Science and the BS in Education 4-8 Science? |
| Q52 | 1 | 1 | 1 | 1 | 1 | How much more per semester credit hour do Oklahoma residents pay than the Texas resident tuition rate? |
| Q53 | 1 | 1 | 1 | 1 | 1 | Which terms do the 2026-2027 variable tuition plan rates apply to? |
| Q54 | 1 | – | – | 1 | 1 | What are the two paths for teacher certification listed on UT Dallas's academics page, and who is each for? |
| Q55 | 1 | 1 | 1 | 1 | 1 | What is the Bursar Office's email address and what are its office hours? |

## Strict vs duplicate-aware: what changed

2 question/method pairs change. The last column lists every non-target document that counted in the top 10, as `#rank doc -> target [exact|near (ratio)]`. `rescued` marks the first document credited to that target, which raised recall or MRR; the others only raised precision.

| Q | method | changed at k | R@10 strict → dup | MRR@10 strict → dup | P@10 strict → dup (dup counts copies) | duplicate documents counted (top 10) |
|---|---|---|---|---|---|---|
| Q5 | dense | 5, 10 | 1.000 → 1.000 | 0.333 → 0.333 | 0.100 → 0.200 | #4 bs_in_healthcare_management_and_biology_double_major/requirements -> bs_in_biology_and_healthcare_management_double_major/requirements [near (0.992)] |
| Q5 | bm25 | 10 | 1.000 → 1.000 | 0.167 → 0.167 | 0.100 → 0.200 | #7 bs_in_healthcare_management_and_biology_double_major/requirements -> bs_in_biology_and_healthcare_management_double_major/requirements [near (0.992)] |

### Equivalence sets used for targets (targets with at least one duplicate)

- `bs_in_biology_and_healthcare_management_double_major/requirements`: `bs_in_healthcare_management_and_biology_double_major/requirements` (near (0.992))

## Repeated documents in chunk rankings

| method | questions with a repeat in top 10 chunks | mean repeats in top 10 chunks | max | mean chunks needed for 10 distinct docs | max |
|---|---:|---:|---:|---:|---:|
| dense | 50/55 | 3.38 | 9 | 15.5 | 41 |

dense: pool did not reach 10 distinct documents for Q52, Q53.
| bm25 | 43/55 | 1.93 | 9 | 13.3 | 42 |

bm25: pool did not reach 10 distinct documents for Q52.

## Catalog index pages (`1/`, `2/`, `3/requirements`) in the top 5

These three documents are identical copies of the catalog's program index page.

| method | questions with ≥1 in top 5 docs | slots taken in top 5 docs | questions with ≥1 in top 5 chunks | slots taken in top 5 chunks |
|---|---:|---:|---:|---:|
| dense | 0/55 | 0/275 | 0/55 | 0/275 |
| bm25 | 0/55 | 0/275 | 0/55 | 0/275 |

## Documents that appear in the top 5 most often

A document in many unrelated top-5 lists is crowding out targets. Count = questions (of 55) with that document in the top 5.

**dense**: `bachelor_of_science_in_software_engineering/requirements` 9 (a target), `undergraduate_catalog_overview/requirements` 9 (a target), `bachelor_of_science_in_computer_science/requirements` 6 (a target), `bachelor_of_science_in_cybersecurity_and_risk_management/requirements` 6 (a target), `bachelor_of_science_in_systems_engineering/requirements` 6, `bachelor_of_science_in_computer_engineering/requirements` 6

**bm25**: `bachelor_of_arts_in_economics/requirements` 37 (a target), `bachelor_of_arts_in_sociology/requirements` 29, `bachelor_of_arts_in_political_science/requirements` 18, `undergraduate_catalog_overview/requirements` 14 (a target), `bachelor_of_science_in_computer_science/requirements` 10 (a target), `bachelor_of_science_in_software_engineering/requirements` 9 (a target)

## Method comparison (MRR@10)

**strict**: dense better on 24, BM25 better on 5, tied on 26.

- BM25 beats dense: Q3 (1.000 vs 0.500), Q27 (1.000 vs 0.500), Q36 (1.000 vs 0.500), Q46 (1.000 vs 0.500), Q54 (1.000 vs 0.000)
- Both miss in top 10: Q45
- Both miss in top 5: Q10, Q45, Q49

**duplicate-aware**: dense better on 24, BM25 better on 5, tied on 26.

- BM25 beats dense: Q3 (1.000 vs 0.500), Q27 (1.000 vs 0.500), Q36 (1.000 vs 0.500), Q46 (1.000 vs 0.500), Q54 (1.000 vs 0.000)
- Both miss in top 10: Q45
- Both miss in top 5: Q10, Q45, Q49

