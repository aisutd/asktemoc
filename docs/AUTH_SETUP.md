# Auth setup

Ask Temoc signs users in with [Auth.js](https://authjs.dev) and admits only
verified `@utdallas.edu` addresses (`ALLOWED_EMAIL_DOMAIN`). Two providers are
supported. Each one turns on when its env vars are set in `frontend/.env.local`
(locally) or in Vercel (production):

| Provider | Use it for | Env vars |
| --- | --- | --- |
| Microsoft Entra ID | **Production.** UTD email is Microsoft 365, so every student has an Entra account. | `AUTH_MICROSOFT_ENTRA_ID_ID`, `AUTH_MICROSOFT_ENTRA_ID_SECRET`, `AUTH_MICROSOFT_ENTRA_ID_ISSUER` |
| Google | Development. Most students have **no** Google account on utdallas.edu. | `AUTH_GOOGLE_ID`, `AUTH_GOOGLE_SECRET` |

You also need two secrets (see [Secrets](#secrets)): `AUTH_SECRET` and
`BACKEND_JWT_SECRET`.

## Microsoft Entra ID

### 1. Decide where the app registration lives

The issuer must be **UTD's tenant**: the web app rejects multi-tenant issuers
(`common`, `organizations`, `consumers`), and it rejects tokens whose `tid` claim
isn't that tenant. The reason is that Entra doesn't verify the `email` claim
across tenants: another organisation's tenant could assert
`someone@utdallas.edu`.

There are two ways to get a registration that UTD accounts can use:

- **(a) Registered inside the UTD tenant** (single-tenant). This is the cleanest
  option, but students usually can't create app registrations there, so **ask
  UTD OIT** to create it or give you the *Application Developer* role.
- **(b) Registered in a tenant you control, as multi-tenant** ("Accounts in any
  organizational directory"), with the issuer set to UTD's tenant. UTD users can
  sign in once the UTD tenant has consented to the app. If UTD blocks user
  consent (common at universities), **an OIT admin must grant admin consent**.
  Until then, sign-in fails with "Need admin approval".

Either way, plan to contact OIT before launch.

**Finding UTD's tenant ID:** open
<https://login.microsoftonline.com/utdallas.edu/v2.0/.well-known/openid-configuration>.
The `issuer` value looks like
`https://login.microsoftonline.com/<TENANT-ID>/v2.0`.

### 2. Register the app

1. Go to the [Entra admin center](https://entra.microsoft.com) → **Applications** →
   **App registrations** → **New registration**.
2. **Name:** `Ask Temoc`.
3. **Supported account types:** *single tenant* for option (a); *any
   organizational directory* for option (b).
4. **Redirect URI:** platform **Web**, value
   `http://localhost:3000/api/auth/callback/microsoft-entra-id`
5. Click **Register**. Then go to **Authentication** → **Add URI** and add the
   production callback, for example
   `https://<your-vercel-domain>/api/auth/callback/microsoft-entra-id`.
   Add a URI for each preview domain you want sign-in to work on.

### 3. Collect the values

| Where in the portal | Env var |
| --- | --- |
| Overview → *Application (client) ID* | `AUTH_MICROSOFT_ENTRA_ID_ID` |
| Certificates & secrets → New client secret → **Value** (shown once) | `AUTH_MICROSOFT_ENTRA_ID_SECRET` |
| `https://login.microsoftonline.com/<UTD-TENANT-ID>/v2.0` | `AUTH_MICROSOFT_ENTRA_ID_ISSUER` |

Client secrets expire (at most 24 months). Put a reminder in the team calendar.

### 4. Permissions and claims

- **API permissions:** Microsoft Graph *delegated* `openid`, `profile`, `email`
  and `User.Read`. These are low-privilege, but they still need consent (see
  step 1).
- **Token configuration** → **Add optional claim** → token type **ID** → `email`.
  Without the `email` claim, sign-in is rejected because there's no address to
  check.

## Google (development)

1. In the [Google Cloud console](https://console.cloud.google.com), create or
   pick a project and go to **APIs & Services** → **OAuth consent screen**.
   Choose **External**, leave it in **Testing**, and add each teammate as a
   test user.
2. Go to **Credentials** → **Create credentials** → **OAuth client ID** →
   **Web application**.
   - Authorized JavaScript origin: `http://localhost:3000`
   - Authorized redirect URI: `http://localhost:3000/api/auth/callback/google`
     (plus `https://<your-vercel-domain>/api/auth/callback/google` if you
     want it in production)
3. Copy the client ID and secret into `AUTH_GOOGLE_ID` and `AUTH_GOOGLE_SECRET`.

Sign-in requires Google's `email_verified` flag. A teammate who has created a
Google account on their `@utdallas.edu` address can sign in as-is. Anyone
testing with a personal account needs that address in **both** env files:

```
# frontend/.env.local             # backend/.env
ALLOWED_EMAILS=you@gmail.com      ALLOWED_EMAILS=you@gmail.com
                                  ENVIRONMENT=development
```

`ALLOWED_EMAILS` only takes effect under `npm run dev` (frontend) and with
`ENVIRONMENT=development` (API), so it can't leak into production.

## Secrets

| Variable | Where | What it does |
| --- | --- | --- |
| `AUTH_SECRET` | frontend only | Encrypts the session cookie. |
| `BACKEND_JWT_SECRET` | frontend **and** backend, same value, at least 32 characters | Signs and verifies the 5-minute tokens the Next server sends to the API. |

Generate them:

```bash
node -e "console.log(require('crypto').randomBytes(32).toString('base64url'))"   # AUTH_SECRET
python -c "import secrets; print(secrets.token_urlsafe(48))"                       # BACKEND_JWT_SECRET
```

Use different values for local and production, and never commit them. Rotating
`AUTH_SECRET` signs everyone out. Rotating `BACKEND_JWT_SECRET` needs both
sides updated together.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Sign-in page shows "Only verified @utdallas.edu accounts…" | Wrong domain, unverified Google email, Entra issuer not the UTD tenant, or Entra `email` claim missing. An Entra tenant mismatch is also logged by the Next server. |
| Sign-in page says "No sign-in provider is configured" | No provider has all of its env vars set. Restart `npm run dev` after editing `.env.local`. |
| Microsoft says "Need admin approval" | The UTD tenant hasn't consented to the app; see step 1. |
| Signed in, but chat fails and the API logs `401 Invalid token: Signature verification failed` | `BACKEND_JWT_SECRET` differs between frontend and backend. |
| API logs `403 Only @utdallas.edu accounts…` | Using `ALLOWED_EMAILS` on the frontend but not on the backend (or the API isn't in development). |
| `UntrustedHost` errors with `next start` or a non-Vercel host | Set `AUTH_URL=https://<host>` (or `AUTH_TRUST_HOST=true`). Vercel and `next dev` don't need it. |
