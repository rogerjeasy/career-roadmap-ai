import { cn } from "@/lib/utils";

export interface MetricPoint {
  label: string;
  value: number;
}

export interface MetricChartProps {
  title: string;
  unit?: string;
  points: MetricPoint[];
  tone?: "green" | "terra" | "gold";
  className?: string;
}

const TONE_FILL: Record<NonNullable<MetricChartProps["tone"]>, string> = {
  green: "bg-green",
  terra: "bg-terra",
  gold: "bg-gold",
};

/** Lightweight responsive bar chart — no charting dependency. */
export function MetricChart({ title, unit, points, tone = "green", className }: MetricChartProps) {
  const max = Math.max(...points.map((p) => p.value), 1);
  const latest = points[points.length - 1]?.value ?? 0;

  return (
    <div className={cn("rounded-[12px] border border-rule bg-paper p-6", className)}>
      <div className="mb-4 flex items-baseline justify-between">
        <h3 className="font-serif text-[15px] font-medium tracking-[-0.01em] text-ink">{title}</h3>
        <span className="font-mono text-[13px] text-ink-2">
          {latest}
          {unit ? ` ${unit}` : ""}
        </span>
      </div>
      <div className="flex h-28 items-end gap-1.5">
        {points.map((p) => (
          <div key={p.label} className="flex min-w-0 flex-1 flex-col items-center gap-1.5">
            <div className="flex h-full w-full items-end">
              <div
                className={cn("w-full rounded-t-[4px] h-[--h]", TONE_FILL[tone])}
                style={{ "--h": `${(p.value / max) * 100}%` } as React.CSSProperties}
              />
            </div>
            <span className="truncate text-[10px] text-ink-3">{p.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
