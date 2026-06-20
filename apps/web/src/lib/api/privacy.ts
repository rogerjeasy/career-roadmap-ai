import { apiClient } from "./client";

export interface DataExport {
  userId: string;
  generatedAt: string;
  collections: Record<string, Array<Record<string, unknown>>>;
}

export const privacyApi = {
  async export(): Promise<DataExport> {
    const { data } = await apiClient.get<DataExport>("/api/v1/privacy/export");
    return data;
  },

  async purge(): Promise<{ removed: number }> {
    const { data } = await apiClient.post<{ removed: number }>("/api/v1/privacy/purge");
    return data;
  },

  async deleteAccount(): Promise<void> {
    await apiClient.delete("/api/v1/privacy/account");
  },
};
