import { SignJWT } from "jose";
import type { Adapter, AdapterAccount, AdapterUser } from "next-auth/adapters";

function apiOrigin(): string {
  return (process.env.ASKTEMOC_API_ORIGIN || "http://localhost:8000").replace(/\/$/, "");
}

/** Short-lived token for the adapter routes. It cannot call user routes. */
async function mintAdapterToken(): Promise<string> {
  const secret = process.env.BACKEND_JWT_SECRET;
  if (!secret) throw new Error("BACKEND_JWT_SECRET is not set");
  return new SignJWT({ purpose: "auth-adapter" })
    .setProtectedHeader({ alg: "HS256", typ: "JWT" })
    .setSubject("auth-adapter")
    .setAudience("asktemoc-api")
    .setIssuer("asktemoc-web")
    .setIssuedAt()
    .setExpirationTime("1m")
    .sign(new TextEncoder().encode(secret));
}

/**
 * Auth.js database adapter. Every method calls FastAPI, which writes Neon.
 * There is no database driver in this app.
 *
 * JWT sessions only need the user and account methods. Session and
 * verification-token methods are omitted on purpose.
 */

type UserJson = {
  id: string;
  name?: string | null;
  email: string;
  emailVerified?: string | null;
  image?: string | null;
};

async function adapterFetch(path: string, init?: RequestInit): Promise<Response> {
  const token = await mintAdapterToken();
  const headers = new Headers(init?.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (init?.body) headers.set("Content-Type", "application/json");
  return fetch(`${apiOrigin()}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
}

function toUser(data: UserJson): AdapterUser {
  return {
    id: data.id,
    name: data.name ?? null,
    email: data.email,
    emailVerified: data.emailVerified ? new Date(data.emailVerified) : null,
    image: data.image ?? null,
  };
}

async function readUser(res: Response): Promise<AdapterUser | null> {
  if (res.status === 404) return null;
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Auth adapter request failed (${res.status}): ${detail}`);
  }
  return toUser((await res.json()) as UserJson);
}

function userBody(user: Partial<AdapterUser>): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if ("name" in user) body.name = user.name ?? null;
  if ("email" in user && user.email) body.email = user.email;
  if ("emailVerified" in user) body.emailVerified = user.emailVerified ?? null;
  if ("image" in user) body.image = user.image ?? null;
  return body;
}

export function fastapiAdapter(): Adapter {
  return {
    async createUser(user) {
      const res = await adapterFetch("/api/internal/auth/users", {
        method: "POST",
        body: JSON.stringify(userBody(user)),
      });
      const created = await readUser(res);
      if (!created) throw new Error("Auth adapter did not return a user");
      return created;
    },
    async getUser(id) {
      return readUser(await adapterFetch(`/api/internal/auth/users/${encodeURIComponent(id)}`));
    },
    async getUserByEmail(email) {
      const params = new URLSearchParams({ email });
      return readUser(await adapterFetch(`/api/internal/auth/users/by-email?${params}`));
    },
    async getUserByAccount({ provider, providerAccountId }) {
      const params = new URLSearchParams({ provider, providerAccountId });
      return readUser(await adapterFetch(`/api/internal/auth/users/by-account?${params}`));
    },
    async updateUser(user) {
      const res = await adapterFetch(`/api/internal/auth/users/${encodeURIComponent(user.id)}`, {
        method: "PATCH",
        body: JSON.stringify(userBody(user)),
      });
      const updated = await readUser(res);
      if (!updated) throw new Error("Auth adapter did not return a user");
      return updated;
    },
    async linkAccount(account: AdapterAccount) {
      const sessionState = account.session_state;
      const res = await adapterFetch("/api/internal/auth/accounts", {
        method: "POST",
        body: JSON.stringify({
          userId: account.userId,
          type: account.type,
          provider: account.provider,
          providerAccountId: account.providerAccountId,
          refresh_token: account.refresh_token ?? null,
          access_token: account.access_token ?? null,
          expires_at: typeof account.expires_at === "number" ? account.expires_at : null,
          token_type: account.token_type ?? null,
          scope: account.scope ?? null,
          id_token: account.id_token ?? null,
          session_state:
            typeof sessionState === "string" || sessionState == null
              ? (sessionState ?? null)
              : JSON.stringify(sessionState),
        }),
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`Auth adapter request failed (${res.status}): ${detail}`);
      }
    },
  };
}
