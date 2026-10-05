# Ask Temoc

Ask Temoc is a chatbot that answers UT Dallas students' questions about degree
programs, grounded in the UTD undergraduate catalog. It's built by the UTD AI
Society.

## Architecture

```
browser ──► Next.js (frontend/) ──► FastAPI (backend/) ──► Chroma vector store
            Auth.js sign-in          RAG chain (LangChain)     seeded from data/catalog
            /api/chat route handler  OpenAI or Ollama          users table (SQLite/Postgres)
```

- **Sign-in.** The web app uses Auth.js. Only verified `@utdallas.edu` accounts get
  in, through Microsoft Entra ID (UTD's Microsoft 365) or Google.
- **The browser never calls the API directly.** It calls the Next server's own
  `/api/chat`. That route checks the session, signs a 5-minute token for the user
  with a secret shared with the API, and streams the API's response back.
- **The API** checks the token, records the user, retrieves catalog chunks from
  Chroma and streams an answer with its sources as server-sent events.
- **Models.** If `OPENAI_API_KEY` is set, the API uses OpenAI for chat and
  embeddings; otherwise it uses a local [Ollama](https://ollama.com).

```
frontend/   Next.js 15 chat UI + Auth.js
backend/    FastAPI app (app/), seed script (scripts/), tests, catalog scraper (scrapers/)
data/       committed scraped corpus: data/catalog/<program>/{requirements,example}.txt
docs/       AUTH_SETUP.md, KNOWN_ISSUES.md
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

This creates `backend/.venv`, installs backend and frontend dependencies, and
copies `backend/.env.example` to `backend/.env` and `frontend/.env.example` to
`frontend/.env.local`.

**2. Fill in the two env files.** Both are gitignored; never commit them.

| File | Set |
| --- | --- |
| `backend/.env` | `BACKEND_JWT_SECRET`; `OPENAI_API_KEY`, or leave it empty to use Ollama |
| `frontend/.env.local` | `AUTH_SECRET`, `BACKEND_JWT_SECRET` (same value as the backend), and one provider's credentials |

Generate the two secrets:

```bash
node -e "console.log(require('crypto').randomBytes(32).toString('base64url'))"   # AUTH_SECRET
python -c "import secrets; print(secrets.token_urlsafe(48))"                       # BACKEND_JWT_SECRET
```

To get provider credentials (Microsoft Entra ID or Google OAuth client), follow
[docs/AUTH_SETUP.md](docs/AUTH_SETUP.md).

If you're using Ollama instead of OpenAI, pull the two default models first:
`ollama pull llama3.1:8b && ollama pull nomic-embed-text`.

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

**5. Try it.** Open <http://localhost:3000>, sign in with your `@utdallas.edu`
account, and ask *"What are the core requirements for the BS in Computer
Science?"* The answer streams in with linked sources.

Non-UTD accounts are rejected at sign-in, and calling the API without a valid
token returns 401:

```bash
curl -i -X POST localhost:8000/api/chat -H 'content-type: application/json' -d '{"message":"hi"}'
```

### Running the API in Docker instead

```bash
docker compose up --build api
docker compose run --rm api python scripts/seed_catalog.py
```

The container reads `backend/.env`. Its vector store and database live in a
Docker volume. It reaches Ollama on your host by default; `docker-compose.yml`
shows how to use an Ollama container instead.

### Calling the API from scripts (no sign-in)

For retrieval or generation experiments, set `AUTH_DISABLED=true` in
`backend/.env`. Every request then acts as a fixed dev user, so this works:

```bash
curl -N -X POST localhost:8000/api/chat -H 'content-type: application/json' \
  -d '{"message":"core requirements for BS Computer Science"}'
```

The API refuses to start with `AUTH_DISABLED=true` unless `ENVIRONMENT=development`.

## Tests and CI

```bash
scripts/dev.sh test    # backend pytest, then frontend lint + build
```

The backend tests run offline: the RAG chain is faked, and nothing calls OpenAI,
Ollama or the network. On every pull request to `main`, GitHub Actions runs the
same checks (`.github/workflows/ci.yml`).

## Chat API

`POST /api/chat` with body `{"message": "..."}` and header
`Authorization: Bearer <token>` returns `text/event-stream`. Each event is one
line, `data: {json}`:

| `type` | Fields | Meaning |
| --- | --- | --- |
| `source` | `message` (`"Source n: <url>"`), `index`, `url`, `title?` | one retrieved chunk, sent before the answer |
| `text` | `message` | the next piece of the answer; append it |
| `done` | | end of stream |

Clients should ignore unknown types. `GET /api/health` (with or without the
trailing slash) is public.

## Deployment

The frontend deploys to Vercel and the API to Cloud Run. Both fail closed until
they're configured.

**Vercel** (Project → Settings → Environment Variables):
- `AUTH_SECRET`
- `BACKEND_JWT_SECRET`
- `AUTH_MICROSOFT_ENTRA_ID_ID`, `AUTH_MICROSOFT_ENTRA_ID_SECRET`, `AUTH_MICROSOFT_ENTRA_ID_ISSUER`
- optionally `AUTH_GOOGLE_ID` and `AUTH_GOOGLE_SECRET`
- optionally `ALLOWED_EMAIL_DOMAIN`

`ASKTEMOC_API_ORIGIN` is already committed in `vercel.json` and
`.env.production`. Hosts other than Vercel also need `AUTH_URL` (or
`AUTH_TRUST_HOST=true`).

**Cloud Run:**
- `ENVIRONMENT=production`
- `BACKEND_JWT_SECRET` (same value as Vercel)
- `OPENAI_API_KEY`
- `CORS_ORIGINS=https://<your Vercel domain>`
- `DATABASE_URL`, plus `CHROMA_PERSIST_DIRECTORY` on persistent storage, seeded
  with `scripts/seed_catalog.py`

Never set `AUTH_DISABLED` in production; the API won't start.

Run `vercel link` / `vercel deploy` from the repository root with the project's
Root Directory set to `frontend`.
