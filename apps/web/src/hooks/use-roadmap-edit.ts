"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  roadmapApi,
  type PhaseCreateInput,
  type PhaseUpdateInput,
} from "@/lib/api/roadmap";
import { QUERY_KEYS } from "@/lib/constants";
import type { RoadmapDetail } from "@/types/roadmap.types";

/**
 * Mutations for editing a roadmap's phases and milestones. Every endpoint
 * returns the full, canonical roadmap, so on success we replace the cached
 * detail directly (no refetch) and invalidate the derived progress + list
 * caches that an edit can affect.
 */
export function useRoadmapEdit(roadmapId: string | null) {
  const queryClient = useQueryClient();

  const onUpdated = (updated: RoadmapDetail) => {
    queryClient.setQueryData(QUERY_KEYS.roadmap(updated.id), updated);
    queryClient.invalidateQueries({ queryKey: QUERY_KEYS.roadmapProgress(updated.id) });
    queryClient.invalidateQueries({ queryKey: QUERY_KEYS.roadmapList });
  };

  const onError = () => toast.error("Couldn't save your changes. Please try again.");

  const updatePhase = useMutation({
    mutationFn: ({ phaseId, input }: { phaseId: string; input: PhaseUpdateInput }) =>
      roadmapApi.updatePhase(roadmapId as string, phaseId, input),
    onSuccess: onUpdated,
    onError,
  });

  const addPhase = useMutation({
    mutationFn: (input: PhaseCreateInput) => roadmapApi.addPhase(roadmapId as string, input),
    onSuccess: (updated) => {
      onUpdated(updated);
      toast.success("Phase added");
    },
    onError,
  });

  const deletePhase = useMutation({
    mutationFn: (phaseId: string) => roadmapApi.deletePhase(roadmapId as string, phaseId),
    onSuccess: (updated) => {
      onUpdated(updated);
      toast.success("Phase deleted");
    },
    onError,
  });

  const reorderPhases = useMutation({
    mutationFn: (phaseIds: string[]) => roadmapApi.reorderPhases(roadmapId as string, phaseIds),
    onSuccess: onUpdated,
    onError,
  });

  return { updatePhase, addPhase, deletePhase, reorderPhases };
}
