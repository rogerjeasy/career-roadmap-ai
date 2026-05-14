import { firebaseAuth } from "@/lib/firebase";
import type { AgentEvent } from "@/types/agent.types";

const TERMINAL_EVENTS: ReadonlySet<string> = new Set([
  "orchestration_completed",
  "orchestration_failed",
]);

export type SSEEventHandler = (event: AgentEvent) => void;

export interface SSESubscription {
  close(): void;
}

const MAX_RETRIES = 6;
const INITIAL_RETRY_DELAY_MS = 1_000;
const MAX_RETRY_DELAY_MS = 30_000;
// Reset the backoff counter once a connection has been stable this long.
const STABLE_CONNECTION_THRESHOLD_MS = 10_000;

/**
 * Opens an authenticated SSE connection to /api/v1/stream/{sessionId}.
 *
 * Uses fetch + ReadableStream instead of EventSource because EventSource does
 * not support custom request headers (required for the Firebase Bearer token).
 *
 * Reconnects automatically with exponential back-off (1 s → 2 s → … → 30 s)
 * plus ±500 ms jitter. After MAX_RETRIES failed attempts, onError is called
 * once and the subscription terminates. A connection that stays up longer than
 * STABLE_CONNECTION_THRESHOLD_MS resets the retry counter.
 *
 * Lifecycle callbacks:
 *   onEvent  — called for every parsed AgentEvent (including terminal ones)
 *   onError  — called when all reconnect attempts are exhausted
 *   onDone   — called when close() is called before a terminal event arrives,
 *              or when we give up reconnecting after exhausting all retries
 *
 * The stream terminates when:
 *   - orchestration_completed or orchestration_failed arrives (terminal events)
 *   - close() is called by the caller
 *   - MAX_RETRIES reconnect attempts all fail
 *
 * SSE comments (lines starting with `:`) are silently ignored — the server
 * sends them as keepalive probes so proxies do not close idle connections.
 */
export function subscribeToAgentStream(
  sessionId: string,
  onEvent: SSEEventHandler,
  onError: (error: Error) => void,
  onDone: () => void,
): SSESubscription {
  const controller = new AbortController();
  let closed = false;
  let receivedTerminal = false;

  const close = () => {
    if (!closed) {
      closed = true;
      controller.abort();
    }
  };

  (async () => {
    let retryCount = 0;
    let retryDelay = INITIAL_RETRY_DELAY_MS;

    while (!closed && !receivedTerminal) {
      const connectStartMs = Date.now();
      let connectionEstablished = false;

      try {
        const user = firebaseAuth.currentUser;
        if (!user) throw new Error("Not authenticated");

        const token = await user.getIdToken();

        const response = await fetch(`/api/v1/stream/${encodeURIComponent(sessionId)}`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(`Stream connection failed: ${response.status}`);
        }
        if (!response.body) {
          throw new Error("Response has no body");
        }

        connectionEstablished = true;
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (!closed) {
          const { done: streamDone, value } = await reader.read();
          if (streamDone) break;

          buffer += decoder.decode(value, { stream: true });

          const blocks = buffer.split("\n\n");
          buffer = blocks.pop() ?? "";

          for (const block of blocks) {
            const trimmed = block.trim();
            if (!trimmed) continue;
            if (trimmed.startsWith(":")) continue;

            let eventName = "";
            let dataLine = "";

            for (const line of trimmed.split("\n")) {
              if (line.startsWith("event: ")) {
                eventName = line.slice(7).trim();
              } else if (line.startsWith("data: ")) {
                dataLine = dataLine ? dataLine + "\n" + line.slice(6) : line.slice(6).trim();
              }
            }

            if (!dataLine) continue;

            if (eventName === "error") {
              try {
                const body = JSON.parse(dataLine) as { error?: string; detail?: string };
                onError(new Error(body.detail ?? body.error ?? "Stream error"));
              } catch {
                onError(new Error("Stream error"));
              }
              continue;
            }

            if (eventName !== "agent_event") continue;

            let event: AgentEvent;
            try {
              event = JSON.parse(dataLine) as AgentEvent;
            } catch {
              continue;
            }

            onEvent(event);

            if (TERMINAL_EVENTS.has(event.event_type)) {
              receivedTerminal = true;
              closed = true;
              return;
            }
          }
        }
      } catch (err) {
        if (closed || (err as Error).name === "AbortError") return;
        // Fall through to retry logic
      }

      if (closed || receivedTerminal) return;

      // If the connection stayed up long enough, reset the backoff counter.
      if (connectionEstablished && Date.now() - connectStartMs > STABLE_CONNECTION_THRESHOLD_MS) {
        retryCount = 0;
        retryDelay = INITIAL_RETRY_DELAY_MS;
      }

      retryCount++;
      if (retryCount > MAX_RETRIES) {
        onError(new Error(`SSE stream could not reconnect after ${MAX_RETRIES} attempts`));
        return;
      }

      const jitter = Math.random() * 500;
      await new Promise<void>((resolve) => setTimeout(resolve, retryDelay + jitter));
      retryDelay = Math.min(retryDelay * 2, MAX_RETRY_DELAY_MS);
    }

    if (!receivedTerminal) {
      onDone();
    }
  })();

  return { close };
}
