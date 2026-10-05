import "server-only";

import { SignJWT } from "jose";
import type { Session } from "next-auth";

/**
 * Server-side access to the FastAPI backend. The browser never calls the API
 * directly: route handlers check the Auth.js session, mint a short-lived token
 * for the signed-in user, and forward the request.
 */

const TOKEN_TTL = "5m";

export function apiOrigin(): string {
  return (process.env.ASKTEMOC_API_ORIGIN || "http://localhost:8000").replace(/\/$/, "");
}

export async function mintBackendToken(user: Session["user"]): Promise<string> {
  const secret = process.env.BACKEND_JWT_SECRET;
  if (!secret) throw new Error("BACKEND_JWT_SECRET is not set");
  return new SignJWT({ email: user.email, name: user.name ?? undefined })
    .setProtectedHeader({ alg: "HS256", typ: "JWT" })
    .setSubject(user.id)
    .setAudience("asktemoc-api")
    .setIssuer("asktemoc-web")
    .setIssuedAt()
    .setExpirationTime(TOKEN_TTL)
    .sign(new TextEncoder().encode(secret));
}

/** Pass the upstream response through without buffering the body. */
export function relay(upstream: Response): Response {
  const headers = new Headers({
    "Content-Type": upstream.headers.get("Content-Type") ?? "application/json",
    "Cache-Control": "no-cache, no-transform",
  });
  if (headers.get("Content-Type")?.startsWith("text/event-stream")) {
    headers.set("X-Accel-Buffering", "no");
  }
  return new Response(upstream.body, { status: upstream.status, headers });
}
