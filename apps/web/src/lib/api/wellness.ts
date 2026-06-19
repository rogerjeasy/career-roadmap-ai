import { apiClient } from "./client";

export type RiskLevel = "low" | "moderate" | "high";

export interface WellnessCheckin {
  id: string;
  energy: number;
  stress: number;
  motivation: number;
  hoursWorked: number;
  sleepHours: number;
  notes: string;
  createdAt: string | null;
}

export interface WellnessCheckinInput {
  energy: number;
  stress: number;
  motivation: number;
  hoursWorked?: number;
  sleepHours?: number;
  notes?: string;
}

export interface WellnessStatus {
  riskScore: number;
  riskLevel: RiskLevel;
  trend: string;
  drivers: string[];
  recommendation: string;
  recoverySuggested: boolean;
  sampleSize: number;
}

export const wellnessApi = {
  async status(): Promise<WellnessStatus> {
    const { data } = await apiClient.get<WellnessStatus>("/api/v1/wellness/status");
    return data;
  },

  async list(): Promise<WellnessCheckin[]> {
    const { data } = await apiClient.get<WellnessCheckin[]>("/api/v1/wellness/checkins");
    return data;
  },

  async create(input: WellnessCheckinInput): Promise<WellnessCheckin> {
    const { data } = await apiClient.post<WellnessCheckin>("/api/v1/wellness/checkins", input);
    return data;
  },

  async remove(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/wellness/checkins/${id}`);
  },
};
