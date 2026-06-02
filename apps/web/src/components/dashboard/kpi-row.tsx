"use client";

import { cn } from "@/lib/utils";
import type { DashboardKpis } from "@/types/dashboard.types";

// ── Skeleton ──────────────────────────────────────────────────────────────────

function KpiSkeleton() {
  return (
    <div className="animate-pulse rounded-[11px] border border-rule bg-paper p-[18px]">
      <div className="mb-[6px] h-3 w-28 rounded bg-bg-3" />
      <div className="mb-1.5 h-8 w-20 rounded bg-bg-3" />
      <div className="h-3 w-24 rounded bg-bg-2" />
    </div>
  );
}

// ── Single KPI card ───────────────────────────────────────────────────────────

export interface KpiCardProps {
  label: string;
  value: string;
  unit?: string;
  deltaLabel?: string;
  deltaValue?: string;
  deltaDirection?: "up" | "down" | "neutral";
  featured?: boolean;
  children?: React.ReactNode;
}

export function KpiCard({
  label,
  value,
  unit,
  deltaLabel,
  deltaValue,
  deltaDirection = "neutral",
  featured = false,
  children,
}: KpiCardProps) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-[11px] border p-[18px] transition-colors duration-150",
        "flex flex-col gap-1.5",
        featured
          ? "border-ink bg-ink text-bg"
          : "border-rule bg-paper hover:border-rule-strong",
      )}
    >
      {/* Head row */}
      <div
        className={cn(
          "flex items-center justify-between text-[11px] font-semibold uppercase tracking-[0.08em]",
          featured ? "text-terra-soft" : "text-ink-3",
        )}
      >
        <span>{label}</span>
      </div>

      {/* Number */}
      <div
        className={cn(
          "font-serif text-[32px] leading-none tracking-[-0.02em] font-[400]",
          "[font-variant-numeric:tabular-nums]",
          featured ? "text-bg" : "text-ink",
        )}
      >
        <span className={featured ? "italic text-terra-soft" : "italic text-green"}>
          {value}
        </span>
        {unit && (
          <span
            className={cn(
              "ml-0.5 font-[400] text-sm not-italic",
              featured ? "text-terra-soft/60" : "text-ink-3",
            )}
          >
            {unit}
          </span>
        )}
      </div>

      {/* Delta */}
      {deltaLabel && (
        <div
          className={cn(
            "flex items-center gap-2 text-[11.5px]",
            featured ? "text-bg/65" : "text-ink-2",
          )}
        >
          {deltaValue && (
            <span
              className={cn(
                "font-semibold [font-variant-numeric:tabular-nums]",
                deltaDirection === "up" && (featured ? "text-[#7ED2A4]" : "text-green"),
                deltaDirection === "down" && "text-terra-2",
              )}
            >
              {deltaDirection === "up" && "▲ "}
              {deltaDirection === "down" && "▼ "}
              {deltaValue}
            </span>
          )}
          <span>{deltaLabel}</span>
        </div>
      )}

      {children}
    </div>
  );
}

// ── KPI row ───────────────────────────────────────────────────────────────────

export interface KpiRowProps {
  kpis: DashboardKpis | null;
  isLoading: boolean;
}

export function KpiRow({ kpis, isLoading }: KpiRowProps) {
  if (isLoading) {
    return (
      <section className="grid grid-cols-2 gap-3.5 lg:grid-cols-4" aria-label="Key metrics loading">
        {[0, 1, 2, 3].map((i) => <KpiSkeleton key={i} />)}
      </section>
    );
  }

  const health        = kpis?.healthScore ?? 0;
  const delta         = kpis?.healthScoreDelta ?? 0;
  const streak        = kpis?.activeStreakDays ?? 0;
  const hours         = kpis?.hoursThisWeek ?? 0;
  const budget        = kpis?.weeklyBudgetHours ?? 0;
  const milestone     = kpis?.nextMilestoneDays ?? null;
  const milestoneName = kpis?.nextMilestoneName ?? "";

  return (
    <section
      className="grid grid-cols-2 gap-3.5 lg:grid-cols-4"
      aria-label="Key performance metrics"
    >
      {/* Career Health Score — featured dark card */}
      <KpiCard
        label="Career Health Score"
        value={health > 0 ? String(health) : "—"}
        unit={health > 0 ? "/100" : undefined}
        deltaValue={delta > 0 ? `+${delta}` : delta < 0 ? String(delta) : undefined}
        deltaLabel={delta !== 0 ? "since last snapshot" : "Generate roadmap to start"}
        deltaDirection={delta > 0 ? "up" : delta < 0 ? "down" : "neutral"}
        featured
      />

      {/* Active streak */}
      <KpiCard
        label="Active Streak"
        value={streak > 0 ? String(streak) : "—"}
        unit={streak > 0 ? "days" : undefined}
        deltaLabel={streak > 0 ? "your best habit run" : "Start your streak today"}
      />

      {/* Hours this week */}
      <KpiCard
        label="Hours This Week"
        value={hours > 0 ? String(hours) : "—"}
        unit={hours > 0 ? `/ ${budget} h` : undefined}
        deltaValue={hours > 0 ? `${Math.round((hours / budget) * 100)}%` : undefined}
        deltaLabel={hours > 0 ? "of weekly budget" : "No hours logged yet"}
        deltaDirection="up"
      />

      {/* Next milestone */}
      <KpiCard
        label="Next Milestone"
        value={milestone !== null ? String(milestone) : "—"}
        unit={milestone !== null ? "days" : undefined}
        deltaLabel={milestoneName || "No milestone set"}
      />
    </section>
  );
}
