import { apiClient } from "./client";

export interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  last4: string;
  revoked: boolean;
  lastUsedAt: string | null;
  createdAt: string | null;
}

export interface ApiKeyCreated extends ApiKey {
  /** The full secret — shown exactly once, never returned again. */
  key: string;
}

export const apiKeysApi = {
  async list(): Promise<ApiKey[]> {
    const { data } = await apiClient.get<ApiKey[]>("/api/v1/api-keys");
    return data;
  },

  async create(name: string): Promise<ApiKeyCreated> {
    const { data } = await apiClient.post<ApiKeyCreated>("/api/v1/api-keys", { name });
    return data;
  },

  async revoke(id: string): Promise<ApiKey> {
    const { data } = await apiClient.post<ApiKey>(`/api/v1/api-keys/${id}/revoke`);
    return data;
  },

  async remove(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/api-keys/${id}`);
  },
};
