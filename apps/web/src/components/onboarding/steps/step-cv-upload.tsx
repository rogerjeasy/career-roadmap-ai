"use client";

import { useCallback, useState } from "react";
import { toast } from "sonner";
import { CvDropzone } from "@/components/onboarding/cv-dropzone";
import { CvAltInputs } from "@/components/onboarding/cv-alt-inputs";
import { cvApi } from "@/lib/api/cv";
import { useOnboardingStore } from "@/store/onboarding-store";
import { useAgentStore } from "@/store/agent.store";

export interface StepCvUploadProps {
  onBack: () => void;
  onNext: () => void;
}

export function StepCvUpload({ onBack, onNext }: StepCvUploadProps) {
  const { cvResult, setCvResult, resetDownstreamSteps } = useOnboardingStore();
  const resetAgent = useAgentStore((s) => s.reset);

  // File is not serializable → kept in local state only
  const [file, setFile] = useState<File | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);

  const handleFileSelect = useCallback(
    async (picked: File) => {
      // A new CV upload starts a fresh session — wipe all data from steps 3–5
      // so the user never carries forward direction, constraints, or generation
      // state from a previous run.
      resetDownstreamSteps();
      resetAgent();

      setFile(picked);
      setCvResult(null);
      setIsAnalyzing(true);
      try {
        const result = await cvApi.upload(picked);
        setCvResult(result);
        toast.success("CV parsed successfully");
      } catch {
        toast.error("Failed to parse CV — please try again.");
        setFile(null);
      } finally {
        setIsAnalyzing(false);
      }
    },
    [setCvResult, resetDownstreamSteps, resetAgent],
  );

  const handleReplace = useCallback(() => {
    resetDownstreamSteps();
    resetAgent();
    setFile(null);
    setCvResult(null);
  }, [setCvResult, resetDownstreamSteps, resetAgent]);

  const handleUrlSubmit = useCallback((url: string) => {
    toast.info(`URL import coming soon — please upload a CV file for now. (${url})`);
  }, []);

  return (
    <section>
      <div className="mb-9 max-w-[720px]">
        <p className="mb-[22px] inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-terra">
          <span className="font-serif text-[13px] italic font-medium normal-case tracking-normal text-ink-3">
            Step two of five
          </span>
          · Your CV
        </p>
        <h2 className="mb-4 font-serif font-[350] text-[clamp(32px,4.5vw,48px)] leading-[1.05] tracking-[-0.025em] text-ink">
          Bring your <em className="italic text-green">professional self</em> into the room.
        </h2>
        <p className="text-[16px] leading-[1.55] text-ink-2">
          Drop your CV here. We&apos;ll extract your skills, experience and impact signals — then
          use them to draft a roadmap that matches who you actually are.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-[22px] lg:grid-cols-2">
        <CvDropzone
          file={file}
          isAnalyzing={isAnalyzing}
          cvResult={cvResult}
          onFileSelect={handleFileSelect}
          onReplace={handleReplace}
        />
        <CvAltInputs onUrlSubmit={handleUrlSubmit} />
      </div>

      <div className="mt-11 flex items-center justify-between border-t border-rule pt-6">
        <button
          type="button"
          onClick={onBack}
          className="text-[14px] font-medium text-ink-3 transition-colors hover:text-ink"
        >
          ← Back
        </button>
        <div className="flex items-center gap-3">
          {!cvResult && !isAnalyzing && (
            <button
              type="button"
              onClick={onNext}
              className="text-[14px] font-medium text-green transition-colors hover:text-green-2"
            >
              Skip — let AI suggest paths
            </button>
          )}
          <button
            type="button"
            onClick={onNext}
            disabled={isAnalyzing}
            className="group inline-flex items-center gap-2 rounded-lg bg-ink px-5 py-3 text-[14px] font-medium text-bg transition-all hover:-translate-y-px hover:bg-green-2 hover:shadow-[0_8px_20px_-8px_rgba(14,58,43,0.4)] disabled:translate-y-0 disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none"
          >
            {isAnalyzing ? "Analysing…" : "Confirm & continue"}
            {!isAnalyzing && (
              <span className="transition-transform group-hover:translate-x-0.5" aria-hidden="true">
                →
              </span>
            )}
          </button>
        </div>
      </div>
    </section>
  );
}

