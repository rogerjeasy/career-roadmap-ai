import { apiClient } from "./client";

export type TwinVoice = "supportive" | "direct" | "playful" | "stoic" | "analytical";
export type CheckinStatus = "open" | "answered";

export interface TwinPersona {
  name: string;
  voice: TwinVoice;
  focus: string;
  checkInEnabled: boolean;
  createdAt: string | null;
}

export interface TwinPersonaUpsertInput {
  name: string;
  voice: TwinVoice;
  focus?: string;
  checkInEnabled?: boolean;
}

export interface DailyCheckin {
  id: string;
  date: string;
  greeting: string;
  prompt: string;
  focusSuggestion: string;
  userReply: string;
  twinResponse: string;
  mood: number | null;
  status: CheckinStatus;
  createdAt: string | null;
}

export const careerTwinApi = {
  async getPersona(): Promise<TwinPersona> {
    const { data } = await apiClient.get<TwinPersona>("/api/v1/career-twin/persona");
    return data;
  },

  async upsertPersona(input: TwinPersonaUpsertInput): Promise<TwinPersona> {
    const { data } = await apiClient.put<TwinPersona>("/api/v1/career-twin/persona", input);
    return data;
  },

  async today(): Promise<DailyCheckin> {
    const { data } = await apiClient.get<DailyCheckin>("/api/v1/career-twin/today");
    return data;
  },

  async reply(id: string, reply: string, mood?: number): Promise<DailyCheckin> {
    const { data } = await apiClient.post<DailyCheckin>(`/api/v1/career-twin/${id}/reply`, {
      reply,
      mood,
    });
    return data;
  },

  async history(): Promise<DailyCheckin[]> {
    const { data } = await apiClient.get<DailyCheckin[]>("/api/v1/career-twin/history");
    return data;
  },
};
