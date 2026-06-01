"use client";

import Link from "next/link";
import { cn } from "@/lib/utils";
import { ROUTES } from "@/lib/constants";
import type { RoadmapPhaseDetail } from "@/types/roadmap.types";
import { RoadmapProgressBar } from "./roadmap-progress-bar";

export type PhaseStatus = "done" | "current" | "future";

export interface PhaseCardProps {
  phase: RoadmapPhaseDetail;
  status: PhaseStatus;
  /** Count of milestones marked complete (from local progress). */
  milestonesDone: number;
  className?: string;
}

const STATUS_META: Record<PhaseStatus, { label: string; chip: string; bar: "green" | "terra" | "gold" }> = {
  done:    { label: "Complete", chip: "bg-green-soft text-green-2", bar: "green" },
  current: { label: "In progress", chip: "bg-terra-soft text-terra-2", bar: "terra" },
  future:  { label: "Upcoming", chip: "bg-bg-3 text-ink-2", bar: "gold" },
};

export function PhaseCard({ phase, status, milestonesDone, className }: PhaseCardProps) {
  const total = phase.milestones.length;
  const pct = total > 0 ? (milestonesDone / total) * 100 : status === "done" ? 100 : 0;
  const meta = STATUS_META[status];

  return (
    <Link
      href={`${ROUTES.roadmap}/${phase.id}`}
      className={cn(
        "group flex flex-col gap-4 rounded-[12px] border border-rule bg-paper p-5 transition-all duration-150 hover:border-rule-strong hover:shadow-sm sm:p-6",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3.5">
          <span className="font-serif text-[22px] font-medium leading-none text-rule-strong">
            {String(phase.order).padStart(2, "0")}
          </span>
          <div className="min-w-0">
            <h3 className="font-serif text-[17px] font-medium leading-tight tracking-[-0.01em] text-ink">
              {phase.title}
            </h3>
            <p className="mt-1 text-[12px] text-ink-3">
              {phase.durationWeeks} week{phase.durationWeeks !== 1 ? "s" : ""}
              {total > 0 && ` · ${total} milestone${total !== 1 ? "s" : ""}`}
            </p>
          </div>
        </div>
        <span
          className={cn(
            "shrink-0 rounded-[5px] px-2 py-1 text-[10.5px] font-semibold uppercase tracking-[0.04em]",
            meta.chip,
          )}
        >
          {meta.label}
        </span>
      </div>

      {phase.description && (
        <p className="line-clamp-2 text-[13px] leading-relaxed text-ink-2">{phase.description}</p>
      )}

      {phase.skillsToGain.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {phase.skillsToGain.slice(0, 4).map((skill) => (
            <span
              key={skill}
              className="rounded-[5px] bg-bg-2 px-2 py-0.5 text-[11px] font-medium text-ink-2"
            >
              {skill}
            </span>
          ))}
          {phase.skillsToGain.length > 4 && (
            <span className="rounded-[5px] px-1.5 py-0.5 text-[11px] text-ink-3">
              +{phase.skillsToGain.length - 4}
            </span>
          )}
        </div>
      )}

      <div className="mt-auto flex items-center gap-4 border-t border-rule pt-3.5">
        <RoadmapProgressBar value={pct} tone={meta.bar} size="sm" showValue={false} className="flex-1" />
        <span className="shrink-0 font-mono text-[11px] text-ink-3">
          {total > 0 ? `${milestonesDone}/${total}` : `${Math.round(pct)}%`}
        </span>
        <span className="shrink-0 text-[12px] font-medium text-ink-3 transition-colors group-hover:text-ink">
          View →
        </span>
      </div>
    </Link>
  );
}
