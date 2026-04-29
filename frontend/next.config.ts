import type { NextConfig } from "next";

const ASKTEMOC_API_ORIGIN =
  process.env.ASKTEMOC_API_ORIGIN?.replace(/\/$/, "") ||
  "https://asktemoc-api-422855032073.us-central1.run.app";

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
