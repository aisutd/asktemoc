# Retrieval evaluation — 2026-10-21

- Questions: 30 from `origin/feat/crawl4ai-scraper:backend/eval_questions.md` (blob `d9b5dd851313`); parsed copy in `eval/eval_set.json`
- Corpus: 192 documents, 885 chunks (Neon, read-only)
- Code: `1a89404`
- Questions source commit: `d8e03ee212e9` (last commit touching the file on `origin/feat/crawl4ai-scraper`; branch tip `d8e03ee212e9`)
- Dense: `text-embedding-3-small` query embedding, pgvector cosine distance, exact scan
- BM25: rank_bm25 BM25Okapi, lowercase + `[a-z0-9]+` tokens, no stemming or stopwords
- Each method returns the top 50 chunks; these are collapsed to a document ranking (first chunk of each document counts) and metrics are computed on documents.
- STRICT: only the exact target titles are relevant. DUPLICATE-AWARE: documents with identical text (`exact`) or difflib ratio ≥ 0.99 to a target (`near (ratio)`) also count. Recall counts each target once, credited to the first document that matches it.

## Summary (document level)

Headline metrics: Recall@k and MRR@k over the document ranking.

**Recall@k**

| method | mode | @1 | @3 | @5 | @10 |
|---|---|---:|---:|---:|---:|
| dense | strict | 0.578 | 0.706 | 0.761 | 0.967 |
| dense | duplicate-aware | 0.667 | 0.794 | 0.889 | 0.967 |
| bm25 | strict | 0.372 | 0.622 | 0.717 | 0.867 |
| bm25 | duplicate-aware | 0.450 | 0.700 | 0.717 | 0.922 |

**MRR@k**

| method | mode | @1 | @3 | @5 | @10 |
|---|---|---:|---:|---:|---:|
| dense | strict | 0.667 | 0.733 | 0.748 | 0.769 |
| dense | duplicate-aware | 0.767 | 0.811 | 0.833 | 0.838 |
| bm25 | strict | 0.467 | 0.578 | 0.594 | 0.612 |
| bm25 | duplicate-aware | 0.533 | 0.639 | 0.639 | 0.659 |

**Precision@k (strict)**

| method | mode | @1 | @3 | @5 | @10 |
|---|---|---:|---:|---:|---:|
| dense | strict | 0.667 | 0.278 | 0.187 | 0.123 |
| bm25 | strict | 0.467 | 0.244 | 0.173 | 0.103 |

**Precision@k (duplicate-aware)**: counts identical copies as separate hits, so it rewards redundancy; not comparable to strict precision.

| method | mode | @1 | @3 | @5 | @10 |
|---|---|---:|---:|---:|---:|
| dense | duplicate-aware | 0.767 | 0.422 | 0.327 | 0.233 |
| bm25 | duplicate-aware | 0.533 | 0.356 | 0.280 | 0.193 |

## Chunk budget (what generation receives)

Recall and MRR over the raw first k chunks, with no document-level dedup: repeated chunks of one document use up the budget, and MRR uses the position of the first relevant chunk.

**Recall within the first k chunks**

| method | mode | 3 chunks | 5 chunks | 8 chunks |
|---|---|---:|---:|---:|
| dense | strict | 0.689 | 0.761 | 0.922 |
| dense | duplicate-aware | 0.778 | 0.889 | 0.939 |
| bm25 | strict | 0.622 | 0.700 | 0.833 |
| bm25 | duplicate-aware | 0.700 | 0.700 | 0.844 |

**MRR within the first k chunks**

| method | mode | 3 chunks | 5 chunks | 8 chunks |
|---|---|---:|---:|---:|
| dense | strict | 0.728 | 0.743 | 0.762 |
| dense | duplicate-aware | 0.806 | 0.827 | 0.831 |
| bm25 | strict | 0.578 | 0.594 | 0.608 |
| bm25 | duplicate-aware | 0.639 | 0.639 | 0.652 |

## Per question: rank of first relevant document (top 10, – = none)

