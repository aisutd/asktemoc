import type { NextConfig } from "next";

const ASKTEMOC_API_ORIGIN =
  process.env.ASKTEMOC_API_ORIGIN?.replace(/\/$/, "") ||
  "https://asktemoc-api-422855032073.us-central1.run.app";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/proxy/:path*",
        destination: `${ASKTEMOC_API_ORIGIN}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
