# Unified `/api/chat` + Auth + Chat Persistence — Design

Week 1 deliverable (Davis). Covers three decisions:

1. The target request/response contract for a single unified `POST /api/chat`.
2. Auth: NextAuth.js (Auth.js v5) + Google OAuth, restricted to `@utdallas.edu`.
3. The `users` / `conversations` / `messages` schema, living in the same Neon
   instance as `documents` / `chunks` / `embeddings`.

---

## 1. Where the API is today

Seven routers are mounted in `app/main.py`. Two of them answer questions, and they
disagree with each other:

| Route | File | Shape | Verdict |
| --- | --- | --- | --- |
| `POST /api/query/` | `endpoints/query.py` | `{query}` → `{answer}`, blocking, no citations | **Deprecate.** Superseded by `/api/chat?stream=false`. |
| `POST /api/chat` | `endpoints/rag_endpoint.py` | `{message}` → SSE `source`/`text`/`done`/`error` | **Keep and extend.** This is the unified endpoint. |
| `POST /api/ingest` | `endpoints/ingest.py` | scraper payload → documents/chunks/embeddings | Keep, move behind an admin guard. |
| `/api/documents/*` | `endpoints/documents.py` | CRUD over the corpus | Keep, admin-only. Never reachable from the browser. |
| `/api/dashboard/*` | `endpoints/dashboard.py` | corpus analytics | Keep, admin-only. |
| `/api/chroma/*` | `endpoints/chroma.py` | Chroma export/sync | **Dead.** pgvector is the source of truth; retrieval in `rag_chain_service` never touches Chroma. Delete after Week 2. |
| `GET /api/health/` | `endpoints/health.py` | liveness | Keep. Add a DB-ping readiness probe. |

"Unified" therefore means: fold `/api/query` into `/api/chat`, add identity, add
conversation persistence, and keep exactly one answer-shaped contract that the
Next.js frontend codes against.

### What the existing `/api/chat` is missing

- No identity — anyone who can reach the host can burn OpenAI credits.
- No `conversation_id`, so every turn is stateless and nothing is stored.
- No way to get a plain JSON answer (the only non-streaming path is `/api/query`,
  which throws away citations).
- `text` events resend the full `message` on every token, so a 2 KB answer ships
  roughly O(n²) bytes. There is already a `TODO: only send delta` in the router.
- Errors are a single opaque `"Error processing request"` string with no code.

---

## 2. Target contract for `POST /api/chat`

### 2.1 Request

```http
POST /api/chat
Authorization: Bearer <backend JWT minted by Next.js>
Content-Type: application/json
Accept: text/event-stream          # or application/json when stream=false
```

```jsonc
{
  "message": "How many credit hours does the BS in Computer Science require?",
  "conversation_id": "0f8c…",       // null/omitted → server creates a new conversation
  "client_message_id": "7b2a…",     // client-generated UUID, idempotency key
  "stream": true,                   // false → single JSON response
  "options": {
    "top_k": 5,                     // 1..10, default 5
    "include_sources": true
  }
}
```

```python
class ChatOptions(BaseModel):
    top_k: int = Field(5, ge=1, le=10)
    include_sources: bool = True


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: UUID | None = None
    client_message_id: UUID | None = None
    stream: bool = True
    options: ChatOptions = ChatOptions()
```

Notes on the field choices:

- `message` keeps its current name, so the frontend's existing call site still works.
- `client_message_id` is what makes retries safe. React Strict Mode double-invokes
  effects in dev, and users double-click Send. If a message with the same
  `(conversation_id, client_message_id)` already exists, the server replays the stored
  answer instead of paying OpenAI twice.
- `model` is deliberately **not** client-settable. It is pinned server-side from
  `Settings.OPENAI_MODEL`, otherwise the request body becomes a way for a browser to
  pick an expensive model.
- `top_k` is capped at 10 so a client can't blow up the prompt.

### 2.2 Streaming response (`stream: true`)

`text/event-stream`, one JSON object per `data:` line, same as today. Two changes:
a new `meta` event first, and richer `done` / `error` payloads. Clients that ignore
unknown `type` values stay compatible.

