import { apiClient } from "./client";
import type { CvAnalysisResult } from "@/types/onboarding.types";

interface CvUploadResponse {
  analysis: CvAnalysisResult;
  uploadId: string;
}

export const cvApi = {
  async upload(file: File): Promise<CvAnalysisResult> {
    const form = new FormData();
    form.append("file", file);
    const { data } = await apiClient.post<CvUploadResponse>(
      "/api/v1/cv/upload",
      form,
      { headers: { "Content-Type": "multipart/form-data" } },
    );
    return data.analysis;
  },

  /** Import a CV from a public URL — analysed server-side, same result as upload(). */
  async importUrl(url: string): Promise<CvAnalysisResult> {
    const { data } = await apiClient.post<CvUploadResponse>(
      "/api/v1/cv/import-url",
      { url },
    );
    return data.analysis;
  },

  /**
   * Build a CV from a public GitHub profile (username or profile URL).
   * Public data only — analysed server-side, same result as upload().
   */
  async importGithub(handle: string): Promise<CvAnalysisResult> {
    const { data } = await apiClient.post<CvUploadResponse>(
      "/api/v1/cv/import-github",
      { handle },
    );
    return data.analysis;
  },
};
