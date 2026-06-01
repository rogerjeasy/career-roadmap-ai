"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * Tracks which milestones a user has checked off, persisted to localStorage
 * keyed by roadmap id. Used until a server-side progress domain exists.
 *
 * Milestone keys are stable strings of the form `${phaseId}:${milestoneIndex}`.
 */
export interface UseRoadmapProgressResult {
  isDone: (key: string) => boolean;
  toggle: (key: string) => void;
  doneInPhase: (phaseId: string, count: number) => number;
  completedKeys: ReadonlySet<string>;
}

function storageKey(roadmapId: string): string {
  return `crai-roadmap-progress:${roadmapId}`;
}

export function useRoadmapProgress(roadmapId: string | null): UseRoadmapProgressResult {
  const [keys, setKeys] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!roadmapId || typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem(storageKey(roadmapId));
      setKeys(raw ? new Set(JSON.parse(raw) as string[]) : new Set());
    } catch {
      setKeys(new Set());
    }
  }, [roadmapId]);

  const toggle = useCallback(
    (key: string) => {
      setKeys((prev) => {
        const next = new Set(prev);
        if (next.has(key)) next.delete(key);
        else next.add(key);
        if (roadmapId && typeof window !== "undefined") {
          try {
            window.localStorage.setItem(storageKey(roadmapId), JSON.stringify([...next]));
          } catch {
            /* ignore */
          }
        }
        return next;
      });
    },
    [roadmapId],
  );

  const isDone = useCallback((key: string) => keys.has(key), [keys]);

  const doneInPhase = useCallback(
    (phaseId: string, count: number) => {
      let done = 0;
      for (let i = 0; i < count; i += 1) {
        if (keys.has(`${phaseId}:${i}`)) done += 1;
      }
      return done;
    },
    [keys],
  );

  return { isDone, toggle, doneInPhase, completedKeys: keys };
}
