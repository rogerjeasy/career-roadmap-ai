"use client";

import { useState, type FormEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { mentorshipApi, type CaseStudy } from "@/lib/api/mentorship";
import { QUERY_KEYS } from "@/lib/constants";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

export interface InsiderStoriesProps {
  className?: string;
}

export function InsiderStories(_props: InsiderStoriesProps): React.ReactElement {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [fromRole, setFromRole] = useState("");
  const [toRole, setToRole] = useState("");
  const [timeframe, setTimeframe] = useState("");
  const [summary, setSummary] = useState("");
  const [steps, setSteps] = useState("");
  const [lessons, setLessons] = useState("");
  const [anonymous, setAnonymous] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<CaseStudy | null>(null);

  const { data: stories, isLoading } = useQuery({
    queryKey: QUERY_KEYS.caseStudies,
    queryFn: mentorshipApi.listCaseStudies,
    staleTime: 30 * 1000,
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: QUERY_KEYS.caseStudies });

  const createMutation = useMutation({
    mutationFn: mentorshipApi.createCaseStudy,
    onSuccess: () => {
      invalidate();
      toast.success("Story published");
      setFromRole("");
      setToRole("");
      setTimeframe("");
      setSummary("");
      setSteps("");
      setLessons("");
      setAnonymous(false);
      setShowForm(false);
    },
    onError: () => toast.error("Couldn't publish that story."),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => mentorshipApi.deleteCaseStudy(id),
    onSuccess: () => {
      invalidate();
      toast.success("Story removed");
      setPendingDelete(null);
    },
    onError: () => toast.error("Couldn't remove that story."),
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!fromRole.trim() || !toRole.trim() || !summary.trim()) return;
    createMutation.mutate({
      fromRole: fromRole.trim(),
      toRole: toRole.trim(),
      timeframeMonths: timeframe ? Number(timeframe) : 0,
      summary: summary.trim(),
      isAnonymous: anonymous,
      steps: steps.split("\n").map((s) => s.trim()).filter(Boolean),
      lessons: lessons.split("\n").map((s) => s.trim()).filter(Boolean),
    });
  };

  return (
    <div>
      <div className="mb-5 flex justify-end">
        <button
          type="button"
          onClick={() => setShowForm((v) => !v)}
          className="inline-flex items-center rounded-[7px] bg-ink px-3.5 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2"
        >
          {showForm ? "Close" : "+ Share your story"}
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={onSubmit}
          className="mb-6 space-y-3 rounded-[12px] border border-rule bg-paper p-5"
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <input
              value={fromRole}
              onChange={(e) => setFromRole(e.target.value)}
              placeholder="From role"
              className={FIELD_CLASS}
            />
            <input
              value={toRole}
              onChange={(e) => setToRole(e.target.value)}
              placeholder="To role"
              className={FIELD_CLASS}
            />
          </div>
          <input
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            type="number"
            min="0"
            placeholder="Months it took (optional)"
            className={FIELD_CLASS}
          />
          <textarea
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            placeholder="The story in a few sentences"
            rows={3}
            className={`${FIELD_CLASS} resize-y`}
          />
          <textarea
            value={steps}
            onChange={(e) => setSteps(e.target.value)}
            placeholder="Key steps — one per line (optional)"
            rows={3}
            className={`${FIELD_CLASS} resize-y`}
          />
          <textarea
            value={lessons}
            onChange={(e) => setLessons(e.target.value)}
            placeholder="Lessons learned — one per line (optional)"
            rows={3}
            className={`${FIELD_CLASS} resize-y`}
          />
          <label className="flex items-center gap-2 text-[13px] text-ink-2">
            <input
              type="checkbox"
              checked={anonymous}
              onChange={(e) => setAnonymous(e.target.checked)}
              className="h-4 w-4 accent-green"
            />
            Publish anonymously
          </label>
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={
                !fromRole.trim() || !toRole.trim() || !summary.trim() || createMutation.isPending
              }
              className="rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors hover:bg-green-2 disabled:opacity-50"
            >
              {createMutation.isPending ? "Publishing…" : "Publish story"}
            </button>
          </div>
        </form>
      )}

      {isLoading ? (
        <LoadingSpinner fullPage label="Loading stories…" />
      ) : !stories || stories.length === 0 ? (
        <EmptyState
          title="No stories yet"
          description="Made a transition you're proud of? Share how you did it — your path could be someone else's map."
        />
      ) : (
        <div className="space-y-4">
          {stories.map((s: CaseStudy) => (
            <article key={s.id} className="rounded-[12px] border border-rule bg-paper p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2 text-[15px]">
                    <span className="font-serif font-medium text-ink-2">{s.fromRole}</span>
                    <span className="text-ink-3">→</span>
                    <span className="font-serif font-medium text-ink">{s.toRole}</span>
                  </div>
                  <p className="mt-1 text-[12px] text-ink-3">
                    {s.authorName}
                    {s.timeframeMonths > 0 && ` · ${s.timeframeMonths} months`}
                  </p>
                </div>
                {s.isMine && (
                  <button
                    type="button"
                    onClick={() => setPendingDelete(s)}
                    className="shrink-0 text-[12px] font-medium text-ink-3 transition-colors hover:text-destructive"
                  >
                    Remove
                  </button>
                )}
              </div>
              <p className="mt-3 text-[13px] leading-relaxed text-ink-2">{s.summary}</p>
              {s.steps.length > 0 && (
                <div className="mt-3">
                  <p className="text-[11.5px] font-semibold uppercase tracking-[0.06em] text-ink-3">
                    Steps
                  </p>
                  <ol className="mt-1.5 list-decimal space-y-1 pl-5 text-[13px] text-ink-2">
                    {s.steps.map((step, i) => (
                      <li key={i}>{step}</li>
                    ))}
                  </ol>
                </div>
              )}
              {s.lessons.length > 0 && (
                <div className="mt-3">
                  <p className="text-[11.5px] font-semibold uppercase tracking-[0.06em] text-ink-3">
                    Lessons
                  </p>
                  <ul className="mt-1.5 list-disc space-y-1 pl-5 text-[13px] text-ink-2">
                    {s.lessons.map((lesson, i) => (
                      <li key={i}>{lesson}</li>
                    ))}
                  </ul>
                </div>
              )}
            </article>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title="Remove this story?"
        description="It will no longer appear in the insider library."
        confirmLabel="Remove"
        destructive
        pending={deleteMutation.isPending}
        onConfirm={() => pendingDelete && deleteMutation.mutate(pendingDelete.id)}
      />
    </div>
  );
}
