"use client";

import Link from "next/link";
import { ROUTES } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";

const STEPS: { title: string; body: string }[] = [
  {
    title: "Describe your goal",
    body: "Tell your career twin where you want to be and by when. The more specific, the sharper the plan.",
  },
  {
    title: "Add your context",
    body: "Upload a CV or link your profile so the plan starts from your real skills and experience.",
  },
  {
    title: "Set your constraints",
    body: "Weekly hours, location preference, and target compensation shape a plan you can actually follow.",
  },
  {
    title: "Generate & stream",
    body: "A multi-agent pipeline builds your phase-by-phase roadmap live — grounded in current market data.",
  },
];

export default function RoadmapGeneratePage() {
  return (
    <div className="mx-auto max-w-[760px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="New roadmap"
        title="Generate your roadmap"
        description="Your roadmap is built by an AI coaching pipeline from your goal, profile, and the live job market."
      />

      <ol className="space-y-3">
        {STEPS.map((step, i) => (
          <li
            key={step.title}
            className="flex gap-4 rounded-[12px] border border-rule bg-paper p-5"
          >
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-green font-serif text-[14px] font-medium text-white">
              {i + 1}
            </span>
            <div className="min-w-0">
              <p className="text-[14px] font-semibold text-ink">{step.title}</p>
              <p className="mt-1 text-[13px] leading-relaxed text-ink-2">{step.body}</p>
            </div>
          </li>
        ))}
      </ol>

      <div className="mt-7 flex flex-col gap-3 sm:flex-row">
        <Link
          href={ROUTES.onboarding}
          className="inline-flex flex-1 items-center justify-center rounded-[8px] bg-ink px-5 py-3 text-[14px] font-medium text-bg transition-colors duration-150 hover:bg-green-2"
        >
          Start generating →
        </Link>
        <Link
          href={ROUTES.roadmap}
          className="inline-flex items-center justify-center rounded-[8px] border border-rule-strong bg-paper px-5 py-3 text-[14px] font-medium text-ink-2 transition-colors duration-150 hover:bg-bg-2"
        >
          View current roadmap
        </Link>
      </div>
    </div>
  );
}
