# Ask Temoc — Web App

Next.js (App Router) chat UI for Ask Temoc, an AI assistant that answers questions
about UTD using the university catalog. Built with React 19, Tailwind CSS v4 and
shadcn/ui components.

## Getting Started

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). No environment variables are
needed — the app proxies to the deployed chat API by default (see
[Chat API](#chat-api)).

### Scripts

| Script | Purpose |
| --- | --- |
| `npm run dev` | Dev server with Turbopack |
| `npm run build` | Production build |
| `npm start` | Serve a production build (run `build` first) |
| `npm run lint` | ESLint |

## Chat API

The chat API is **not** in this repository — it lives in
[AskTemoc_Backend](https://github.com/davis118/AskTemoc_Backend), a FastAPI service
(pgvector RAG over the scraped catalog, streaming OpenAI completions) deployed to
Cloud Run. It serves `POST /api/chat` and `GET /api/health/`.

`next.config.ts` rewrites proxy to it so the browser only ever calls same-origin
paths:

```
/api/proxy/health    → $ASKTEMOC_API_ORIGIN/api/health/
/api/proxy/:path*    → $ASKTEMOC_API_ORIGIN/api/:path*
```

These rewrites are served by `next dev` too, which is why local development works
without running an API process.

### Environment variables

| Variable | When | Purpose |
| --- | --- | --- |
| `ASKTEMOC_API_ORIGIN` | build time | Cloud Run origin the rewrites point at. Defaults to the deployed URL; also set in `vercel.json` and `.env.production`. |
| `NEXT_PUBLIC_API_BASE_URL` | runtime, optional | Overrides the API base. Set to `http://localhost:8000` if you run the API yourself. Ignored in production when it points at localhost, so a stray value can't make deployments call a developer's machine. |

See `.env.example` for details.

### Running against a local API

Start AskTemoc_Backend on port 8000 (`uvicorn app.main:app --reload`), allow this
origin in its `CORS_ORIGINS`, then point the app at it:

```bash
echo 'NEXT_PUBLIC_API_BASE_URL=http://localhost:8000' > .env.local
```

### Response format

`POST /api/chat` with `{ "message": string }` returns server-sent events. Three
chunk types arrive, each as `data: {…}`:

- `text` — `delta` holds the new fragment and `message` the full text so far, so the
  UI just replaces its text with the latest `message`.
- `source` — a cited page, carrying `index`, `title`, and the URL both in a
  `source` field and inline in `message` as `Source 1: https://…`. The client reads
  the URL out of `message`, since it looks for `url`/`href` rather than `source`.
- `done` — end of stream.

Assistant text embeds citations as `[n, "exact quoted text"]`, which
`src/lib/citations.ts` turns into linked pills whose tooltip shows the quote.

## Source Layout

```
src/
  app/
    page.tsx            landing page
    layout.tsx          root layout (Geist fonts via next/font, navbar)
    chat/               chat route: page, sidebar, message area, citation rendering
  components/ui/        shadcn/ui primitives
  lib/
    api.ts              chat API client + SSE parsing
    citations.ts        [n, "…"] citation parsing and source resolution
    markdown.ts         inline markdown (**bold**, *italic*, `code`)
  types/                shared Message/Conversation types
```

Conversations are held in React state only — there is no persistence, so a reload
clears them.

## Deploy on Vercel

Run `vercel link` / `vercel deploy` from the **repository root**, not from
`frontend/`, with the project's Root Directory set to `frontend`. Running from
`frontend/` makes Vercel look for `frontend/frontend`.

To require a login before the app loads, enable Vercel Authentication under
Project → Deployment Protection.
