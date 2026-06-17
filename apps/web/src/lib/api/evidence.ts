import { apiClient } from "./client";

export type EvidenceType =
  | "achievement"
  | "certification"
  | "project"
  | "recommendation"
  | "metric"
  | "other";

export interface Evidence {
  id: string;
  title: string;
  description: string;
  type: EvidenceType;
  link: string;
  dateLabel: string;
  skills: string[];
  createdAt: string;
}

export interface EvidenceCreateInput {
  title: string;
  description?: string;
  type?: EvidenceType;
  link?: string;
  dateLabel?: string;
  skills?: string[];
}

export type EvidenceUpdateInput = Partial<EvidenceCreateInput>;

export const evidenceApi = {
  async list(): Promise<Evidence[]> {
    const { data } = await apiClient.get<Evidence[]>("/api/v1/evidence");
    return data;
  },

  async create(input: EvidenceCreateInput): Promise<Evidence> {
    const { data } = await apiClient.post<Evidence>("/api/v1/evidence", input);
    return data;
  },

  async update(id: string, input: EvidenceUpdateInput): Promise<Evidence> {
    const { data } = await apiClient.patch<Evidence>(`/api/v1/evidence/${id}`, input);
    return data;
  },

  async remove(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/evidence/${id}`);
  },
};
