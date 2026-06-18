import { apiClient } from "./client";

export type ProposalSeverity = "info" | "warn";
export type ProposalStatus = "open" | "accepted" | "dismissed";

export interface AutopilotProposal {
  id: string;
  kind: string;
  title: string;
  detail: string;
  severity: ProposalSeverity;
  actionLabel: string;
  actionRoute: string;
  status: ProposalStatus;
  createdAt: string | null;
}

export const autopilotApi = {
  async list(): Promise<AutopilotProposal[]> {
    const { data } = await apiClient.get<AutopilotProposal[]>("/api/v1/autopilot");
    return data;
  },

  async refresh(): Promise<AutopilotProposal[]> {
    const { data } = await apiClient.post<AutopilotProposal[]>("/api/v1/autopilot/refresh");
    return data;
  },

  async accept(id: string): Promise<AutopilotProposal> {
    const { data } = await apiClient.post<AutopilotProposal>(`/api/v1/autopilot/${id}/accept`);
    return data;
  },

  async dismiss(id: string): Promise<AutopilotProposal> {
    const { data } = await apiClient.post<AutopilotProposal>(`/api/v1/autopilot/${id}/dismiss`);
    return data;
  },
};
