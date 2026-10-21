import { auth } from "@/auth";
import { authorizedBackendFetch, relay } from "@/lib/backend";

export const dynamic = "force-dynamic";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

/** GET /api/conversations/:id → FastAPI, only if it belongs to the signed-in user. */
export async function GET(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const session = await auth();
  if (!session?.user?.email || !session.user.id) {
    return Response.json({ error: "Not signed in" }, { status: 401 });
  }

  const { id } = await params;
  if (!UUID_RE.test(id)) {
    return Response.json({ error: "Invalid conversation id" }, { status: 400 });
  }

  try {
    const upstream = await authorizedBackendFetch(
      session.user,
      `/api/conversations/${id}`,
      { signal: req.signal },
    );
    return relay(upstream);
  } catch (e) {
    console.error("[api/conversations/:id] backend unreachable:", e);
    return Response.json({ error: "Backend unreachable" }, { status: 502 });
  }
}
