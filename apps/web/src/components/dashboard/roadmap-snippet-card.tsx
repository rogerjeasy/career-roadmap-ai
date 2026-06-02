"use client";

import Link from "next/link";
import { cn } from "@/lib/utils";
import type { RoadmapPhase } from "@/types/dashboard.types";
import { ROUTES } from "@/lib/constants";

// ── Roadmap path visualisation ────────────────────────────────────────────────

// Hand-tuned label anchor positions along the decorative curve (max 4 shown).
const LABEL_SLOTS = [
  "left-[18px] top-[154px]",
  "left-[296px] top-[156px]",
  "right-[92px] top-[122px]",
  "right-2 top-1",
] as const;

function slotClass(status: RoadmapPhase["status"]): string {
  if (status === "done") return "border-green bg-green text-white";
  if (status === "current")
    return "border-terra bg-terra text-white shadow-[0_4px_12px_-2px_rgba(201,90,61,0.4)]";
  return "border-rule bg-paper text-ink-3";
}

function RoadmapPath({ phases, currentPhaseIdx }: { phases: RoadmapPhase[]; currentPhaseIdx: number }) {
  // Current progress dot position based on phase (0-indexed)
  const dotPositions = [
    { cx: 30,  cy: 170 },
    { cx: 220, cy: 60  },
    { cx: 350, cy: 142 },
    { cx: 580, cy: 30  },
  ];
  const currentDot = dotPositions[Math.min(currentPhaseIdx, dotPositions.length - 1)];

  return (
    <div className="relative h-[200px] overflow-hidden rounded-[8px] border border-dashed border-rule bg-[radial-gradient(circle_at_0%_100%,#E9F0E5_0%,transparent_40%),radial-gradient(circle_at_100%_0%,#F9E8DD_0%,transparent_35%)]">
      <svg
        viewBox="0 0 600 200"
        preserveAspectRatio="none"
        className="absolute inset-0 h-full w-full"
        aria-hidden="true"
      >
        {/* Full dotted path */}
        <path
          d="M 30 170 C 100 170, 130 60, 220 60 C 310 60, 320 150, 410 130 C 470 116, 510 50, 580 30"
          stroke="#C9BFA7"
          strokeWidth="1.5"
          fill="none"
          strokeDasharray="3 4"
        />
        {/* Progress path (up to current position) */}
        <path
          d="M 30 170 C 100 170, 130 60, 220 60 C 310 60, 320 150, 350 142"
          stroke="#134E3A"
          strokeWidth="2"
          fill="none"
        />
        {/* Start dot */}
        <circle cx="30"  cy="170" r="5" fill="#134E3A"/>
        {/* Phase 2 dot */}
        <circle cx="220" cy="60"  r="5" fill="#134E3A"/>
        {/* Current position */}
        <circle cx={currentDot.cx} cy={currentDot.cy} r="6" fill="#C95A3D" stroke="#fff" strokeWidth="2"/>
        {/* Phase 3 dot */}
        <circle cx="410" cy="130" r="4" fill="#fff" stroke="#C9BFA7" strokeWidth="1.5"/>
        {/* Goal dot */}
        <circle cx="580" cy="30"  r="6" fill="#fff" stroke="#15140F" strokeWidth="2"/>
      </svg>

      {/* Stage labels — derived from the real roadmap (first 4 phases) */}
      {phases.slice(0, 4).map((phase, i) => (
        <span
          key={phase.number}
          className={cn(
            "stage-label absolute max-w-[120px] truncate rounded-[4px] border px-2 py-[3px] text-[10px] font-semibold uppercase tracking-[0.1em]",
            LABEL_SLOTS[i],
            slotClass(phase.status),
          )}
        >
          P{phase.number} · {phase.title}
          {phase.status === "current" && " · now"}
        </span>
      ))}
    </div>
  );
}

// ── Phase item ────────────────────────────────────────────────────────────────

