import { apiClient } from "./client";

export type StoryFormat =
  | "resume_bullets"
  | "linkedin_about"
  | "cover_letter"
  | "interview_story";

export type StoryTone = "professional" | "confident" | "warm" | "concise";

export interface StoryDraft {
  id: string;
  format: StoryFormat;
  tone: StoryTone;
  targetRole: string;
  targetCompany: string;
  title: string;
  content: string;
  highlights: string[];
  tips: string[];
  evidenceTitles: string[];
  createdAt: string | null;
}

export interface StoryGenerateInput {
  format: StoryFormat;
  tone: StoryTone;
  targetRole?: string;
  targetCompany?: string;
  evidenceIds: string[];
  extraContext?: string;
}

export const storytellingApi = {
  async generate(input: StoryGenerateInput): Promise<StoryDraft> {
    const { data } = await apiClient.post<StoryDraft>("/api/v1/storytelling/generate", input);
    return data;
  },

  async listDrafts(): Promise<StoryDraft[]> {
    const { data } = await apiClient.get<StoryDraft[]>("/api/v1/storytelling/drafts");
    return data;
  },

  async remove(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/storytelling/drafts/${id}`);
  },
};
