"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useRoadmap } from "@/hooks/use-roadmap";
import { useRoadmapProgress } from "@/hooks/use-roadmap-progress";
import { ROUTES } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { RoadmapProgressBar } from "@/components/roadmap/roadmap-progress-bar";
import { PhaseNav } from "@/components/roadmap/phase-nav";
import { MilestoneToggle } from "@/components/roadmap/milestone-toggle";

export default function PhaseDetailPage() {
  const params = useParams<{ phaseId: string }>();
  const phaseId = params.phaseId;
  const { roadmap, isLoading } = useRoadmap();
  const { isDone, toggle, doneInPhase } = useRoadmapProgress(roadmap?.id ?? null);

  if (isLoading) {
    return (
      <div className="mx-auto max-w-[1100px] px-7 py-7">
        <LoadingSpinner fullPage label="Loading phase…" />
      </div>
    );
  }

  const phase = roadmap?.phases.find((p) => p.id === phaseId);

  if (!phase || !roadmap) {
    return (
      <div className="mx-auto max-w-[1100px] px-7 py-7">
        <EmptyState
          title="Phase not found"
          description="This phase doesn't exist or belongs to a different roadmap."
          action={
            <Link
              href={ROUTES.roadmap}
              className="inline-flex items-center rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2"
            >
              Back to roadmap
            </Link>
          }
        />
      </div>
    );
  }

  const phases = [...roadmap.phases].sort((a, b) => a.order - b.order);
  const total = phase.milestones.length;
  const done = doneInPhase(phase.id, total);
  const pct = total > 0 ? (done / total) * 100 : 0;

  return (
    <div className="mx-auto max-w-[1100px] px-7 pb-24 pt-7">
      <Link
        href={ROUTES.roadmap}
        className="mb-4 inline-flex items-center gap-1 text-[12.5px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
      >
        ← All phases
      </Link>

      <PageHeader
        eyebrow={`Phase ${String(phase.order).padStart(2, "0")} · ${phase.durationWeeks} weeks`}
        title={phase.title}
        description={phase.description || undefined}
      />

      <div className="grid gap-7 lg:grid-cols-[220px_1fr]">
        {/* Phase nav (desktop) */}
        <aside className="hidden lg:block">
          <div className="sticky top-[80px]">
            <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-3">
              Phases
            </p>
            <PhaseNav phases={phases} activeId={phase.id} />
          </div>
        </aside>

        <div className="min-w-0 space-y-7">
          {/* Progress */}
          {total > 0 && (
            <section className="rounded-[12px] border border-rule bg-paper p-6">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="font-serif text-[17px] font-medium tracking-[-0.01em] text-ink">
                  Milestones
                </h2>
                <span className="font-mono text-[12px] text-ink-3">
                  {done}/{total} done
                </span>
              </div>
              <RoadmapProgressBar value={pct} showValue={false} className="mb-4" />
              <ul role="list" className="-mx-2">
                {phase.milestones.map((milestone, i) => {
                  const key = `${phase.id}:${i}`;
                  return (
                    <li key={key}>
                      <MilestoneToggle
                        label={milestone}
                        done={isDone(key)}
                        onToggle={() => toggle(key)}
                      />
                    </li>
                  );
                })}
              </ul>
            </section>
          )}

          {/* Weekly tasks */}
          {phase.weeklyTasks.length > 0 && (
            <section>
              <h2 className="mb-3.5 font-serif text-[17px] font-medium tracking-[-0.01em] text-ink">
                Week-by-week
              </h2>
              <ol className="space-y-3">
                {phase.weeklyTasks.map((wt) => (
                  <li
                    key={wt.weekNumber}
                    className="rounded-[10px] border border-rule bg-paper p-4"
                  >
                    <div className="mb-2 flex items-center justify-between">
                      <p className="text-[13px] font-semibold text-ink">
                        Week {wt.weekNumber}
                        {wt.focusArea && <span className="text-ink-3"> · {wt.focusArea}</span>}
                      </p>
                      {wt.estimatedHours > 0 && (
                        <span className="shrink-0 rounded-[5px] bg-bg-2 px-2 py-0.5 font-mono text-[11px] text-ink-3">
                          {wt.estimatedHours}h
                        </span>
                      )}
                    </div>
                    <ul className="space-y-1.5">
                      {wt.tasks.map((task, i) => (
                        <li key={i} className="flex gap-2 text-[13px] leading-snug text-ink-2">
                          <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-terra" aria-hidden="true" />
                          <span className="min-w-0">{task}</span>
                        </li>
                      ))}
                    </ul>
                    {wt.deliverable && (
                      <p className="mt-2.5 rounded-[6px] bg-green-faint px-3 py-1.5 text-[12px] text-green-2">
                        <strong className="font-semibold">Deliverable:</strong> {wt.deliverable}
                      </p>
                    )}
                  </li>
                ))}
              </ol>
            </section>
          )}

          {/* Skills + deliverables */}
          <div className="grid gap-7 sm:grid-cols-2">
            {phase.skillsToGain.length > 0 && (
              <section>
                <h2 className="mb-3 font-serif text-[16px] font-medium tracking-[-0.01em] text-ink">
                  Skills you&apos;ll gain
                </h2>
                <div className="flex flex-wrap gap-2">
                  {phase.skillsToGain.map((skill) => (
                    <span
                      key={skill}
                      className="rounded-[6px] bg-bg-2 px-2.5 py-1 text-[12.5px] font-medium text-ink-2"
                    >
                      {skill}
                    </span>
                  ))}
                </div>
              </section>
            )}

            {phase.deliverables.length > 0 && (
              <section>
                <h2 className="mb-3 font-serif text-[16px] font-medium tracking-[-0.01em] text-ink">
                  Deliverables
                </h2>
                <ul className="space-y-2">
                  {phase.deliverables.map((d, i) => (
                    <li key={i} className="flex gap-2 text-[13px] leading-snug text-ink-2">
                      <span className="mt-[6px] h-1.5 w-1.5 shrink-0 rounded-full bg-green" aria-hidden="true" />
                      <span className="min-w-0">{d}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>

          {/* Learning resources */}
          {phase.curatedResources.concat(phase.resources).length > 0 && (
            <section>
              <h2 className="mb-3.5 font-serif text-[17px] font-medium tracking-[-0.01em] text-ink">
                Learning resources
              </h2>
              <div className="grid gap-3 sm:grid-cols-2">
                {phase.curatedResources.concat(phase.resources).map((r, i) => {
                  const body = (
                    <>
                      <div className="mb-1.5 flex items-center gap-2">
                        <span className="rounded-[4px] bg-bg-2 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.04em] text-ink-3">
                          {r.resourceType}
                        </span>
                        {r.isFree && (
                          <span className="rounded-[4px] bg-green-faint px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.04em] text-green-2">
                            Free
                          </span>
                        )}
                      </div>
                      <p className="text-[13.5px] font-medium leading-snug text-ink">{r.title}</p>
                      {r.provider && <p className="mt-0.5 text-[12px] text-ink-3">{r.provider}</p>}
                    </>
                  );
                  return r.url ? (
                    <a
                      key={i}
                      href={r.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block rounded-[10px] border border-rule bg-paper p-4 transition-colors duration-150 hover:border-rule-strong"
                    >
                      {body}
                    </a>
                  ) : (
                    <div key={i} className="rounded-[10px] border border-rule bg-paper p-4">
                      {body}
                    </div>
                  );
                })}
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
