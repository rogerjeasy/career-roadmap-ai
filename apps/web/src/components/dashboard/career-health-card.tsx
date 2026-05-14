"use client";

import Link from "next/link";
import { cn } from "@/lib/utils";
import type { HealthSignal } from "@/types/dashboard.types";

// ── SVG gauge ─────────────────────────────────────────────────────────────────

interface GaugeProps {
  score: number;
  delta: number;
}

function Gauge({ score, delta }: GaugeProps) {
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - score / 100);

  return (
    <div className="relative h-[110px] w-[110px] shrink-0">
      <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90" aria-hidden="true">
        <circle
          cx="60" cy="60" r={radius}
          fill="none"
          stroke="var(--color-bg-2)"
          strokeWidth="8"
        />
        <circle
          cx="60" cy="60" r={radius}
          fill="none"
          stroke="var(--color-green)"
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          className="transition-[stroke-dashoffset] duration-[1.6s] ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-serif text-[32px] font-[400] leading-none tracking-[-0.02em] text-ink [font-variant-numeric:tabular-nums]">
          {score}
        </span>
        <span className="mt-0.5 text-[10.5px] font-semibold text-green">
          {delta >= 0 ? "▲" : "▼"} {Math.abs(delta)}
        </span>
      </div>
    </div>
  );
}

// ── Health signal row ─────────────────────────────────────────────────────────

function HealthRow({ signal }: { signal: HealthSignal }) {
  return (
    <div className="grid grid-cols-[1fr_36px_28px] items-center gap-2.5 text-[12px]">
      <span className="min-w-0 truncate text-ink-2">{signal.label}</span>
      <div className="h-1 overflow-hidden rounded-sm bg-bg-2">
        <div
          className={cn("h-full w-[--score] rounded-sm", signal.isWarn ? "bg-terra" : "bg-green")}
          style={{ "--score": `${signal.score}%` } as React.CSSProperties}
        />
      </div>
      <span className="text-right font-mono text-[11.5px] text-ink [font-variant-numeric:tabular-nums]">
        {signal.score}
      </span>
    </div>
  );
}

// ── Skeleton ──────────────────────────────────────────────────────────────────

function HealthSkeleton() {
  return (
    <div className="flex animate-pulse items-center gap-[18px]">
      <div className="h-[110px] w-[110px] shrink-0 rounded-full bg-bg-3" />
      <div className="flex flex-1 flex-col gap-2">
        {[0,1,2,3,4].map((i) => (
          <div key={i} className="grid grid-cols-[1fr_36px_28px] items-center gap-2.5">
            <div className="h-3 w-24 rounded bg-bg-3" />
            <div className="h-1 rounded bg-bg-2" />
            <div className="h-3 w-6 rounded bg-bg-2" />
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Career Health card ────────────────────────────────────────────────────────

export interface CareerHealthCardProps {
  score: number;
  delta: number;
  signals: HealthSignal[];
  lastUpdatedLabel: string;
  isLoading: boolean;
}

const DEFAULT_SIGNALS: HealthSignal[] = [
  { label: "Roadmap progress",  score: 0, isWarn: false },
  { label: "Skill readiness",   score: 0, isWarn: false },
  { label: "Portfolio strength", score: 0, isWarn: false },
  { label: "Market alignment",  score: 0, isWarn: false },
  { label: "Network activity",  score: 0, isWarn: true  },
];

export function CareerHealthCard({
  score,
  delta,
  signals,
  lastUpdatedLabel,
  isLoading,
}: CareerHealthCardProps) {
  const displaySignals = signals.length > 0 ? signals : DEFAULT_SIGNALS;

  return (
    <div className="rounded-[12px] border border-rule bg-paper p-6">
      {/* Header */}
      <div className="mb-[18px] flex items-start justify-between border-b border-rule pb-3.5">
        <div>
          <h2 className="font-serif text-[17px] font-medium tracking-[-0.01em] text-ink">
            Career Health
          </h2>
          <p className="mt-[3px] text-[11.5px] text-ink-3">
            Five honest signals ·{" "}
            <em className="font-serif italic text-terra">{lastUpdatedLabel || "updated soon"}</em>
          </p>
        </div>
        <Link
          href="#"
          className="text-[12px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
        >
          Method →
        </Link>
      </div>

      {isLoading ? (
        <HealthSkeleton />
      ) : (
        <div className="grid grid-cols-[110px_1fr] items-center gap-[18px]">
          <Gauge score={score} delta={delta} />
          <div className="flex flex-col gap-2">
            {displaySignals.map((sig) => (
              <HealthRow key={sig.label} signal={sig} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
