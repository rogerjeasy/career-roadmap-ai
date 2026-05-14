"use client";

import Link from "next/link";
import { ROUTES } from "@/lib/constants";

export interface StepWelcomeProps {
  onNext: () => void;
}

const BULLETS = [
  {
    icon: (
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7" className="h-3.5 w-3.5" aria-hidden="true">
        <rect x="3" y="2" width="10" height="12" rx="1.5" />
        <path d="M5 5h6M5 8h6M5 11h4" strokeLinecap="round" />
      </svg>
    ),
    bg: "bg-green-soft text-green",
    title: "Bring your CV",
    desc: "PDF, DOCX, or LinkedIn URL — we'll parse skills, projects, and impact signals.",
  },
  {
    icon: (
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7" className="h-3.5 w-3.5" aria-hidden="true">
        <circle cx="8" cy="8" r="6" />
        <path d="M8 5v3l2 1.5" strokeLinecap="round" />
      </svg>
    ),
    bg: "bg-terra-soft text-terra-2",
    title: "Twelve minutes",
    desc: "Five short steps. You can pause anytime — your progress saves automatically.",
  },
  {
    icon: (
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7" className="h-3.5 w-3.5" aria-hidden="true">
        <rect x="2" y="3" width="12" height="10" rx="1.5" />
        <path d="M5 6h6M5 9h4" strokeLinecap="round" />
        <circle cx="11.5" cy="9.5" r="1" fill="currentColor" />
      </svg>
    ),
    bg: "bg-gold-soft text-gold",
    title: "Private by default",
    desc: "Your data stays yours. Export, delete, or rebuild your plan whenever you want.",
  },
];

export function StepWelcome({ onNext }: StepWelcomeProps) {
  return (
    <section className="pt-6">
      <div className="grid grid-cols-1 items-center gap-10 lg:grid-cols-[1.05fr_0.95fr] lg:gap-14">
        {/* Left — text */}
        <div>
          <h2 className="mb-4 font-serif font-[350] text-[clamp(36px,5vw,56px)] leading-[1.05] tracking-[-0.025em] text-ink">
            Welcome. Let&apos;s build your{" "}
            <em className="italic text-green">career roadmap</em>.
          </h2>
          <p className="mb-7 text-[16px] leading-[1.55] text-ink-2">
            In about <strong className="font-semibold text-ink">twelve minutes</strong>, we&apos;ll
            turn your CV and goals into a multi-phase plan, with weekly habits and milestones that
            adapt as the market shifts. Everything is editable. Nothing is shared without your
            permission.
          </p>
          <blockquote className="max-w-[540px] rounded-xl border border-rule border-l-[3px] border-l-terra bg-paper p-5 font-serif text-[16px] italic font-[350] leading-[1.55] text-ink-2">
            &ldquo;I expected another generic career quiz. What I got was a plan that knew me better
            than my last three managers combined.&rdquo;
            <cite className="mt-3 block not-italic font-sans text-[12px] text-ink-3">
              <strong className="font-semibold text-ink">Maya R.</strong> · 12 months in · backend
              → ML engineer
            </cite>
          </blockquote>
        </div>

        {/* Right — illustration card */}
        <div className="relative aspect-square max-w-[420px] overflow-hidden rounded-2xl border border-rule bg-paper p-6 shadow-[0_14px_40px_-20px_rgba(21,20,15,0.12)] lg:max-w-none">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0"
            style={{
              background:
                "radial-gradient(circle at 0% 0%, #F9E8DD 0%, transparent 35%), radial-gradient(circle at 100% 100%, #E9F0E5 0%, transparent 40%)",
            }}
          />
          <div className="relative z-10">
            <p className="mb-1.5 font-serif text-[14px] italic text-terra">— Sample roadmap preview —</p>
            <p className="mb-5 font-serif text-[24px] font-[450] leading-[1.15] tracking-[-0.015em] text-ink">
              Full-Stack → AI Systems Eng.
            </p>
            <svg viewBox="0 0 360 100" preserveAspectRatio="none" className="w-full" aria-hidden="true">
              <path
                d="M 10 80 C 60 80, 80 25, 130 25 C 180 25, 200 70, 250 60 C 290 52, 320 18, 350 12"
                stroke="#C9BFA7" strokeWidth="1.5" fill="none" strokeDasharray="2 4"
              />
              <path
                d="M 10 80 C 60 80, 80 25, 130 25 C 180 25, 200 70, 230 65"
                stroke="#134E3A" strokeWidth="2" fill="none"
              />
              <circle cx="10" cy="80" r="5" fill="#134E3A" />
              <circle cx="130" cy="25" r="5" fill="#134E3A" />
              <circle cx="230" cy="65" r="6" fill="#C95A3D" stroke="#fff" strokeWidth="2" />
              <circle cx="350" cy="12" r="6" fill="#fff" stroke="#15140F" strokeWidth="2" />
            </svg>
          </div>
          <div className="absolute bottom-6 left-6 right-6 grid grid-cols-3 gap-2.5 z-10">
            {[
              { label: "Phase 1", value: "Done", color: "text-green" },
              { label: "Now", value: "Specialise", color: "text-terra-2 italic font-serif" },
              { label: "Goal", value: "18 mo." },
            ].map(({ label, value, color }) => (
              <div key={label} className="rounded-lg border border-rule bg-bg p-3">
                <p className="mb-1 font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3">{label}</p>
                <p className={`text-[13.5px] font-medium leading-tight text-ink ${color ?? ""}`}>{value}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Feature bullets */}
      <div className="mt-8 grid grid-cols-1 gap-3.5 sm:grid-cols-3 max-w-[720px]">
        {BULLETS.map(({ icon, bg, title, desc }) => (
          <div key={title} className="flex gap-[11px]">
            <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-[7px] ${bg}`}>
              {icon}
            </span>
            <div>
              <p className="mb-0.5 text-[13px] font-semibold text-ink">{title}</p>
              <p className="text-[12px] leading-[1.45] text-ink-2">{desc}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="mt-11 flex items-center justify-between border-t border-rule pt-6">
        <Link href={ROUTES.home} className="text-[14px] font-medium text-ink-3 hover:text-ink transition-colors">
          ← Back to home
        </Link>
        <button
          type="button"
          onClick={onNext}
          className="group inline-flex items-center gap-2 rounded-lg bg-ink px-5 py-3 text-[14px] font-medium text-bg transition-all hover:-translate-y-px hover:bg-green-2 hover:shadow-[0_8px_20px_-8px_rgba(14,58,43,0.4)]"
        >
          Let&apos;s begin
          <span className="transition-transform group-hover:translate-x-0.5" aria-hidden="true">→</span>
        </button>
      </div>
    </section>
  );
}

