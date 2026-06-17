import { apiClient } from "./client";

export type FeedbackCategory = "bug" | "idea" | "question" | "praise" | "other";

export interface Feedback {
  id: string;
  category: FeedbackCategory;
  subject: string;
  message: string;
  rating: number | null;
  createdAt: string;
}

export interface FeedbackCreateInput {
  category: FeedbackCategory;
  subject: string;
  message: string;
  rating?: number | null;
}

export const feedbackApi = {
  async list(): Promise<Feedback[]> {
    const { data } = await apiClient.get<Feedback[]>("/api/v1/feedback");
    return data;
  },

  async create(input: FeedbackCreateInput): Promise<Feedback> {
    const { data } = await apiClient.post<Feedback>("/api/v1/feedback", input);
    return data;
  },
};
