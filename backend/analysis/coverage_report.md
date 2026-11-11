# Embedding coverage report

Source: 940 chunk embeddings (text-embedding-3-small, 1536-dim) across 122 program folders in Neon.
Reproduce with `python backend/embedding_coverage.py`. Topic labels are keyword rules on the folder name, so they are approximate.

Plots: `embedding_map.png` (PCA + UMAP by topic), `embedding_clusters.png` (UMAP + KMeans), `eval_coverage.png` (programs vs eval targets).
Raw numbers: `coverage_summary.json`.

## What the embedding maps show

- UMAP separates Business, Arts/media, and Behavioral sciences into distinct regions. Engineering, Natural sciences, and Econ/policy overlap more.
- Double-major docs sit beside their parent business/biology programs rather than forming their own region, so they will compete with the single-degree docs at retrieval time.
- PCA on two components explains only 18% of variance, so use UMAP for judging structure.
- Most isolated programs by nearest-neighbour similarity: Innovation and Entrepreneurship certificate (0.71, a very short doc), Biomedical Sciences certificate, Neuroscience, Philosophy.

## Eval coverage (programs that are the target of at least one question)

| Topic | Programs | Before (Q1-Q30) | After (Q1-Q51) |
|---|---|---|---|
| Engineering & CS | 14 | 8 | 8 |
| Natural sciences & math | 14 | 2 | 7 |
| Business | 12 | 6 | 6 |
| Econ, policy & social science | 14 | 3 | 7 |
| Arts, humanities & media | 29 | 6 | 10 |
| Behavioral & brain sciences | 8 | 2 | 3 |
| Education & interdisciplinary | 13 | 0 | 8 |
| Double majors | 15 | 5 | 5 |
| Catalog index | 3 | 0 | 1 |
| Total | 122 | 32 | 55 |

Education grew from 6 to 13 programs after the missing 4-8 and EC-6 concentration pages were added to the corpus.

## Still underrepresented

- Arts, humanities & media: 19 of 29 programs untargeted, mostly the VPA, Literature, and Media Arts concentration folders.
- Double majors: 10 of 15 untargeted.
- Behavioral & brain sciences: 5 of 8 untargeted.
- Four-year sample plans: 77 `example.txt` files in the corpus, only 3 questions (Q43, Q44, Q50) target them.
- Catalog index folders `2/` and `3/` have no question.

## Corpus note

`bachelor_of_arts_in_education/requirements.txt` is a footer-only file because the catalog URL for that page returns HTTP 404. It is excluded from Neon. The program's content is covered by its concentration pages.
