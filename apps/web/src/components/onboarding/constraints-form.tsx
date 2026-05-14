"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import type { LocationPreference, OnboardingConstraints } from "@/types/onboarding.types";

const LOCATION_PREFS: { id: LocationPreference; label: string }[] = [
  { id: "remote", label: "Open to remote" },
  { id: "relocate_eu", label: "Open to relocate · EU" },
  { id: "relocate_global", label: "Open to relocate · global" },
  { id: "local", label: "Local only" },
];

const WORK_STYLES = [
  "Deep technical work",
  "Shipping & impact",
  "Mentoring others",
  "Public speaking",
  "Open-source",
  "Writing & thought leadership",
  "Founding / 0→1",
];

export interface ConstraintsFormProps {
  constraints: OnboardingConstraints;
  onWeeklyHoursChange: (hours: number) => void;
  onLocationChange: (location: string) => void;
  onLocationPrefChange: (pref: LocationPreference) => void;
  onCompensationChange: (amount: number) => void;
  onWorkStyleToggle: (style: string) => void;
  onLifeContextChange: (text: string) => void;
  onLifeContextPrivateToggle: (val: boolean) => void;
}

export function ConstraintsForm({
  constraints,
  onWeeklyHoursChange,
  onLocationChange,
  onLocationPrefChange,
  onCompensationChange,
  onWorkStyleToggle,
  onLifeContextChange,
  onLifeContextPrivateToggle,
}: ConstraintsFormProps) {
  const hoursPct = ((constraints.weeklyHours - 2) / (20 - 2)) * 100;
  const compPct = ((constraints.compensationTarget - 80) / (300 - 80)) * 100;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      {/* Weekly hours */}
      <FieldCard
        icon={<ClockIcon />}
        iconVariant="green"
        label="Weekly time budget"
        subLabel="honest estimate"
        description="How many hours per week can you realistically invest in growing — alongside work, family, life?"
      >
        <div className="mt-2.5">
          <div className="mb-2 flex items-baseline justify-between font-serif text-[22px] font-[400] tracking-[-0.01em] text-ink">
            <span className="text-[11.5px] font-normal font-sans text-ink-3">2 h</span>
            <span>
              <em className="italic text-green">{constraints.weeklyHours} h</em>
              <span className="ml-0.5 text-[13px] font-normal text-ink-3"> / week</span>
            </span>
            <span className="text-[11.5px] font-normal font-sans text-ink-3">20+ h</span>
          </div>
          <SliderInput
            min={2}
            max={20}
            value={constraints.weeklyHours}
            pct={hoursPct}
            onChange={onWeeklyHoursChange}
          />
          <div className="mt-2 flex justify-between font-mono text-[9.5px] text-ink-3">
            <span>Light</span>
            <span>Steady</span>
            <span>Intense</span>
          </div>
        </div>
      </FieldCard>

      {/* Geography */}
      <FieldCard
        icon={<GlobeIcon />}
        iconVariant="terra"
        label="Where are you working from"
        description="We'll tune the plan for visa rules, salary norms, hiring rhythms and local communities."
      >
        <input
          type="text"
          value={constraints.location}
          onChange={(e) => onLocationChange(e.target.value)}
          placeholder="City, Country"
          className="mb-3 w-full rounded-lg border border-rule bg-bg px-3.5 py-3 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none"
        />
        <div className="flex flex-wrap gap-1.5">
          {LOCATION_PREFS.map(({ id, label }) => (
            <OptButton
              key={id}
              active={constraints.locationPreference === id}
              onClick={() => onLocationPrefChange(id)}
            >
              {label}
            </OptButton>
          ))}
        </div>
      </FieldCard>

      {/* Compensation */}
      <FieldCard
        icon={<CoinIcon />}
        iconVariant="gold"
        label="Compensation target"
        subLabel="optional"
        description="Your roadmap will weight roles and milestones to make this realistic — not just aspirational."
      >
        <div className="mt-2.5">
          <div className="mb-2 flex items-baseline justify-between font-serif text-[22px] font-[400] tracking-[-0.01em] text-ink">
            <span className="text-[11.5px] font-normal font-sans text-ink-3">$80k</span>
            <em className="italic text-green">${constraints.compensationTarget}k</em>
            <span className="text-[11.5px] font-normal font-sans text-ink-3">$300k+</span>
          </div>
          <SliderInput
            min={80}
            max={300}
            value={constraints.compensationTarget}
            pct={compPct}
            onChange={onCompensationChange}
          />
          <div className="mt-2 flex justify-between font-mono text-[9.5px] text-ink-3">
            <span>Mid</span>
            <span>Senior</span>
            <span>Staff+</span>
          </div>
        </div>
      </FieldCard>

      {/* Working style */}
      <FieldCard
        icon={<TeamIcon />}
        iconVariant="green"
        label="What energises you most"
        description="Pick all that resonate — we'll bias your weekly habits and milestone types accordingly."
      >
        <div className="flex flex-wrap gap-1.5">
          {WORK_STYLES.map((style) => (
            <OptButton
              key={style}
              active={constraints.workStyles.includes(style)}
              onClick={() => onWorkStyleToggle(style)}
            >
              {style}
            </OptButton>
          ))}
        </div>
      </FieldCard>

      {/* Life context — full width */}
      <div className="sm:col-span-2">
        <FieldCard
          icon={<HeartIcon />}
          iconVariant="terra"
          label="Life context"
          subLabel="optional, helps the coach be human"
          description="A short note to ground the plan in your actual life. Anything happening you'd want the coach to know about?"
        >
          <textarea
            value={constraints.lifeContext}
            onChange={(e) => onLifeContextChange(e.target.value)}
            placeholder="e.g. partner is also job-hunting · expecting in October · prefer mornings · etc."
            rows={3}
            className="mt-1 w-full resize-y rounded-lg border border-rule bg-bg px-3.5 py-3 text-[13.5px] leading-relaxed text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none"
          />

          <div className="mt-3.5 flex items-center gap-3.5 rounded-lg bg-bg px-3.5 py-3">
            <div className="flex-1">
              <p className="text-[13px] font-semibold text-ink">
                Use this context privately for personalisation
              </p>
              <p className="mt-0.5 text-[11.5px] leading-snug text-ink-3">
                Never shared, never used for ads, never seen by humans except you.
              </p>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={constraints.lifeContextPrivate}
              onClick={() => onLifeContextPrivateToggle(!constraints.lifeContextPrivate)}
              className={cn(
                "relative h-[22px] w-[38px] shrink-0 rounded-full transition-colors duration-200",
                constraints.lifeContextPrivate ? "bg-green" : "bg-rule-strong",
              )}
            >
              <span
                className={cn(
                  "absolute top-0.5 h-[18px] w-[18px] rounded-full bg-white shadow transition-all duration-200",
                  constraints.lifeContextPrivate ? "left-[18px]" : "left-0.5",
                )}
              />
            </button>
          </div>
        </FieldCard>
      </div>
    </div>
  );
}

