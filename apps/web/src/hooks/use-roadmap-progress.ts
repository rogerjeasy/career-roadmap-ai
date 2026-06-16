"use client";

import { useCallback, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { roadmapApi, type RoadmapProgress } from "@/lib/api/roadmap";
import { QUERY_KEYS } from "@/lib/constants";

/**
 * Tracks which milestones a user has checked off, persisted server-side via
 * `/roadmaps/{id}/progress`. State is shared across the app (dashboard + roadmap
 * views) through the TanStack Query cache and survives reloads and devices.
 *
 * Milestone keys are stable strings of the form `${phaseId}:${milestoneIndex}`.
 */
export interface UseRoadmapProgressResult {
  isDone: (key: string) => boolean;
  toggle: (key: string) => void;
  doneInPhase: (phaseId: string, count: number) => number;
  completedKeys: ReadonlySet<string>;
}

export function useRoadmapProgress(roadmapId: string | null): UseRoadmapProgressResult {
  const queryClient = useQueryClient();
  const queryKey = QUERY_KEYS.roadmapProgress(roadmapId ?? "none");

  const { data } = useQuery({
    queryKey,
    queryFn: () => roadmapApi.getProgress(roadmapId as string),
    enabled: Boolean(roadmapId),
    staleTime: 60 * 1000,
  });

  const completedKeys = useMemo(
    () => new Set(data?.completedMilestones ?? []),
    [data],
  );

  const { mutate } = useMutation({
    mutationFn: (key: string) => roadmapApi.toggleMilestone(roadmapId as string, key),
    // Optimistic: the checkbox flips instantly, reconciles with the server
    // response, and rolls back if the request fails.
    onMutate: async (key) => {
      await queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData<RoadmapProgress>(queryKey);
      const next = new Set(previous?.completedMilestones ?? []);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      queryClient.setQueryData<RoadmapProgress>(queryKey, {
        roadmapId: roadmapId as string,
        completedMilestones: [...next],
        updatedAt: previous?.updatedAt ?? null,
      });
      return { previous };
    },
    onError: (_err, _key, ctx) => {
      if (ctx?.previous) queryClient.setQueryData(queryKey, ctx.previous);
    },
    onSuccess: (updated) => queryClient.setQueryData(queryKey, updated),
  });

  const toggle = useCallback(
    (key: string) => {
      if (!roadmapId) return;
      mutate(key);
    },
    [roadmapId, mutate],
  );

  const isDone = useCallback((key: string) => completedKeys.has(key), [completedKeys]);

  const doneInPhase = useCallback(
    (phaseId: string, count: number) => {
      let done = 0;
      for (let i = 0; i < count; i += 1) {
        if (completedKeys.has(`${phaseId}:${i}`)) done += 1;
      }
      return done;
    },
    [completedKeys],
  );

  return { isDone, toggle, doneInPhase, completedKeys };
}