| Q | targets | dense strict | dense dup-aware | bm25 strict | bm25 dup-aware | question |
|---|---:|---:|---:|---:|---:|---|
| Q1 | 1 | 1 | 1 | 8 | 8 | What are the core requirements for the BS in Computer Science at UTD? |
| Q2 | 1 | 1 | 1 | 2 | 2 | How many total credit hours are required to complete the BS in Computer Science? |
| Q3 | 1 | 2 | 2 | 1 | 1 | What math courses are required for the BS in Electrical Engineering? |
| Q4 | 1 | 1 | 1 | 4 | 3 | What is the Certificate in Quantum Information and what courses does it require? |
| Q5 | 1 | 4 | 4 | 8 | 8 | What are the requirements for the BS in Biology and Healthcare Management double major? |
| Q6 | 1 | 6 | 1 | 4 | 1 | What courses are listed under the Certificate in Intercultural Communication? |
| Q7 | 1 | 2 | 1 | 2 | 1 | What does the Certificate in Military Science Leadership require, and who is eligible? |
| Q8 | 1 | 8 | 5 | 1 | 1 | What courses make up the Certificate in Applied Experience Design and Research? |
| Q9 | 1 | 1 | 1 | 2 | 2 | What are the upper-division elective options for the BS in Computer Science? |
| Q10 | 1 | 6 | 6 | 7 | 7 | What are the requirements for the standalone BS in Healthcare Management at UTD? |
| Q11 | 1 | 1 | 1 | 1 | 1 | What science or lab courses are required in the BS in Electrical Engineering? |
| Q12 | 1 | 2 | 2 | 2 | 2 | What courses are required for the BS in Accounting at UTD? |
| Q13 | 3 | 2 | 1 | 1 | 1 | What certificates at UTD focus on communication, design, or user experience? |
| Q14 | 2 | 1 | 1 | 1 | 1 | What is the difference in core requirements between a BS in Computer Science and a BS in Electrical Engineering at UTD? |
| Q15 | 1 | 1 | 1 | 1 | 1 | What are the course requirements for the BA in Animation and Games at UTD? |
| Q16 | 1 | 1 | 1 | 2 | 2 | What does the BS in Business Analytics and Artificial Intelligence require? |
| Q17 | 1 | 1 | 1 | 1 | 1 | What courses are required for the BS in Cybersecurity and Risk Management? |
| Q18 | 2 | 1 | 1 | 1 | 1 | How do the core requirements for the BS in Software Engineering compare to those for the BS in Computer Science? |
| Q19 | 1 | 6 | 3 | 3 | 3 | What are the requirements for the Certificate in Cyber Defense? |
| Q20 | 1 | 1 | 1 | 1 | 1 | What courses does the BS in Biomedical Engineering require? |
| Q21 | 1 | 1 | 1 | 2 | 2 | What is required for the BS in Neuroscience at UTD? |
| Q22 | 2 | 1 | 1 | 1 | 1 | How do the requirements differ between the BA in Economics and the BS in Finance and Economics double major? |
| Q23 | 1 | 1 | 1 | – | 10 | What courses make up the Certificate in Data Science? |
| Q24 | 1 | 1 | 1 | 1 | 1 | What are the requirements for the BS in Mechanical Engineering? |
| Q25 | 3 | 1 | 1 | 1 | 1 | What programs at UTD focus on sustainability or environmental topics? |
| Q26 | 1 | 1 | 1 | 8 | 8 | What is the BS in Marketing and what courses does it require? |
| Q27 | 1 | 1 | 1 | 1 | 1 | What are the requirements for the Certificate in Innovation and Entrepreneurship? |
| Q28 | 2 | 1 | 1 | – | – | Does UTD have a pre-law program or certificate, and what does it cover? |
| Q29 | 1 | 1 | 1 | 1 | 1 | What are the requirements for the BA in Visual and Performing Arts — Film concentration? |
| Q30 | 3 | 5 | 5 | – | – | What programs at UTD combine business with another discipline as a prescribed double major? |

## Strict vs duplicate-aware: what changed

21 question/method pairs change. The last column lists every non-target document that counted in the top 10, as `#rank doc -> target [exact|near (ratio)]`. `rescued` marks the first document credited to that target, which raised recall or MRR; the others only raised precision.