// â”€â”€ Sub-components â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

type IconVariant = "green" | "terra" | "gold";

function FieldCard({
  icon,
  iconVariant,
  label,
  subLabel,
  description,
  children,
}: {
  icon: ReactNode;
  iconVariant: IconVariant;
  label: string;
  subLabel?: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-rule bg-paper p-[22px] transition-colors hover:border-rule-strong">
      <div className="mb-3.5 flex items-center gap-[11px]">
        <span
          className={cn(
            "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
            iconVariant === "green" && "bg-green-soft text-green",
            iconVariant === "terra" && "bg-terra-soft text-terra-2",
            iconVariant === "gold" && "bg-gold-soft text-gold",
          )}
        >
          {icon}
        </span>
        <p className="font-serif text-[16px] font-medium tracking-[-0.005em] text-ink">
          {label}
          {subLabel && (
            <span className="ml-1.5 font-sans text-[11px] italic font-medium text-ink-3">
              — {subLabel}
            </span>
          )}
        </p>
      </div>
      <p className="mb-3.5 text-[12.5px] leading-relaxed text-ink-3">{description}</p>
      {children}
    </div>
  );
}

function OptButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-[7px] border px-[13px] py-2 text-[12.5px] font-medium transition-all duration-150",
        active
          ? "border-green bg-green text-white"
          : "border-rule bg-bg text-ink-2 hover:border-green hover:text-ink",
      )}
    >
      {children}
    </button>
  );
}

function SliderInput({
  min,
  max,
  value,
  pct,
  onChange,
}: {
  min: number;
  max: number;
  value: number;
  pct: number;
  onChange: (v: number) => void;
}) {
  return (
    <input
      type="range"
      min={min}
      max={max}
      value={value}
      onChange={(e) => onChange(Number(e.target.value))}
      className="w-full cursor-pointer appearance-none rounded-full outline-none"
      style={{
        height: 4,
        background: `linear-gradient(to right, #134E3A 0%, #134E3A ${pct}%, #EFE8D7 ${pct}%, #EFE8D7 100%)`,
        WebkitAppearance: "none",
      }}
    />
  );
}

function ClockIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" className="h-[15px] w-[15px]" aria-hidden="true">
      <circle cx="8" cy="8" r="6" />
      <path d="M8 4v4l3 2" strokeLinecap="round" />
    </svg>
  );
}

function GlobeIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" className="h-[15px] w-[15px]" aria-hidden="true">
      <circle cx="8" cy="8" r="6" />
      <path d="M2 8h12M8 2c1.8 2 1.8 10 0 12M8 2c-1.8 2-1.8 10 0 12" />
    </svg>
  );
}

function CoinIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" className="h-[15px] w-[15px]" aria-hidden="true">
      <circle cx="8" cy="8" r="6" />
      <path d="M8 5c-1.5 0-2 .8-2 1.5C6 8 10 8 10 9.5c0 .7-.5 1.5-2 1.5M8 4v8" strokeLinecap="round" />
    </svg>
  );
}

function TeamIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" className="h-[15px] w-[15px]" aria-hidden="true">
      <circle cx="6" cy="6" r="2.4" />
      <circle cx="11" cy="5" r="1.8" />
      <path d="M2 13c0-2.2 2-3.6 4-3.6s4 1.4 4 3.6M9 13c0-1.6 1.5-2.6 3-2.6s2 .8 2 2.4" />
    </svg>
  );
}

function HeartIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" className="h-[15px] w-[15px]" aria-hidden="true">
      <path d="M8 14s-5-3-5-7a3 3 0 0 1 5-2 3 3 0 0 1 5 2c0 4-5 7-5 7z" />
    </svg>
  );
}

