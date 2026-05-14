/**
 * SSE stream proxy — bypasses the Next.js rewrite layer.
 *
 * Next.js `rewrites()` buffer the entire upstream response before sending it
 * to the client, which breaks Server-Sent Events. This Route Handler solves
 * the problem by piping the upstream ReadableStream directly through Node.js
 * without buffering.
 *
 * All requests to /api/v1/stream/{sessionId} are handled here instead of the
 * catch-all /api/v1/:path* rewrite in next.config.ts.
 */
import { type NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const UPSTREAM_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

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
      `${UPSTREAM_BASE}/stream/${encodeURIComponent(sessionId)}`,
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
