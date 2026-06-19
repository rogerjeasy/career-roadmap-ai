import { apiClient } from "./client";

export type LearningType =
  | "course"
  | "book"
  | "certification"
  | "bootcamp"
  | "degree"
  | "article"
  | "other";

export type LearningStatus = "planned" | "in_progress" | "completed" | "abandoned";

export interface LearningItem {
  id: string;
  title: string;
  type: LearningType;
  provider: string;
  cost: number;
  currency: string;
  hours: number;
  status: LearningStatus;
  skills: string[];
  notes: string;
  link: string;
  impactScore: number;
  relevance: number;
  roiScore: number;
  matchedSkills: string[];
  rationale: string;
  rank: number;
  createdAt: string | null;
}

export interface LearningItemCreateInput {
  title: string;
  type?: LearningType;
  provider?: string;
  cost?: number;
  currency?: string;
  hours?: number;
  status?: LearningStatus;
  skills?: string[];
  notes?: string;
  link?: string;
}

export type LearningItemUpdateInput = Partial<LearningItemCreateInput>;

export interface LearningRoiSummary {
  totalItems: number;
  totalCost: number;
  totalHours: number;
  averageRoi: number;
  topItemId: string | null;
  hasMarketSignals: boolean;
}

export const learningApi = {
  async list(): Promise<LearningItem[]> {
    const { data } = await apiClient.get<LearningItem[]>("/api/v1/learning");
    return data;
  },

  async summary(): Promise<LearningRoiSummary> {
    const { data } = await apiClient.get<LearningRoiSummary>("/api/v1/learning/summary");
    return data;
  },

  async create(input: LearningItemCreateInput): Promise<LearningItem> {
    const { data } = await apiClient.post<LearningItem>("/api/v1/learning", input);
    return data;
  },

  async update(id: string, input: LearningItemUpdateInput): Promise<LearningItem> {
    const { data } = await apiClient.patch<LearningItem>(`/api/v1/learning/${id}`, input);
    return data;
  },

  async remove(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/learning/${id}`);
  },
};
