"use client";

import Link from "next/link";
import { cn } from "@/lib/utils";
import { ROUTES } from "@/lib/constants";
import type { RoadmapPhaseDetail } from "@/types/roadmap.types";

export interface PhaseNavProps {
  phases: RoadmapPhaseDetail[];
  /** id of the currently-open phase, if any. */
  activeId?: string;
  className?: string;
}

export function PhaseNav({ phases, activeId, className }: PhaseNavProps) {
  return (
    <nav aria-label="Roadmap phases" className={cn("flex flex-col gap-1", className)}>
      {phases.map((phase) => {
        const active = phase.id === activeId;
        return (
          <Link
            key={phase.id}
            href={`${ROUTES.roadmap}/${phase.id}`}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-[7px] px-3 py-2.5 transition-colors duration-150",
              active ? "bg-ink text-bg" : "text-ink-2 hover:bg-bg-2 hover:text-ink",
            )}
          >
            <span
              className={cn(
                "font-mono text-[12px]",
                active ? "text-terra-soft" : "text-ink-3",
              )}
            >
              {String(phase.order).padStart(2, "0")}
            </span>
            <span className="min-w-0 truncate text-[13px] font-medium">{phase.title}</span>
          </Link>
        );
      })}
    </nav>
  );
}