| Q | method | changed at k | R@10 strict → dup | MRR@10 strict → dup | P@10 strict → dup (dup counts copies) | duplicate documents counted (top 10) |
|---|---|---|---|---|---|---|
| Q4 | dense | 3, 5, 10 | 1.000 → 1.000 | 1.000 → 1.000 | 0.100 → 0.200 | #2 bachelor_of_arts_in_physics/requirements -> certificate_in_quantum_information/requirements [exact] |
| Q4 | bm25 | 3, 5, 10 | 1.000 → 1.000 | 0.250 → 0.333 | 0.100 → 0.200 | #3 bachelor_of_arts_in_physics/requirements -> certificate_in_quantum_information/requirements [exact, rescued] |
| Q5 | dense | 10 | 1.000 → 1.000 | 0.250 → 0.250 | 0.100 → 0.200 | #8 bs_in_healthcare_management_and_biology_double_major/requirements -> bs_in_biology_and_healthcare_management_double_major/requirements [near (0.992)] |
| Q5 | bm25 | 10 | 1.000 → 1.000 | 0.125 → 0.125 | 0.100 → 0.200 | #9 bs_in_healthcare_management_and_biology_double_major/requirements -> bs_in_biology_and_healthcare_management_double_major/requirements [near (0.992)] |
| Q6 | dense | 1, 3, 5, 10 | 1.000 → 1.000 | 0.167 → 1.000 | 0.100 → 0.600 | #1 certificate_in_holocaust_genocide_and_human_rights/requirements -> certificate_in_intercultural_communication/requirements [exact, rescued]; #2 certificate_in_creative_writing/requirements -> certificate_in_intercultural_communication/requirements [exact]; #3 certificate_in_professional_communication/requirements -> certificate_in_intercultural_communication/requirements [exact]; #4 certificate_in_legal_research_and_writing/requirements -> certificate_in_intercultural_communication/requirements [exact]; #5 certificate_in_applied_experience_design_and_research/requirements -> certificate_in_intercultural_communication/requirements [exact] |
| Q6 | bm25 | 1, 3, 5, 10 | 1.000 → 1.000 | 0.250 → 1.000 | 0.100 → 0.600 | #1 certificate_in_applied_experience_design_and_research/requirements -> certificate_in_intercultural_communication/requirements [exact, rescued]; #2 certificate_in_creative_writing/requirements -> certificate_in_intercultural_communication/requirements [exact]; #3 certificate_in_holocaust_genocide_and_human_rights/requirements -> certificate_in_intercultural_communication/requirements [exact]; #5 certificate_in_legal_research_and_writing/requirements -> certificate_in_intercultural_communication/requirements [exact]; #6 certificate_in_professional_communication/requirements -> certificate_in_intercultural_communication/requirements [exact] |
| Q7 | dense | 1, 3, 5, 10 | 1.000 → 1.000 | 0.500 → 1.000 | 0.100 → 0.300 | #1 certificate_in_public_service_and_civic_leadership/requirements -> certificate_in_military_science_leadership/requirements [exact, rescued]; #3 certificate_in_compassionate_law_enforcement_active_response_clear/requirements -> certificate_in_military_science_leadership/requirements [exact] |
| Q7 | bm25 | 1, 3, 5, 10 | 1.000 → 1.000 | 0.500 → 1.000 | 0.100 → 0.300 | #1 certificate_in_compassionate_law_enforcement_active_response_clear/requirements -> certificate_in_military_science_leadership/requirements [exact, rescued]; #3 certificate_in_public_service_and_civic_leadership/requirements -> certificate_in_military_science_leadership/requirements [exact] |
| Q8 | dense | 5, 10 | 1.000 → 1.000 | 0.125 → 0.200 | 0.100 → 0.600 | #5 certificate_in_holocaust_genocide_and_human_rights/requirements -> certificate_in_applied_experience_design_and_research/requirements [exact, rescued]; #6 certificate_in_creative_writing/requirements -> certificate_in_applied_experience_design_and_research/requirements [exact]; #7 certificate_in_legal_research_and_writing/requirements -> certificate_in_applied_experience_design_and_research/requirements [exact]; #9 certificate_in_professional_communication/requirements -> certificate_in_applied_experience_design_and_research/requirements [exact]; #10 certificate_in_intercultural_communication/requirements -> certificate_in_applied_experience_design_and_research/requirements [exact] |
| Q8 | bm25 | 3, 5, 10 | 1.000 → 1.000 | 1.000 → 1.000 | 0.100 → 0.600 | #2 certificate_in_creative_writing/requirements -> certificate_in_applied_experience_design_and_research/requirements [exact]; #3 certificate_in_holocaust_genocide_and_human_rights/requirements -> certificate_in_applied_experience_design_and_research/requirements [exact]; #4 certificate_in_intercultural_communication/requirements -> certificate_in_applied_experience_design_and_research/requirements [exact]; #5 certificate_in_legal_research_and_writing/requirements -> certificate_in_applied_experience_design_and_research/requirements [exact]; #6 certificate_in_professional_communication/requirements -> certificate_in_applied_experience_design_and_research/requirements [exact] |
| Q13 | dense | 1, 3, 5, 10 | 1.000 → 1.000 | 0.500 → 1.000 | 0.300 → 1.000 | #1 certificate_in_legal_research_and_writing/requirements -> certificate_in_intercultural_communication/requirements [exact, rescued], certificate_in_applied_experience_design_and_research/requirements [exact, rescued]; #3 certificate_in_professional_communication/requirements -> certificate_in_intercultural_communication/requirements [exact], certificate_in_applied_experience_design_and_research/requirements [exact]; #4 certificate_in_holocaust_genocide_and_human_rights/requirements -> certificate_in_intercultural_communication/requirements [exact], certificate_in_applied_experience_design_and_research/requirements [exact]; #5 certificate_in_creative_writing/requirements -> certificate_in_intercultural_communication/requirements [exact], certificate_in_applied_experience_design_and_research/requirements [exact]; #7 certificate_in_behavioral_research_methods/requirements -> certificate_in_user_experience_ux_research/requirements [exact, rescued]; #8 certificate_in_biobehavioral_data_science/requirements -> certificate_in_user_experience_ux_research/requirements [exact]; #9 certificate_in_neural_net_math/requirements -> certificate_in_user_experience_ux_research/requirements [exact] |
| Q13 | bm25 | 1, 3, 5, 10 | 0.667 → 1.000 | 1.000 → 1.000 | 0.200 → 0.900 | #2 certificate_in_creative_writing/requirements -> certificate_in_intercultural_communication/requirements [exact], certificate_in_applied_experience_design_and_research/requirements [exact]; #3 certificate_in_holocaust_genocide_and_human_rights/requirements -> certificate_in_intercultural_communication/requirements [exact], certificate_in_applied_experience_design_and_research/requirements [exact]; #5 certificate_in_legal_research_and_writing/requirements -> certificate_in_intercultural_communication/requirements [exact], certificate_in_applied_experience_design_and_research/requirements [exact]; #6 certificate_in_professional_communication/requirements -> certificate_in_intercultural_communication/requirements [exact], certificate_in_applied_experience_design_and_research/requirements [exact]; #8 certificate_in_behavioral_research_methods/requirements -> certificate_in_user_experience_ux_research/requirements [exact, rescued]; #9 certificate_in_biobehavioral_data_science/requirements -> certificate_in_user_experience_ux_research/requirements [exact]; #10 certificate_in_neural_net_math/requirements -> certificate_in_user_experience_ux_research/requirements [exact] |
| Q19 | dense | 3, 5, 10 | 1.000 → 1.000 | 0.167 → 0.333 | 0.100 → 0.400 | #3 certificate_in_sustainable_energy_engineering/requirements -> certificate_in_cyber_defense/requirements [exact, rescued]; #4 certificate_in_semiconductor_technology/requirements -> certificate_in_cyber_defense/requirements [exact]; #5 certificate_in_nanoscience_and_nanotechnology/requirements -> certificate_in_cyber_defense/requirements [exact] |
| Q19 | bm25 | 5, 10 | 1.000 → 1.000 | 0.333 → 0.333 | 0.100 → 0.400 | #4 certificate_in_nanoscience_and_nanotechnology/requirements -> certificate_in_cyber_defense/requirements [exact]; #5 certificate_in_semiconductor_technology/requirements -> certificate_in_cyber_defense/requirements [exact]; #6 certificate_in_sustainable_energy_engineering/requirements -> certificate_in_cyber_defense/requirements [exact] |
| Q22 | dense | 3, 5, 10 | 1.000 → 1.000 | 1.000 → 1.000 | 0.200 → 0.300 | #2 bs_in_finance_and_economics_double_major/requirements -> bs_in_economics_and_finance_double_major/requirements [near (0.994)] |
| Q22 | bm25 | 10 | 1.000 → 1.000 | 1.000 → 1.000 | 0.200 → 0.300 | #7 bs_in_finance_and_economics_double_major/requirements -> bs_in_economics_and_finance_double_major/requirements [near (0.994)] |
| Q23 | dense | 3, 5, 10 | 1.000 → 1.000 | 1.000 → 1.000 | 0.100 → 0.200 | #2 bachelor_of_science_in_data_science/requirements -> certificate_in_data_science/requirements [exact] |
| Q23 | bm25 | 10 | 0.000 → 1.000 | 0.000 → 0.100 | 0.000 → 0.100 | #10 bachelor_of_science_in_data_science/requirements -> certificate_in_data_science/requirements [exact, rescued] |
| Q25 | dense | 3, 5, 10 | 0.667 → 0.667 | 1.000 → 1.000 | 0.200 → 0.400 | #2 bachelor_of_science_in_geosciences/requirements -> certificate_in_sustainable_earth_and_environment/requirements [exact, rescued]; #3 certificate_in_geophysics/requirements -> certificate_in_sustainable_earth_and_environment/requirements [exact] |
| Q25 | bm25 | 10 | 0.333 → 0.667 | 1.000 → 1.000 | 0.100 → 0.200 | #10 bachelor_of_science_in_geosciences/requirements -> certificate_in_sustainable_earth_and_environment/requirements [exact, rescued] |
| Q28 | dense | 5, 10 | 1.000 → 1.000 | 1.000 → 1.000 | 0.200 → 0.700 | #5 certificate_in_applied_experience_design_and_research/requirements -> certificate_in_legal_research_and_writing/requirements [exact, rescued]; #6 certificate_in_professional_communication/requirements -> certificate_in_legal_research_and_writing/requirements [exact]; #7 certificate_in_holocaust_genocide_and_human_rights/requirements -> certificate_in_legal_research_and_writing/requirements [exact]; #8 certificate_in_creative_writing/requirements -> certificate_in_legal_research_and_writing/requirements [exact]; #10 certificate_in_intercultural_communication/requirements -> certificate_in_legal_research_and_writing/requirements [exact] |

