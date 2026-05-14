"use client";

import { ConstraintsForm } from "@/components/onboarding/constraints-form";
import { useOnboardingStore } from "@/store/onboarding-store";
import type { LocationPreference } from "@/types/onboarding.types";

export interface StepConstraintsProps {
  onBack: () => void;
  onNext: () => void;
}

export function StepConstraints({ onBack, onNext }: StepConstraintsProps) {
  const {
    constraints,
    setWeeklyHours,
    setLocation,
    setLocationPreference,
    setCompensationTarget,
    toggleWorkStyle,
    setLifeContext,
    setLifeContextPrivate,
  } = useOnboardingStore();

  return (
    <section>
      <div className="mb-9 max-w-[720px]">
        <p className="mb-[22px] inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-terra">
          <span className="font-serif text-[13px] italic font-medium normal-case tracking-normal text-ink-3">
            Step four of five
          </span>
          · Your reality
        </p>
        <h2 className="mb-4 font-serif font-[350] text-[clamp(32px,4.5vw,48px)] leading-[1.05] tracking-[-0.025em] text-ink">
          The <em className="italic text-green">constraints</em> that make a plan real.
        </h2>
        <p className="text-[16px] leading-[1.55] text-ink-2">
          A career plan that ignores your life isn&apos;t a plan, it&apos;s a fantasy. Tell us
          what&apos;s true for you right now — we&apos;ll design around it. Everything below is
          editable later.
        </p>
      </div>

      <ConstraintsForm
        constraints={constraints}
        onWeeklyHoursChange={setWeeklyHours}
        onLocationChange={setLocation}
        onLocationPrefChange={(pref: LocationPreference) => setLocationPreference(pref)}
        onCompensationChange={setCompensationTarget}
        onWorkStyleToggle={toggleWorkStyle}
        onLifeContextChange={setLifeContext}
        onLifeContextPrivateToggle={setLifeContextPrivate}
      />

      <div className="mt-11 flex items-center justify-between border-t border-rule pt-6">
        <button
          type="button"
          onClick={onBack}
          className="text-[14px] font-medium text-ink-3 transition-colors hover:text-ink"
        >
          ← Back
        </button>
        <button
          type="button"
          onClick={onNext}
          className="group inline-flex items-center gap-2 rounded-lg bg-ink px-5 py-3 text-[14px] font-medium text-bg transition-all hover:-translate-y-px hover:bg-green-2 hover:shadow-[0_8px_20px_-8px_rgba(14,58,43,0.4)]"
        >
          Generate my roadmap
          <span className="transition-transform group-hover:translate-x-0.5" aria-hidden="true">
            →
          </span>
        </button>
      </div>
    </section>
  );
}

