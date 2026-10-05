import { auth } from "@/auth";
import { apiOrigin, mintBackendToken, relay } from "@/lib/backend";

export const dynamic = "force-dynamic";

/** POST /api/chat → FastAPI /api/chat as the signed-in user; SSE streamed through. */
export async function POST(req: Request) {
  const session = await auth();
  if (!session?.user?.email) {
    return Response.json({ error: "Not signed in" }, { status: 401 });
  }

  // Throws (→ 500, logged) if BACKEND_JWT_SECRET is missing.
  const token = await mintBackendToken(session.user);
  let upstream: Response;
  try {
    upstream = await fetch(`${apiOrigin()}/api/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        Authorization: `Bearer ${token}`,
      },
      body: await req.text(),
      signal: req.signal,
      cache: "no-store",
    });
  } catch (e) {
    console.error("[api/chat] backend unreachable:", e);
    return Response.json({ error: "Backend unreachable" }, { status: 502 });
  }
  return relay(upstream);
}
