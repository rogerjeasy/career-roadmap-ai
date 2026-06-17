import { apiClient } from "./client";

export type ProjectStatus = "live" | "in_progress" | "archived";

export interface PortfolioItem {
  id: string;
  title: string;
  description: string;
  role: string;
  url: string;
  repoUrl: string;
  status: ProjectStatus;
  dateLabel: string;
  tech: string[];
  highlights: string[];
  createdAt: string;
}

export interface PortfolioItemCreateInput {
  title: string;
  description?: string;
  role?: string;
  url?: string;
  repoUrl?: string;
  status?: ProjectStatus;
  dateLabel?: string;
  tech?: string[];
  highlights?: string[];
}

export type PortfolioItemUpdateInput = Partial<PortfolioItemCreateInput>;

export const portfolioApi = {
  async list(): Promise<PortfolioItem[]> {
    const { data } = await apiClient.get<PortfolioItem[]>("/api/v1/portfolio");
    return data;
  },

  async create(input: PortfolioItemCreateInput): Promise<PortfolioItem> {
    const { data } = await apiClient.post<PortfolioItem>("/api/v1/portfolio", input);
    return data;
  },

  async update(
    id: string,
    input: PortfolioItemUpdateInput,
  ): Promise<PortfolioItem> {
    const { data } = await apiClient.patch<PortfolioItem>(
      `/api/v1/portfolio/${id}`,
      input,
    );
    return data;
  },

  async remove(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/portfolio/${id}`);
  },
};
