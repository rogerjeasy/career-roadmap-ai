import { apiClient } from "./client";

export type ContactTopic = "sales" | "support" | "partnership" | "general";

export interface ContactRequestInput {
  name: string;
  email: string;
  company?: string;
  topic: ContactTopic;
  message: string;
}

export interface ContactAck {
  received: boolean;
  message: string;
}

export const contactApi = {
  /** Public — no auth required. */
  async submit(input: ContactRequestInput): Promise<ContactAck> {
    const { data } = await apiClient.post<ContactAck>("/api/v1/contact", input);
    return data;
  },
};
