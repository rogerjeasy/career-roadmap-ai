import { apiClient } from "./client";

export type NewsletterFrequency = "weekly" | "biweekly" | "monthly";

export interface NewsletterPrefs {
  subscribed: boolean;
  frequency: NewsletterFrequency;
  topics: string[];
  updatedAt: string | null;
}

export interface NewsletterPrefsInput {
  subscribed: boolean;
  frequency: NewsletterFrequency;
  topics: string[];
}

export const newsletterApi = {
  async get(): Promise<NewsletterPrefs> {
    const { data } = await apiClient.get<NewsletterPrefs>("/api/v1/newsletter");
    return data;
  },

  async update(input: NewsletterPrefsInput): Promise<NewsletterPrefs> {
    const { data } = await apiClient.put<NewsletterPrefs>("/api/v1/newsletter", input);
    return data;
  },
};
