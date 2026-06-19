import { apiClient } from "./client";

export interface OssIssue {
  issueId: number;
  title: string;
  url: string;
  repo: string;
  repoUrl: string;
  language: string;
  labels: string[];
  comments: number;
  updatedAt: string;
  matchScore: number;
  matchReason: string;
}

export interface OssSearchResult {
  issues: OssIssue[];
  languagesUsed: string[];
  queryUsed: string;
  note: string;
}

export interface OssBookmark {
  id: string;
  issueId: number;
  title: string;
  url: string;
  repo: string;
  language: string;
  labels: string[];
  status: string;
  createdAt: string | null;
}

export interface OssBookmarkCreateInput {
  issueId: number;
  title: string;
  url: string;
  repo?: string;
  language?: string;
  labels?: string[];
  status?: string;
}

export const ossApi = {
  async search(language?: string, query?: string): Promise<OssSearchResult> {
    const { data } = await apiClient.get<OssSearchResult>("/api/v1/oss/issues", {
      params: { language: language || undefined, query: query || undefined },
    });
    return data;
  },

  async listBookmarks(): Promise<OssBookmark[]> {
    const { data } = await apiClient.get<OssBookmark[]>("/api/v1/oss/bookmarks");
    return data;
  },

  async addBookmark(input: OssBookmarkCreateInput): Promise<OssBookmark> {
    const { data } = await apiClient.post<OssBookmark>("/api/v1/oss/bookmarks", input);
    return data;
  },

  async updateStatus(id: string, status: string): Promise<OssBookmark> {
    const { data } = await apiClient.patch<OssBookmark>(`/api/v1/oss/bookmarks/${id}`, {
      status,
    });
    return data;
  },

  async removeBookmark(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/oss/bookmarks/${id}`);
  },
};
