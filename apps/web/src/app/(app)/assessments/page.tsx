"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { assessmentsApi, type AssessmentSummary } from "@/lib/api/assessments";
import { LEVEL_LABEL, LEVEL_TONE, scoreTone } from "@/lib/assessments-meta";
import { ROUTES, QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { formatRelative } from "@/lib/date";
import { cn } from "@/lib/utils";

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

export default function AssessmentsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [skill, setSkill] = useState("");
  const [numQuestions, setNumQuestions] = useState(6);

  const { data: items, isLoading } = useQuery({
    queryKey: QUERY_KEYS.assessments,
    queryFn: assessmentsApi.list,
    staleTime: 30 * 1000,
  });

  const startMutation = useMutation({
    mutationFn: assessmentsApi.start,
    onSuccess: (assessment) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.assessments });
      router.push(ROUTES.assessment(assessment.id));
    },
    onError: () => toast.error("Couldn't start that assessment. Try a different skill."),
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!skill.trim()) return;
    startMutation.mutate({ skill: skill.trim(), numQuestions });
  };

  return (
    <div className="mx-auto max-w-[820px] px-4 pb-24 pt-7 sm:px-7">
      <PageHeader
        eyebrow="Prove it"
        title="Skill assessments"
        description="Turn a self-reported skill into a measured one. Take a short quiz; pass it and earn a verifiable, shareable credential. Your measured gaps feed straight into your roadmap."
      />

      <form
        onSubmit={onSubmit}
        className="mb-8 space-y-3 rounded-[12px] border border-rule bg-paper p-5"
      >
        <p className="text-[12px] font-semibold uppercase tracking-[0.06em] text-ink-3">
          Assess a skill
        </p>
        <div className="flex flex-col gap-3 sm:flex-row">
          <input
            value={skill}
            onChange={(e) => setSkill(e.target.value)}
            placeholder="e.g. React, SQL, Product strategy…"
            className={cn(FIELD_CLASS, "sm:flex-1")}
          />
          <select
            value={numQuestions}
            onChange={(e) => setNumQuestions(Number(e.target.value))}
            className="rounded-[8px] border border-rule bg-bg px-3 py-2.5 text-[13.5px] text-ink focus:border-green focus:outline-none sm:w-[150px]"
          >
            {[4, 6, 8, 10].map((n) => (
              <option key={n} value={n}>
                {n} questions
              </option>
            ))}
          </select>
          <button
            type="submit"
            disabled={!skill.trim() || startMutation.isPending}
            className="rounded-[8px] bg-ink px-4 py-2.5 text-[13px] font-medium text-bg transition-colors hover:bg-green-2 disabled:opacity-50"
          >
            {startMutation.isPending ? "Building…" : "Start"}
          </button>
        </div>
      </form>

      {isLoading ? (
        <LoadingSpinner fullPage label="Loading your assessments…" />
      ) : !items || items.length === 0 ? (
        <EmptyState
          title="No assessments yet"
          description="Assess your first skill above to get a measured proficiency level and, on a pass, a verifiable badge."
        />
      ) : (
        <div className="space-y-2.5">
          {items.map((a: AssessmentSummary) => (
            <button
              key={a.id}
              type="button"
              onClick={() => router.push(ROUTES.assessment(a.id))}
              className="flex w-full items-center justify-between gap-3 rounded-[12px] border border-rule bg-paper p-4 text-left transition-colors hover:border-rule-strong"
            >
              <div className="min-w-0">
                <h3 className="truncate font-serif text-[15px] font-medium tracking-[-0.01em] text-ink">
                  {a.skill}
                </h3>
                <p className="text-[12px] text-ink-3">
                  {a.status === "graded"
                    ? a.createdAt
                      ? `Taken ${formatRelative(a.createdAt)}`
                      : "Graded"
                    : "In progress — finish the quiz"}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {a.status === "graded" && a.score !== null && (
                  <span className={cn("rounded-[6px] px-2.5 py-1 text-[12px] font-semibold", scoreTone(a.score))}>
                    {a.score}%
                  </span>
                )}
                {a.level && (
                  <span className={cn("rounded-[6px] px-2.5 py-1 text-[11.5px] font-semibold", LEVEL_TONE[a.level])}>
                    {LEVEL_LABEL[a.level]}
                  </span>
                )}
                {a.status === "in_progress" && (
                  <span className="rounded-[6px] bg-bg-2 px-2.5 py-1 text-[11.5px] font-medium text-ink-3">
                    Resume
                  </span>
                )}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
