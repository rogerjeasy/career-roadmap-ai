"use client";

import { cn } from "@/lib/utils";
import type { OnboardingStep } from "@/types/onboarding.types";

const STEPS: { num: string; label: string }[] = [
  { num: "01", label: "Welcome" },
  { num: "02", label: "Your CV" },
  { num: "03", label: "Your direction" },
  { num: "04", label: "Constraints" },
  { num: "05", label: "Your roadmap" },
];

export interface OnboardingStepperProps {
  current: OnboardingStep;
  onStepClick?: (step: OnboardingStep) => void;
}

export function OnboardingStepper({ current, onStepClick }: OnboardingStepperProps) {
  return (
    <div className="sticky top-[57px] z-40 border-b border-rule bg-bg px-5 pb-5 pt-4 sm:px-9">
      <div className="mx-auto grid max-w-[980px] grid-cols-5 gap-1.5 sm:gap-2">
        {STEPS.map(({ num, label }, i) => {
          const stepNum = (i + 1) as OnboardingStep;
          const isDone = stepNum < current;
          const isCurrent = stepNum === current;
          const isClickable = isDone || isCurrent;

          return (
            <button
              key={num}
              type="button"
              onClick={() => isClickable && onStepClick?.(stepNum)}
              className={cn(
                "flex flex-col gap-2 text-left",
                isClickable ? "cursor-pointer" : "cursor-default",
              )}
              aria-current={isCurrent ? "step" : undefined}
              disabled={!isClickable}
            >
              {/* Progress bar */}
              <div className="relative h-[3px] overflow-hidden rounded-full bg-rule">
                <div
                  className={cn(
                    "absolute inset-y-0 left-0 rounded-full transition-all duration-500",
                    isDone && "w-full bg-green",
                    isCurrent && "w-full bg-terra",
                    !isDone && !isCurrent && "w-0",
                  )}
                />
              </div>

              {/* Label row */}
              <div className="flex items-baseline justify-between gap-2">
                <span className="font-mono text-[10px] font-medium tracking-[0.08em] text-ink-3">
                  {num}
                </span>
                <span
                  className={cn(
                    "hidden text-[12.5px] font-medium transition-colors sm:block",
                    isDone && "text-ink-2",
                    isCurrent && "font-semibold text-ink",
                    !isDone && !isCurrent && "text-ink-3",
                  )}
                >
                  {label}
                </span>
                {isDone && (
                  <span
                    aria-hidden="true"
                    className="flex h-3 w-3 shrink-0 items-center justify-center rounded-full bg-green"
                  >
                    <svg viewBox="0 0 12 12" fill="none" className="h-2 w-2">
                      <path
                        d="M2 6.5l3 3 5-7"
                        stroke="#fff"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