### Equivalence sets used for targets (targets with at least one duplicate)

- `bs_in_biology_and_healthcare_management_double_major/requirements`: `bs_in_healthcare_management_and_biology_double_major/requirements` (near (0.992))
- `bs_in_economics_and_finance_double_major/requirements`: `bs_in_finance_and_economics_double_major/requirements` (near (0.994))
- `certificate_in_applied_experience_design_and_research/requirements`: `certificate_in_creative_writing/requirements` (exact), `certificate_in_holocaust_genocide_and_human_rights/requirements` (exact), `certificate_in_intercultural_communication/requirements` (exact), `certificate_in_legal_research_and_writing/requirements` (exact), `certificate_in_professional_communication/requirements` (exact)
- `certificate_in_cyber_defense/requirements`: `certificate_in_nanoscience_and_nanotechnology/requirements` (exact), `certificate_in_semiconductor_technology/requirements` (exact), `certificate_in_sustainable_energy_engineering/requirements` (exact)
- `certificate_in_data_science/requirements`: `bachelor_of_science_in_data_science/requirements` (exact)
- `certificate_in_intercultural_communication/requirements`: `certificate_in_applied_experience_design_and_research/requirements` (exact), `certificate_in_creative_writing/requirements` (exact), `certificate_in_holocaust_genocide_and_human_rights/requirements` (exact), `certificate_in_legal_research_and_writing/requirements` (exact), `certificate_in_professional_communication/requirements` (exact)
- `certificate_in_legal_research_and_writing/requirements`: `certificate_in_applied_experience_design_and_research/requirements` (exact), `certificate_in_creative_writing/requirements` (exact), `certificate_in_holocaust_genocide_and_human_rights/requirements` (exact), `certificate_in_intercultural_communication/requirements` (exact), `certificate_in_professional_communication/requirements` (exact)
- `certificate_in_military_science_leadership/requirements`: `certificate_in_compassionate_law_enforcement_active_response_clear/requirements` (exact), `certificate_in_public_service_and_civic_leadership/requirements` (exact)
- `certificate_in_quantum_information/requirements`: `bachelor_of_arts_in_physics/requirements` (exact)
- `certificate_in_sustainable_earth_and_environment/requirements`: `bachelor_of_science_in_geosciences/requirements` (exact), `certificate_in_geophysics/requirements` (exact)
- `certificate_in_sustainable_energy_engineering/requirements`: `certificate_in_cyber_defense/requirements` (exact), `certificate_in_nanoscience_and_nanotechnology/requirements` (exact), `certificate_in_semiconductor_technology/requirements` (exact)
- `certificate_in_user_experience_ux_research/requirements`: `certificate_in_behavioral_research_methods/requirements` (exact), `certificate_in_biobehavioral_data_science/requirements` (exact), `certificate_in_neural_net_math/requirements` (exact)

