# Week 3 retrieval review

Sources: `retrieval_eval_2026-10-21.md` (code `1a89404`) and
`retrieval_eval_2026-10-21_small-vs-large.md` (code `0330a52`), with their CSVs.
30 questions, 192 documents, 885 chunks. The eval was not rerun for this
review; every number below is copied from those reports.

"dense" means `text-embedding-3-small` over Neon pgvector. "dense-large" means
`text-embedding-3-large` over a local numpy cache of the same 885 chunks.

## 1. Dense vs BM25

Document-level metrics:

| metric | dense strict | dense dup-aware | bm25 strict | bm25 dup-aware |
|---|---:|---:|---:|---:|
| Recall@1 | 0.578 | 0.667 | 0.372 | 0.450 |
| Recall@3 | 0.706 | 0.794 | 0.622 | 0.700 |
| Recall@5 | 0.761 | 0.889 | 0.717 | 0.717 |
| Recall@10 | 0.967 | 0.967 | 0.867 | 0.922 |
| MRR@1 | 0.667 | 0.767 | 0.467 | 0.533 |
| MRR@5 | 0.748 | 0.833 | 0.594 | 0.639 |
| MRR@10 | 0.769 | 0.838 | 0.612 | 0.659 |

- Dense wins at every k, in both modes. Per question (MRR@10), strict mode:
  dense is better on 12, BM25 on 5, and 13 tie. Duplicate-aware: 12 / 2 / 16.
- BM25's strict wins are Q3, Q6, Q8, Q13 and Q19. Four of those five are
  certificate questions whose target belongs to an exact-duplicate cluster. In
  duplicate-aware mode only Q3 and Q8 are still BM25 wins.
- BM25 misses Q28 and Q30 entirely in the top 10 (Q23 too, in strict mode).
  `bachelor_of_arts_in_economics/requirements` shows up in BM25's top 5 for
  20 of the 30 questions, so it is a strong hub document for BM25.
- The difference between strict and duplicate-aware scores comes from
  duplicate documents in the corpus. Dense Recall@5 is 0.761 strict and 0.889
  duplicate-aware. MRR@1 is 0.667 and 0.767. Duplicate copies change 21
  question/method pairs.

## 2. Chunk budget (what generation receives)

Recall and MRR over the first k chunks, with no document-level dedup:

| method | mode | R @3 chunks | R @5 chunks | R @8 chunks | MRR @3 | MRR @5 | MRR @8 |
|---|---|---:|---:|---:|---:|---:|---:|
| dense | strict | 0.689 | 0.761 | 0.922 | 0.728 | 0.743 | 0.762 |
| dense | dup-aware | 0.778 | 0.889 | 0.939 | 0.806 | 0.827 | 0.831 |
| dense-large | strict | 0.728 | 0.839 | 0.856 | 0.683 | 0.705 | 0.709 |
| dense-large | dup-aware | 0.739 | 0.839 | 0.856 | 0.794 | 0.809 | 0.814 |
| bm25 | strict | 0.622 | 0.700 | 0.833 | 0.578 | 0.594 | 0.608 |
| bm25 | dup-aware | 0.700 | 0.700 | 0.844 | 0.639 | 0.639 | 0.652 |

- For dense, going from 5 to 8 chunks raises strict recall from 0.761 to
  0.922. Going from 3 to 5 raises it from 0.689 to 0.761. With small
  embeddings, 8 chunks is the budget where recall is close to the
  document-level Recall@10 of 0.967.
- Dense has the same document's chunks repeated in the top 10 for 25 of 30
  questions, with 3.07 repeats on average (max 6). It needs 15.1 chunks on
  average to reach 10 distinct documents (max 24). For BM25 the figures are
  24/30, 2.00 and 13.3.
- The three catalog index pages (`1/`, `2/` and `3/requirements`, which are
  identical copies) take 10 of the 150 top-5 chunk slots for dense, across 4
  questions.

## 3. Small vs large embeddings

| metric | small strict | large strict | small dup-aware | large dup-aware |
|---|---:|---:|---:|---:|
| Recall@1 | 0.578 | 0.528 | 0.667 | 0.672 |
| Recall@3 | 0.706 | 0.778 | 0.794 | 0.822 |
| Recall@5 | 0.761 | 0.856 | 0.889 | 0.911 |
| Recall@10 | 0.967 | 0.950 | 0.967 | 0.950 |
| MRR@10 | 0.769 | 0.725 | 0.838 | 0.832 |
| R @5 chunks | 0.761 | 0.839 | 0.889 | 0.839 |
| R @8 chunks | 0.922 | 0.856 | 0.939 | 0.856 |

- The results are mixed and do not justify switching. Large does better at
  Recall@3 and @5, but small does better at Recall@1, Recall@10 and MRR@10.
  Per question (duplicate-aware MRR@10), large is better on 4, small is
  better on 4, and 22 tie.
- Large makes chunk repetition worse: repeats in 28/30 questions, mean 4.37
  (max 7), and 18.2 chunks needed for 10 distinct docs (max 32). That is why
  its 8-chunk recall is 0.856, against 0.922 for small.
- Large lets fewer index pages into the top 5 (3/30 questions and 8/150
  slots, against 5/30 and 13/150 for small). This fixes Q5 (MRR@10
  0.250 → 1.000).
- Large's worst regression is Q28 (pre-law): MRR@10 drops from 1.000 to
  0.167, and recall within 5 chunks drops to 0.000. The law-enforcement,
  military and public-service certificates (an exact-duplicate cluster)
  outrank both pre-law targets.

## 4. Five worst questions for dense (small)

Ranked by strict MRR@10. Ties are broken by duplicate-aware MRR@10.

