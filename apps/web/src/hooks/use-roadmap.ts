"use client";

import { useQuery } from "@tanstack/react-query";
import { roadmapApi, type RoadmapSummary } from "@/lib/api/roadmap";
import type { RoadmapDetail } from "@/types/roadmap.types";
import { QUERY_KEYS } from "@/lib/constants";

export interface UseRoadmapResult {
  roadmap: RoadmapDetail | null;
  summaries: RoadmapSummary[];
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
  /** True once the list resolved and there are no roadmaps yet. */
  isEmpty: boolean;
}

/**
 * Loads the user's most recent roadmap in full.
 *
 * Two-step fetch: list summaries (newest-first) → fetch the full document for
 * the first id. Pass an explicit `roadmapId` to load a specific roadmap.
 */
export function useRoadmap(roadmapId?: string): UseRoadmapResult {
  const listQuery = useQuery({
    queryKey: QUERY_KEYS.roadmapList,
    queryFn: () => roadmapApi.list(20),
    staleTime: 60 * 1000,
    enabled: !roadmapId,
  });

  const resolvedId = roadmapId ?? listQuery.data?.[0]?.id;

  const detailQuery = useQuery({
    queryKey: QUERY_KEYS.roadmap(resolvedId),
    queryFn: () => roadmapApi.get(resolvedId as string),
    staleTime: 60 * 1000,
    enabled: Boolean(resolvedId),
  });

  const listSettled = roadmapId ? true : !listQuery.isLoading;
  const isEmpty = listSettled && !resolvedId;

  return {
    roadmap: detailQuery.data ?? null,
    summaries: listQuery.data ?? [],
    isLoading:
      (!roadmapId && listQuery.isLoading) ||
      (Boolean(resolvedId) && detailQuery.isLoading),
    isError: listQuery.isError || detailQuery.isError,
    error: (listQuery.error ?? detailQuery.error) as Error | null,
    isEmpty,
  };
}
