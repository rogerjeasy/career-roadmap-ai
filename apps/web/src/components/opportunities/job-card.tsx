import type { JobMatch } from "@/lib/api/opportunities";
import { cn } from "@/lib/utils";
import { MatchScoreBadge } from "./match-score-badge";

export interface JobCardProps {
  job: JobMatch;
  className?: string;
}

function formatSalary(min: number | null, max: number | null): string | null {
  if (min == null && max == null) return null;
  const fmt = (n: number) => (n >= 1000 ? `${Math.round(n / 1000)}k` : `${n}`);
  if (min != null && max != null) return `${fmt(min)}–${fmt(max)}`;
  return fmt((min ?? max) as number);
}

export function JobCard({ job, className }: JobCardProps) {
  const salary = formatSalary(job.salaryMin, job.salaryMax);

  return (
    <div className={cn("flex flex-col gap-3 rounded-[12px] border border-rule bg-paper p-5", className)}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate font-serif text-[16px] font-medium tracking-[-0.01em] text-ink">
            {job.title || "Untitled role"}
          </h3>
          <p className="mt-0.5 truncate text-[13px] text-ink-2">
            {job.company}
            {job.location && <span className="text-ink-3"> · {job.location}</span>}
          </p>
        </div>
        <MatchScoreBadge score={job.matchScore} />
      </div>

      <div className="flex flex-wrap gap-1.5">
        {job.remote && (
          <span className="rounded-[5px] bg-green-faint px-2 py-0.5 text-[11px] font-medium text-green-2">
            Remote
          </span>
        )}
        {job.seniorityLevel && (
          <span className="rounded-[5px] bg-bg-2 px-2 py-0.5 text-[11px] font-medium capitalize text-ink-2">
            {job.seniorityLevel}
          </span>
        )}
        {salary && (
          <span className="rounded-[5px] bg-bg-2 px-2 py-0.5 font-mono text-[11px] text-ink-2">
            {salary}
          </span>
        )}
      </div>

      {job.matchReasons.length > 0 && (
        <ul className="space-y-1">
          {job.matchReasons.slice(0, 2).map((reason, i) => (
            <li key={i} className="flex gap-2 text-[12.5px] leading-snug text-ink-2">
              <span className="mt-[6px] h-1 w-1 shrink-0 rounded-full bg-green" aria-hidden="true" />
              <span className="min-w-0">{reason}</span>
            </li>
          ))}
        </ul>
      )}

      {(job.skillOverlap.length > 0 || job.missingSkills.length > 0) && (
        <div className="flex flex-wrap gap-1.5 border-t border-rule pt-3">
          {job.skillOverlap.slice(0, 4).map((s) => (
            <span key={`o-${s}`} className="rounded-[5px] bg-green-soft px-2 py-0.5 text-[11px] font-medium text-green-2">
              {s}
            </span>
          ))}
          {job.missingSkills.slice(0, 3).map((s) => (
            <span key={`m-${s}`} className="rounded-[5px] border border-dashed border-terra-soft px-2 py-0.5 text-[11px] font-medium text-terra-2">
              {s}
            </span>
          ))}
        </div>
      )}

      {job.url && (
        <a
          href={job.url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-auto inline-flex items-center gap-1 text-[12.5px] font-medium text-terra transition-colors duration-150 hover:text-terra-2"
        >
          View posting →
        </a>
      )}
    </div>
  );
}
