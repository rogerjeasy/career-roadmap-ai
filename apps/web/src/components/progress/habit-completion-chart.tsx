import { cn } from "@/lib/utils";

export interface HabitWeek {
  habit: string;
  /** 7 booleans, Mon–Sun. */
  days: boolean[];
}

export interface HabitCompletionChartProps {
  weeks: HabitWeek[];
  className?: string;
}

const DAY_LABELS = ["M", "T", "W", "T", "F", "S", "S"];

export function HabitCompletionChart({ weeks, className }: HabitCompletionChartProps) {
  return (
    <div className={cn("rounded-[12px] border border-rule bg-paper p-6", className)}>
      <h3 className="mb-4 font-serif text-[15px] font-medium tracking-[-0.01em] text-ink">
        This week&apos;s habits
      </h3>
      <ul className="space-y-3">
        {weeks.map((row) => {
          const done = row.days.filter(Boolean).length;
          return (
            <li key={row.habit} className="flex items-center gap-3">
              <span className="min-w-0 flex-1 truncate text-[13px] text-ink-2">{row.habit}</span>
              <div className="flex shrink-0 gap-1" aria-label={`${done} of 7 days completed`}>
                {row.days.map((d, i) => (
                  <span
                    key={i}
                    title={DAY_LABELS[i]}
                    className={cn(
                      "flex h-5 w-5 items-center justify-center rounded-[4px] text-[9px] font-semibold",
                      d ? "bg-green text-white" : "bg-bg-3 text-ink-3",
                    )}
                  >
                    {DAY_LABELS[i]}
                  </span>
                ))}
              </div>
              <span className="w-9 shrink-0 text-right font-mono text-[11.5px] text-ink-3">{done}/7</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
