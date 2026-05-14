"use client";

import { useMemo } from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import type { ActivityStats } from "@/types/dashboard.types";

// ── Activity level → Tailwind class ──────────────────────────────────────────

const LEVEL_CLASSES = [
  "bg-bg-2",
  "bg-[#D6E2D2]",
  "bg-[#A8C5A0]",
  "bg-[#5C9474]",
  "bg-green",
];

// ── Heatmap grid ──────────────────────────────────────────────────────────────

const WEEK_PATTERN = [
  [0,1,1,1,0,1,0],
  [0,2,2,1,1,2,0],
  [0,2,3,2,2,1,0],
  [1,3,3,3,2,2,0],
  [0,2,3,2,3,2,1],
  [0,1,2,2,2,1,0],
  [0,3,4,3,2,3,1],
  [0,2,3,3,4,2,0],
  [1,3,3,4,3,3,1],
  [0,3,4,3,3,2,0],
  [0,2,3,3,4,3,1],
  [1,3,4,4,3,2,1],
  [0,2,3,3,3,3,0],
  [1,4,4,3,4,3,1],
  [0,3,4,4,3,4,1],
  [0,3,4,4,3,2,0],
] as const;

const MILESTONE_INDICES = new Set([4 * 7 + 5, 11 * 7 + 3, 14 * 7 + 2]);

const WEEKS = 16;
const DAY_LABELS = ["", "M", "", "W", "", "F", ""];

interface HeatmapCell {
  level: number;
  isMilestone: boolean;
  label: string;
}

function buildCells(): HeatmapCell[] {
  const cells: HeatmapCell[] = [];
  const now = new Date();

  for (let w = 0; w < WEEKS; w++) {
    for (let d = 0; d < 7; d++) {
      const idx = w * 7 + d;
      const date = new Date(now);
      date.setDate(date.getDate() - (WEEKS - 1 - w) * 7 - (6 - d));
      const level   = WEEK_PATTERN[w]?.[d] ?? 0;
      const isMilestone = MILESTONE_INDICES.has(idx);
      const sessions = level;
      cells.push({
        level,
        isMilestone,
        label: `${date.toDateString()}${sessions ? ` · ${sessions} session${sessions > 1 ? "s" : ""}` : " · rest"}`,
      });
    }
  }

  return cells;
}

function HeatmapGrid() {
  const cells = useMemo(buildCells, []);
  const months = ["Jan", "Feb", "Mar", "Apr"];

  return (
    <div className="grid grid-cols-[22px_1fr] gap-1.5">
      {/* Day labels */}
      <div className="flex flex-col gap-0.5 pt-[18px]">
        {DAY_LABELS.map((label, i) => (
          <span key={i} className="h-3 font-mono text-[9px] leading-3 text-ink-3">
            {label}
          </span>
        ))}
      </div>

      <div>
        {/* Month labels */}
        <div className="mb-1.5 flex font-mono text-[9.5px] uppercase tracking-[0.04em] text-ink-3">
          {months.map((m) => (
            <span key={m} className="flex-1">{m}</span>
          ))}
        </div>

        {/* Grid */}
        <div
          className="grid grid-rows-7 grid-flow-col auto-cols-3 gap-0.5"
          role="grid"
          aria-label="Activity heatmap"
        >
          {cells.map((cell, i) => (
            <div
              key={i}
              title={cell.label}
              aria-label={cell.label}
              className={cn(
                "h-3 w-3 rounded-sm transition-transform duration-[120ms] hover:scale-[1.4] hover:rounded-[3px]",
                cell.isMilestone
                  ? "bg-terra ring-1 ring-terra ring-offset-1 ring-offset-paper"
                  : LEVEL_CLASSES[cell.level] ?? LEVEL_CLASSES[0],
              )}
            />
          ))}
        </div>

        {/* Legend */}
        <div className="mt-3 flex items-center justify-end gap-1.5 text-[10px] text-ink-3">
          <span>Less</span>
          <div className="flex gap-0.5">
            {LEVEL_CLASSES.map((cls, i) => (
              <span key={i} className={cn("h-[11px] w-[11px] rounded-sm", cls)} />
            ))}
          </div>
          <span>More</span>
        </div>
      </div>
    </div>
  );
}

// ── Activity stat ─────────────────────────────────────────────────────────────

interface ActivityStatProps {
  label: string;
  sub: string;
  value: React.ReactNode;
}

function ActivityStat({ label, sub, value }: ActivityStatProps) {
  return (
    <div className="grid grid-cols-[1fr_auto] items-baseline gap-3 border-b border-rule pb-3.5 last:border-b-0 last:pb-0">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-ink-3">{label}</p>
        <p className="mt-1 text-[11.5px] text-ink-2">{sub}</p>
      </div>
      <div className="font-serif text-[28px] font-[400] leading-none tracking-[-0.018em] text-ink [font-variant-numeric:tabular-nums]">
        {value}
      </div>
    </div>
  );
}

// ── Activity heatmap card ─────────────────────────────────────────────────────

export interface ActivityHeatmapCardProps {
  stats: ActivityStats | null;
  isLoading: boolean;
}

const DEFAULT_STATS: ActivityStats = {
  longestStreakDays:    34,
  totalDeepWorkHours:  142,
  milestonesCompleted: 12,
  milestonesTotal:     26,
  weeklyReviewsFiled:  16,
  totalWeeks:          16,
};

export function ActivityHeatmapCard({ stats, isLoading }: ActivityHeatmapCardProps) {
  const s = stats ?? DEFAULT_STATS;

  return (
    <section className="rounded-[12px] border border-rule bg-paper p-6">
      {/* Header */}
      <div className="mb-[18px] flex items-start justify-between border-b border-rule pb-3.5">
        <div>
          <h2 className="font-serif text-[17px] font-medium tracking-[-0.01em] text-ink">
            Your activity
          </h2>
          <p className="mt-[3px] text-[11.5px] text-ink-3">
            Last 16 weeks ·{" "}
            <em className="font-serif italic text-terra">terracotta marks completed milestones</em>
          </p>
        </div>
        <Link
          href="#"
          className="text-[12px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
        >
          Detailed log →
        </Link>
      </div>

      {isLoading ? (
        <div className="animate-pulse">
          <div className="h-[110px] w-full rounded bg-bg-2" />
        </div>
      ) : (
        <div className="grid gap-7 xl:grid-cols-[1.7fr_1fr]">
          <HeatmapGrid />

          <div className="flex flex-col gap-[18px]">
            <ActivityStat
              label="Longest streak"
              sub="Best run since starting your roadmap"
              value={<><em className="italic text-terra">{s.longestStreakDays}</em><span className="ml-0.5 text-[13px] not-italic text-ink-3">d</span></>}
            />
            <ActivityStat
              label="Total deep-work"
              sub="Hours logged across all categories"
              value={<>{s.totalDeepWorkHours}<span className="ml-0.5 text-[13px] text-ink-3">h</span></>}
            />
            <ActivityStat
              label="Milestones"
              sub="Completed across two phases"
              value={<>{s.milestonesCompleted} <span className="text-[18px] text-ink-3">/ {s.milestonesTotal}</span></>}
            />
            <ActivityStat
              label="Weekly reviews filed"
              sub={`Friday retros · all ${s.totalWeeks} weeks`}
              value={<><em className="italic text-terra">{s.weeklyReviewsFiled}</em><span className="ml-0.5 text-[13px] not-italic text-ink-3">/ {s.totalWeeks}</span></>}
            />
          </div>
        </div>
      )}
    </section>
  );
}
