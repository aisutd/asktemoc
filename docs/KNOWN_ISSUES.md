# Known issues

These were noticed while building the runnable baseline and deliberately left
for the 10-week plan, because they don't block cloning, signing in and getting
an answer. They're grouped by area and roughly by priority within each group.

## Security

- **Admin routes are unauthenticated.** Anyone who can reach the API can create,
  modify or delete records and vectors through `/api/documents/*`,
  `/api/chroma/*` (including `DELETE /api/chroma/vectors`) and
  `/api/dashboard/*`. Only `POST /api/chat` requires a token. Before the API is
  exposed beyond the team, put these behind `get_current_user` plus an
  admin/role check, or remove them.
- **`POST /api/query/` is a placeholder.** It ignores the question, asks a
  hard-coded Ollama model for the capital of a random country, and is
  unauthenticated.
- **The deployed Cloud Run API is open.** The currently deployed API predates
  this branch and accepts unauthenticated chat until it's redeployed from here.
- **No rate limiting or quotas** on `/api/chat`. Any signed-in user can drive
  unbounded OpenAI spend.
- **One user row per email.** Users are matched by `provider_sub`, then by
  email. If someone's email changes to an address another row already holds,
  the upsert hits the unique constraint and the request fails with a 500.

## Backend divergence

- **Production may run AskTemoc_Backend's `speedrun` branch, not `main`.**
  `speedrun` is 12 commits ahead of `main`. It has a citation prompt producing
  `[n, "verbatim quote"]`, a lower temperature, and a different SSE shape
  (`delta` plus cumulative `message`, and `error` events). This repo imported
  `main`. The web app accepts both SSE shapes, but the `[n, "…"]` citation pills
  in `src/lib/citations.ts` only appear with the `speedrun` prompt; with
  `main`'s prompt, answers cite sources in prose. Decide what to port.
- Other unmerged AskTemoc_Backend branches: `citations-test`,
  `feat/update_scrapers` (scraper reorganisation and change detection),
  `db_sync` (Streamlit dashboard), `VectorService`.

## Retrieval and data

- **Repeated sources.** The retriever returns 4 chunks, often from the same
  program page, so the UI can list the same URL several times.
- **Corpus noise.** The scraped text includes page chrome ("Download page as a
  PDF", "Compare Versions"). Folders `data/catalog/1`, `2`, `3` are artefacts of
  footnote links and have no catalog page, so they cite the programs index.
  The catalog year (2025) is hard-coded in the scraper and seed script.
- **Ambiguous URLs.** `bachelor_of_science_in_computational_and_geospatial_science`
  and `bachelor_of_science_in_data_science` are each linked twice from the
  catalog index; `sources.json` keeps the first link.
- **Housing isn't seeded.** `data/housing/` (from the backend repo's housing
  scraper) isn't seeded.
- **Embedding/model mismatch only warns.** If the collection was seeded with a
  different provider or model, the API logs a warning but still serves
  (wrong) results. `seed_catalog.py` rebuilds the collection when it detects
  the mismatch.
- **Chroma is a local directory.** That's fine for one dev machine or one
  container with a volume, but Cloud Run's filesystem is ephemeral. Production
  needs persistent storage or the planned pgvector migration.
- **The SQLite Document/Chunk/Embedding tables aren't the retrieval store.**
  The seed script writes straight to Chroma, so these tables (and the
  `/api/documents` and `/api/chroma` export flow) are unused by chat.

## Backend code

- `DataIngestionService` (`app/services/data_ingestion_service.py`) is
  superseded by `scripts/seed_catalog.py`. It only reads `requirements.txt`,
  adds duplicates on re-run, and uses folder names as sources.
- `general_webscraper.py`, `html_processing_pipeline.py`, `housing_scraper.py`
  and `scraper_service.py` import Crawl4AI, docling or Playwright. They only
  work with `requirements-scrape.txt` installed, and nothing in the API imports
  them. `embedding_service.py` defines a separate FastAPI app using
  HuggingFace embeddings and is unused.
- **No migrations.** Tables are created with `Base.metadata.create_all`, so
  later column changes won't apply to existing databases (add Alembic before
  the Postgres move). The Postgres driver isn't in `requirements.txt`.
- **Deprecations:** `@app.on_event("startup")` (use lifespan),
  `datetime.utcnow`, Pydantic v1-style `class Config` and `min_items` in
  `app/schemas/db_schemas.py`. These show as warnings in pytest.
- **Errors look like answers.** A failure mid-stream is reported as a `text`
  event, "Error processing request", followed by `done`, so the UI shows it as
  answer text. A dedicated `error` event would be clearer.
- **The Docker image** runs as root and keeps `build-essential`.

## Frontend

- **`next-auth` is pinned to `5.0.0-beta.32`.** Auth.js v5 is still published
  only as a beta; upgrade deliberately.
- **npm 11 skips install scripts** for `sharp`, `@tailwindcss/oxide` and
  `unrs-resolver` (the "allow-scripts" warnings). Lint and build pass without
  them; run `npm approve-scripts` if image optimisation misbehaves.
- **`next start` locally talks to production.** It loads
  `frontend/.env.production`, which points `ASKTEMOC_API_ORIGIN` at Cloud Run.
  Set `ASKTEMOC_API_ORIGIN=http://localhost:8000` to test a production build
  against a local API. `npm run dev` is unaffected.
- **Conversations aren't saved.** They live in React state, with three
  hard-coded sample conversations, and a reload clears them. (Persistence is
  part of the 10-week plan.)
- **The landing page's "Learn More" button links to `/`.**
- **An unused profile photo.** The Entra provider fetches the profile photo
  from Microsoft Graph on every sign-in, but nothing displays it.
- **Vercel Deployment Protection is redundant.** If it's still enabled on the
  project, it adds a second login in front of the app's own sign-in. Decide
  whether to keep it.

## Repo hygiene

- **Stale backend docs.** `backend/IMPLEMENTATION_STATUS.md`,
  `IMPLEMENTATION_SUMMARY.md`, `CHANGES.md`, `QUICK_START.md` and
  `DATABASE_API_DOCS.md` describe the old standalone backend and were left
  unchanged on purpose.
- **Retire the old repo.** `davis118/AskTemoc_Backend` should be archived or
  pointed here once this branch merges, so work doesn't split again.
