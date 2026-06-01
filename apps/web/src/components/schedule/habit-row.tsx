"use client";

import { cn } from "@/lib/utils";
import { HabitStreakBadge } from "./habit-streak-badge";

export interface HabitRowProps {
  label: string;
  cadence: string;
  streak: number;
  doneToday: boolean;
  onToggle: () => void;
  className?: string;
}

function CheckMark() {
  return (
    <svg viewBox="0 0 12 12" fill="none" className="h-3 w-3" aria-hidden="true">
      <path d="M2 6.5l3 3 5-7" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function HabitRow({ label, cadence, streak, doneToday, onToggle, className }: HabitRowProps) {
  return (
    <div className={cn("flex items-center gap-3.5 rounded-[10px] border border-rule bg-paper px-4 py-3", className)}>
      <button
        type="button"
        role="checkbox"
        aria-checked={doneToday}
        onClick={onToggle}
        className={cn(
          "flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-[6px] border-[1.5px] transition-all duration-150",
          doneToday ? "border-green bg-green text-white" : "border-rule-strong bg-paper hover:border-green",
        )}
      >
        {doneToday && <CheckMark />}
      </button>
      <div className="min-w-0 flex-1">
        <p className={cn("truncate text-[13.5px] font-medium text-ink", doneToday && "text-ink-3")}>{label}</p>
        <p className="text-[11.5px] text-ink-3">{cadence}</p>
      </div>
      {streak > 0 && <HabitStreakBadge days={streak} />}
    </div>
  );
}
