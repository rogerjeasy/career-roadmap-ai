import { apiClient } from "./client";

export type ContentKind = "linkedin_post" | "build_in_public" | "milestone_announcement";
export type ContentTone = "professional" | "conversational" | "bold" | "reflective";
export type ContentSource = "roadmap_milestone" | "freeform";
export type ContentStatus = "draft" | "approved" | "published";

export interface ContentDraft {
  id: string;
  kind: ContentKind;
  tone: ContentTone;
  title: string;
  content: string;
  hashtags: string[];
  status: ContentStatus;
  basedOn: string;
  createdAt: string | null;
  publishedAt: string | null;
}

export interface ContentGenerateInput {
  kind: ContentKind;
  tone: ContentTone;
  source: ContentSource;
  milestone?: string;
  extraContext?: string;
}

export const contentApi = {
  async list(): Promise<ContentDraft[]> {
    const { data } = await apiClient.get<ContentDraft[]>("/api/v1/content");
    return data;
  },

  async generate(input: ContentGenerateInput): Promise<ContentDraft> {
    const { data } = await apiClient.post<ContentDraft>("/api/v1/content", input);
    return data;
  },

  async setStatus(id: string, status: ContentStatus): Promise<ContentDraft> {
    const { data } = await apiClient.patch<ContentDraft>(`/api/v1/content/${id}/status`, {
      status,
    });
    return data;
  },

  async remove(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/content/${id}`);
  },
};
