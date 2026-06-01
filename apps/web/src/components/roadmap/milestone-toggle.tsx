"use client";

import { cn } from "@/lib/utils";

export interface MilestoneToggleProps {
  label: string;
  done: boolean;
  onToggle: () => void;
  className?: string;
}

function CheckMark() {
  return (
    <svg viewBox="0 0 12 12" fill="none" className="h-[11px] w-[11px]" aria-hidden="true">
      <path d="M2 6.5l3 3 5-7" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function MilestoneToggle({ label, done, onToggle, className }: MilestoneToggleProps) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={done}
      onClick={onToggle}
      className={cn(
        "flex w-full items-start gap-3 rounded-[7px] px-2 py-2 text-left transition-colors duration-150 hover:bg-bg",
        className,
      )}
    >
      <span
        className={cn(
          "mt-px flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-[5px] border-[1.5px] transition-all duration-150",
          done ? "border-green bg-green text-white" : "border-rule-strong bg-paper",
        )}
      >
        {done && <CheckMark />}
      </span>
      <span
        className={cn(
          "min-w-0 text-[13.5px] leading-snug text-ink",
          done && "text-ink-3 line-through decoration-rule-strong",
        )}
      >
        {label}
      </span>
    </button>
  );
}