```
data: {"type":"meta","conversation_id":"0f8c…","user_message_id":"41d…","assistant_message_id":"9ac…","model":"gpt-4o-mini","created_at":"2026-10-07T21:14:03Z"}

data: {"type":"source","index":1,"source":"https://catalog.utdallas.edu/…/computer-science","title":"BS in Computer Science","document_id":"a12…","chunk_id":"c77…","score":0.87,"message":"Source 1: https://catalog.utdallas.edu/…"}

data: {"type":"text","delta":"The BS in Computer Science requires 124 ","message":"The BS in Computer Science requires 124 "}

data: {"type":"done","message":"…full answer…","citations":[{"source_index":1,"quote":"The program requires a minimum of 124 semester credit hours.","url":"https://catalog.utdallas.edu/…","title":"BS in Computer Science"}],"conversation_id":"0f8c…","assistant_message_id":"9ac…","usage":{"prompt_tokens":3120,"completion_tokens":88,"latency_ms":2410},"finish_reason":"stop"}
```

| Event | Count | Payload |
| --- | --- | --- |
| `meta` | exactly 1, first | `conversation_id`, `user_message_id`, `assistant_message_id`, `model`, `created_at` |
| `source` | 0–`top_k`, before any `text` | `index` (1-based, matches `Source n` in the prompt), `source` (URL), `title`, `document_id`, `chunk_id`, `score` |
| `text` | 0–N | `delta` (the new tokens), `message` (cumulative — **deprecated**, see below) |
| `done` | 0 or 1, terminal | `message`, `citations[]`, `conversation_id`, `assistant_message_id`, `usage`, `finish_reason` |
| `error` | 0 or 1, terminal | `code`, `message`, `retryable`, plus the two IDs when the row already exists |

The stream always ends in exactly one `done` or one `error`.

`message` on `text` events stays for one release so the frontend can migrate, then
gets dropped; the client accumulates `delta` itself. Call this out in the frontend PR
because it is the one breaking change in the protocol.

### 2.3 Non-streaming response (`stream: false`)

```json
{
  "conversation_id": "0f8c…",
  "user_message_id": "41d…",
  "message": {
    "id": "9ac…",
    "role": "assistant",
    "content": "The BS in Computer Science requires 124 semester credit hours [1, \"…\"].",
    "created_at": "2026-10-07T21:14:06Z"
  },
  "sources": [{ "index": 1, "url": "…", "title": "…", "document_id": "…", "chunk_id": "…", "score": 0.87 }],
  "citations": [{ "source_index": 1, "quote": "…", "url": "…", "title": "…" }],
  "usage": { "prompt_tokens": 3120, "completion_tokens": 88, "latency_ms": 2410 },
  "finish_reason": "stop"
}
```

Same information as the terminal `done` event plus the `sources` array, so server-side
rendering, tests, and `curl` all have a path that doesn't require an SSE parser.

### 2.4 Errors

Failures *before* the stream opens are ordinary HTTP errors with a JSON body
`{"code": "...", "message": "...", "retryable": bool}`:

| Status | `code` | When |
| --- | --- | --- |
| 401 | `unauthorized` | missing / expired / unverifiable JWT |
| 403 | `forbidden_domain` | token's email isn't `@utdallas.edu` |
| 403 | `forbidden_conversation` | `conversation_id` belongs to another user |
| 404 | `conversation_not_found` | unknown or soft-deleted conversation |
| 422 | `invalid_request` | Pydantic validation |
| 429 | `rate_limited` | per-user quota; include `Retry-After` |
| 503 | `database_unavailable` | Neon cold start / pool exhaustion |

Failures *after* 200 and the first byte must be `error` events, because the status line
is already on the wire: `retrieval_failed`, `llm_failed`, `llm_timeout`, `internal`.
Codes are stable strings — the frontend switches on `code`, never on prose.

### 2.5 Companion endpoints (new `conversations` router)

All of these are scoped to the caller's `user_id`; a conversation belonging to someone
else is a 404, not a 403, so IDs can't be enumerated.

| Route | Purpose |
| --- | --- |
| `GET /api/conversations?limit=20&cursor=<ts>` | sidebar list, keyset-paginated by `last_message_at` |
| `GET /api/conversations/{id}?limit=50&before_seq=<n>` | one conversation with its messages |
| `PATCH /api/conversations/{id}` | rename (`{"title": "…"}`) or `{"is_archived": true}` |
| `DELETE /api/conversations/{id}` | soft delete (sets `deleted_at`) |
| `POST /api/conversations/{id}/messages/{message_id}/feedback` | thumbs up/down, free-text; feeds retrieval evaluation |

---

## 3. Auth decision: NextAuth.js v5 + Google, restricted to `@utdallas.edu`

**Decision: approved.** Google provider only, `openid email profile` scopes, JWT
session strategy, Auth.js tables persisted in the same Neon database via the Drizzle
adapter. No password auth, no email magic links, no second identity provider.

