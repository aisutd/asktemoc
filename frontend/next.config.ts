import type { NextConfig } from "next";

// Where /api/proxy/* is forwarded. `next dev` defaults to the local API; production
// builds get the Cloud Run origin from .env.production / vercel.json.
const ASKTEMOC_API_ORIGIN =
  process.env.ASKTEMOC_API_ORIGIN?.replace(/\/$/, "") || "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    const o = ASKTEMOC_API_ORIGIN;
    return [
      // Cloud Run redirects /api/health → http://.../api/health/ which breaks browser fetch
      // from HTTPS; hit the canonical path directly.
      {
        source: "/api/proxy/health",
        destination: `${o}/api/health/`,
      },
      {
        source: "/api/proxy/:path*",
        destination: `${o}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
