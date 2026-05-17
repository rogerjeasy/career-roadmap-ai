import { apiClient } from "./client";

export interface IntakeStartResponse {
  sessionId: string;
  streamChannel: string;
}

export interface IntakeReplyResponse {
  resolved: boolean;
  completeness: number;
}

export const intakeApi = {
  async start(): Promise<IntakeStartResponse> {
    const { data } = await apiClient.post<IntakeStartResponse>("/api/v1/intake/start");
    return data;
  },

  async reply(userReply: string): Promise<IntakeReplyResponse> {
    const { data } = await apiClient.post<IntakeReplyResponse>("/api/v1/intake/reply", {
      userReply,
    });
    return data;
  },
};