function PhaseItem({ phase }: { phase: RoadmapPhase }) {
  const isCurrent = phase.status === "current";
  const isDone    = phase.status === "done";

  return (
    <div
      className={cn(
        "rounded-[7px] border p-[10px] transition-colors duration-150",
        isCurrent ? "border-terra bg-terra-faint" : "border-rule",
      )}
    >
      <p className="mb-1 font-mono text-[10px] text-ink-3">
        PHASE {String(phase.number).padStart(2, "0")}
        {isCurrent && " · CURRENT"}
      </p>
      <p
        className={cn(
          "mb-1.5 font-serif text-[13.5px] font-medium leading-[1.2] tracking-[-0.005em]",
          isDone || isCurrent ? "text-ink" : "text-ink-2",
        )}
      >
        {phase.title}
      </p>
      <div className="h-[3px] overflow-hidden rounded-full bg-bg-2">
        <div
          className={cn(
            "h-full w-[--prog] rounded-full",
            isDone    ? "bg-green" : isCurrent ? "bg-terra" : "bg-rule",
          )}
          style={{ "--prog": `${phase.progressPercent}%` } as React.CSSProperties}
        />
      </div>
      <div
        className={cn(
          "mt-1.5 flex justify-between text-[10.5px]",
          isCurrent ? "font-medium text-terra-2" : "text-ink-3",
        )}
      >
        <span>
          {isDone ? "Complete" : isCurrent
            ? `${phase.milestonesCompleted} of ${phase.milestonesTotal} milestones`
            : phase.dateLabel}
        </span>
        <span>
          {isDone
            ? `${phase.milestonesTotal}/${phase.milestonesTotal}`
            : `${Math.round(phase.progressPercent)}%`}
        </span>
      </div>
    </div>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────

function RoadmapEmpty() {
  return (
    <div className="flex flex-col items-center justify-center rounded-[8px] border border-dashed border-rule py-10 text-center">
      <p className="mb-1 text-[13px] font-medium text-ink-2">No roadmap yet</p>
      <p className="mb-4 max-w-[240px] text-[12px] text-ink-3">
        Generate your personalised career plan to see the roadmap here.
      </p>
      <Link
        href={ROUTES.roadmapGenerate}
        className="inline-flex items-center gap-1.5 rounded-[7px] bg-ink px-4 py-2 text-[12px] font-medium text-bg transition-colors duration-150 hover:bg-green-2"
      >
        Generate roadmap
      </Link>
    </div>
  );
}

// ── Roadmap snippet card ──────────────────────────────────────────────────────

export interface RoadmapSnippetCardProps {
  phases: RoadmapPhase[];
  trackLabel: string;
  isLoading: boolean;
}

export function RoadmapSnippetCard({ phases, trackLabel, isLoading }: RoadmapSnippetCardProps) {
  const hasPhases = phases.length > 0;
  const currentPhaseIdx = phases.findIndex((p) => p.status === "current");

  return (
    <div className="rounded-[12px] border border-rule bg-paper p-6">
      {/* Header */}
      <div className="mb-[18px] flex items-start justify-between border-b border-rule pb-3.5">
        <div>
          <h2 className="font-serif text-[17px] font-medium tracking-[-0.01em] text-ink">
            Your roadmap
          </h2>
          <p className="mt-[3px] text-[11.5px] text-ink-3">
            {trackLabel || "Generate a roadmap to see your track"}
            {hasPhases && (
              <>
                {" · "}
                <em className="font-serif italic text-terra">
                  {phases.length}-phase plan
                </em>
              </>
            )}
          </p>
        </div>
        <Link
          href={ROUTES.roadmap}
          className="inline-flex items-center gap-1 text-[12px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
        >
          Open full view →
        </Link>
      </div>

      {isLoading ? (
        <div className="animate-pulse">
          <div className="mb-[18px] h-[200px] rounded-[8px] bg-bg-2" />
          <div className="grid grid-cols-4 gap-2.5">
            {[0,1,2,3].map((i) => <div key={i} className="h-20 rounded-[7px] bg-bg-2" />)}
          </div>
        </div>
      ) : !hasPhases ? (
        <RoadmapEmpty />
      ) : (
        <>
          <RoadmapPath phases={phases} currentPhaseIdx={Math.max(currentPhaseIdx, 0)} />
          <div className="mt-[18px] grid grid-cols-2 gap-2.5 sm:grid-cols-4">
            {phases.map((phase) => (
              <PhaseItem key={phase.number} phase={phase} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
