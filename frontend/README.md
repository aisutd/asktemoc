# Ask Temoc — Web App

Next.js 15 / React 19 chat UI. For setup, see the [root README](../README.md).

## Scripts

- `npm run dev`: development server on http://localhost:3000
- `npm run build` / `npm start`: production build and server
- `npm run lint`: ESLint

## How chat reaches the API

The browser calls same-origin `/api/proxy/chat` and `/api/proxy/health`.
`next.config.ts` rewrites those to `ASKTEMOC_API_ORIGIN`:

- `npm run dev`: `http://localhost:8000` by default (the local API).
- Production builds and Vercel: the Cloud Run origin, set in `.env.production`
  and `vercel.json`.

`NEXT_PUBLIC_API_BASE_URL` makes the browser call an API origin directly instead
of going through the proxy. That needs CORS on the API; never point it at
localhost in production.

There's no app-level sign-in yet; it's planned for Weeks 2-4 of the 10-week plan.
In production, Vercel Deployment Protection gates visitors.

## Response format

SSE events, one `data: {json}` per line:

- `source`: `message` is `Source n: <url>`, plus `index`, `url` and optionally
  `title`.
- `text`: the next piece of the answer. It's appended; when an event also has a
  `delta` field (older API builds), the `delta` is appended instead.
- `done`: end of stream. Unknown types are ignored.

Assistant text may embed citations as `[n, "exact quoted text"]`, which
`src/lib/citations.ts` turns into linked pills.

## Source layout

```
src/
  app/
    page.tsx            landing page
    layout.tsx          root layout (Geist fonts via next/font, navbar)
    chat/               chat page, sidebar, message area, citation rendering
  components/           navbar and shadcn/ui primitives
  lib/
    api.ts              chat API client + SSE parsing
    citations.ts        [n, "…"] citation parsing and source resolution
    markdown.ts         inline markdown (**bold**, *italic*, `code`)
  types/                shared Message/Conversation types
```

Conversations are held in React state only, so a reload clears them.

## Deploy on Vercel

Run `vercel link` / `vercel deploy` from the **repository root**, not from
`frontend/`, with the project's Root Directory set to `frontend`. To require a
login before the app loads, enable Vercel Authentication under Project →
Deployment Protection.
