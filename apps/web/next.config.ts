import type { NextConfig } from "next";

// Kong proxy URL — in dev this is localhost:8080 (Kong container).
// In production set NEXT_PUBLIC_API_URL to the Kong proxy FQDN output by Terraform.
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      // All API calls route through Kong, which forwards to FastAPI and MCP servers.
      // Kong handles CORS, rate limiting, and routing — no duplicate config needed here.
      {
        source: "/api/v1/:path*",
        destination: `${API_URL}/api/v1/:path*`,
      },
      {
        source: "/auth/:path*",
        destination: `${API_URL}/auth/:path*`,
      },
      // SSE stream — Kong is configured with 1h timeouts and response_buffering:false.
      {
        source: "/stream/:path*",
        destination: `${API_URL}/stream/:path*`,
      },
      // MCP tool servers (job-board, calendar, social-signals, etc.)
      {
        source: "/mcp/:path*",
        destination: `${API_URL}/mcp/:path*`,
      },
      // Health checks (useful for integration tests against the gateway)
      {
        source: "/livez",
        destination: `${API_URL}/livez`,
      },
      {
        source: "/readyz",
        destination: `${API_URL}/readyz`,
      },
    ];
  },
};

export default nextConfig;
