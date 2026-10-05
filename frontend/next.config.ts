import type { NextConfig } from "next";

// The browser calls this app's own route handlers (src/app/api/*), which add the
// signed-in user's token and forward to ASKTEMOC_API_ORIGIN server-side.
const nextConfig: NextConfig = {};

export default nextConfig;
