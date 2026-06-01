import type { CvAnalysisResult } from "@/types/onboarding.types";
import { ReadinessMeter } from "./readiness-meter";
import { SkillComparisonTable } from "./skill-comparison-table";
import { GapReportCard } from "./gap-report-card";

export interface CvResultsProps {
  analysis: CvAnalysisResult;
}

/** Heuristic 0–100 readiness score until the gap-analysis agent scores it. */
export function computeReadiness(a: CvAnalysisResult): number {
  const exp = Math.min(a.yearsOfExperience / 8, 1) * 40;
  const strong = Math.min(a.strongSkillsCount / 10, 1) * 30;
  const leadership = Math.min(a.leadershipSignals / 5, 1) * 15;
  const projects = Math.min(a.projects.length / 5, 1) * 15;
  return Math.round(exp + strong + leadership + projects);
}

export function CvResults({ analysis }: CvResultsProps) {
  const readiness = computeReadiness(analysis);

  return (
    <div className="space-y-6">
      {/* Summary + readiness */}
      <div className="grid gap-5 lg:grid-cols-[1fr_auto] lg:items-center">
        <div className="rounded-[12px] border border-rule bg-paper p-6">
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-ink-3">
            Profile summary
          </p>
          <p className="text-[14px] leading-relaxed text-ink-2">
            {analysis.summary ??
              `${analysis.currentRole ?? "Professional"} with ${analysis.yearsOfExperience} years of experience.`}
          </p>
          <div className="mt-4 flex flex-wrap gap-x-7 gap-y-3 border-t border-rule pt-4">
            <Stat value={`${analysis.yearsOfExperience}`} label="years experience" />
            <Stat value={`${analysis.strongSkillsCount}`} label="strong skills" />
            <Stat value={`${analysis.roles.length}`} label="roles" />
            <Stat value={`${analysis.projects.length}`} label="projects" />
            <Stat value={`${analysis.leadershipSignals}`} label="leadership signals" />
          </div>
        </div>
        <div className="flex justify-center rounded-[12px] border border-rule bg-paper p-6 lg:w-[220px]">
          <ReadinessMeter score={readiness} label="CV readiness" />
        </div>
      </div>

      {/* Skills + gaps */}
      <div className="grid gap-5 lg:grid-cols-2">
        <div className="rounded-[12px] border border-rule bg-paper p-6">
          <h2 className="mb-4 font-serif text-[16px] font-medium tracking-[-0.01em] text-ink">
            Skills detected
          </h2>
          <SkillComparisonTable skills={analysis.skills} />
        </div>
        <GapReportCard suggestions={analysis.careerPathSuggestions ?? []} />
      </div>

      {/* Experience */}
      {analysis.roles.length > 0 && (
        <div className="rounded-[12px] border border-rule bg-paper p-6">
          <h2 className="mb-4 font-serif text-[16px] font-medium tracking-[-0.01em] text-ink">
            Experience
          </h2>
          <ul className="space-y-3">
            {analysis.roles.map((role, i) => (
              <li key={i} className="flex items-start justify-between gap-4 border-b border-rule pb-3 last:border-b-0 last:pb-0">
                <div className="min-w-0">
                  <p className="text-[13.5px] font-medium text-ink">{role.title}</p>
                  {role.company && <p className="text-[12.5px] text-ink-3">{role.company}</p>}
                </div>
                {role.durationMonths != null && (
                  <span className="shrink-0 rounded-[5px] bg-bg-2 px-2 py-0.5 font-mono text-[11px] text-ink-3">
                    {role.durationMonths >= 12
                      ? `${(role.durationMonths / 12).toFixed(1).replace(/\.0$/, "")}y`
                      : `${role.durationMonths}mo`}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div>
      <p className="font-serif text-[20px] font-medium leading-none text-ink">{value}</p>
      <p className="mt-1 text-[11px] text-ink-3">{label}</p>
    </div>
  );
}
