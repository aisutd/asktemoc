# AskTemoc Backend

FastAPI service for Ask Temoc (pgvector RAG over the UTD catalog, streaming
`POST /api/chat`). This directory is the full backend imported from
[AskTemoc_Backend](https://github.com/davis118/AskTemoc_Backend). The previous
contents of `asktemoc/backend` were catalog-scraper scripts only.

The web app in `../frontend` talks to:

- `POST /api/chat` — SSE stream (`source`, `text`, `done` / `error`)
- `GET /api/health/` — liveness

Copy `.env.example` to `.env` and set at least `DATABASE_URL` (Neon Postgres)
and `OPENAI_API_KEY`. For the API only, `pip install -r requirements-deploy.txt`
is enough; `requirements.txt` is the full scrape/dev freeze.

---

### Requirements

- Python 3.13+
- [`ollama`](https://ollama.com/) installed and running (optional local LLM; OpenAI is the default)
- `pip` (Python package installer)
- Git

---

### Setup

From this directory:

```bash
python3.13 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements-deploy.txt
cp .env.example .env      # then fill in DATABASE_URL and OPENAI_API_KEY
```

Ollama is optional (`LLM_PROVIDER=ollama`). The default is OpenAI.

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