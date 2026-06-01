import { cn } from "@/lib/utils";

export interface MatchScoreBadgeProps {
  /** 0–1 fractional match score. */
  score: number;
  size?: "sm" | "md";
  className?: string;
}

export function MatchScoreBadge({ score, size = "md", className }: MatchScoreBadgeProps) {
  const pct = Math.round(Math.max(0, Math.min(1, score)) * 100);
  const tone =
    pct >= 80
      ? "bg-green-soft text-green-2"
      : pct >= 60
      ? "bg-gold-soft text-gold"
      : "bg-bg-3 text-ink-2";

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-[6px] font-semibold",
        size === "sm" ? "px-1.5 py-0.5 text-[11px]" : "px-2 py-1 text-[12px]",
        tone,
        className,
      )}
      aria-label={`${pct} percent match`}
    >
      {pct}% match
    </span>
  );
}
