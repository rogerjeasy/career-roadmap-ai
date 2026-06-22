import { apiClient } from "./client";

export type ApplicationStatus =
  | "saved"
  | "applied"
  | "screening"
  | "interview"
  | "offer"
  | "closed";

export type ApplicationOutcome = "accepted" | "rejected" | "withdrawn";

export interface BulletChange {
  before: string;
  after: string;
}

export interface TailoredCv {
  summary: string;
  bullets: string[];
  changes: BulletChange[];
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

export interface StatusEvent {
  status: ApplicationStatus;
  outcome: ApplicationOutcome | null;
  note: string;
  at: string | null;
}

export interface Reminder {
  id: string;
  title: string;
  dueAt: string;
  done: boolean;
  createdAt: string | null;
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
  outcome: ApplicationOutcome | null;
  notes: string;
  stageNotes: Record<string, string>;
  timeline: StatusEvent[];
  reminders: Reminder[];
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

export interface ApplicationUpdateInput
  extends Partial<ApplicationCreateInput> {
  outcome?: ApplicationOutcome | null;
}

export interface ApplicationSummary {
  total: number;
  byStatus: Record<string, number>;
  active: number;
  dueReminders: number;
}

export interface ReminderCreateInput {
  title: string;
  dueAt: string;
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

  async setStageNote(id: string, stage: ApplicationStatus, note: string): Promise<Application> {
    const { data } = await apiClient.put<Application>(
      `/api/v1/applications/${id}/stage-notes/${stage}`,
      { note },
    );
    return data;
  },

  async addReminder(id: string, input: ReminderCreateInput): Promise<Application> {
    const { data } = await apiClient.post<Application>(
      `/api/v1/applications/${id}/reminders`,
      input,
    );
    return data;
  },

  async setReminderDone(id: string, reminderId: string, done: boolean): Promise<Application> {
    const { data } = await apiClient.patch<Application>(
      `/api/v1/applications/${id}/reminders/${reminderId}`,
      { done },
    );
    return data;
  },

  async removeReminder(id: string, reminderId: string): Promise<Application> {
    const { data } = await apiClient.delete<Application>(
      `/api/v1/applications/${id}/reminders/${reminderId}`,
    );
    return data;
  },
};
