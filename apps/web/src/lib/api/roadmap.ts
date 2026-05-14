import { apiClient } from "./client";

export interface RoadmapSummary {
  id: string;
  sessionId: string;
  summary: string;
  confidence: number;
  status: string;
  phaseCount: number;
  createdAt: string;
}

export interface RoadmapSummaryPage {
  items: RoadmapSummary[];
  nextCursor: string | null;
  hasMore: boolean;
}

export const roadmapApi = {
  async list(limit = 20): Promise<RoadmapSummary[]> {
    const { data } = await apiClient.get<RoadmapSummary[]>("/api/v1/roadmaps", {
      params: { limit },
    });
    return data;
  },

  async listPaginated(params: { limit?: number; cursor?: string }): Promise<RoadmapSummaryPage> {
    const { data } = await apiClient.get<RoadmapSummaryPage>("/api/v1/roadmaps/paginated", {
      params,
    });
    return data;
  },
};