Rationale: every UTD student already has a Google-backed `@utdallas.edu` account, so
there is nothing to register and no passwords to store. The domain check gives us the
"UTD students only" property almost for free.

### 3.1 How Google OAuth actually works under NextAuth

The flow is OAuth 2.0 Authorization Code + PKCE, with OpenID Connect layered on top.
NextAuth implements all of it behind one catch-all route, `app/api/auth/[...nextauth]/route.ts`,
which serves `/api/auth/signin`, `/api/auth/callback/google`, `/api/auth/session`, and
`/api/auth/signout`.

1. **Kickoff.** The browser calls `signIn("google")`. That POSTs to
   `/api/auth/signin/google` with a CSRF token from the `authjs.csrf-token` cookie.
   NextAuth generates a random `state`, a `nonce`, and a PKCE `code_verifier`, stores
   them in short-lived cookies, and 302s the browser to
   `https://accounts.google.com/o/oauth2/v2/auth` with `client_id`,
   `redirect_uri=https://asktemoc.…/api/auth/callback/google`,
   `response_type=code`, `scope=openid email profile`, `state`, `nonce`, and
   `code_challenge` (the SHA-256 of the verifier).

2. **Google authenticates the user.** This happens entirely on Google's domain. We
   never see a password. Because we pass `hd=utdallas.edu` as an authorization param,
   the account chooser is filtered to UTD Workspace accounts.

3. **Redirect back with a code.** Google sends the browser to our callback with
   `?code=…&state=…`. NextAuth compares `state` against the cookie (CSRF defense) and
   discards the request if it doesn't match.

4. **Token exchange, server-to-server.** NextAuth POSTs the `code`, the
   `code_verifier`, `client_id`, and `client_secret` to
   `https://oauth2.googleapis.com/token`. The authorization code never grants anything
   on its own — it has to be redeemed with the secret, from our server, which is why a
   leaked redirect URL isn't a session. Google returns an `access_token`, a
   `refresh_token` (only when `access_type=offline` is requested), and an `id_token`.

5. **ID token verification.** The `id_token` is a JWT signed by Google. NextAuth fetches
   Google's JWKS, verifies the RS256 signature, then checks `iss` is
   `https://accounts.google.com`, `aud` equals our `client_id`, `exp` is in the future,
   and `nonce` matches the cookie. Its claims are the user's identity: `sub` (Google's
   stable user ID), `email`, `email_verified`, `name`, `picture`, and `hd` (the hosted
   Workspace domain).

6. **Our authorization gate.** The `signIn` callback runs with those claims and is
   where the `@utdallas.edu` restriction is enforced. Returning `false` aborts the
   sign-in and no session is created.

7. **Session issuance.** The adapter upserts `users` and `accounts` rows. Then NextAuth
   sets `__Secure-authjs.session-token` — `HttpOnly`, `Secure`, `SameSite=Lax`. With
   the JWT strategy that cookie is a **JWE**: encrypted, not merely signed, so the
   browser cannot read its contents, and it is validated with `AUTH_SECRET` on every
   request without a database round trip.

The critical point about the domain restriction:

> **`hd=utdallas.edu` is a UI hint, not a security control.** It filters Google's
> account picker. An attacker crafting their own authorization URL can drop it, sign in
> with `attacker@gmail.com`, and land on our callback with a perfectly valid `id_token`.
> The *only* thing keeping non-UTD users out is our own server-side check on the
> verified claims.

```ts
// auth.ts
import NextAuth from "next-auth";
import Google from "next-auth/providers/google";
import { DrizzleAdapter } from "@auth/drizzle-adapter";
import { db } from "@/db";

const ALLOWED_DOMAIN = "utdallas.edu";

export const { handlers, auth, signIn, signOut } = NextAuth({
  adapter: DrizzleAdapter(db),
  session: { strategy: "jwt", maxAge: 60 * 60 * 24 * 7 },
  providers: [
    Google({
      clientId: process.env.AUTH_GOOGLE_ID!,
      clientSecret: process.env.AUTH_GOOGLE_SECRET!,
      authorization: {
        params: { hd: ALLOWED_DOMAIN, prompt: "select_account", scope: "openid email profile" },
      },
    }),
  ],
  callbacks: {
    async signIn({ profile }) {
      // Enforced on claims from a signature-verified id_token, not on the hd hint.
      const email = profile?.email?.toLowerCase();
      if (!email || profile?.email_verified !== true) return false;
      if (profile?.hd !== ALLOWED_DOMAIN) return false;
      return email.endsWith(`@${ALLOWED_DOMAIN}`);
    },
    async jwt({ token, user }) {
      if (user) token.uid = user.id;
      return token;
    },
    async session({ session, token }) {
      if (session.user) session.user.id = token.uid as string;
      return session;
    },
  },
});
```