## Repeated documents in chunk rankings

| method | questions with a repeat in top 10 chunks | mean repeats in top 10 chunks | max | mean chunks needed for 10 distinct docs | max |
|---|---:|---:|---:|---:|---:|
| dense | 25/30 | 3.07 | 6 | 15.1 | 24 |
| bm25 | 24/30 | 2.00 | 6 | 13.3 | 23 |

## Catalog index pages (`1/`, `2/`, `3/requirements`) in the top 5

These three documents are identical copies of the catalog's program index page.

| method | questions with ≥1 in top 5 docs | slots taken in top 5 docs | questions with ≥1 in top 5 chunks | slots taken in top 5 chunks |
|---|---:|---:|---:|---:|
| dense | 5/30 | 13/150 | 4/30 | 10/150 |
| bm25 | 7/30 | 16/150 | 4/30 | 14/150 |

BM25 questions affected: Q5 (3), Q7 (2), Q10 (3), Q14 (1), Q16 (1), Q22 (3), Q29 (3)

## Documents that appear in the top 5 most often

A document in many unrelated top-5 lists is crowding out targets. Count = questions (of 30) with that document in the top 5.

**dense**: `bachelor_of_science_in_software_engineering/requirements` 8 (a target), `bachelor_of_science_in_computer_science/requirements` 6 (a target), `bachelor_of_science_in_computer_engineering/requirements` 6, `bachelor_of_science_in_systems_engineering/requirements` 5, `bachelor_of_science_in_cybersecurity_and_risk_management/requirements` 5 (a target), `2/requirements` 5

**bm25**: `bachelor_of_arts_in_economics/requirements` 20 (a target), `bachelor_of_arts_in_sociology/requirements` 12, `bachelor_of_arts_in_political_science/requirements` 9, `1/requirements` 7, `bachelor_of_science_in_computer_science/requirements` 6 (a target), `bachelor_of_science_in_software_engineering/requirements` 6 (a target)

## Method comparison (MRR@10)

**strict**: dense better on 12, BM25 better on 5, tied on 13.

- BM25 beats dense: Q3 (1.000 vs 0.500), Q6 (0.250 vs 0.167), Q8 (1.000 vs 0.125), Q13 (1.000 vs 0.500), Q19 (0.333 vs 0.167)
- Both miss in top 10: none
- Both miss in top 5: Q10

**duplicate-aware**: dense better on 12, BM25 better on 2, tied on 16.

- BM25 beats dense: Q3 (1.000 vs 0.500), Q8 (1.000 vs 0.200)
- Both miss in top 10: none
- Both miss in top 5: Q10

