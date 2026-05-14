"use client";

import { useEffect } from "react";
import { subscribeToAgentStream } from "@/lib/sse";
import { useAgentStore } from "@/store/agent.store";
import { useRoadmapStore } from "@/store/roadmap.store";
import type { OrchestratorCompletedPayload } from "@/types/agent.types";
import type { RoadmapData } from "@/types/roadmap.types";

/**
 * Opens and manages an SSE connection to the agent stream for a given session.
 *
 * - Resets agent store state when sessionId changes.
 * - Dispatches all incoming events to the agent store.
 * - Persists the final roadmap to the roadmap store on ORCHESTRATION_COMPLETED.
 * - Cleans up the subscription on unmount or sessionId change.
 *
 * onDone (stream closed without terminal event):
 *   Sets status to "failed" so the UI shows an error + retry option instead
 *   of remaining stuck on "Generating" indefinitely.
 *
 * On clarification (CLARIFICATION_REQUIRED), the SSE connection stays open:
 * the backend does not emit a terminal event. When the user re-triggers
 * generation on the same session, new events flow in on the same connection.
 */
export function useAgentStream(sessionId: string | null): void {
  const reset = useAgentStore((s) => s.reset);
  const setStatus = useAgentStore((s) => s.setStatus);
  const setError = useAgentStore((s) => s.setError);
  const handleEvent = useAgentStore((s) => s.handleEvent);
  const setRoadmap = useRoadmapStore((s) => s.setRoadmap);

  useEffect(() => {
    if (!sessionId) return;

    reset();
    setStatus("connecting");

    const subscription = subscribeToAgentStream(
      sessionId,
      (event) => {
        handleEvent(event);

        if (event.event_type === "orchestration_completed") {
          const payload = event.payload as unknown as OrchestratorCompletedPayload;
          if (payload.roadmap) {
            setRoadmap(payload.roadmap as RoadmapData, sessionId);
          }
        }
      },
      (_error) => {
        // Connection-level error (network failure, 4xx/5xx, parse error).
        setError("Connection error. Please try again.");
      },
      () => {
        // Stream closed without a terminal event — the pipeline may have timed
        // out or the server restarted. Surface as a failure so the user can retry.
        setError("Generation timed out or was interrupted. Please try again.");
      },
    );

    return () => subscription.close();
  }, [sessionId, reset, setStatus, setError, handleEvent, setRoadmap]);
}
