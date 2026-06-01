import { apiClient } from "./client";

export type NotificationTone = "info" | "success" | "warn";

export interface ApiNotification {
  id: string;
  title: string;
  body: string;
  tone: NotificationTone;
  link: string | null;
  read: boolean;
  createdAt: string;
}

export interface NotificationListResponse {
  items: ApiNotification[];
  unreadCount: number;
}

export const notificationsApi = {
  async list(limit = 30): Promise<NotificationListResponse> {
    const { data } = await apiClient.get<NotificationListResponse>("/api/v1/notifications", {
      params: { limit },
    });
    return data;
  },

  async markRead(id: string): Promise<ApiNotification> {
    const { data } = await apiClient.patch<ApiNotification>(`/api/v1/notifications/${id}/read`);
    return data;
  },

  async markAllRead(): Promise<number> {
    const { data } = await apiClient.post<{ updated: number }>("/api/v1/notifications/read-all");
    return data.updated;
  },

  async remove(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/notifications/${id}`);
  },
};
