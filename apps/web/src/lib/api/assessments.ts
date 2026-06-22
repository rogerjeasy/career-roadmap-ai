import { apiClient } from "./client";

export type AssessmentStatus = "in_progress" | "graded";
export type QuestionKind = "mcq" | "short";
export type SkillLevel = "beginner" | "intermediate" | "advanced" | "expert";

export interface QuizQuestion {
  id: string;
  kind: QuestionKind;
  prompt: string;
  options: string[];
}

export interface MeasuredGap {
  topic: string;
  note: string;
}

export interface Assessment {
  id: string;
  skill: string;
  status: AssessmentStatus;
  numQuestions: number;
  questions: QuizQuestion[];
  score: number | null;
  level: SkillLevel | null;
  passed: boolean;
  summary: string;
  strengths: string[];
  gaps: MeasuredGap[];
  credentialId: string | null;
  evidenceId: string | null;
  createdAt: string | null;
  gradedAt: string | null;
}

export interface AssessmentSummary {
  id: string;
  skill: string;
  status: AssessmentStatus;
  score: number | null;
  level: SkillLevel | null;
  passed: boolean;
  createdAt: string | null;
}

export interface AssessmentStartInput {
  skill: string;
  numQuestions?: number;
}

export interface AssessmentAnswerInput {
  questionId: string;
  answer: string;
}

export const assessmentsApi = {
  async list(): Promise<AssessmentSummary[]> {
    const { data } = await apiClient.get<AssessmentSummary[]>("/api/v1/assessments");
    return data;
  },

  async get(id: string): Promise<Assessment> {
    const { data } = await apiClient.get<Assessment>(`/api/v1/assessments/${id}`);
    return data;
  },

  async start(input: AssessmentStartInput): Promise<Assessment> {
    const { data } = await apiClient.post<Assessment>("/api/v1/assessments", input);
    return data;
  },

  async submit(id: string, answers: AssessmentAnswerInput[]): Promise<Assessment> {
    const { data } = await apiClient.post<Assessment>(
      `/api/v1/assessments/${id}/submit`,
      { answers },
    );
    return data;
  },
};
