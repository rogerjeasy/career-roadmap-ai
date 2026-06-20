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

export interface DigestArticle {
  title: string;
  why: string;
  url: string | null;
}

export interface DigestPerson {
  name: string;
  reason: string;
  handle: string | null;
}

export interface NewsletterDigest {
  periodLabel: string;
  summary: string;
  articles: DigestArticle[];
  peopleToFollow: DigestPerson[];
  actionItem: string;
  confidence: number;
  hasData: boolean;
  generatedAt: string | null;
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

  async getDigest(): Promise<NewsletterDigest> {
    const { data } = await apiClient.get<NewsletterDigest>("/api/v1/newsletter/digest");
    return data;
  },

  async generateDigest(): Promise<NewsletterDigest> {
    const { data } = await apiClient.post<NewsletterDigest>(
      "/api/v1/newsletter/digest/generate",
    );
    return data;
  },

  async deliverDigest(): Promise<NewsletterDigest> {
    const { data } = await apiClient.post<NewsletterDigest>(
      "/api/v1/newsletter/digest/deliver",
    );
    return data;
  },
};
