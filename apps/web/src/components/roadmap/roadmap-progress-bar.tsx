import { cn } from "@/lib/utils";

export interface RoadmapProgressBarProps {
  /** 0–100. */
  value: number;
  label?: string;
  showValue?: boolean;
  tone?: "green" | "terra" | "gold";
  size?: "sm" | "md";
  className?: string;
}

const TONE_FILL: Record<NonNullable<RoadmapProgressBarProps["tone"]>, string> = {
  green: "bg-green",
  terra: "bg-terra",
  gold: "bg-gold",
};

export function RoadmapProgressBar({
  value,
  label,
  showValue = true,
  tone = "green",
  size = "md",
  className,
}: RoadmapProgressBarProps) {
  const pct = Math.max(0, Math.min(100, Math.round(value)));

  return (
    <div className={cn("w-full", className)}>
      {(label || showValue) && (
        <div className="mb-1.5 flex items-center justify-between text-[11.5px]">
          {label && <span className="font-medium text-ink-2">{label}</span>}
          {showValue && <span className="font-mono text-ink-3">{pct}%</span>}
        </div>
      )}
      <div
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
        className={cn(
          "w-full overflow-hidden rounded-full bg-bg-3",
          size === "sm" ? "h-1.5" : "h-2.5",
        )}
      >
        <div
          className={cn(
            "h-full w-[--bar] rounded-full transition-[width] duration-500 ease-out",
            TONE_FILL[tone],
          )}
          style={{ "--bar": `${pct}%` } as React.CSSProperties}
        />
      </div>
    </div>
  );
}
