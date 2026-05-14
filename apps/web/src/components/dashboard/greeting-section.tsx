"use client";

import Link from "next/link";
import { cn, fixMojibake } from "@/lib/utils";
import type { UserProfile } from "@/types/api.types";
import type { SessionState } from "@/types/session.types";
import type { NextBestAction } from "@/types/dashboard.types";
import { ROUTES } from "@/lib/constants";

// ── Phase progress bar ────────────────────────────────────────────────────────

interface PhaseTagProps {
  currentPhase: number;
  totalPhases: number;
  phaseName: string;
}

function PhaseTag({ currentPhase, totalPhases, phaseName }: PhaseTagProps) {
  return (
    <div className="mb-3.5 inline-flex items-center gap-2 rounded-full bg-green-soft px-[11px] py-[5px] text-[11px] font-semibold uppercase tracking-[0.12em] text-green">
      <span className="flex gap-0.5" aria-hidden="true">
        {Array.from({ length: totalPhases }, (_, i) => (
          <span
            key={i}
            className={cn(
              "h-1 w-2 rounded-sm",
              i < currentPhase ? "bg-green" : "bg-green opacity-25",
            )}
          />
        ))}
      </span>
      <span>
        Phase {currentPhase} of {totalPhases} · {phaseName}
      </span>
    </div>
  );
}

// ── NBA (Next Best Action) card ───────────────────────────────────────────────

interface NbaCardProps {
  action: NextBestAction;
}

function NbaCard({ action }: NbaCardProps) {
  return (
    <div className="relative overflow-hidden rounded-[12px] border border-rule bg-paper p-[18px] pl-5">
      {/* Left accent bar */}
      <span className="absolute inset-y-0 left-0 w-[3px] bg-terra rounded-l-[12px]" aria-hidden="true" />

      <div className="mb-2 flex items-center gap-[7px] text-[11px] font-semibold uppercase tracking-[0.12em] text-terra">
        <svg viewBox="0 0 14 14" fill="currentColor" className="h-3.5 w-3.5" aria-hidden="true">
          <path d="M7 1l1.5 4 4 1.5-4 1.5L7 12l-1.5-4L1.5 6.5l4-1.5z"/>
        </svg>
        Suggested next · {action.estimateMinutes} min
      </div>

      <h4 className="mb-1 font-serif text-[17px] font-[450] leading-[1.25] tracking-[-0.005em] text-ink">
        {action.title}
      </h4>
      <p className="mb-3 text-[12.5px] leading-[1.45] text-ink-2">
        {action.description}
        {action.milestoneLabel && (
          <> milestone <strong className="font-semibold text-ink">{action.milestoneLabel}</strong>.</>
        )}
      </p>

      <div className="flex items-center gap-2.5">
        <Link
          href={ROUTES.coach}
          className="inline-flex items-center gap-[5px] rounded-[6px] bg-ink px-[13px] py-[6px] text-[12px] font-medium text-bg transition-colors duration-150 hover:bg-green-2"
        >
          Start now
          <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" className="h-[11px] w-[11px]" aria-hidden="true">
            <path d="M2 6h8M7 3l3 3-3 3" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </Link>
        <button
          type="button"
          className="text-[12px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
        >
          Snooze · later today
        </button>
      </div>
    </div>
  );
}

// ── Greeting section ──────────────────────────────────────────────────────────

export interface GreetingSectionProps {
  user: UserProfile | null;
  session: SessionState | null;
  isLoading: boolean;
}

function getFirstName(displayName: string | null, email: string): string {
  if (displayName) {
    return displayName.split(" ")[0];
  }
  return email.split("@")[0];
}

const FALLBACK_ACTION: NextBestAction = {
  title: "Generate your personalised career roadmap",
  description: "Chat with the Career Twin to map your goal, current skills, and timeline. Your week-by-week plan will be ready in minutes.",
  estimateMinutes: 10,
};

export function GreetingSection({ user, session, isLoading }: GreetingSectionProps) {
  const firstName = user
    ? getFirstName(user.displayName, user.email)
    : "there";

  const targetRole = session?.userProfileContext?.targetRole
    ? fixMojibake(session.userProfileContext.targetRole)
    : undefined;
  const currentPhase = 2;
  const totalPhases  = 4;
  const phaseName    = "Specialisation";

  const hasRoadmap = !!session?.planContext?.roadmapId;

  const nbaAction: NextBestAction = hasRoadmap
    ? {
        title:           "Push your RAG retriever to GitHub & tag the milestone.",
        description:     "You're one commit away from closing",
        estimateMinutes: 25,
        milestoneLabel:  "M-07: Production retrieval pipeline",
      }
    : FALLBACK_ACTION;

  if (isLoading) {
    return (
      <section className="mb-[22px] grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <div className="animate-pulse space-y-3">
          <div className="h-5 w-48 rounded bg-bg-3" />
          <div className="h-12 w-72 rounded bg-bg-3" />
          <div className="h-4 w-96 rounded bg-bg-2" />
        </div>
        <div className="animate-pulse rounded-[12px] border border-rule bg-paper p-5">
          <div className="mb-2 h-3 w-32 rounded bg-bg-3" />
          <div className="mb-3 h-5 w-full rounded bg-bg-3" />
          <div className="h-8 w-24 rounded bg-bg-2" />
        </div>
      </section>
    );
  }

  return (
    <section
      className="mb-[22px] grid items-center gap-6 lg:grid-cols-[1.4fr_1fr]"
      aria-label="Dashboard greeting"
    >
      {/* Greeting text */}
      <div>
        {hasRoadmap && (
          <PhaseTag
            currentPhase={currentPhase}
            totalPhases={totalPhases}
            phaseName={phaseName}
          />
        )}
        <h1 className="mb-2 font-serif text-[40px] font-[350] leading-[1.1] tracking-[-0.025em] text-ink">
          Welcome back, <em className="italic text-green">{firstName}</em>.
        </h1>
        <p className="max-w-[540px] text-[14.5px] leading-[1.5] text-ink-2">
          {targetRole
            ? (
              <>
                You&apos;re on your path to{" "}
                <strong className="font-semibold text-ink">{targetRole}</strong>.
                {hasRoadmap
                  ? " The coach noticed you've been crushing deep-work sessions this week."
                  : " Chat with your Career Twin to build your week-by-week plan."}
              </>
            )
            : "Set your target role to get a personalised roadmap and week-by-week career plan."}
        </p>
      </div>

      {/* Next best action */}
      <NbaCard action={nbaAction} />
    </section>
  );
}
