"use client";

import { useState, type ReactElement } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  assessmentsApi,
  type Assessment,
  type AssessmentAnswerInput,
} from "@/lib/api/assessments";
import { LEVEL_LABEL, LEVEL_TONE, scoreTone } from "@/lib/assessments-meta";
import { ROUTES, QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { cn } from "@/lib/utils";

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

export default function AssessmentDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const queryClient = useQueryClient();
  const [answers, setAnswers] = useState<Record<string, string>>({});

  const { data: assessment, isLoading, isError } = useQuery({
    queryKey: QUERY_KEYS.assessment(id),
    queryFn: () => assessmentsApi.get(id),
    enabled: Boolean(id),
    retry: false,
  });

  const submitMutation = useMutation({
    mutationFn: (payload: AssessmentAnswerInput[]) => assessmentsApi.submit(id, payload),
    onSuccess: (data) => {
      queryClient.setQueryData(QUERY_KEYS.assessment(id), data);
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.assessments });
      toast.success(data.passed ? "Passed — badge issued!" : "Graded");
    },
    onError: () => toast.error("Couldn't grade your answers. Try again."),
  });

  const backLink = (
    <Link
      href={ROUTES.assessments}
      className="mb-4 inline-flex items-center gap-1 text-[12.5px] font-medium text-ink-3 transition-colors hover:text-ink"
    >
      ← Assessments
    </Link>
  );

  if (isLoading) {
    return (
      <div className="mx-auto max-w-[760px] px-4 pb-24 pt-7 sm:px-7">
        {backLink}
        <LoadingSpinner fullPage label="Loading…" />
      </div>
    );
  }

  if (isError || !assessment) {
    return (
      <div className="mx-auto max-w-[760px] px-4 pb-24 pt-7 sm:px-7">
        {backLink}
        <EmptyState title="Assessment not found" description="It may have been removed." />
      </div>
    );
  }

  const graded = assessment.status === "graded";
  const answeredCount = assessment.questions.filter((q) => (answers[q.id] ?? "").trim()).length;
  const allAnswered = answeredCount === assessment.questions.length;

  return (
    <div className="mx-auto max-w-[760px] px-4 pb-24 pt-7 sm:px-7">
      {backLink}
      <PageHeader
        eyebrow="Assessment"
        title={assessment.skill}
        description={
          graded
            ? "Your measured result is below."
            : `${assessment.questions.length} questions · answer all, then submit for grading.`
        }
      />

      {graded ? (
        <Result assessment={assessment} />
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const payload = assessment.questions.map((q) => ({
              questionId: q.id,
              answer: answers[q.id] ?? "",
            }));
            submitMutation.mutate(payload);
          }}
          className="space-y-5"
        >
          {assessment.questions.map((q, idx) => (
            <fieldset key={q.id} className="rounded-[12px] border border-rule bg-paper p-5">
              <legend className="px-1 text-[12px] font-semibold text-ink-3">
                Question {idx + 1}
              </legend>
              <p className="mb-3 text-[14px] leading-relaxed text-ink">{q.prompt}</p>
              {q.kind === "mcq" ? (
                <div className="space-y-2">
                  {q.options.map((opt) => (
                    <label
                      key={opt}
                      className={cn(
                        "flex cursor-pointer items-start gap-2.5 rounded-[8px] border px-3.5 py-2.5 text-[13.5px] transition-colors",
                        answers[q.id] === opt
                          ? "border-green bg-green-faint text-ink"
                          : "border-rule bg-bg text-ink-2 hover:border-rule-strong",
                      )}
                    >
                      <input
                        type="radio"
                        name={q.id}
                        value={opt}
                        checked={answers[q.id] === opt}
                        onChange={() => setAnswers((a) => ({ ...a, [q.id]: opt }))}
                        className="mt-0.5 size-4 shrink-0 accent-[var(--color-green)]"
                      />
                      <span className="min-w-0">{opt}</span>
                    </label>
                  ))}
                </div>
              ) : (
                <textarea
                  value={answers[q.id] ?? ""}
                  onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: e.target.value }))}
                  placeholder="Your answer…"
                  rows={4}
                  className={`${FIELD_CLASS} resize-y`}
                />
              )}
            </fieldset>
          ))}

          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-[12.5px] text-ink-3">
              {answeredCount} / {assessment.questions.length} answered
            </p>
            <button
              type="submit"
              disabled={!allAnswered || submitMutation.isPending}
              className="rounded-[8px] bg-ink px-5 py-2.5 text-[13px] font-medium text-bg transition-colors hover:bg-green-2 disabled:opacity-50"
            >
              {submitMutation.isPending ? "Grading…" : "Submit for grading"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

function Result({ assessment }: { assessment: Assessment }): ReactElement {
  const score = assessment.score ?? 0;
  return (
    <div className="space-y-5">
      <section
        className={cn(
          "rounded-[12px] border bg-paper p-5",
          assessment.passed ? "border-green" : "border-rule",
        )}
      >
        <div className="flex flex-wrap items-center gap-3">
          <span className={cn("rounded-[8px] px-3 py-1.5 text-[18px] font-semibold", scoreTone(score))}>
            {score}%
          </span>
          {assessment.level && (
            <span className={cn("rounded-[7px] px-3 py-1.5 text-[12.5px] font-semibold", LEVEL_TONE[assessment.level])}>
              {LEVEL_LABEL[assessment.level]}
            </span>
          )}
          <span
            className={cn(
              "rounded-[7px] px-3 py-1.5 text-[12.5px] font-semibold",
              assessment.passed ? "bg-green-soft text-green-2" : "bg-bg-2 text-ink-3",
            )}
          >
            {assessment.passed ? "Passed" : "Not yet passed"}
          </span>
        </div>
        {assessment.summary && (
          <p className="mt-3 text-[13.5px] leading-relaxed text-ink-2">{assessment.summary}</p>
        )}
        {assessment.passed && assessment.credentialId && (
          <Link
            href={ROUTES.credentials}
            className="mt-3 inline-block text-[12.5px] font-medium text-terra transition-colors hover:text-terra-2"
          >
            View your verifiable credential →
          </Link>
        )}
      </section>

      {assessment.strengths.length > 0 && (
        <section className="rounded-[12px] border border-rule bg-paper p-5">
          <p className="mb-2 text-[12px] font-semibold uppercase tracking-[0.06em] text-green-2">
            Measured strengths
          </p>
          <ul className="list-disc space-y-1 pl-5 text-[13px] text-ink-2">
            {assessment.strengths.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </section>
      )}

      {assessment.gaps.length > 0 && (
        <section className="rounded-[12px] border border-rule bg-paper p-5">
          <p className="mb-2 text-[12px] font-semibold uppercase tracking-[0.06em] text-terra-2">
            Measured gaps — now feeding your roadmap
          </p>
          <ul className="space-y-2.5">
            {assessment.gaps.map((g, i) => (
              <li key={i}>
                <p className="text-[13px] font-medium text-ink">{g.topic}</p>
                {g.note && <p className="text-[12.5px] text-ink-2">{g.note}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
