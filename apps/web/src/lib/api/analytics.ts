import { apiClient } from "./client";

export interface ApplicationsFunnel {
  total: number;
  byStatus: Record<string, number>;
  active: number;
  offers: number;
  interviewRate: number;
  offerRate: number;
}

export interface LearningSummary {
  items: number;
  totalCost: number;
  totalHours: number;
  avgRoi: number;
}

export interface WellnessSummary {
  checkins: number;
  latestRisk: number | null;
  latestLevel: string | null;
}

export interface AssetCounts {
  evidence: number;
  portfolio: number;
  credentials: number;
  storyDrafts: number;
  ossBookmarks: number;
}

export interface MomentumSummary {
  weeklyReviews: number;
  daysSinceReview: number | null;
  habitsTracked: number;
  interviewPractices: number;
}

export interface AnalyticsOverview {
  applications: ApplicationsFunnel;
  learning: LearningSummary;
  wellness: WellnessSummary;
  assets: AssetCounts;
  momentum: MomentumSummary;
}

export const analyticsApi = {
  async overview(): Promise<AnalyticsOverview> {
    const { data } = await apiClient.get<AnalyticsOverview>("/api/v1/analytics/overview");
    return data;
  },
};
