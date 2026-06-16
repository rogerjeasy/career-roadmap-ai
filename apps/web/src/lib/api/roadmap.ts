import { apiClient } from "./client";
import type { RoadmapDetail } from "@/types/roadmap.types";

export interface PhaseUpdateInput {
  title?: string;
  description?: string;
  durationWeeks?: number;
  milestones?: string[];
  skillsToGain?: string[];
}

export interface PhaseCreateInput {
  title: string;
  description?: string;
  durationWeeks?: number;
  milestones?: string[];
  skillsToGain?: string[];
}

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

export interface RoadmapProgress {
  roadmapId: string;
  /** Completed milestone keys, each `${phaseId}:${milestoneIndex}`. */
  completedMilestones: string[];
  updatedAt: string | null;
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

  async getProgress(id: string): Promise<RoadmapProgress> {
    const { data } = await apiClient.get<RoadmapProgress>(
      `/api/v1/roadmaps/${id}/progress`,
    );
    return data;
  },

  async toggleMilestone(id: string, key: string): Promise<RoadmapProgress> {
    const { data } = await apiClient.post<RoadmapProgress>(
      `/api/v1/roadmaps/${id}/progress/toggle`,
      { key },
    );
    return data;
  },

  // ── Editing ──────────────────────────────────────────────────────────────

  async addPhase(id: string, input: PhaseCreateInput): Promise<RoadmapDetail> {
    const { data } = await apiClient.post<RoadmapDetail>(
      `/api/v1/roadmaps/${id}/phases`,
      input,
    );
    return data;
  },

  async updatePhase(
    id: string,
    phaseId: string,
    input: PhaseUpdateInput,
  ): Promise<RoadmapDetail> {
    const { data } = await apiClient.patch<RoadmapDetail>(
      `/api/v1/roadmaps/${id}/phases/${phaseId}`,
      input,
    );
    return data;
  },

  async deletePhase(id: string, phaseId: string): Promise<RoadmapDetail> {
    const { data } = await apiClient.delete<RoadmapDetail>(
      `/api/v1/roadmaps/${id}/phases/${phaseId}`,
    );
    return data;
  },

  async reorderPhases(id: string, phaseIds: string[]): Promise<RoadmapDetail> {
    const { data } = await apiClient.post<RoadmapDetail>(
      `/api/v1/roadmaps/${id}/phases/reorder`,
      { phaseIds },
    );
    return data;
  },
};
