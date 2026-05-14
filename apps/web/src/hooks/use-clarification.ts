"use client";

import { useCallback, useState } from "react";
import { apiClient } from "@/lib/api/client";
import { useAgentStore } from "@/store/agent.store";

/**
 * Handles the multi-turn clarification flow.
 *
 * When CLARIFICATION_REQUIRED is received, status = "clarification" and
 * clarification questions are stored in the agent store. The UI renders a form.
 *
 * On submit:
 *   1. POST answers to /api/v1/session/clarification/reply
 *   2. POST /api/v1/orchestrator/generate again (same session)
 *
 * The SSE connection for the session stays open throughout — the backend does
 * not emit a terminal event on clarification, so new pipeline events from the
 * follow-up generation flow in on the same subscription automatically.
 * The incoming ORCHESTRATION_STARTED event resets the store state to "generating".
 */
export function useClarification() {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const clarification = useAgentStore((s) => s.clarification);
  const status = useAgentStore((s) => s.status);

  const submitAnswers = useCallback(
    async (answers: Record<string, string>) => {
      if (isSubmitting) return;
      setIsSubmitting(true);
      setSubmitError(null);

      try {
        await apiClient.post("/api/v1/session/clarification/reply", { answers });

        const combinedMessage = Object.values(answers)
          .filter(Boolean)
          .join(". ");

        await apiClient.post("/api/v1/orchestrator/generate", {
          message: combinedMessage,
        });
        // No state change needed here: the next ORCHESTRATION_STARTED event on
        // the existing SSE stream resets status to "generating" automatically.
      } catch {
        setSubmitError("Failed to submit answers. Please try again.");
      } finally {
        setIsSubmitting(false);
      }
    },
    [isSubmitting],
  );

  return {
    clarification,
    isClarifying: status === "clarification",
    isSubmitting,
    submitError,
    submitAnswers,
  };
}
