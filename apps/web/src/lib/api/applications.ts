import { apiClient } from "./client";

export type ApplicationStatus =
  | "saved"
  | "applied"
  | "interviewing"
  | "offer"
  | "rejected"
  | "accepted"
  | "withdrawn";

export interface TailoredCv {
  summary: string;
  bullets: string[];
  matchedKeywords: string[];
  missingKeywords: string[];
  fitScore: number;
  advice: string;
  generatedAt: string | null;
}

export interface CoverLetter {
  content: string;
  generatedAt: string | null;
}

export interface Application {
  id: string;
  company: string;
  role: string;
  jobUrl: string;
  jobDescription: string;
  location: string;
  salary: string;
  status: ApplicationStatus;
  notes: string;
  tailoredCv: TailoredCv | null;
  coverLetter: CoverLetter | null;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface ApplicationCreateInput {
  company: string;
  role: string;
  jobUrl?: string;
  jobDescription?: string;
  location?: string;
  salary?: string;
  status?: ApplicationStatus;
  notes?: string;
}

export type ApplicationUpdateInput = Partial<ApplicationCreateInput>;

export interface ApplicationSummary {
  total: number;
  byStatus: Record<string, number>;
  active: number;
}

export const applicationsApi = {
  async list(): Promise<Application[]> {
    const { data } = await apiClient.get<Application[]>("/api/v1/applications");
    return data;
  },

  async summary(): Promise<ApplicationSummary> {
    const { data } = await apiClient.get<ApplicationSummary>("/api/v1/applications/summary");
    return data;
  },

  async get(id: string): Promise<Application> {
    const { data } = await apiClient.get<Application>(`/api/v1/applications/${id}`);
    return data;
  },

  async create(input: ApplicationCreateInput): Promise<Application> {
    const { data } = await apiClient.post<Application>("/api/v1/applications", input);
    return data;
  },

  async update(id: string, input: ApplicationUpdateInput): Promise<Application> {
    const { data } = await apiClient.patch<Application>(`/api/v1/applications/${id}`, input);
    return data;
  },

  async remove(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/applications/${id}`);
  },

  async tailorCv(id: string): Promise<Application> {
    const { data } = await apiClient.post<Application>(`/api/v1/applications/${id}/tailor-cv`);
    return data;
  },

  async coverLetter(id: string): Promise<Application> {
    const { data } = await apiClient.post<Application>(`/api/v1/applications/${id}/cover-letter`);
    return data;
  },
};
