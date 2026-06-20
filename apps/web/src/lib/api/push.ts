import { apiClient } from "./client";

export interface PushConfig {
  enabled: boolean;
  publicKey: string | null;
}

export interface PushSendResult {
  sent: number;
  failed: number;
  enabled: boolean;
  detail: string;
}

interface SubscribeBody {
  endpoint: string;
  keys: { p256dh: string; auth: string };
  expirationTime: number | null;
}

export const pushApi = {
  async config(): Promise<PushConfig> {
    const { data } = await apiClient.get<PushConfig>("/api/v1/push/config");
    return data;
  },

  async subscribe(body: SubscribeBody): Promise<void> {
    await apiClient.post("/api/v1/push/subscribe", body);
  },

  async unsubscribe(endpoint: string): Promise<void> {
    await apiClient.post("/api/v1/push/unsubscribe", { endpoint });
  },

  async test(): Promise<PushSendResult> {
    const { data } = await apiClient.post<PushSendResult>("/api/v1/push/test");
    return data;
  },
};
