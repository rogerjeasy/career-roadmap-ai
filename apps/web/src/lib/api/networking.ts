import { apiClient } from "./client";
import type { ContactStatus } from "@/types/networking.types";

export interface ApiContact {
  id: string;
  name: string;
  role: string;
  company: string;
  status: ContactStatus;
  reason: string | null;
  createdAt: string;
}

export interface ContactInput {
  name: string;
  role?: string;
  company?: string;
  status?: ContactStatus;
  reason?: string | null;
}

export type EventKind = "meetup" | "conference" | "webinar" | "ama";

export interface ApiEvent {
  id: string;
  title: string;
  kind: EventKind;
  dateLabel: string;
  location: string;
  isOnline: boolean;
  createdAt: string;
}

export type OutreachChannel = "email" | "linkedin" | "in_person" | "other";

export interface ApiOutreach {
  id: string;
  contactName: string;
  channel: OutreachChannel;
  note: string;
  createdAt: string;
}

export const networkingApi = {
  // ── Contacts ──
  async listContacts(): Promise<ApiContact[]> {
    const { data } = await apiClient.get<ApiContact[]>("/api/v1/networking/contacts");
    return data;
  },
  async createContact(input: ContactInput): Promise<ApiContact> {
    const { data } = await apiClient.post<ApiContact>("/api/v1/networking/contacts", input);
    return data;
  },
  async updateContact(id: string, input: Partial<ContactInput>): Promise<ApiContact> {
    const { data } = await apiClient.patch<ApiContact>(`/api/v1/networking/contacts/${id}`, input);
    return data;
  },
  async deleteContact(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/networking/contacts/${id}`);
  },

  // ── Events ──
  async listEvents(): Promise<ApiEvent[]> {
    const { data } = await apiClient.get<ApiEvent[]>("/api/v1/networking/events");
    return data;
  },
  async createEvent(input: {
    title: string;
    kind?: EventKind;
    dateLabel?: string;
    location?: string;
    isOnline?: boolean;
  }): Promise<ApiEvent> {
    const { data } = await apiClient.post<ApiEvent>("/api/v1/networking/events", input);
    return data;
  },
  async deleteEvent(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/networking/events/${id}`);
  },

  // ── Outreach log ──
  async listOutreach(limit = 50): Promise<ApiOutreach[]> {
    const { data } = await apiClient.get<ApiOutreach[]>("/api/v1/networking/outreach", {
      params: { limit },
    });
    return data;
  },
  async logOutreach(input: {
    contactName: string;
    channel?: OutreachChannel;
    note?: string;
  }): Promise<ApiOutreach> {
    const { data } = await apiClient.post<ApiOutreach>("/api/v1/networking/outreach", input);
    return data;
  },
};
