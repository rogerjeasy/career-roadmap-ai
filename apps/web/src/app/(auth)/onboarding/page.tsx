"use client";

import { useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { OnboardingTopbar } from "@/components/onboarding/onboarding-topbar";
import { OnboardingStepper } from "@/components/onboarding/onboarding-stepper";
import { StepWelcome } from "@/components/onboarding/steps/step-welcome";
import { StepCvUpload } from "@/components/onboarding/steps/step-cv-upload";
import { StepDirection } from "@/components/onboarding/steps/step-direction";
import { StepConstraints } from "@/components/onboarding/steps/step-constraints";
import { StepGenerating } from "@/components/onboarding/steps/step-generating";

import { updateUserProfileContext } from "@/lib/api/session";
import { apiClient } from "@/lib/api/client";
import { fixMojibake } from "@/lib/utils";
import { useOnboardingStore } from "@/store/onboarding-store";
import { useAuthStore } from "@/store/auth.store";
import { ROUTES } from "@/lib/constants";
import type { OnboardingStep } from "@/types/onboarding.types";

export default function OnboardingPage() {
  const router = useRouter();
  const { user, isLoading } = useAuthStore();
  const {
    step,
    setStep,
    cvResult,
    direction,
    constraints,
    setGenerationIds,
    reset,
  } = useOnboardingStore();

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!isLoading && !user) {
      router.replace(ROUTES.login);
    }
  }, [isLoading, user, router]);

  const goTo = useCallback((s: OnboardingStep) => setStep(s), [setStep]);

  const handleExit = useCallback(() => {
    router.push(ROUTES.dashboard);
  }, [router]);

  const handleStepperClick = useCallback(
    (s: OnboardingStep) => {
      if (s < step) goTo(s);
    },
    [goTo, step],
  );

  const handleGenerateRoadmap = useCallback(async () => {
    // Persist all collected data into the session profile context
    try {
      await updateUserProfileContext({
        targetRole: direction.goal ? fixMojibake(direction.goal) : undefined,
        currentRole: cvResult?.currentRole ?? undefined,
        skills: cvResult?.skills.map((s) => s.name) ?? [],
        goals: direction.goal ? [direction.goal] : [],
        constraints: [
          constraints.locationPreference,
          ...constraints.workStyles,
        ].filter(Boolean),
        location: constraints.location || undefined,
        timelineMonths: direction.timelineMonths ?? undefined,
        weeklyHoursAvailable: constraints.weeklyHours,
        salaryGoal: constraints.compensationTarget * 1000,
        additional: {
          lifeContext: constraints.lifeContext,
          workStyles: constraints.workStyles,
          cvAnalysis: cvResult
            ? {
                yearsOfExperience: cvResult.yearsOfExperience,
                leadershipSignals: cvResult.leadershipSignals,
                strongSkillsCount: cvResult.strongSkillsCount,
                projects: cvResult.projects.length,
              }
            : null,
        },
      });
    } catch {
      // Non-fatal — we still proceed to generate
    }

    // Dispatch roadmap generation
    try {
      const goalMsg =
        (direction.goal ? fixMojibake(direction.goal) : "") ||
        `Help me build a career roadmap based on my background and goals.`;
      const { data } = await apiClient.post<{
        requestId: string;
        sessionId: string;
        streamChannel: string;
      }>("/api/v1/orchestrator/generate", { message: goalMsg });
      setGenerationIds(data.requestId, data.sessionId);
    } catch {
      toast.error("Failed to start generation — we'll retry. You can still see progress.");
    }

    goTo(5);
  }, [direction, cvResult, constraints, setGenerationIds, goTo]);

  const handleGenerationComplete = useCallback(() => {
    reset();
    router.push(ROUTES.dashboard);
  }, [reset, router]);

  const userName = user?.displayName ?? user?.email ?? null;

  // Show nothing while auth state resolves (redirect effect handles non-auth users)
  if (isLoading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg">
        <svg
          className="animate-spin text-green"
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          aria-label="Loading"
        >
          <path d="M21 12a9 9 0 1 1-6.219-8.56" strokeLinecap="round" />
        </svg>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bg">
      <OnboardingTopbar onExit={handleExit} />
      <OnboardingStepper current={step} onStepClick={handleStepperClick} />

      <div className="mx-auto max-w-[980px] px-5 pb-24 pt-14 sm:px-9">
        {step === 1 && <StepWelcome onNext={() => goTo(2)} />}

        {step === 2 && <StepCvUpload onBack={() => goTo(1)} onNext={() => goTo(3)} />}

        {step === 3 && (
          <StepDirection
            onBack={() => goTo(2)}
            onNext={() => goTo(4)}
            userName={userName}
          />
        )}

        {step === 4 && (
          <StepConstraints onBack={() => goTo(3)} onNext={handleGenerateRoadmap} />
        )}

        {step === 5 && (
          <StepGenerating
            onComplete={handleGenerationComplete}
            onRetry={handleGenerateRoadmap}
          />
        )}
      </div>
    </div>
  );
}
