import { auth } from "@/auth";
import { authorizedBackendFetch, relay } from "@/lib/backend";

export const dynamic = "force-dynamic";

async function sessionUser() {
  const session = await auth();
  if (!session?.user?.email || !session.user.id) return null;
  return session.user;
}

/** GET /api/conversations → FastAPI list for the signed-in user. */
export async function GET(req: Request) {
  const user = await sessionUser();
  if (!user) return Response.json({ error: "Not signed in" }, { status: 401 });

  try {
    const upstream = await authorizedBackendFetch(user, "/api/conversations", {
      signal: req.signal,
    });
    return relay(upstream);
  } catch (e) {
    console.error("[api/conversations] backend unreachable:", e);
    return Response.json({ error: "Backend unreachable" }, { status: 502 });
  }
}

/** POST /api/conversations → FastAPI creates an empty conversation. */
export async function POST(req: Request) {
  const user = await sessionUser();
  if (!user) return Response.json({ error: "Not signed in" }, { status: 401 });

  try {
    const upstream = await authorizedBackendFetch(user, "/api/conversations", {
      method: "POST",
      signal: req.signal,
    });
    return relay(upstream);
  } catch (e) {
    console.error("[api/conversations] backend unreachable:", e);
    return Response.json({ error: "Backend unreachable" }, { status: 502 });
  }
}
