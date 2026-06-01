import { cn } from "@/lib/utils";

export interface HabitStreakBadgeProps {
  days: number;
  className?: string;
}

export function HabitStreakBadge({ days, className }: HabitStreakBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-[6px] bg-terra-faint px-2 py-0.5 text-[11.5px] font-semibold text-terra-2",
        className,
      )}
      aria-label={`${days} day streak`}
    >
      <svg viewBox="0 0 16 16" fill="currentColor" className="h-3 w-3" aria-hidden="true">
        <path d="M8 1c1 2.5-.5 3.5-1 5-1-1-1.5-2-1-3.5C4 4 3 6 3 8a5 5 0 0 0 10 0c0-2.5-2-4.5-3.5-6C9 3.5 9 4.5 8 1z" />
      </svg>
      {days}-day streak
    </span>
  );
}
