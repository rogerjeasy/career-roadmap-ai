import { apiClient } from "./client";

export type Competitiveness = "below" | "at" | "above" | "unknown";

export interface OfferInput {
  role: string;
  company?: string;
  location?: string;
  currency?: string;
  baseSalary?: number;
  bonus?: number;
  equity?: string;
  otherBenefits?: string;
  yearsExperience?: number;
  competingOffer?: string;
  notes?: string;
}

export interface OfferAnalysis {
  id: string;
  offer: Required<Pick<OfferInput, "role">> & OfferInput;
  assessment: string;
  competitiveness: Competitiveness;
  benchmarkLow: number;
  benchmarkHigh: number;
  benchmarkCurrency: string;
  counterBase: number;
  counterRationale: string;
  talkingPoints: string[];
  risks: string[];
  assumptions: string[];
  confidence: number;
  createdAt: string | null;
}

export interface RoleplayMessage {
  role: "user" | "recruiter";
  content: string;
}

export interface RoleplayInput {
  offer: OfferInput;
  history: RoleplayMessage[];
  message: string;
}

export interface RoleplayReply {
  reply: string;
  coaching: string;
  tip: string;
}

export const negotiationApi = {
  async analyze(offer: OfferInput): Promise<OfferAnalysis> {
    const { data } = await apiClient.post<OfferAnalysis>("/api/v1/negotiation/analyze", offer);
    return data;
  },

  async list(): Promise<OfferAnalysis[]> {
    const { data } = await apiClient.get<OfferAnalysis[]>("/api/v1/negotiation/offers");
    return data;
  },

  async remove(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/negotiation/offers/${id}`);
  },

  async roleplay(input: RoleplayInput): Promise<RoleplayReply> {
    const { data } = await apiClient.post<RoleplayReply>("/api/v1/negotiation/roleplay", input);
    return data;
  },
};
