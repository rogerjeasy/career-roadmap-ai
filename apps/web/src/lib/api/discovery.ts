import { apiClient } from "./client";

export type EffortLevel = "low" | "medium" | "high";

export interface SamplePhase {
  title: string;
  durationWeeks: number;
  focus: string;
}

export interface CareerPathOption {
  title: string;
  summary: string;
  fitScore: number;
  effortToSwitch: EffortLevel;
  timelineMonths: number;
  salaryCurrency: string;
  salaryLow: number;
  salaryHigh: number;
  growthOutlook: string;
  keySkillsToGain: string[];
  transferableStrengths: string[];
  samplePhases: SamplePhase[];
  rationale: string;
}

export interface DiscoveryResult {
  paths: CareerPathOption[];
  basedOn: string;
  confidence: number;
  hasData: boolean;
  generatedAt: string | null;
}

export const discoveryApi = {
  async get(): Promise<DiscoveryResult> {
    const { data } = await apiClient.get<DiscoveryResult>("/api/v1/discovery");
    return data;
  },

  async generate(): Promise<DiscoveryResult> {
    const { data } = await apiClient.post<DiscoveryResult>("/api/v1/discovery/generate");
    return data;
  },
};
