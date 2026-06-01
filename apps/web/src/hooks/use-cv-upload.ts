"use client";

import { useState, useCallback } from "react";
import { cvApi } from "@/lib/api/cv";
import { useCvStore } from "@/store/cv.store";
import type { CvAnalysisResult } from "@/types/onboarding.types";

export interface UseCvUploadResult {
  analysis: CvAnalysisResult | null;
  fileName: string | null;
  analysedAt: string | null;
  isUploading: boolean;
  error: string | null;
  upload: (file: File) => Promise<void>;
  reset: () => void;
}

export function useCvUpload(): UseCvUploadResult {
  const analysis = useCvStore((s) => s.analysis);
  const fileName = useCvStore((s) => s.fileName);
  const analysedAt = useCvStore((s) => s.analysedAt);
  const setAnalysis = useCvStore((s) => s.setAnalysis);
  const clear = useCvStore((s) => s.clear);

  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const upload = useCallback(
    async (file: File) => {
      setIsUploading(true);
      setError(null);
      try {
        const result = await cvApi.upload(file);
        setAnalysis(result, file.name);
      } catch {
        setError("We couldn't analyse that file. Please try a PDF or Word document.");
      } finally {
        setIsUploading(false);
      }
    },
    [setAnalysis],
  );

  const reset = useCallback(() => {
    clear();
    setError(null);
  }, [clear]);

  return { analysis, fileName, analysedAt, isUploading, error, upload, reset };
}
