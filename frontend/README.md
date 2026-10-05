# Ask Temoc — Web App

Next.js 15 / React 19 chat UI with Auth.js sign-in. For setup, see the
[root README](../README.md); for providers and secrets, see
[docs/AUTH_SETUP.md](../docs/AUTH_SETUP.md).

## Scripts

- `npm run dev`: development server on http://localhost:3000
- `npm run build` / `npm start`: production build and server
- `npm run lint`: ESLint

## How chat reaches the API

The browser only calls this app's own routes:

- `POST /api/chat` and `GET /api/health` (`src/app/api/*/route.ts`) require a
  signed-in session. They sign a 5-minute HS256 token for the user with
  `BACKEND_JWT_SECRET` (`src/lib/backend.ts`), call
  `${ASKTEMOC_API_ORIGIN}/api/chat`, and stream the SSE response back
  unbuffered.
- `/chat` is protected by `src/middleware.ts`. Signed-out visitors go to
  `/signin`.
- If the session has expired, `src/lib/api.ts` gets a 401 and sends the user to
  sign in again.

`ASKTEMOC_API_ORIGIN` defaults to `http://localhost:8000`. `.env.production`
(used by `next build`/`next start` and Vercel) points it at Cloud Run.

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
  auth.ts               Auth.js config: providers, domain policy, session shape
  middleware.ts         protects /chat
  app/
    page.tsx            landing page
    signin/             sign-in page
    chat/               chat page, sidebar, message area, citation rendering
    api/auth/           Auth.js handlers
    api/chat, api/health  authenticated proxy to the FastAPI backend
  components/           navbar (session-aware) and shadcn/ui primitives
  lib/
    api.ts              browser chat client + SSE parsing
    backend.ts          server-only: token minting and response relay
    auth-policy.ts      allowed-email rule (mirrors the API)
    citations.ts, markdown.ts
```

Conversations are held in React state only, so a reload clears them.

## Deploy on Vercel

Run `vercel link` / `vercel deploy` from the **repository root** with the
project's Root Directory set to `frontend`. For the required environment
variables, see "Deployment" in the root README.
