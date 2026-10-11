/** @type {import('next').NextConfig} */
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

const nextConfig = {
  reactStrictMode: true,
  // The dev proxy gives up after 30s by default; an Opus thinking move plus Bedrock retries can take longer.
  experimental: { proxyTimeout: 300_000 },
  // Proxy /api/* to FastAPI so the browser never needs CORS or the backend URL.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }];
  },
};

export default nextConfig;
