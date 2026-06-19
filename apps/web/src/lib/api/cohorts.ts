import { apiClient } from "./client";

export type CohortStatus = "open" | "full" | "archived";
export type CohortCadence = "weekly" | "biweekly";

export interface CohortMember {
  uid: string;
  name: string;
  joinedAt: string | null;
}

export interface Cohort {
  id: string;
  name: string;
  focus: string;
  description: string;
  capacity: number;
  cadence: CohortCadence;
  status: CohortStatus;
  createdBy: string;
  members: CohortMember[];
  memberCount: number;
  isMember: boolean;
  isOwner: boolean;
  matchScore: number;
  matchReason: string;
  createdAt: string | null;
}

export interface Checkin {
  id: string;
  cohortId: string;
  userId: string;
  userName: string;
  done: string;
  next: string;
  blockers: string;
  createdAt: string | null;
}

export interface CohortDashboard {
  cohort: Cohort;
  checkins: Checkin[];
}

export interface CohortCreateInput {
  name: string;
  focus: string;
  description?: string;
  capacity?: number;
  cadence?: CohortCadence;
}

export interface CheckinInput {
  done: string;
  next?: string;
  blockers?: string;
}

export const cohortsApi = {
  async listMine(): Promise<Cohort[]> {
    const { data } = await apiClient.get<Cohort[]>("/api/v1/cohorts");
    return data;
  },

  async discover(): Promise<Cohort[]> {
    const { data } = await apiClient.get<Cohort[]>("/api/v1/cohorts/discover");
    return data;
  },

  async create(input: CohortCreateInput): Promise<Cohort> {
    const { data } = await apiClient.post<Cohort>("/api/v1/cohorts", input);
    return data;
  },

  async dashboard(id: string): Promise<CohortDashboard> {
    const { data } = await apiClient.get<CohortDashboard>(`/api/v1/cohorts/${id}`);
    return data;
  },

  async join(id: string): Promise<Cohort> {
    const { data } = await apiClient.post<Cohort>(`/api/v1/cohorts/${id}/join`);
    return data;
  },

  async leave(id: string): Promise<void> {
    await apiClient.post(`/api/v1/cohorts/${id}/leave`);
  },

  async postCheckin(id: string, input: CheckinInput): Promise<Checkin> {
    const { data } = await apiClient.post<Checkin>(`/api/v1/cohorts/${id}/checkins`, input);
    return data;
  },
};
