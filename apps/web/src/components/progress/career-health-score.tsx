import { cn } from "@/lib/utils";

export interface HealthSignal {
  label: string;
  score: number;
}

export interface CareerHealthScoreProps {
  score: number;
  delta?: number;
  signals: HealthSignal[];
  className?: string;
}

export function CareerHealthScore({ score, delta, signals, className }: CareerHealthScoreProps) {
  const pct = Math.max(0, Math.min(100, Math.round(score)));

  return (
    <div className={cn("rounded-[12px] border border-rule bg-paper p-6", className)}>
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-[12px] font-semibold uppercase tracking-[0.1em] text-ink-3">
            Career health
          </p>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="font-serif text-[36px] font-medium leading-none text-ink">{pct}</span>
            {typeof delta === "number" && (
              <span className={cn("text-[13px] font-semibold", delta >= 0 ? "text-green-2" : "text-terra-2")}>
                {delta >= 0 ? "+" : ""}
                {delta}
              </span>
            )}
          </div>
        </div>
        <span className="flex h-12 w-12 items-center justify-center rounded-full bg-green-faint text-green-2">
          <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" className="h-6 w-6" aria-hidden="true">
            <path d="M2 11l4-4 3 3 5-6 4 4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      </div>

      <ul className="mt-5 space-y-3 border-t border-rule pt-4">
        {signals.map((sig) => (
          <li key={sig.label}>
            <div className="mb-1 flex items-center justify-between text-[12.5px]">
              <span className="text-ink-2">{sig.label}</span>
              <span className="font-mono text-ink-3">{sig.score}</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-bg-3">
              <div
                className={cn(
                  "h-full w-[--bar] rounded-full",
                  sig.score >= 70 ? "bg-green" : sig.score >= 45 ? "bg-gold" : "bg-terra",
                )}
                style={{ "--bar": `${sig.score}%` } as React.CSSProperties}
              />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
