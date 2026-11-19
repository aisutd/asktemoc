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