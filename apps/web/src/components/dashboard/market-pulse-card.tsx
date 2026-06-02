"use client";

import Link from "next/link";
import { cn } from "@/lib/utils";
import type { SkillTrend } from "@/types/dashboard.types";
import { ROUTES } from "@/lib/constants";

// ── Mini spark line ───────────────────────────────────────────────────────────

interface SparkProps {
  points: number[];
  color: string;
}

function MiniSpark({ points, color }: SparkProps) {
  if (points.length < 2) return null;
  const max = Math.max(...points);
  const min = Math.min(...points);
  const range = max - min || 1;
  const w = 56;
  const h = 16;
  const step = w / (points.length - 1);
  const pathPoints = points
    .map((p, i) => `${i * step},${h - ((p - min) / range) * (h - 2) - 1}`)
    .join(" ");

  return (
    <svg viewBox={`0 0 ${w} ${h}`} fill="none" className="h-4 w-14 shrink-0" aria-hidden="true">
      <polyline
        points={pathPoints}
        stroke={color}
        strokeWidth="1.4"
        fill="none"
        strokeLinecap="round"
      />
    </svg>
  );
}

// ── Skill trend row ───────────────────────────────────────────────────────────

function SkillTrendRow({ trend }: { trend: SkillTrend }) {
  const isPositive = trend.changePercent > 10;
  const sparkColor = trend.isSteady ? "#8A8170" : isPositive ? "#C95A3D" : "#134E3A";

  return (
    <div className="grid grid-cols-[1fr_auto_auto] items-center gap-2.5 border-b border-dashed border-rule py-[9px] last:border-b-0">
      <div className="min-w-0">
        <span className="text-[13px] font-medium text-ink">{trend.name}</span>
        {trend.isInPlan && (
          <span className="ml-1.5 rounded-[3px] bg-green-soft px-[5px] py-px text-[9.5px] font-semibold uppercase tracking-[0.04em] text-green">
            in your plan
          </span>
        )}
      </div>
      <MiniSpark points={trend.sparkPoints} color={sparkColor} />
      <span
        className={cn(
          "w-11 text-right font-mono text-[11.5px] font-semibold [font-variant-numeric:tabular-nums]",
          trend.isSteady ? "text-ink-3" : isPositive ? "text-terra-2" : "text-green",
        )}
      >
        {trend.changePercent > 0 ? "+" : ""}{trend.changePercent}%
      </span>
    </div>
  );
}

// ── Skeleton ──────────────────────────────────────────────────────────────────

function MarketSkeleton() {
  return (
    <div className="animate-pulse space-y-3">
      <div className="h-10 rounded-[8px] bg-bg-2" />
      {[0,1,2,3,4].map((i) => (
        <div key={i} className="grid grid-cols-[1fr_56px_44px] items-center gap-2.5 py-1">
          <div className="h-3.5 w-32 rounded bg-bg-3" />
          <div className="h-3 rounded bg-bg-2" />
          <div className="h-3 w-10 rounded bg-bg-2" />
        </div>
      ))}
    </div>
  );
}

// ── Market Pulse card ─────────────────────────────────────────────────────────

export interface MarketPulseCardProps {
  targetRole: string | null;
  salaryLabel: string | null;
  trends: SkillTrend[];
  coachInsight: string | null;
  isLoading: boolean;
}

export function MarketPulseCard({
  targetRole,
  salaryLabel,
  trends,
  coachInsight,
  isLoading,
}: MarketPulseCardProps) {
  return (
    <div className="rounded-[12px] border border-rule bg-paper p-6">
      {/* Header */}
      <div className="mb-[18px] flex items-start justify-between border-b border-rule pb-3.5">
        <div>
          <h2 className="font-serif text-[17px] font-medium tracking-[-0.01em] text-ink">
            Market pulse
          </h2>
          <p className="mt-[3px] text-[11.5px] text-ink-3">
            Live · personalised to your target
          </p>
        </div>
        <Link
          href={ROUTES.market}
          className="text-[12px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
        >
          Pulse →
        </Link>
      </div>

      {isLoading ? (
        <MarketSkeleton />
      ) : (
        <>
          {/* Target role + salary */}
          <div className="mb-3.5 flex items-center justify-between rounded-[8px] border border-rule bg-bg-2 px-3 py-2.5 text-[12px]">
            <div>
              <p className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-ink-3">Your target role</p>
              <p className="font-serif italic text-[14px] font-medium text-ink">
                {targetRole ?? "Not set — update your profile"}
              </p>
            </div>
            {salaryLabel && (
              <div className="text-right">
                <p className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-ink-3">Median TC</p>
                <p className="font-serif italic text-[14px] font-medium text-ink">{salaryLabel}</p>
              </div>
            )}
          </div>

          {/* Skill trends */}
          {trends.length > 0 ? (
            <div>
              {trends.map((trend) => (
                <SkillTrendRow key={trend.name} trend={trend} />
              ))}
            </div>
          ) : (
            <p className="py-4 text-center text-[12px] text-ink-3">
              No live market signals yet — generate a roadmap to ground trending
              skills in your target market.
            </p>
          )}

          {/* Coach insight */}
          {coachInsight && (
            <div className="mt-3.5 border-t border-rule pt-3 text-[11px] leading-[1.45] text-ink-3">
              <em className="font-serif italic text-[12px] text-terra">Coach insight ·</em>{" "}
              {coachInsight}
            </div>
          )}
        </>
      )}
    </div>
  );
}
