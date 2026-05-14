import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { RoadmapData } from "@/types/roadmap.types";

interface RoadmapState {
  currentRoadmap: RoadmapData | null;
  roadmapSessionId: string | null;
  savedAt: string | null;

  setRoadmap: (roadmap: RoadmapData, sessionId: string) => void;
  clearRoadmap: () => void;
}

export const useRoadmapStore = create<RoadmapState>()(
  persist(
    (set) => ({
      currentRoadmap: null,
      roadmapSessionId: null,
      savedAt: null,

      setRoadmap: (currentRoadmap, roadmapSessionId) =>
        set({
          currentRoadmap,
          roadmapSessionId,
          savedAt: new Date().toISOString(),
        }),

      clearRoadmap: () =>
        set({ currentRoadmap: null, roadmapSessionId: null, savedAt: null }),
    }),
    { name: "crai-roadmap", version: 1 },
  ),
);
