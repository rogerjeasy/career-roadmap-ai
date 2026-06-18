import { apiClient } from "./client";

export type VisaDifficulty = "easy" | "moderate" | "hard" | "unknown";

export interface VisaPathway {
  name: string;
  summary: string;
  difficulty: VisaDifficulty;
}

export interface SalaryBand {
  currency: string;
  low: number;
  median: number;
  high: number;
  note: string;
}

export interface LocalisationReport {
  id: string;
  country: string;
  role: string;
  summary: string;
  salary: SalaryBand;
  costOfLiving: string;
  visaPathways: VisaPathway[];
  languageRequirements: string;
  hiringCulture: string[];
  networkingChannels: string[];
  relocationSteps: string[];
  confidence: number;
  assumptions: string[];
  generatedAt: string | null;
}

export interface LocalisationReportSummary {
  id: string;
  country: string;
  role: string;
  confidence: number;
  generatedAt: string | null;
}

export const localisationApi = {
  async getReport(
    country: string,
    opts?: { role?: string; refresh?: boolean },
  ): Promise<LocalisationReport> {
    const { data } = await apiClient.get<LocalisationReport>("/api/v1/localisation", {
      params: {
        country,
        ...(opts?.role ? { role: opts.role } : {}),
        ...(opts?.refresh ? { refresh: true } : {}),
      },
    });
    return data;
  },

  async listSaved(): Promise<LocalisationReportSummary[]> {
    const { data } = await apiClient.get<LocalisationReportSummary[]>(
      "/api/v1/localisation/saved",
    );
    return data;
  },

  async remove(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/localisation/${id}`);
  },
};
