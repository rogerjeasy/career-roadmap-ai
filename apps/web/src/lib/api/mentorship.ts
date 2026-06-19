import { apiClient } from "./client";

export type SessionStatus = "requested" | "accepted" | "declined" | "completed";

export interface MentorProfile {
  userId: string;
  name: string;
  headline: string;
  bio: string;
  expertise: string[];
  capacity: number;
  isActive: boolean;
  matchScore: number;
  matchReason: string;
  createdAt: string | null;
}

export interface MentorProfileUpsertInput {
  headline: string;
  bio?: string;
  expertise?: string[];
  capacity?: number;
  isActive?: boolean;
}

export interface MentorSession {
  id: string;
  mentorId: string;
  mentorName: string;
  menteeId: string;
  menteeName: string;
  topic: string;
  message: string;
  reply: string;
  status: SessionStatus;
  role: "mentor" | "mentee";
  createdAt: string | null;
  respondedAt: string | null;
}

export interface SessionRequestInput {
  mentorId: string;
  topic: string;
  message?: string;
}

export interface SessionRespondInput {
  decision: "accepted" | "declined";
  reply?: string;
}

export interface CaseStudy {
  id: string;
  authorName: string;
  fromRole: string;
  toRole: string;
  timeframeMonths: number;
  summary: string;
  steps: string[];
  lessons: string[];
  isMine: boolean;
  createdAt: string | null;
}

export interface CaseStudyCreateInput {
  fromRole: string;
  toRole: string;
  timeframeMonths?: number;
  summary: string;
  steps?: string[];
  lessons?: string[];
  isAnonymous?: boolean;
}

export const mentorshipApi = {
  async getProfile(): Promise<MentorProfile | null> {
    const { data } = await apiClient.get<MentorProfile | null>("/api/v1/mentorship/profile");
    return data;
  },

  async upsertProfile(input: MentorProfileUpsertInput): Promise<MentorProfile> {
    const { data } = await apiClient.put<MentorProfile>("/api/v1/mentorship/profile", input);
    return data;
  },

  async deactivateProfile(): Promise<void> {
    await apiClient.delete("/api/v1/mentorship/profile");
  },

  async discoverMentors(): Promise<MentorProfile[]> {
    const { data } = await apiClient.get<MentorProfile[]>("/api/v1/mentorship/mentors");
    return data;
  },

  async listSessions(): Promise<MentorSession[]> {
    const { data } = await apiClient.get<MentorSession[]>("/api/v1/mentorship/sessions");
    return data;
  },

  async requestSession(input: SessionRequestInput): Promise<MentorSession> {
    const { data } = await apiClient.post<MentorSession>("/api/v1/mentorship/sessions", input);
    return data;
  },

  async respondSession(id: string, input: SessionRespondInput): Promise<MentorSession> {
    const { data } = await apiClient.post<MentorSession>(
      `/api/v1/mentorship/sessions/${id}/respond`,
      input,
    );
    return data;
  },

  async completeSession(id: string): Promise<MentorSession> {
    const { data } = await apiClient.post<MentorSession>(
      `/api/v1/mentorship/sessions/${id}/complete`,
    );
    return data;
  },

  async listCaseStudies(): Promise<CaseStudy[]> {
    const { data } = await apiClient.get<CaseStudy[]>("/api/v1/mentorship/case-studies");
    return data;
  },

  async createCaseStudy(input: CaseStudyCreateInput): Promise<CaseStudy> {
    const { data } = await apiClient.post<CaseStudy>("/api/v1/mentorship/case-studies", input);
    return data;
  },

  async deleteCaseStudy(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/mentorship/case-studies/${id}`);
  },
};
