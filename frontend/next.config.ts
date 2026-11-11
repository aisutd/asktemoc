import type { NextConfig } from "next";
import { apiOrigin } from "./src/lib/api-origin";

const nextConfig: NextConfig = {
  async rewrites() {
    const o = apiOrigin();
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
