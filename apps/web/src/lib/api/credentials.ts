import { apiClient } from "./client";

export type CredentialLevel = "beginner" | "intermediate" | "advanced" | "expert";
export type CredentialStatus = "active" | "revoked";

export interface CredentialEvidenceRef {
  evidenceId: string;
  title: string;
  type: string;
  link: string;
  dateLabel: string;
}

export interface Credential {
  id: string;
  skill: string;
  level: CredentialLevel;
  summary: string;
  holderName: string;
  evidence: CredentialEvidenceRef[];
  status: CredentialStatus;
  signature: string;
  shareToken: string;
  verifyUrl: string;
  issuedAt: string | null;
  revokedAt: string | null;
}

export interface CredentialIssueInput {
  skill: string;
  level: CredentialLevel;
  summary?: string;
  evidenceIds: string[];
}

export interface CredentialVerification {
  valid: boolean;
  status: CredentialStatus | null;
  reason: string;
  skill: string | null;
  level: CredentialLevel | null;
  summary: string | null;
  holderName: string | null;
  evidenceCount: number;
  evidence: CredentialEvidenceRef[];
  issuedAt: string | null;
  revokedAt: string | null;
}

export const credentialsApi = {
  async list(): Promise<Credential[]> {
    const { data } = await apiClient.get<Credential[]>("/api/v1/credentials");
    return data;
  },

  async issue(input: CredentialIssueInput): Promise<Credential> {
    const { data } = await apiClient.post<Credential>("/api/v1/credentials", input);
    return data;
  },

  async revoke(id: string): Promise<Credential> {
    const { data } = await apiClient.post<Credential>(`/api/v1/credentials/${id}/revoke`);
    return data;
  },

  async remove(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/credentials/${id}`);
  },

  /** Public — no auth required. */
  async verify(shareToken: string): Promise<CredentialVerification> {
    const { data } = await apiClient.get<CredentialVerification>(
      `/api/v1/credentials/verify/${shareToken}`,
    );
    return data;
  },
};
