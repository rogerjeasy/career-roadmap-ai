"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { coachApi } from "@/lib/api/coach";
import { subscribeToAgentStream, type SSESubscription } from "@/lib/sse";
import type { AgentEvent } from "@/types/agent.types";

export interface CoachMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  /** True while the assistant message is still streaming in. */
  streaming?: boolean;
}

export interface UseCoachResult {
  messages: CoachMessage[];
  send: (text: string) => void;
  isThinking: boolean;
  isLoadingHistory: boolean;
  error: string | null;
}

function makeId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

/** Pull a streamed token out of an arbitrary stream_token payload shape. */
function extractToken(payload: Record<string, unknown>): string {
  for (const key of ["token", "text", "content", "delta"]) {
    const v = payload[key];
    if (typeof v === "string") return v;
  }
  return "";
}

/** Find the coach narrative inside the orchestration_completed agent_results. */
function extractCoachAnswer(payload: Record<string, unknown>): string | null {
  const results = payload.agent_results;
  if (results && typeof results === "object") {
    for (const value of Object.values(results as Record<string, unknown>)) {
      if (value && typeof value === "object") {
        const resp = (value as Record<string, unknown>).response;
        if (typeof resp === "string" && resp.trim()) return resp;
      }
    }
  }
  return null;
}

export function useCoach(): UseCoachResult {
  const [messages, setMessages] = useState<CoachMessage[]>([]);
  const [isThinking, setIsThinking] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const subRef = useRef<SSESubscription | null>(null);
  // id of the assistant message currently being streamed
  const activeAssistantId = useRef<string | null>(null);

  // Load conversation history once on mount.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { turns } = await coachApi.getHistory(30);
        if (cancelled) return;
        setMessages(
          turns
            .filter((t) => t.role === "user" || t.role === "assistant")
            .map((t) => ({
              id: makeId(),
              role: t.role as "user" | "assistant",
              content: t.content,
            })),
        );
      } catch {
        /* history is best-effort — start with an empty thread */
      } finally {
        if (!cancelled) setIsLoadingHistory(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Tear down any open stream on unmount.
  useEffect(() => () => subRef.current?.close(), []);

  const appendToActive = useCallback((chunk: string) => {
    const id = activeAssistantId.current;
    if (!id) return;
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, content: m.content + chunk } : m)),
    );
  }, []);

  const finalizeActive = useCallback((finalText?: string) => {
    const id = activeAssistantId.current;
    if (!id) return;
    setMessages((prev) =>
      prev.map((m) =>
        m.id === id
          ? {
              ...m,
              content: finalText && finalText.trim() ? finalText : m.content,
              streaming: false,
            }
          : m,
      ),
    );
    activeAssistantId.current = null;
    setIsThinking(false);
  }, []);

  const handleEvent = useCallback(
    (event: AgentEvent) => {
      switch (event.event_type) {
        case "stream_token":
          appendToActive(extractToken(event.payload));
          break;
        case "stream_done":
          finalizeActive();
          break;
        case "orchestration_completed":
          finalizeActive(extractCoachAnswer(event.payload) ?? undefined);
          break;
        case "orchestration_failed":
          setError("The coach couldn't respond. Please try again.");
          finalizeActive("Sorry — I ran into a problem answering that. Please try again.");
          break;
        default:
          break;
      }
    },
    [appendToActive, finalizeActive],
  );

  const send = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isThinking) return;
      setError(null);

      const assistantId = makeId();
      activeAssistantId.current = assistantId;
      setMessages((prev) => [
        ...prev,
        { id: makeId(), role: "user", content: trimmed },
        { id: assistantId, role: "assistant", content: "", streaming: true },
      ]);
      setIsThinking(true);

      coachApi
        .sendMessage(trimmed)
        .then(({ sessionId }) => {
          subRef.current?.close();
          subRef.current = subscribeToAgentStream(
            sessionId,
            handleEvent,
            () => {
              setError("Connection error. Please try again.");
              finalizeActive("Sorry — the connection dropped. Please try again.");
            },
            () => finalizeActive(),
          );
        })
        .catch(() => {
          setError("Couldn't reach the coach. Please try again.");
          finalizeActive("Sorry — I couldn't start a session. Please try again.");
        });
    },
    [isThinking, handleEvent, finalizeActive],
  );

  return { messages, send, isThinking, isLoadingHistory, error };
}
