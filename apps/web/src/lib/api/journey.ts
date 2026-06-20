import { apiClient } from "./client";

export interface AskMessage {
  role: "user" | "assistant";
  content: string;
}

export interface AskReply {
  answer: string;
  sources: string[];
  suggestions: string[];
}

export const journeyApi = {
  async ask(question: string, history: AskMessage[]): Promise<AskReply> {
    const { data } = await apiClient.post<AskReply>("/api/v1/journey/ask", {
      question,
      history,
    });
    return data;
  },
};
