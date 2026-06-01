import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { CvAnalysisResult } from "@/types/onboarding.types";

interface CvState {
  analysis: CvAnalysisResult | null;
  fileName: string | null;
  analysedAt: string | null;

  setAnalysis: (analysis: CvAnalysisResult, fileName: string) => void;
  clear: () => void;
}

export const useCvStore = create<CvState>()(
  persist(
    (set) => ({
      analysis: null,
      fileName: null,
      analysedAt: null,

      setAnalysis: (analysis, fileName) =>
        set({ analysis, fileName, analysedAt: new Date().toISOString() }),

      clear: () => set({ analysis: null, fileName: null, analysedAt: null }),
    }),
    { name: "crai-cv-analysis", version: 1 },
  ),
);