Both `hd` and the `endsWith` check are there on purpose: `hd` proves the account is
governed by the UTD Workspace tenant, and the suffix check blocks a subdomain
look-alike like `student.utdallas.edu.evil.com`. Compare lowercased, since Google's
`email` casing is not guaranteed.

### 3.2 How FastAPI learns who the caller is

Next.js holds an encrypted cookie; FastAPI needs a verifiable identity. Three options:

| Option | How | Verdict |
| --- | --- | --- |
| **A. Next.js mints a short-lived backend JWT** | A route handler reads the session via `auth()`, signs a 10-minute JWT (`sub`, `email`, `role`) with a secret shared with FastAPI, and the client sends it as `Authorization: Bearer`. | **Chosen.** FastAPI stays stateless, no DB lookup per request, and it works with plain `fetch` + SSE. |
| B. FastAPI verifies Google's `id_token` directly | FastAPI caches Google's JWKS and validates `aud`/`iss`/`exp`. | Workable, but `id_token` lifetime is Google's to decide and refreshing it from the browser is awkward. |
| C. Shared `sessions` table | FastAPI reads the session cookie and looks it up in `auth.sessions`. | Requires the database session strategy and a DB round trip on every request, including every SSE connection. |

For option A, use `RS256` with a key pair if the backend is ever deployed separately
from the frontend; `HS256` with a shared `BACKEND_JWT_SECRET` is fine while both run
under the same deployment. Add to `Settings`:

```python
BACKEND_JWT_SECRET: str
BACKEND_JWT_ALGORITHM: str = "HS256"
BACKEND_JWT_AUDIENCE: str = "asktemoc-api"
ALLOWED_EMAIL_DOMAIN: str = "utdallas.edu"
```

FastAPI re-checks the email domain from the token claim even though NextAuth already
did. Defense in depth costs one string comparison, and it means a misconfigured
frontend can't open the API to the world.

Two deployment details that will bite otherwise:

- **Use `fetch`, not `EventSource`, for the stream.** `EventSource` cannot set an
  `Authorization` header and does not support POST. Read the stream from
  `response.body.getReader()` instead.
- `CORS_ORIGINS` in `app/core/config.py` already drives `allow_origins`, and
  `allow_credentials=True` is set. Set it to the deployed frontend origin. A wildcard
  origin with credentials is rejected by browsers anyway.

### 3.3 Google Cloud Console setup

1. Create an OAuth 2.0 Client ID of type **Web application** in the project.
2. Authorized redirect URIs: `http://localhost:3000/api/auth/callback/google` and
   `https://<prod-domain>/api/auth/callback/google`. These must match character for
   character, including the trailing path.
3. Consent screen: if we can get a client inside the university's Workspace tenant,
   choose **Internal** and the domain restriction is enforced by Google too. Otherwise
   **External** is fine — `openid`, `email`, and `profile` are non-sensitive scopes, so
   publishing does not require Google's verification review, and our own `signIn`
   callback is what restricts the domain.
4. `AUTH_SECRET` (`openssl rand -base64 32`), `AUTH_GOOGLE_ID`, `AUTH_GOOGLE_SECRET`,
   and `AUTH_URL` go in the frontend env. The client secret never reaches the browser.

---

## 4. `users` / `conversations` / `messages` schema

### 4.1 Ownership, and why it matters

Two codebases will touch one Neon database, so each table needs exactly one owner:

- **Auth.js owns `users`, `accounts`, `sessions`, `verification_token`**, migrated by
  Drizzle on the Next.js side. The adapter expects specific column names; hand-editing
  these breaks sign-in on the next `next-auth` upgrade.
- **FastAPI owns `conversations`, `messages`, `message_feedback`**, plus the existing
  `documents` / `chunks` / `embeddings`.

Put the Auth.js tables in a dedicated `auth` Postgres schema and app tables in `public`.
Cross-schema foreign keys work normally in Postgres, and the separation makes the
ownership boundary visible in `\dt` instead of living in a wiki page.

In SQLAlchemy, declare the `users` mapping against a **separate `Base`** so
`Base.metadata.create_all()` in `init_db()` never tries to create or "fix" an
Auth.js-owned table:

