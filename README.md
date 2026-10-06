# Ask Temoc

Ask Temoc is a chatbot that answers UT Dallas students' questions about degree
programs, grounded in the UTD undergraduate catalog. It's built by the UTD AI
Society.

## Architecture

```
browser ──► Next.js (frontend/) ──► FastAPI (backend/) ──► Chroma vector store
            /api/proxy/* rewrite     RAG chain (LangChain)     seeded from data/catalog
                                     OpenAI or Ollama
```

- **The browser calls the web app's own `/api/proxy/*`.** Next.js forwards those
  requests to the API (`ASKTEMOC_API_ORIGIN`): `http://localhost:8000` under
  `npm run dev`, Cloud Run in production builds.
- **The API** retrieves catalog chunks from Chroma and streams an answer with its
  sources as server-sent events.
- **Models.** If `OPENAI_API_KEY` is set, the API uses OpenAI for chat and
  embeddings; otherwise it uses a local [Ollama](https://ollama.com).
- **No sign-in yet.** There's no app-level sign-in; it's planned for Weeks 2-4 of
  the 10-week plan. See [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md).

```
frontend/   Next.js 15 chat UI
backend/    FastAPI app (app/), seed script (scripts/), tests, catalog scraper (scrapers/)
data/       committed scraped corpus: data/catalog/<program>/{requirements,example}.txt
docs/       KNOWN_ISSUES.md
scripts/    dev.sh / dev.ps1 task runners
```

## Quickstart

You need **Python 3.11**, **Node 20+**, and Docker (optional). You also need
**either** an OpenAI API key with billing enabled **or** a local Ollama.

All commands below run from the repo root. They're written for macOS/Linux/Git
Bash; on Windows PowerShell, replace `scripts/dev.sh` with `.\scripts\dev.ps1`.

**1. Clone and install.**

```bash
git clone https://github.com/aisutd/asktemoc.git
cd asktemoc
scripts/dev.sh setup
```

This creates `backend/.venv` and installs backend and frontend dependencies. It
also copies `backend/.env.example` to `backend/.env` and `frontend/.env.example`
to `frontend/.env.local`. Both copies are gitignored; never commit them.

**2. Choose a model provider** in `backend/.env`. Either:
- set `OPENAI_API_KEY`, or
- leave it empty and pull the two default Ollama models:
  `ollama pull llama3.1:8b && ollama pull nomic-embed-text`.

Every other setting has a working default. The frontend needs no env vars for
local development.

**3. Seed the vector store** from the catalog files in `data/catalog/`:

```bash
scripts/dev.sh seed
```

This prints document and chunk counts (193 documents and 2047 chunks today).
Re-running is safe: it replaces the chunks rather than duplicating them. If you
switch between OpenAI and Ollama (or change the embedding model), run this
again; vectors from different models can't be mixed, and the API logs a warning
if they don't match.

**4. Start the API and the web app** in two terminals:

```bash
scripts/dev.sh api     # http://localhost:8000
scripts/dev.sh web     # http://localhost:3000
```

**5. Try it.** Open <http://localhost:3000>, click **Get Started**, and ask
*"What are the core requirements for the BS in Computer Science?"* The answer
streams in with linked sources.

You can also call the API directly, for example from scripts:

```bash
curl -N -X POST localhost:8000/api/chat -H 'content-type: application/json' \
  -d '{"message":"core requirements for BS Computer Science"}'
```

### Running the API in Docker instead

```bash
docker compose up --build api
docker compose run --rm api python scripts/seed_catalog.py
```

The container reads `backend/.env`. Its vector store and database live in a
Docker volume. It reaches Ollama on your host by default; `docker-compose.yml`
shows how to use an Ollama container instead.

## Tests and CI

```bash
scripts/dev.sh test    # backend pytest, then frontend lint + build
```

The backend tests run offline: the RAG chain is faked, and nothing calls OpenAI,
Ollama or the network. On every pull request to `main`, GitHub Actions runs the
same checks (`.github/workflows/ci.yml`).

## Chat API

`POST /api/chat` with body `{"message": "..."}` returns `text/event-stream`.
Each event is one line, `data: {json}`:

| `type` | Fields | Meaning |
| --- | --- | --- |
| `source` | `message` (`"Source n: <url>"`), `index`, `url`, `title?` | one retrieved chunk, sent before the answer |
| `text` | `message` | the next piece of the answer; append it |
| `done` | | end of stream |

Clients should ignore unknown types. `GET /api/health` works with or without the
trailing slash.

## Deployment

The frontend deploys to Vercel and the API to Cloud Run.

**Vercel:** `ASKTEMOC_API_ORIGIN` is already committed in `vercel.json` and
`frontend/.env.production`, so no extra variables are needed. Until app-level
sign-in exists, visitors are gated by Vercel Deployment Protection (Project →
Deployment Protection → Vercel Authentication). Run `vercel link` /
`vercel deploy` from the repository root with the project's Root Directory set
to `frontend`.

**Cloud Run:**
- `ENVIRONMENT=production`
- `OPENAI_API_KEY`
- `CORS_ORIGINS=https://<your Vercel domain>`
- `DATABASE_URL`, plus `CHROMA_PERSIST_DIRECTORY` on persistent storage, seeded
  with `scripts/seed_catalog.py`

The API has no authentication, so anyone who knows its URL can use it. See
[docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md).
