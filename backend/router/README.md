# Query router data

Labeled student queries for the query router, which decides which source
should answer a query.

## Labels (one per query)

- **housing**: questions University Housing answers. This covers residence
  halls, University Village, Canyon Creek, housing contracts, roommates,
  move-in, residence hall access and mail, and the meal-plan requirement that
  comes with living on campus.
- **academics**: questions the catalog, an academic department, an advisor or
  the registrar answers. This covers degree, certificate and double-major
  requirements, courses, registration, grades, GPA, probation, transfer
  credit and graduation.
- **general**: everything else on campus, plus off-topic requests. Examples
  are tuition and billing, financial aid and scholarships, parking, dining,
  the Comet Card, the health and counseling centers, accessibility services,
  printing, and questions like "what's the weather".

**Tiebreaker:** label a query by the office or source that would actually
answer it, not by the words it contains. Examples:

| query | label | why |
|---|---|---|
| "Can financial aid pay for my dorm?" | general | the financial aid office answers it |
| "If I withdraw from all my classes do I lose my dorm?" | housing | it is a housing eligibility question |
| "How much is tuition?" | general | the bursar answers it, not an academic department |

## in_corpus

`in_corpus` records whether the current corpus
(`backend/.cache/bm25_chunks.json`, 192 catalog program pages) contains a
document that could answer the query. It was decided by searching the chunk
text for the topic, not by running retrieval.

- `yes`: a document answers it.
- `no`: nothing in the corpus answers it.
- `unsure`: the corpus touches the topic but probably does not answer it.

## Confidence

- `high`: the label is clear.
- `medium`: an edge case that the tiebreaker settles.
- `low`: a reasonable annotator could pick a different label.

## Files

| file | contents |
|---|---|
| `data/corpus_grounded.csv` | Catalog questions written in student phrasing. All are academics with `in_corpus=yes`. |
| `data/seed_synthetic.csv` | Off-corpus housing, academics-policy and general questions, including edge cases and off-topic requests. |
| `data/labels_batch1.csv` | The two files above combined, with a `split` column. Built by `python -m router.build_batch1` from `backend/`. The split is stratified by label and source together: 20% of each group is `test`, seed 42. |
| `data/eval_set_check.csv` | The 30 retrieval eval questions, labeled academics. For sanity checks only. |

## Rules

- **Rows with `split=test` in `labels_batch1.csv` are frozen.** They are held
  out for the Week 6 comparison of a trained classifier against zero-shot
  routing. Never use them for training, prompt writing, few-shot examples,
  threshold tuning or model selection.
- **Never use `eval_set_check.csv` for training or tuning.** It exists only
  to check that the router sends catalog questions to academics.
- Put new labels in new batch files. Do not edit or reshuffle batch 1.

## Known limitations

- **in_corpus is almost perfectly correlated with source.** Every
  `corpus_grounded` row is `in_corpus=yes`, and every `synthetic` row is `no`
  or `unsure`. The two sets were also written in separate batches, so their
  phrasing differs. A classifier trained on this data may learn writing style
  rather than corpus coverage. Real user queries are needed to check this.
- **The test split is small (18 rows).** One row is about 5.6 points of
  accuracy, so a Week 6 difference of a few points between the classifier
  and zero-shot routing is noise.

`tests/test_router_data.py` checks both CSVs: no duplicate queries, valid
`label` and `in_corpus` values, a split on every batch-1 row, and no eval-set
question inside batch 1.
