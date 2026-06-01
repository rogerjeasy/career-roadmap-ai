import { cn } from "@/lib/utils";

export interface ReadinessMeterProps {
  /** 0–100. */
  score: number;
  label?: string;
  className?: string;
}

function toneFor(score: number): { ring: string; text: string; verdict: string } {
  if (score >= 75) return { ring: "text-green", text: "text-green-2", verdict: "Strong" };
  if (score >= 50) return { ring: "text-gold", text: "text-gold", verdict: "Developing" };
  return { ring: "text-terra", text: "text-terra-2", verdict: "Early" };
}

export function ReadinessMeter({ score, label = "Readiness", className }: ReadinessMeterProps) {
  const pct = Math.max(0, Math.min(100, Math.round(score)));
  const tone = toneFor(pct);
  const radius = 52;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (pct / 100) * circumference;

  return (
    <div className={cn("flex flex-col items-center", className)}>
      <div className="relative h-[132px] w-[132px]">
        <svg viewBox="0 0 132 132" className="h-full w-full -rotate-90" aria-hidden="true">
          <circle cx="66" cy="66" r={radius} fill="none" stroke="currentColor" strokeWidth="10" className="text-bg-3" />
          <circle
            cx="66"
            cy="66"
            r={radius}
            fill="none"
            stroke="currentColor"
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            className={cn("transition-[stroke-dashoffset] duration-700 ease-out", tone.ring)}
          />
        </svg>
        <div
          className="absolute inset-0 flex flex-col items-center justify-center"
          role="meter"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={label}
        >
          <span className={cn("font-serif text-[30px] font-medium leading-none", tone.text)}>
            {pct}
          </span>
          <span className="mt-1 text-[10.5px] font-semibold uppercase tracking-[0.1em] text-ink-3">
            / 100
          </span>
        </div>
      </div>
      <p className="mt-3 text-[13px] font-medium text-ink">{label}</p>
      <p className={cn("text-[12px] font-semibold", tone.text)}>{tone.verdict}</p>
    </div>
  );
}
