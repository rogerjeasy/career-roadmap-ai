import { apiClient } from "./client";

export interface CoachChatResponse {
  requestId: string;
  sessionId: string;
  streamChannel: string;
  message: string;
}

export interface CoachTurn {
  role: "user" | "assistant" | string;
  content: string;
  timestamp: string;
}

export interface CoachHistoryResponse {
  turns: CoachTurn[];
  total: number;
}

export const coachApi = {
  /** Dispatch a coaching query (202). Response streams via SSE on the session. */
  async sendMessage(message: string): Promise<CoachChatResponse> {
    const { data } = await apiClient.post<CoachChatResponse>("/api/v1/coach/chat", {
      message,
    });
    return data;
  },

  async getHistory(limit = 20): Promise<CoachHistoryResponse> {
    const { data } = await apiClient.get<CoachHistoryResponse>("/api/v1/coach/history", {
      params: { limit },
    });
    return data;
  },
};
