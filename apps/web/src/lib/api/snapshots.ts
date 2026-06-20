import { apiClient } from "./client";

export interface RoadmapSnapshot {
  id: string;
  roadmapId: string;
  label: string;
  summary: string;
  phaseCount: number;
  auto: boolean;
  createdAt: string | null;
}

export const snapshotsApi = {
  async list(roadmapId: string): Promise<RoadmapSnapshot[]> {
    const { data } = await apiClient.get<RoadmapSnapshot[]>("/api/v1/roadmap-snapshots", {
      params: { roadmapId },
    });
    return data;
  },

  async create(roadmapId: string, label: string): Promise<RoadmapSnapshot> {
    const { data } = await apiClient.post<RoadmapSnapshot>("/api/v1/roadmap-snapshots", {
      roadmapId,
      label,
    });
    return data;
  },

  async restore(id: string): Promise<RoadmapSnapshot> {
    const { data } = await apiClient.post<RoadmapSnapshot>(
      `/api/v1/roadmap-snapshots/${id}/restore`,
    );
    return data;
  },

  async remove(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/roadmap-snapshots/${id}`);
  },
};
