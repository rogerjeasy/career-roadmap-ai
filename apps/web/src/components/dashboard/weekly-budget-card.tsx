"use client";

import Link from "next/link";
import { cn } from "@/lib/utils";
import type { WeeklyBudgetCategory, TaskCategory } from "@/types/dashboard.types";
import { ROUTES } from "@/lib/constants";

// ── Category config ───────────────────────────────────────────────────────────

const CAT_CONFIG: Record<TaskCategory, { label: string; barClass: string; swatchClass: string }> = {
  build:   { label: "Build · projects, code", barClass: "bg-green",              swatchClass: "bg-green" },
  read:    { label: "Read & learn",           barClass: "bg-gold",               swatchClass: "bg-gold" },
  network: { label: "Network & outreach",     barClass: "bg-terra",              swatchClass: "bg-terra" },
  review:  { label: "Review & reflect",       barClass: "bg-[#7BA08D]",          swatchClass: "bg-[#7BA08D]" },
};

// ── Stacked bar ───────────────────────────────────────────────────────────────

interface StackedBarProps {
  categories: WeeklyBudgetCategory[];
  totalBudget: number;
}

function StackedBar({ categories, totalBudget }: StackedBarProps) {
  const logged = categories.reduce((s, c) => s + c.hoursLogged, 0);
  const remaining = Math.max(0, totalBudget - logged);

  return (
    <div className="mb-[18px] flex h-3.5 overflow-hidden rounded-full border border-rule bg-bg-2">
      {categories.map((cat) => {
        const pct = (cat.hoursLogged / totalBudget) * 100;
        if (pct <= 0) return null;
        return (
          <div
            key={cat.id}
            className={cn("h-full w-[--seg] border-r border-white/40 transition-opacity duration-150 hover:opacity-85 last:border-r-0", CAT_CONFIG[cat.id].barClass)}
            style={{ "--seg": `${pct}%` } as React.CSSProperties}
            title={`${cat.hoursLogged}h ${CAT_CONFIG[cat.id].label}`}
          />
        );
      })}
      {remaining > 0 && (
        <div
          className="h-full w-[--rem]"
          style={{ "--rem": `${(remaining / totalBudget) * 100}%` } as React.CSSProperties}
        />
      )}
    </div>
  );
}

// ── Category breakdown row ────────────────────────────────────────────────────

function CategoryRow({ cat }: { cat: WeeklyBudgetCategory }) {
  const cfg = CAT_CONFIG[cat.id];
  return (
    <div className="grid grid-cols-[10px_1fr_auto] items-center gap-[9px] text-[12.5px]">
      <span className={cn("h-2 w-2 rounded-sm", cfg.swatchClass)} aria-hidden="true" />
      <span className="min-w-0 truncate font-medium text-ink-2">{cfg.label}</span>
      <span className="font-mono text-[11.5px] text-ink [font-variant-numeric:tabular-nums]">
        {cat.hoursLogged}h{" "}
        <span className="text-ink-3">/ {cat.hoursTarget}h</span>
      </span>
    </div>
  );
}

// ── Weekly budget card ────────────────────────────────────────────────────────

export interface WeeklyBudgetCardProps {
  categories: WeeklyBudgetCategory[];
  totalBudgetHours: number;
  isLoading: boolean;
}

const DEFAULT_CATEGORIES: WeeklyBudgetCategory[] = [
  { id: "build",   hoursLogged: 0, hoursTarget: 5 },
  { id: "read",    hoursLogged: 0, hoursTarget: 3 },
  { id: "network", hoursLogged: 0, hoursTarget: 2 },
  { id: "review",  hoursLogged: 0, hoursTarget: 2 },
];

export function WeeklyBudgetCard({ categories, totalBudgetHours, isLoading }: WeeklyBudgetCardProps) {
  const cats = categories.length > 0 ? categories : DEFAULT_CATEGORIES;
  const totalLogged = cats.reduce((s, c) => s + c.hoursLogged, 0);
  const pct = totalBudgetHours > 0 ? Math.round((totalLogged / totalBudgetHours) * 100) : 0;
  const isOnPace = pct >= 60;

  const weekNum = Math.ceil(
    (new Date().getTime() - new Date(new Date().getFullYear(), 0, 1).getTime()) /
    (7 * 24 * 60 * 60 * 1000),
  );

  return (
    <div className="rounded-[12px] border border-rule bg-paper p-6">
      {/* Header */}
      <div className="mb-[18px] flex items-start justify-between border-b border-rule pb-3.5">
        <div>
          <h2 className="font-serif text-[17px] font-medium tracking-[-0.01em] text-ink">
            This week&apos;s time budget
          </h2>
          <p className="mt-[3px] text-[11.5px] text-ink-3">
            Wk {weekNum} ·{" "}
            <em className="font-serif italic text-terra">resets Sunday 23:59</em>
          </p>
        </div>
        <Link
          href={ROUTES.schedule}
          className="text-[12px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
        >
          Adjust →
        </Link>
      </div>

      {isLoading ? (
        <div className="animate-pulse space-y-3">
          <div className="h-10 w-40 rounded bg-bg-3" />
          <div className="h-3.5 w-full rounded-full bg-bg-2" />
          <div className="grid grid-cols-2 gap-2.5">
            {[0,1,2,3].map((i) => <div key={i} className="h-4 rounded bg-bg-2" />)}
          </div>
        </div>
      ) : (
        <>
          {/* Total */}
          <div className="mb-[18px] flex items-baseline gap-3">
            <div className="font-serif text-[36px] font-[350] leading-none tracking-[-0.02em] text-ink [font-variant-numeric:tabular-nums]">
              <em className="italic text-green">{totalLogged}</em> h
            </div>
            <div className="text-sm text-ink-3">
              of <strong className="font-semibold text-ink-2">{totalBudgetHours} h</strong> budgeted
            </div>
            <div
              className={cn(
                "ml-auto rounded-full px-[10px] py-1 text-[11px] font-semibold",
                isOnPace ? "bg-green-soft text-green" : "bg-terra-faint text-terra-2",
              )}
            >
              {pct}% · {isOnPace ? "on pace" : "behind pace"}
            </div>
          </div>

          <StackedBar categories={cats} totalBudget={totalBudgetHours} />

          <div className="grid grid-cols-2 gap-x-[22px] gap-y-2.5">
            {cats.map((cat) => (
              <CategoryRow key={cat.id} cat={cat} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
