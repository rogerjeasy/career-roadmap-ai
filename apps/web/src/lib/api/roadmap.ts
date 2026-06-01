import { apiClient } from "./client";
import type { RoadmapDetail } from "@/types/roadmap.types";

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

  async get(id: string): Promise<RoadmapDetail> {
    const { data } = await apiClient.get<RoadmapDetail>(`/api/v1/roadmaps/${id}`);
    return data;
  },

  async remove(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/roadmaps/${id}`);
  },
};
