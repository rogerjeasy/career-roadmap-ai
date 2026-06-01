import { cn } from "@/lib/utils";

export interface GapReportCardProps {
  /** AI-suggested next steps / transitions derived from the CV. */
  suggestions: string[];
  className?: string;
}

export function GapReportCard({ suggestions, className }: GapReportCardProps) {
  return (
    <div className={cn("rounded-[12px] border border-rule bg-paper p-6", className)}>
      <div className="mb-1 flex items-center gap-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-[7px] bg-terra-faint text-terra-2">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" className="h-4 w-4" aria-hidden="true">
            <path d="M8 1l2 4 4 .5-3 3 .8 4L8 14.5 4.2 16.5 5 12 2 9l4-.5z" />
          </svg>
        </span>
        <h2 className="font-serif text-[16px] font-medium tracking-[-0.01em] text-ink">
          Suggested next steps
        </h2>
      </div>
      <p className="mb-4 text-[12.5px] text-ink-3">
        Career directions and gaps inferred from your experience. These are starting points — your roadmap refines them.
      </p>

      {suggestions.length === 0 ? (
        <p className="rounded-[8px] bg-bg px-4 py-3 text-[13px] text-ink-3">
          Generate a roadmap to get tailored gap analysis against your target role.
        </p>
      ) : (
        <ul className="space-y-2.5">
          {suggestions.map((s, i) => (
            <li
              key={i}
              className="flex items-start gap-3 rounded-[8px] border border-rule bg-bg px-3.5 py-3"
            >
              <span className="mt-px flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-green font-mono text-[11px] font-semibold text-white">
                {i + 1}
              </span>
              <span className="min-w-0 text-[13px] leading-snug text-ink-2">{s}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
