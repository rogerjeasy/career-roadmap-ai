"use client";

import { useCallback, useState } from "react";

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

function loadKeys(roadmapId: string | null): Set<string> {
  if (!roadmapId || typeof window === "undefined") return new Set();
  try {
    const raw = window.localStorage.getItem(storageKey(roadmapId));
    return raw ? new Set(JSON.parse(raw) as string[]) : new Set();
  } catch {
    return new Set();
  }
}

export function useRoadmapProgress(roadmapId: string | null): UseRoadmapProgressResult {
  const [keys, setKeys] = useState<Set<string>>(() => loadKeys(roadmapId));
  const [loadedId, setLoadedId] = useState<string | null>(roadmapId);

  // Reload from storage when the roadmap changes — the sanctioned effect-free
  // "adjust state during render" pattern (no flash, no cascading effect).
  if (roadmapId !== loadedId) {
    setLoadedId(roadmapId);
    setKeys(loadKeys(roadmapId));
  }

  const persist = useCallback(
    (next: Set<string>) => {
      if (!roadmapId || typeof window === "undefined") return;
      try {
        window.localStorage.setItem(storageKey(roadmapId), JSON.stringify([...next]));
      } catch {
        /* storage unavailable — keep in-memory state only */
      }
    },
    [roadmapId],
  );

  const toggle = useCallback(
    (key: string) => {
      setKeys((prev) => {
        const next = new Set(prev);
        if (next.has(key)) next.delete(key);
        else next.add(key);
        persist(next);
        return next;
      });
    },
    [persist],
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
