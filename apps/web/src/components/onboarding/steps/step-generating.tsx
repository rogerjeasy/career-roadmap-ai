"use client";

import { GenerateProgress } from "@/components/onboarding/generate-progress";
import { useOnboardingStore } from "@/store/onboarding-store";

export interface StepGeneratingProps {
  onComplete: () => void;
  onRetry: () => void;
}

export function StepGenerating({ onComplete, onRetry }: StepGeneratingProps) {
  const { cvResult, direction, constraints, generationSessionId } =
    useOnboardingStore();

  return (
    <section className="pb-16">
      <GenerateProgress
        cvResult={cvResult}
        direction={direction}
        constraints={constraints}
        sessionId={generationSessionId}
        onComplete={onComplete}
        onRetry={onRetry}
      />
    </section>
  );
}
