import { apiClient } from "./client";

export type OutreachChannel = "email" | "linkedin" | "other";
export type OutreachTone = "warm" | "professional" | "concise" | "enthusiastic";
export type DraftStatus = "draft" | "approved" | "sent";

export interface OutreachDraft {
  id: string;
  recipientName: string;
  recipientRole: string;
  channel: OutreachChannel;
  tone: OutreachTone;
  goal: string;
  subject: string;
  body: string;
  status: DraftStatus;
  createdAt: string | null;
}

export interface OutreachDraftRequest {
  recipientName?: string;
  recipientRole?: string;
  channel: OutreachChannel;
  tone: OutreachTone;
  goal: string;
  context?: string;
}

export const outreachApi = {
  async list(): Promise<OutreachDraft[]> {
    const { data } = await apiClient.get<OutreachDraft[]>("/api/v1/outreach");
    return data;
  },

  async draft(req: OutreachDraftRequest): Promise<OutreachDraft> {
    const { data } = await apiClient.post<OutreachDraft>("/api/v1/outreach/draft", req);
    return data;
  },

  async edit(id: string, input: { subject?: string; body?: string }): Promise<OutreachDraft> {
    const { data } = await apiClient.patch<OutreachDraft>(`/api/v1/outreach/${id}`, input);
    return data;
  },

  async approve(id: string): Promise<OutreachDraft> {
    const { data } = await apiClient.post<OutreachDraft>(`/api/v1/outreach/${id}/approve`);
    return data;
  },

  async markSent(id: string): Promise<OutreachDraft> {
    const { data } = await apiClient.post<OutreachDraft>(`/api/v1/outreach/${id}/sent`);
    return data;
  },

  async remove(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/outreach/${id}`);
  },
};
