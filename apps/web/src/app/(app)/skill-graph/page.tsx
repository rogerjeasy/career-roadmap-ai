"use client";

import Link from "next/link";
import { cn } from "@/lib/utils";
import { ROUTES } from "@/lib/constants";
import { useSkillGraph } from "@/hooks/use-skill-graph";
import type { PhaseStatus, SkillStatus } from "@/types/skill-graph.types";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { SkillChip } from "@/components/skill-graph/skill-chip";

const PHASE_NODE_STYLE: Record<PhaseStatus, string> = {
  done: "border-green bg-green text-white",
  current: "border-terra bg-terra text-white",
  future: "border-rule-strong bg-paper text-ink-3",
};

const PHASE_LABEL: Record<PhaseStatus, string> = {
  done: "Complete",
  current: "In progress",
  future: "Upcoming",
};

const LEGEND: { status: SkillStatus; label: string }[] = [
  { status: "have", label: "Already have" },
  { status: "acquired", label: "Acquired via roadmap" },
  { status: "learning", label: "Building now" },
  { status: "planned", label: "Planned" },
];

interface StatCardProps {
  label: string;
  value: string;
  hint?: string;
}

function StatCard({ label, value, hint }: StatCardProps) {
  return (
    <div className="rounded-[12px] border border-rule bg-paper p-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-ink-3">
        {label}
      </p>
      <p className="mt-1.5 font-serif text-[24px] font-medium leading-none tracking-[-0.02em] text-ink">
        {value}
      </p>
      {hint && <p className="mt-1.5 text-[12px] text-ink-3">{hint}</p>}
    </div>
  );
}

export default function SkillGraphPage() {
  const { isLoading, hasRoadmap, targetRole, foundationSkills, phases, stats } =
    useSkillGraph();

  return (
    <div className="mx-auto max-w-[1000px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Planning"
        title="Skill Graph"
        description={
          targetRole
            ? `A living map of the skills between you and ${targetRole} — what you already have, what you're building, and what's still ahead.`
            : "A living map of your skills — what you already have, what you're building, and what's still ahead on your roadmap."
        }
      />

      {isLoading ? (
        <LoadingSpinner fullPage label="Mapping your skills…" />
      ) : !hasRoadmap ? (
        <EmptyState
          title="No roadmap to map yet"
          description="Your skill graph is built from your roadmap's target skills and your profile. Generate a roadmap to see where you stand."
          action={
            <Link
              href={ROUTES.roadmapGenerate}
              className="inline-flex items-center rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2"
            >
              Generate your roadmap →
            </Link>
          }
        />
      ) : stats.targetTotal === 0 ? (
        <EmptyState
          title="No target skills on this roadmap"
          description="This roadmap doesn't list skills to gain yet. Edit a phase to add target skills and they'll appear here."
          action={
            <Link
              href={ROUTES.roadmap}
              className="inline-flex items-center rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2"
            >
              Open your roadmap →
            </Link>
          }
        />
      ) : (
        <>
          {/* Stats */}
          <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard
              label="Readiness"
              value={`${stats.readinessPercent}%`}
              hint={`${stats.acquired}/${stats.targetTotal} skills`}
            />
            <StatCard label="Acquired" value={String(stats.acquired)} hint="have or earned" />
            <StatCard label="Building" value={String(stats.learning)} hint="current phase" />
            <StatCard label="Gaps" value={String(stats.gaps)} hint="not started" />
          </div>

          {/* Legend */}
          <div className="mb-7 flex flex-wrap gap-x-4 gap-y-2">
            {LEGEND.map((item) => (
              <span
                key={item.status}
                className="inline-flex items-center gap-1.5 text-[12px] text-ink-2"
              >
                <SkillChip label={item.label} status={item.status} />
              </span>
            ))}
          </div>

          {/* Foundation */}
          {foundationSkills.length > 0 && (
            <section className="mb-7 rounded-[12px] border border-rule bg-paper p-5">
              <h2 className="mb-1 font-serif text-[16px] font-medium tracking-[-0.01em] text-ink">
                Your foundation
              </h2>
              <p className="mb-3.5 text-[13px] leading-relaxed text-ink-2">
                Skills you already bring that sit outside the roadmap&apos;s targets — your starting base.
              </p>
              <div className="flex flex-wrap gap-2">
                {foundationSkills.map((s) => (
                  <SkillChip key={s.name} label={s.name} status={s.status} />
                ))}
              </div>
            </section>
          )}

          {/* Phase spine graph */}
          <section aria-label="Skills by roadmap phase">
            <h2 className="mb-4 text-[12px] font-semibold uppercase tracking-[0.14em] text-ink-3">
              Skills by phase
            </h2>
            <ol className="relative" role="list">
              {phases.map((phase, i) => {
                const isLast = i === phases.length - 1;
                return (
                  <li key={phase.id} className="relative flex gap-4 pb-7 last:pb-0">
                    {/* Spine: node + connector line */}
                    <div className="flex shrink-0 flex-col items-center">
                      <span
                        className={cn(
                          "flex h-9 w-9 items-center justify-center rounded-full border-2 font-serif text-[14px] font-medium",
                          PHASE_NODE_STYLE[phase.status],
                        )}
                      >
                        {phase.number}
                      </span>
                      {!isLast && (
                        <span
                          aria-hidden="true"
                          className="mt-1 w-px flex-1 bg-rule-strong"
                        />
                      )}
                    </div>

                    {/* Phase content */}
                    <div className="min-w-0 flex-1 pt-1">
                      <div className="mb-2.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                        <h3 className="font-serif text-[16px] font-medium leading-snug tracking-[-0.01em] text-ink">
                          {phase.title}
                        </h3>
                        <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-3">
                          {PHASE_LABEL[phase.status]}
                        </span>
                        {phase.skills.length > 0 && (
                          <span className="text-[12px] text-ink-3">
                            {phase.acquiredCount}/{phase.skills.length} acquired
                          </span>
                        )}
                      </div>
                      {phase.skills.length > 0 ? (
                        <div className="flex flex-wrap gap-2">
                          {phase.skills.map((s) => (
                            <SkillChip key={s.name} label={s.name} status={s.status} />
                          ))}
                        </div>
                      ) : (
                        <p className="text-[13px] text-ink-3">
                          No new target skills in this phase.
                        </p>
                      )}
                    </div>
                  </li>
                );
              })}
            </ol>
          </section>
        </>
      )}
    </div>
  );
}
