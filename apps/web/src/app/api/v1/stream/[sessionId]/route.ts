/**
 * SSE stream proxy — fallback for server-side SSE consumers (e.g. server
 * components, integration tests). Browser clients should NOT go through this
 * Route Handler; instead they use sse.ts which connects directly to FastAPI
 * (via NEXT_PUBLIC_SSE_URL) to avoid undici / Next.js response buffering.
 *
 * In dev we bypass Kong and hit FastAPI directly so SSE chunks are never
 * held in Kong's response buffer before reaching the caller.
 * In prod all traffic goes through Kong, which is configured with
 * response_buffering:false and 1-hour timeouts on /api/v1/stream.
 */
import { type NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const IS_PROD = process.env.NODE_ENV === "production";
// In dev bypass Kong — undici (Node.js fetch) is used here and it does not
// buffer SSE chunks, but Kong's 60s read timeout on the api-v1 route would
// cut long-running streams. FastAPI directly has no such timeout.
const UPSTREAM_BASE = IS_PROD
  ? (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080")
  : (process.env.FASTAPI_DIRECT_URL ?? "http://localhost:8000");

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ sessionId: string }> },
) {
  const { sessionId } = await context.params;
  const authHeader = request.headers.get("Authorization");

  if (!authHeader) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(
      `${UPSTREAM_BASE}/api/v1/stream/${encodeURIComponent(sessionId)}`,
      {
        headers: {
          Authorization: authHeader,
          Accept: "text/event-stream",
          "Cache-Control": "no-cache",
        },
        // Prevent Node.js / Next.js from buffering the response body
        cache: "no-store",
        // Abort the upstream request if the client disconnects
        signal: request.signal,
      },
    );
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Stream proxy error";
    return NextResponse.json({ error: msg }, { status: 502 });
  }

  if (!upstream.ok) {
    return NextResponse.json(
      { error: "Upstream error", status: upstream.status },
      { status: upstream.status },
    );
  }

  // Pipe the upstream ReadableStream directly — no buffering.
  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      // Disable proxy buffering (Nginx / Kong / Vercel edge)
      "X-Accel-Buffering": "no",
    },
  });
}
