import { apiOrigin, relay } from "@/lib/backend";

export const dynamic = "force-dynamic";

/** GET /api/health → FastAPI /api/health/. Public so the UI can probe liveness. */
export async function GET(req: Request) {
  try {
    const upstream = await fetch(`${apiOrigin()}/api/health/`, {
      signal: req.signal,
      cache: "no-store",
    });
    return relay(upstream);
  } catch (e) {
    console.error("[api/health] backend unreachable:", e);
    return Response.json({ status: "unreachable" }, { status: 502 });
  }
}