```python
# app/db/auth_models.py — read-only mirror of the Auth.js schema. Never create_all() this.
AuthBase = declarative_base()

class User(AuthBase):
    __tablename__ = "users"
    __table_args__ = {"schema": "auth"}

    id = Column(Text, primary_key=True)          # adapter default: text holding a UUID
    name = Column(Text)
    email = Column(Text, nullable=False, unique=True)
    email_verified = Column("emailVerified", DateTime(timezone=True))
    image = Column(Text)
    # Columns we added to the Drizzle schema; adapters tolerate extra columns.
    role = Column(Text, nullable=False, server_default="student")
    is_active = Column(Boolean, nullable=False, server_default="true")
    last_login_at = Column(DateTime(timezone=True))
```

`users.id` stays `text` because that is the Drizzle adapter's default
(`crypto.randomUUID()` stored as text). Every `user_id` column therefore has to be
`text` too, or the foreign key won't typecheck.

**Alembic is now required.** `init_db()` only calls `create_all`, which is
`CREATE TABLE IF NOT EXISTS` — it silently does nothing when a table exists with the
wrong columns. The moment `conversations` and `messages` carry real user data, "drop
and recreate" stops being an option. Add Alembic before the first migration, not after.

### 4.2 DDL

```sql
CREATE SCHEMA IF NOT EXISTS auth;   -- Auth.js / Drizzle territory
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()

-- ---------------------------------------------------------------- conversations
CREATE TABLE conversations (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          text        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title            text,                       -- NULL until auto-titled from turn 1
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    last_message_at  timestamptz,                -- sidebar sort key
    message_count    integer     NOT NULL DEFAULT 0,
    is_archived      boolean     NOT NULL DEFAULT false,
    deleted_at       timestamptz,                -- soft delete
    conv_metadata    jsonb       NOT NULL DEFAULT '{}'::jsonb
);

-- The sidebar query: live conversations for one user, newest first.
CREATE INDEX idx_conversations_user_recent
    ON conversations (user_id, last_message_at DESC NULLS LAST)
    WHERE deleted_at IS NULL;

-- ---------------------------------------------------------------- messages
CREATE TYPE message_role   AS ENUM ('user', 'assistant', 'system');
CREATE TYPE message_status AS ENUM ('pending', 'streaming', 'complete', 'error');

CREATE TABLE messages (
    id                 uuid           PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id    uuid           NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_id            text           NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    seq                integer        NOT NULL,          -- 1-based, monotonic per conversation
    role               message_role   NOT NULL,
    content            text           NOT NULL DEFAULT '',
    status             message_status NOT NULL DEFAULT 'complete',

    client_message_id  uuid,                             -- idempotency key from the browser
    parent_message_id  uuid           REFERENCES messages(id) ON DELETE SET NULL,

    model              text,                             -- NULL for user messages
    sources            jsonb,                            -- [{index,url,title,document_id,chunk_id,score}]
    citations          jsonb,                            -- [{source_index,quote,url,title}]
    prompt_tokens      integer,
    completion_tokens  integer,
    latency_ms         integer,
    error_code         text,

    created_at         timestamptz    NOT NULL DEFAULT now(),
    updated_at         timestamptz    NOT NULL DEFAULT now(),

    CONSTRAINT uq_messages_seq UNIQUE (conversation_id, seq),
    CONSTRAINT ck_messages_assistant_model
        CHECK (role <> 'assistant' OR status <> 'complete' OR model IS NOT NULL)
);

-- Transcript read: ORDER BY seq within one conversation.
CREATE INDEX idx_messages_conversation_seq ON messages (conversation_id, seq);

-- Idempotent retries: same client_message_id in the same conversation is the same message.
CREATE UNIQUE INDEX uq_messages_client_id
    ON messages (conversation_id, client_message_id)
    WHERE client_message_id IS NOT NULL;

-- ---------------------------------------------------------------- feedback
CREATE TABLE message_feedback (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id  uuid        NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    user_id     text        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    rating      smallint    NOT NULL CHECK (rating IN (-1, 1)),
    comment     text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_feedback_per_user UNIQUE (message_id, user_id)
);
```

### 4.3 Why it is shaped this way

**`seq` instead of sorting by `created_at`.** Two messages inserted in the same
transaction can share a timestamp, and `now()` is transaction-start time in Postgres, so
`ORDER BY created_at` can render the assistant's reply above the question that produced
it. An integer `seq` with a unique constraint makes ordering total and lets the client
paginate with `before_seq`.

