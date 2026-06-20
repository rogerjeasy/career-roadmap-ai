import { apiClient } from "./client";

export interface Webhook {
  id: string;
  url: string;
  events: string[];
  active: boolean;
  secretPrefix: string;
  lastStatus: number | null;
  lastDeliveryAt: string | null;
  createdAt: string | null;
}

export interface WebhookCreated extends Webhook {
  secret: string;
}

export interface WebhookPingResult {
  delivered: boolean;
  status: number | null;
  detail: string;
}

export const WEBHOOK_EVENTS = [
  "*",
  "application.created",
  "application.status_changed",
  "credential.issued",
  "roadmap.updated",
  "interview.completed",
] as const;

export const webhooksApi = {
  async list(): Promise<Webhook[]> {
    const { data } = await apiClient.get<Webhook[]>("/api/v1/webhooks");
    return data;
  },

  async create(url: string, events: string[]): Promise<WebhookCreated> {
    const { data } = await apiClient.post<WebhookCreated>("/api/v1/webhooks", { url, events });
    return data;
  },

  async ping(id: string): Promise<WebhookPingResult> {
    const { data } = await apiClient.post<WebhookPingResult>(`/api/v1/webhooks/${id}/ping`);
    return data;
  },

  async remove(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/webhooks/${id}`);
  },
};
