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
};