Assign it inside the transaction that locks the parent row, so two concurrent sends
can't claim the same number:

```sql
SELECT id FROM conversations WHERE id = :cid AND user_id = :uid FOR UPDATE;
SELECT COALESCE(MAX(seq), 0) + 1 FROM messages WHERE conversation_id = :cid;
```

The unique constraint is the real guarantee; the lock just keeps retries rare.

**`user_id` denormalized onto `messages`.** It's derivable through `conversation_id`,
but it turns the ownership check in the hot path into a single-table predicate and makes
per-user analytics a `GROUP BY` instead of a join. Enforced by the FK on both tables.

**`sources` and `citations` as `jsonb`, with `chunk_id` as a plain value — not a FK.**
This is the non-obvious one. `/api/ingest` re-ingests a URL by *deleting and recreating*
its chunks (`_upsert_document` in `endpoints/ingest.py`). A real foreign key from a
citation to `chunks.id` would either block every re-scrape or cascade-delete the
history of what the bot actually said. Keep the answer's provenance as an immutable
snapshot — URL, title, and the verbatim quote are what the UI renders anyway — and treat
`chunk_id` as a soft breadcrumb for debugging retrieval.

**Status lifecycle.** The assistant row is written *before* streaming starts, so the
`meta` event can carry a real `assistant_message_id` the client can reference for
feedback or a retry. It moves `pending` → `streaming` → `complete`, or lands on `error`
with a partial `content` and an `error_code` when the LLM or the connection dies.

**Soft delete via `deleted_at`.** Matches the `is_deleted` convention already used on
`documents` and `chunks`, and a nullable timestamp carries *when* as well as *whether*.
Every read filters `deleted_at IS NULL` — put that in one query helper rather than
repeating it per route.

**`message_count` / `last_message_at` as stored counters.** Denormalized so the sidebar
never aggregates over `messages`. Update them in the same transaction that completes the
assistant message.

### 4.4 Write path for one streamed turn

```
1. Validate the Bearer JWT → user_id, email. Re-check the email domain.
2. BEGIN
     - resolve conversation: SELECT … FOR UPDATE WHERE id = ? AND user_id = ?
       (or INSERT a new one when conversation_id is null)
     - if (conversation_id, client_message_id) already exists → COMMIT and replay
       the stored assistant answer; do not call OpenAI
     - INSERT user message      (seq = n+1, role='user',      status='complete')
     - INSERT assistant message (seq = n+2, role='assistant', status='pending')
   COMMIT                     ← must commit before the first byte of the stream
3. Emit `meta` with both IDs.
4. Retrieve from pgvector, emit `source` events, stream LLM tokens as `text` events.
   No database writes per token.
5. On completion: ONE UPDATE of the assistant row (content, sources, citations, usage,
   status='complete') plus the conversation counters. Emit `done`.
6. In a `finally` block: if the row is still pending/streaming — client disconnect,
   timeout, exception — write the partial content with status='error' and an
   error_code. Otherwise rows leak as permanently 'pending'.
```

Step 2 commits before step 4 on purpose. A transaction held open for the whole stream
pins a Neon connection for the entire LLM latency, and the pool is small.

### 4.5 Neon specifics

- Use the **pooled** connection string (`-pooler` host) for the app. Use the **direct**
  string for Alembic, since PgBouncer in transaction mode doesn't support the session
  state some DDL needs.
- Scale-to-zero means the first request after idle can take a few seconds. The
  `pool_pre_ping` / `pool_recycle=1800` already set in `app/db/database.py` are the right
  settings; the retry-with-backoff loop in `endpoints/ingest.py` is the pattern to reuse
  for conversation writes.
- Conversation writes are small and frequent — the opposite of the ingest workload — so
  keep them off the same long-lived sessions the scraper uses.

---

## 5. Week 2 order of work

1. Alembic baseline against the current `documents` / `chunks` / `embeddings` tables.
2. `auth` schema + Drizzle migration for the Auth.js tables; Google OAuth working
   end-to-end in dev with the domain check.
3. Backend JWT minting in Next.js + `get_current_user` dependency in FastAPI.
4. Migration for `conversations` / `messages` / `message_feedback`.
5. Rewrite `rag_endpoint.py` to the contract in §2 — `meta` event, persistence, error
   codes, `stream=false` branch.
6. New `conversations` router for history.
7. Admin guard on `/api/ingest`, `/api/documents`, `/api/dashboard`; delete `/api/chroma`
   and `/api/query`.
