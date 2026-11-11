const PRODUCTION_ORIGIN = "https://asktemoc-api-422855032073.us-central1.run.app";

/** FastAPI origin. A preview deploy sets ASKTEMOC_PREVIEW_API_ORIGIN and wins over the production value in vercel.json. */
export function apiOrigin(): string {
  const configured =
    process.env.ASKTEMOC_PREVIEW_API_ORIGIN || process.env.ASKTEMOC_API_ORIGIN;
  const fallback =
    process.env.NODE_ENV === "production"
      ? PRODUCTION_ORIGIN
      : "http://localhost:8000";
  return (configured || fallback).replace(/\/$/, "");
}
