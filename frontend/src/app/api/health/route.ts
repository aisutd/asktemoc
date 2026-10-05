import { auth } from "@/auth";
import { apiOrigin, mintBackendToken, relay } from "@/lib/backend";

export const dynamic = "force-dynamic";

/** GET /api/health → FastAPI /api/health/, for signed-in users. */
export async function GET(req: Request) {
  const session = await auth();
  if (!session?.user?.email) {
    return Response.json({ error: "Not signed in" }, { status: 401 });
  }

  const token = await mintBackendToken(session.user);
  try {
    const upstream = await fetch(`${apiOrigin()}/api/health/`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: req.signal,
      cache: "no-store",
    });
    return relay(upstream);
  } catch (e) {
    console.error("[api/health] backend unreachable:", e);
    return Response.json({ status: "unreachable" }, { status: 502 });
  }
}
