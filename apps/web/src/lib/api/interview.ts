import { apiClient } from "./client";

export type InterviewType =
  | "behavioral"
  | "technical"
  | "system_design"
  | "role_specific"
  | "mixed";

export interface InterviewQuestion {
  question: string;
  category: string;
  assesses: string;
  answerTips: string[];
}

export interface QuestionSet {
  role: string;
  interviewType: InterviewType;
  questions: InterviewQuestion[];
}

export interface QuestionRequest {
  role: string;
  company?: string;
  interviewType: InterviewType;
  jobDescription?: string;
  count?: number;
}

export interface TurnMessage {
  role: "candidate" | "interviewer";
  content: string;
}

export interface TurnInput {
  role: string;
  company?: string;
  interviewType: InterviewType;
  currentQuestion?: string;
  history: TurnMessage[];
  answer: string;
}

export interface TurnReply {
  feedback: string;
  score: number;
  strengths: string[];
  improvements: string[];
  nextQuestion: string;
  done: boolean;
}

export interface InterviewSession {
  id: string;
  role: string;
  company: string;
  interviewType: InterviewType;
  overallScore: number;
  transcript: TurnMessage[];
  notes: string;
  createdAt: string | null;
}

export interface SessionCreateInput {
  role: string;
  company?: string;
  interviewType: InterviewType;
  overallScore: number;
  transcript: TurnMessage[];
  notes?: string;
}

export const interviewApi = {
  async generateQuestions(req: QuestionRequest): Promise<QuestionSet> {
    const { data } = await apiClient.post<QuestionSet>("/api/v1/interview/questions", req);
    return data;
  },

  async turn(input: TurnInput): Promise<TurnReply> {
    const { data } = await apiClient.post<TurnReply>("/api/v1/interview/turn", input);
    return data;
  },

  async listSessions(): Promise<InterviewSession[]> {
    const { data } = await apiClient.get<InterviewSession[]>("/api/v1/interview/sessions");
    return data;
  },

  async saveSession(input: SessionCreateInput): Promise<InterviewSession> {
    const { data } = await apiClient.post<InterviewSession>("/api/v1/interview/sessions", input);
    return data;
  },

  async deleteSession(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/interview/sessions/${id}`);
  },
};
