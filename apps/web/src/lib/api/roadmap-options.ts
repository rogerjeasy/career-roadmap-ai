import { apiClient } from "./client";

export type StrategyType = "aggressive" | "balanced" | "long_term";

export interface StrategyPhase {
  title: string;
  durationWeeks: number;
  focus: string;
}

export interface RoadmapStrategyOption {
  id: string;
  strategy: StrategyType;
  title: string;
  timelineMonths: number;
  weeklyHours: number;
  intensity: string;
  summary: string;
  phases: StrategyPhase[];
  tradeoffs: string[];
  risks: string[];
  bestFor: string;
  selected: boolean;
}

export interface RoadmapOptionsSet {
  hasData: boolean;
  basedOn: string;
  options: RoadmapStrategyOption[];
  selectedStrategy: StrategyType | null;
  generatedAt: string | null;
}

export const roadmapOptionsApi = {
  async get(): Promise<RoadmapOptionsSet> {
    const { data } = await apiClient.get<RoadmapOptionsSet>("/api/v1/roadmap-options");
    return data;
  },

  async generate(): Promise<RoadmapOptionsSet> {
    const { data } = await apiClient.post<RoadmapOptionsSet>("/api/v1/roadmap-options/generate");
    return data;
  },

  async select(strategy: StrategyType): Promise<RoadmapOptionsSet> {
    const { data } = await apiClient.post<RoadmapOptionsSet>("/api/v1/roadmap-options/select", {
      strategy,
    });
    return data;
  },
};
