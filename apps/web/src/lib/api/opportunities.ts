import { apiClient } from "./client";

export interface AlertsResponse {
  alerts: string[];
  targetCompanies: { name: string; [key: string]: unknown }[];
  highMatchCount: number;
  searchQuery: string | null;
}

export interface OpportunitySearchResponse {
  requestId: string;
  sessionId: string;
  streamChannel: string;
  searchQuery: string;
  message: string;
}

export const opportunitiesApi = {
  async getAlerts(): Promise<AlertsResponse> {
    const { data } = await apiClient.get<AlertsResponse>("/api/v1/opportunity/alerts");
    return data;
  },

  async search(payload: { role?: string; location?: string } = {}): Promise<OpportunitySearchResponse> {
    const { data } = await apiClient.post<OpportunitySearchResponse>(
      "/api/v1/opportunity/search",
      payload,
    );
    return data;
  },
};
