# AskTemoc Backend

This directory contains:
FastAPI service for AskTemoc (pgvector RAG over the UTD catalog, streaming `POST /api/chat`), entry point at main.py, deploy files in /deploy.
Scripts to scrape UTD website data, and add it to the Neon database.

The web app in `../frontend` talks to:

- `POST /api/chat` — SSE stream (`source`, `text`, `done` / `error`)
- `GET /api/health/` — liveness

We also have endpoints for a potential admin dashboard to view scraped documents. 

- `GET /api/dashboard/overview` — document list plus corpus totals
- `GET /api/dashboard/document/{id}/stats` — chunk and embedding counts for one document
- `GET /api/dashboard/document/{id}/export` — document, chunks, and embedding metadata
- `GET /api/dashboard/search?query=` — substring search over chunk text, titles, and sources
- `GET /api/dashboard/activity` — recently updated documents, chunks, and embeddings
- `POST /api/dashboard/document/{id}/duplicate` — copy a document with its chunks and embeddings
- `POST /api/dashboard/documents/batch-delete` — soft-delete documents (`hard_delete=true` removes them)

---

### Requirements

- Python 3.13+
- [`ollama`](https://ollama.com/) installed and running or OPENAI_API_KEY.
- `pip` (Python package installer)
- Git

---

### Setup

Copy `.env.example` to `.env` and set at least `DATABASE_URL` (Neon URL, ask [davis118](https://github.com/davis118)).

From this directory:

```bash
python3.13 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r deploy/requirements-deploy.txt
cp .env.example .env      # then fill in DATABASE_URL and OPENAI_API_KEY
```
---

### Run the FastAPI Server

```bash
uvicorn app.main:app --reload
```

- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- Chat (what the frontend uses): `POST /api/chat` with `{"message": "..."}`
- Legacy non-streaming query: `POST /api/query/` with `{"query": "..."}`
---


### Webscraper Setup
If you haven’t already installed the **Crawl4AI** library (it should be listed in `requirements.txt`), run:

```bash
pip install crawl4ai
```

After installing dependencies, run:

```bash
crawl4ai-setup
```

Then verify the installation with:

```bash
crawl4ai-doctor
```

---

### Scheduled re-scrape

`app/services/scrapers/rescrape.py` re-fetches the UTD catalog (every program page and its example plan, plus the catalog overview) and the three web pages (UTD home, academics, tuition rates), finds the pages whose content changed, and re-embeds only those.

```bash
python -m app.services.scrapers.rescrape --dry-run   # fetch and compare, write nothing
python -m app.services.scrapers.rescrape             # apply changes (applies pending migrations first)
python -m app.services.scrapers.rescrape --status    # summary of the last run
```

Other flags: `--limit N` (first N programs), `--only TEXT` (pages whose key contains TEXT), `--force` (skip the guards below). Run it from this directory with `DATABASE_URL` and `OPENAI_API_KEY` set. It needs Playwright's Chromium and Crawl4AI installed (see Webscraper Setup).

Keeping git in step with Neon: the re-scrape writes straight to the database, so by default git does not see the new page text. Add `--save-dir app/services/data` (and `--save-web-dir ../crawl4ai_output` for the web pages) and the run also writes the pages it fetched to those folders, in the layout `corpus_prep.py` reads, then commit the changes. Only pages that already match Neon are written (after `--dry-run`, only the unchanged ones), and a file is only rewritten when its content differs. A Cloud Run Job's disk is ephemeral, so the scheduled job cannot update git by itself; run it with `--save-dir` from a machine or CI job that can commit after a refresh. `--status` shows when the last run happened and what changed, so anyone can tell when Neon last moved.

How it decides a page changed:

- A page is only used if it came back HTTP 200 with at least 30 words. Anything else is logged as `failed` and the stored document is left alone. A document is soft-deleted only after three consecutive 404/410 responses; timeouts and 5xx errors never delete anything.
- Combined certificate pages (and certificate pages that are copies of a degree page) are cut to the one certificate section, so each certificate gets its own document. Certificates have no example-plan document.
- The hash is sha256 over normalized text: Unicode NFKC, collapsed whitespace, and the catalog's `Updated: ...` stamp removed. Crawl4AI pages are stripped of navigation and footer first.
- The hash is compared with `doc_metadata.content_hash` on the stored document. An unchanged page is not re-embedded. A page whose content matches a different document is logged as `duplicate` and not stored.
- A changed page is chunked (512 tokens, 64 overlap), embedded, and swapped in one transaction together with its `scrape_log` row. If embedding fails the old document stays.

Where the log lives: the `scrape_log` table in Postgres (`app/migrations/003_scrape_log.sql`), one row per page per run with the outcome (`new`, `changed`, `unchanged`, `failed`, `duplicate`, `removed`), hash, HTTP status and word count. Documents are identified by `sha256("<program>/<requirements|example>.txt")[:32]`, the same ids the existing Neon documents were created with, so a re-scrape updates them instead of adding copies. Unchanged documents whose `source` is still a local file path get the real page URL on the first run.

Two guards stop a run before it writes anything (exit code 2, and a `failed` row with key `__run__`): more than 30% of the existing pages changed, or more than 30% of all pages failed. The first run after a long gap can legitimately trip the first guard; check `--dry-run` output, then use `--force`.

Schedule: weekly, Sundays 02:00 America/Chicago, as a Cloud Run Job triggered by Cloud Scheduler (`bash deploy/deploy_rescrape_job.sh`; needs the Secret Manager and service account variables listed at the top of the script). The API image does not include a browser, so the job has its own image (`deploy/Dockerfile.rescrape`). The deploy files have not been run against a real project.

`scheduler.py` and `scraper_state.py` (APScheduler plus a local JSON hash file) are an older design. The scheduler is not started by `app/main.py`, and publishing through `catalog_scraper.py` creates documents keyed by URL that would duplicate the ones above, so do not run both.

---

### Update Google Cloud

From this directory, with the [gcloud CLI](https://cloud.google.com/sdk/docs/install) logged in and a project selected:

```bash
export GCP_PROJECT=your-project-id   # or: gcloud config set project your-project-id
export GCP_REGION=us-central1        # optional; this is the default
bash deploy/deploy_cloud_run.sh
```

The script submits a Cloud Build of this directory, pushes `backend:latest` to Artifact Registry repo `asktemoc-api`, and deploys Cloud Run service `asktemoc-api` (port 8080, 1 GiB, unauthenticated). The frontend calls that service at `https://asktemoc-api-422855032073.us-central1.run.app`.

`gcloud run deploy` in the script uses `--set-env-vars`, which replaces the service's environment variables with `LLM_PROVIDER=openai`. After a deploy, confirm these are set again on the service (Cloud Run → `asktemoc-api` → Edit & deploy → Variables & secrets):

- `DATABASE_URL` — Neon Postgres
- `OPENAI_API_KEY`
- `CORS_ORIGINS` — the deployed frontend origin, for example `https://your-app.vercel.app`