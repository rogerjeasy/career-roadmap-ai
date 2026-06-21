import type { NextConfig } from "next";
import { withSentryConfig } from "@sentry/nextjs";

// Kong proxy URL — in dev this is localhost:8080 (Kong container).
// In production set NEXT_PUBLIC_API_URL to the Kong proxy FQDN output by Terraform.
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      // NOTE: /api/v1/stream/:path* is handled by the Route Handler at
      // src/app/api/v1/stream/[sessionId]/route.ts — it pipes the upstream
      // ReadableStream directly without buffering. Kong's fastapi-sse service
      // covers this path with response_buffering:false and 1-hour timeouts.
      // Do NOT add a rewrite for that path here — Route Handlers take
      // precedence over rewrites anyway.

      // All other API calls route through Kong.
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

// Wrap with Sentry: instruments the build, uploads source maps (only when
// SENTRY_AUTH_TOKEN/ORG/PROJECT are set — skipped silently otherwise), and
// tree-shakes Sentry logger statements out of production bundles.
export default withSentryConfig(nextConfig, {
  org: process.env.SENTRY_ORG,
  project: process.env.SENTRY_PROJECT,
  authToken: process.env.SENTRY_AUTH_TOKEN,
  // Quiet build logs unless running in CI.
  silent: !process.env.CI,
  // Upload a wider set of source maps for richer stack traces.
  widenClientFileUpload: true,
  // Strip Sentry SDK logger statements from the client bundle.
  disableLogger: true,
  // Route Sentry requests through the app to dodge ad-blockers blocking events.
  tunnelRoute: "/monitoring",
});