| # | Q | first hit strict / dup | dense top 3 docs | likely cause |
|---|---|---|---|---|
| 1 | Q8 Cert. Applied Experience Design & Research | 8 / 5 | cert:user_experience_ux_research, cert:behavioral_research_methods, cert:biobehavioral_data_science | **Duplicate docs.** The target's text is identical to five other certificates (creative writing, Holocaust/genocide, intercultural communication, legal research, professional communication), because all six are the Bass School's combined certificates page. Its content therefore cannot single it out. A second exact-duplicate cluster (the UX research group) is semantically closer and takes the top 3. Large does no better (6 / 5). BM25 ranks it 1. |
| 2 | Q10 standalone BS Healthcare Management | 6 / 6 | bs:healthcare_studies, bs:cybersecurity_and_risk_management, bs:supply_chain_management_and_analytics | **Wrong ranking.** No duplicates are involved. Sibling programs with similar names outrank the target, and recall within 5 chunks is 0.000. This is the only question that dense and BM25 both miss in the top 5. Large reaches rank 4 through the healthcare-management double majors and `bs:healthcare_management/ex`. Whether that `/ex` page should also count as relevant needs checking. |
| 3 | Q19 Cert. Cyber Defense | 6 / 3 | bs:software_engineering, bs:computer_science, cert:sustainable_energy_engineering | **Duplicate docs plus hub crowding.** The target's text is identical to the sustainable-energy, semiconductor and nanoscience certificates, because all four are the Jonsson School's combined certificates page. SE and CS take the top 2, and they are dense's most frequent top-5 documents (8 and 6 questions). |
| 4 | Q6 Cert. Intercultural Communication | 6 / 1 | cert:holocaust_genocide_and_human_rights, cert:creative_writing, cert:professional_communication | **Duplicate docs only.** The target belongs to the same six-document identical cluster as Q8. Ranks 1–5 are all copies, so the duplicate-aware rank is 1. Strict recall within 5 chunks is 0.000, which means the named certificate never reaches generation. This is not a scraping error. All six documents are the Bass School's combined certificates page, saved once per certificate, so each copy contains the Intercultural Communication requirements but cannot be told apart from the other five. |
| 5 | Q30 business + discipline double majors (3 targets) | 5 / 5 | 3, 2, 1 (catalog index pages) | **Index-page crowding.** The three identical index pages fill the top 3. This is a broad list question with 3 targets, and recall within 5 chunks is only 0.333. BM25 finds none of the targets in its top 10. |

Next in line is Q5 (first hit 4 / 4). Its top 3 are also the index pages
(3, 2, 1), and large embeddings fix it (rank 1).

Coverage of the candidate causes:
- **Missing doc:** none. Dense has no question with zero targets in the top
  10, and every target exists in the corpus.
- **Chunk repetition:** not the main cause in any of the five questions
  above, but it costs recall overall. Dense strict recall at 8 chunks is
  0.922, against 0.967 for documents at Recall@10.

## 5. Week 5 experiments (ranked by expected impact)

1. **Split combined pages into one document per certificate at ingestion.**
   Four exact-text clusters cover 6, 4, 4 and 3 certificates. These are not
   scraping errors: each cluster is a school's combined certificates page,
   saved once per certificate. For example, every copy in the Bass School
   cluster lists all six certificates, starting with Applied Experience
   Design and Research. Some certificates are also exact copies of degree
   pages: quantum information ↔ BA physics, data science ↔ BS data science,
   and sustainable earth ↔ BS geosciences / cert geophysics. The
   `certificate_in_geophysics` page, for one, is the Geosciences (BS) page
   with the certificate section at the end, which suggests the same
   combined-page pattern. Duplicate content, counting the identical index
   pages, drives 4 of the 5 worst questions (Q6, Q8, Q19, Q30). It also
   explains why strict and duplicate-aware scores differ (dense R@5: 0.761
   vs 0.889). The fix is to cut each combined page at its `Certificate in …`
   headings during ingestion, keep only the matching section in each
   certificate's document, and keep one copy of the three catalog index
   pages (or drop them). No re-scrape is needed. Then rerun the eval. This
   should also make the strict scores the trustworthy ones.
2. **Diversify chunks per document before generation.** Cap the number of
   chunks taken from one document, or apply MMR. Dense repeats a document in
   25/30 questions and needs 15.1 chunks to cover 10 distinct documents. The
   cap should let a 5-chunk budget get close to the current 8-chunk recall
   (0.761 → 0.922 strict).
3. **Hybrid dense + BM25 (reciprocal rank fusion).** BM25 is stronger on Q3,
   Q6, Q8, Q13 and Q19 in strict mode, and dense is stronger on 12
   questions. Fusion should keep dense's lead and recover some exact-name
   matches. BM25's hub document (BA Economics, in the top 5 for 20/30
   questions) needs a check first so it does not leak into the fused list.
4. **Rerank the top candidates against the program name.** Q10 (sibling
   programs) and Q19 (SE/CS hubs) are ranking errors. A cross-encoder or
   title-match rerank over the top 20 targets those directly.
5. **Tidy up the eval set.** Decide whether the `/ex` documents (for example
   `bs:healthcare_management/ex`, `bs:accounting/ex`) count as relevant, and
   add non-catalog questions for the router work. All 30 current questions
   are catalog-program questions.
6. **Keep `text-embedding-3-small`.** Large is no better overall (MRR@10 dup
   0.838 vs 0.832, 4/4/22 per question) and makes chunk repetition worse.
   Revisit only after items 1 and 2, because large's Recall@5 gain may
   survive once the duplicates are gone.
