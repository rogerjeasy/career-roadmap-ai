import { cn } from "@/lib/utils";

export interface HabitHeatmapProps {
  /** Completion intensity 0–4 per day, oldest → newest (e.g. last 12 weeks × 7). */
  values: number[];
  weeks?: number;
  className?: string;
}

const LEVEL_CLASS = [
  "bg-bg-3",
  "bg-green-soft",
  "bg-green/40",
  "bg-green/70",
  "bg-green",
];

export function HabitHeatmap({ values, weeks = 12, className }: HabitHeatmapProps) {
  const total = weeks * 7;
  const cells = values.slice(-total);
  // Pad the front so the grid is always full.
  const padded = Array<number>(Math.max(0, total - cells.length)).fill(0).concat(cells);

  // Build columns of 7 (one week each).
  const columns: number[][] = [];
  for (let w = 0; w < weeks; w += 1) {
    columns.push(padded.slice(w * 7, w * 7 + 7));
  }

  return (
    <div className={cn("rounded-[12px] border border-rule bg-paper p-6", className)}>
      <h3 className="mb-4 font-serif text-[15px] font-medium tracking-[-0.01em] text-ink">
        Consistency
      </h3>
      <div className="flex gap-1 overflow-x-auto pb-1">
        {columns.map((col, ci) => (
          <div key={ci} className="flex flex-col gap-1">
            {col.map((level, ri) => (
              <span
                key={ri}
                className={cn("h-3 w-3 rounded-[3px]", LEVEL_CLASS[Math.max(0, Math.min(4, level))])}
                aria-hidden="true"
              />
            ))}
          </div>
        ))}
      </div>
      <div className="mt-3 flex items-center gap-1.5 text-[11px] text-ink-3">
        <span>Less</span>
        {LEVEL_CLASS.map((cls, i) => (
          <span key={i} className={cn("h-3 w-3 rounded-[3px]", cls)} aria-hidden="true" />
        ))}
        <span>More</span>
      </div>
    </div>
  );
}
