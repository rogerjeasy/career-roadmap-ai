import { apiClient } from "./client";

export interface WeeklyReview {
  id: string;
  energy: number;
  focus: number;
  wins: string;
  blockers: string;
  weekOf: string | null;
  hoursInvested: number;
  milestonesClosed: number;
  createdAt: string;
}

export interface WeeklyReviewInput {
  energy: number;
  focus: number;
  wins?: string;
  blockers?: string;
  weekOf?: string | null;
  hoursInvested?: number;
  milestonesClosed?: number;
}

export interface HealthSignalData {
  label: string;
  score: number;
}

export interface HealthSnapshot {
  score: number;
  delta: number | null;
  signals: HealthSignalData[];
  updatedAt: string | null;
}

export const progressApi = {
  async listReviews(limit = 26): Promise<WeeklyReview[]> {
    const { data } = await apiClient.get<WeeklyReview[]>("/api/v1/progress/reviews", {
      params: { limit },
    });
    return data;
  },

  async createReview(input: WeeklyReviewInput): Promise<WeeklyReview> {
    const { data } = await apiClient.post<WeeklyReview>("/api/v1/progress/reviews", input);
    return data;
  },

  async getHealth(): Promise<HealthSnapshot> {
    const { data } = await apiClient.get<HealthSnapshot>("/api/v1/progress/health");
    return data;
  },

  async setHealth(input: {
    score: number;
    delta?: number | null;
    signals: HealthSignalData[];
  }): Promise<HealthSnapshot> {
    const { data } = await apiClient.put<HealthSnapshot>("/api/v1/progress/health", input);
    return data;
  },
};
