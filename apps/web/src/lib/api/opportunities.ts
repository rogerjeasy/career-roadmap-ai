import { apiClient } from "./client";

export interface TargetCompanyAlert {
  name: string;
  reason?: string;
  jobCount?: number;
  topRoles?: string[];
  avgMatchScore?: number;
}

export interface AlertsResponse {
  alerts: string[];
  targetCompanies: TargetCompanyAlert[];
  highMatchCount: number;
  searchQuery: string | null;
}

/** Normalised job match for the UI (assembled from snake_case SSE payloads). */
export interface JobMatch {
  id: string;
  title: string;
  company: string;
  location: string;
  url: string;
  remote: boolean;
  seniorityLevel: string | null;
  salaryMin: number | null;
  salaryMax: number | null;
  matchScore: number;
  skillOverlap: string[];
  missingSkills: string[];
  matchReasons: string[];
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
