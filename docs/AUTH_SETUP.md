# Auth setup

Ask Temoc signs users in with [Auth.js](https://authjs.dev) and admits only
`@utdallas.edu` addresses (`ALLOWED_EMAIL_DOMAIN`). There is **no public UTD
OAuth API** for student apps. Campus identity is Microsoft 365 / Entra ID.

## Can we connect to UTD OAuth?

Short answer: **OIDC through UTD's Microsoft tenant, not a UTD-branded OAuth portal.**

| Path | What it is | Can this app use it? |
| --- | --- | --- |
| **Microsoft Entra ID (OIDC)** | Every NetID is a Microsoft 365 account in tenant `utdallas.edu` (issuer `https://login.microsoftonline.com/8d281d1d-9c4d-4bf7-b16e-032d15de9f6c/v2.0`). | **Yes — this is the production path.** Register an app and send users through Auth.js `microsoft-entra-id`. |
| **OIT Single Sign-On (SAML / Shibboleth)** | Official campus SSO. [Request form](https://atlas.utdallas.edu/TDClient/30/Portal/KB/Article/217/Request-Single-Sign-On-for-Application-or-Service). | Only if a **faculty or staff** sponsor files the ticket. Student and student-employee requests are denied. |
| **Google Workspace `hd=utdallas.edu`** | The earlier design assumed a Google-backed `@utdallas.edu` account. | Most students **do not** have a Google account on that domain. A personal Gmail address is rejected. |

To go live on Entra you still need UTD OIT: either they register the app **inside**
the UTD tenant, or they grant **admin consent** to a multi-tenant app you
registered. Until then, Microsoft will show “Need admin approval.”

## Microsoft Entra ID

1. Confirm the issuer at
   <https://login.microsoftonline.com/utdallas.edu/v2.0/.well-known/openid-configuration>.
2. [Entra admin center](https://entra.microsoft.com) → **App registrations** →
   **New registration**. Redirect URI (Web):
   `http://localhost:3000/api/auth/callback/microsoft-entra-id`
   plus the production callback.
3. Set `AUTH_MICROSOFT_ENTRA_ID_ID`, `_SECRET`, and `_ISSUER`
   (`https://login.microsoftonline.com/<UTD-TENANT-ID>/v2.0`).
   Do **not** use `common` / `organizations` / `consumers` — Entra does not
   verify `email` across tenants.
4. API permissions: Graph delegated `openid`, `profile`, `email`, `User.Read`.
   Token configuration → optional ID claim `email`.

## Google (development)

OAuth client of type Web, redirect `http://localhost:3000/api/auth/callback/google`.
Sign-in requires `email_verified` and an `@utdallas.edu` address. Personal accounts are rejected.

## Secrets

| Variable | Where | Purpose |
| --- | --- | --- |
| `AUTH_SECRET` | frontend | Encrypts the Auth.js session cookie. |
| `BACKEND_JWT_SECRET` | frontend **and** backend, same value | HS256 for the 5-minute API token. |

```bash
node -e "console.log(require('crypto').randomBytes(32).toString('base64url'))"
```

The browser never holds the API JWT. `POST /api/chat` on Next.js checks the
session, mints the token, and relays SSE to FastAPI. FastAPI requires a valid
signed JWT on every chat request. A missing secret, missing token, or invalid
token is rejected.
