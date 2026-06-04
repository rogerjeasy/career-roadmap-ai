import { apiClient } from "./client";

export type IntegrationProvider = "github" | "linkedin" | "calendar";

export interface IntegrationStatus {
  provider: IntegrationProvider;
  name: string;
  description: string;
  consentNote: string;
  /** Server has OAuth client credentials configured for this provider. */
  available: boolean;
  /** The current user has an active connection. */
  connected: boolean;
  accountLabel: string | null;
  connectedAt: string | null;
  scopes: string[];
}

export const integrationsApi = {
  async list(): Promise<IntegrationStatus[]> {
    const { data } = await apiClient.get<IntegrationStatus[]>("/api/v1/integrations");
    return data;
  },

  async authorize(provider: IntegrationProvider): Promise<string> {
    const { data } = await apiClient.post<{ authorizationUrl: string }>(
      `/api/v1/integrations/${provider}/authorize`,
    );
    return data.authorizationUrl;
  },

  async disconnect(provider: IntegrationProvider): Promise<void> {
    await apiClient.delete(`/api/v1/integrations/${provider}`);
  },
};
