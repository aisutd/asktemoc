# Ask Temoc API

FastAPI service behind the Ask Temoc web app: a LangChain RAG chain over a
Chroma collection seeded from `data/catalog/`, streamed as server-sent events.
For setup, see the [root README](../README.md).

## Layout

```
app/
  main.py                    app, CORS, routers
  core/config.py             all settings (env + backend/.env), see .env.example
  core/auth.py               bearer-token verification, get_current_user
  api/endpoints/rag_endpoint.py   POST /api/chat (SSE)
  api/endpoints/health.py         GET /api/health
  services/rag_chain_service.py   the RAG chain (built lazily)
  services/retriever_service.py   Chroma retriever + shared embeddings factory
  db/                        SQLAlchemy models (incl. users) and services
scripts/seed_catalog.py      load data/catalog into Chroma (idempotent)
scrapers/catalog/            Playwright catalog scraper + sources.json builder
tests/                       pytest suite (offline)
```

## Requirements files

| File | For |
| --- | --- |
| `requirements.txt` | running the API and the seed script (the Dockerfile uses it) |
| `requirements-dev.txt` | the above plus pytest |
| `requirements-scrape.txt` | scrapers and the Crawl4AI/docling ingestion experiments |

## Common commands (from `backend/`, venv active)

```bash
python scripts/seed_catalog.py              # seed / re-seed the vector store
uvicorn app.main:app --reload --port 8000   # run the API
python -m pytest                            # tests
```
