import { cn } from "@/lib/utils";
import type { MarketSignal, MarketSentiment } from "@/types/market.types";

export interface MarketSignalCardProps {
  signal: MarketSignal;
  className?: string;
}

const SENTIMENT_STYLE: Record<MarketSentiment, { dot: string; chip: string }> = {
  positive: { dot: "bg-green", chip: "bg-green-soft text-green-2" },
  neutral: { dot: "bg-gold", chip: "bg-gold-soft text-gold" },
  negative: { dot: "bg-terra", chip: "bg-terra-soft text-terra-2" },
};

export function MarketSignalCard({ signal, className }: MarketSignalCardProps) {
  const style = SENTIMENT_STYLE[signal.sentiment];

  return (
    <article className={cn("flex flex-col gap-2.5 rounded-[12px] border border-rule bg-paper p-5", className)}>
      <div className="flex items-center justify-between gap-2">
        <span className={cn("rounded-[5px] px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.04em]", style.chip)}>
          {signal.tag}
        </span>
        <span className="flex items-center gap-1.5 text-[11.5px] text-ink-3">
          <span className={cn("h-1.5 w-1.5 rounded-full", style.dot)} aria-hidden="true" />
          {signal.timeLabel}
        </span>
      </div>
      <h3 className="font-serif text-[15.5px] font-medium leading-snug tracking-[-0.01em] text-ink">
        {signal.title}
      </h3>
      <p className="text-[13px] leading-relaxed text-ink-2">{signal.summary}</p>
      <p className="mt-auto pt-1 text-[11.5px] text-ink-3">Source · {signal.source}</p>
    </article>
  );
}
