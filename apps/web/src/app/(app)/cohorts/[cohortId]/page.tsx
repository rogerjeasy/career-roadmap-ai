"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { cohortsApi, type Checkin } from "@/lib/api/cohorts";
import { ROUTES, QUERY_KEYS } from "@/lib/constants";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { formatRelative } from "@/lib/date";

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

export default function CohortDashboardPage() {
  const params = useParams<{ cohortId: string }>();
  const cohortId = params.cohortId;
  const queryClient = useQueryClient();
  const router = useRouter();

  const [done, setDone] = useState("");
  const [next, setNext] = useState("");
  const [blockers, setBlockers] = useState("");
  const [confirmLeave, setConfirmLeave] = useState(false);

  const { data, isLoading, isError } = useQuery({
    queryKey: QUERY_KEYS.cohort(cohortId),
    queryFn: () => cohortsApi.dashboard(cohortId),
    enabled: Boolean(cohortId),
    retry: false,
  });

  const checkinMutation = useMutation({
    mutationFn: (input: { done: string; next: string; blockers: string }) =>
      cohortsApi.postCheckin(cohortId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.cohort(cohortId) });
      toast.success("Check-in posted");
      setDone("");
      setNext("");
      setBlockers("");
    },
    onError: () => toast.error("Couldn't post your check-in."),
  });

  const leaveMutation = useMutation({
    mutationFn: () => cohortsApi.leave(cohortId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.cohorts });
      toast.success("You left the cohort");
      router.push(ROUTES.cohorts);
    },
    onError: () => toast.error("Couldn't leave the cohort."),
  });

  const backLink = (
    <Link
      href={ROUTES.cohorts}
      className="mb-4 inline-flex items-center gap-1 text-[12.5px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
    >
      ← Cohorts
    </Link>
  );

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!done.trim()) return;
    checkinMutation.mutate({ done: done.trim(), next: next.trim(), blockers: blockers.trim() });
  };

  if (isLoading) {
    return (
      <div className="mx-auto max-w-[760px] px-7 pb-24 pt-7">
        {backLink}
        <LoadingSpinner fullPage label="Loading cohort…" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="mx-auto max-w-[760px] px-7 pb-24 pt-7">
        {backLink}
        <EmptyState
          title="Cohort unavailable"
          description="This cohort may no longer exist, or you're not a member."
        />
      </div>
    );
  }

  const { cohort, checkins } = data;

  return (
    <div className="mx-auto max-w-[760px] px-7 pb-24 pt-7">
      {backLink}

      <div className="mb-6 rounded-[12px] border border-rule bg-paper p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="font-serif text-[24px] font-medium leading-tight tracking-[-0.02em] text-ink">
              {cohort.name}
            </h1>
            <p className="mt-1 text-[13px] text-ink-2">{cohort.focus}</p>
          </div>
          <button
            type="button"
            onClick={() => setConfirmLeave(true)}
            className="shrink-0 text-[12.5px] font-medium text-ink-3 transition-colors hover:text-destructive"
          >
            Leave
          </button>
        </div>
        {cohort.description && (
          <p className="mt-3 text-[13px] leading-relaxed text-ink-2">{cohort.description}</p>
        )}
        <div className="mt-4 flex flex-wrap gap-1.5">
          {cohort.members.map((m) => (
            <span
              key={m.uid}
              className="rounded-[5px] bg-bg-2 px-2 py-0.5 text-[11.5px] font-medium text-ink-2"
            >
              {m.name}
              {m.uid === cohort.createdBy ? " · host" : ""}
            </span>
          ))}
        </div>
      </div>

      <form
        onSubmit={onSubmit}
        className="mb-6 space-y-3 rounded-[12px] border border-rule bg-paper p-5"
      >
        <p className="text-[12px] font-semibold uppercase tracking-[0.06em] text-ink-3">
          Post a check-in
        </p>
        <textarea
          value={done}
          onChange={(e) => setDone(e.target.value)}
          placeholder="What did you get done since last time?"
          rows={2}
          className={`${FIELD_CLASS} resize-y`}
        />
        <textarea
          value={next}
          onChange={(e) => setNext(e.target.value)}
          placeholder="What's next? (optional)"
          rows={2}
          className={`${FIELD_CLASS} resize-y`}
        />
        <textarea
          value={blockers}
          onChange={(e) => setBlockers(e.target.value)}
          placeholder="Any blockers the group can help with? (optional)"
          rows={2}
          className={`${FIELD_CLASS} resize-y`}
        />
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={!done.trim() || checkinMutation.isPending}
            className="rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-50"
          >
            {checkinMutation.isPending ? "Posting…" : "Post check-in"}
          </button>
        </div>
      </form>

      {checkins.length === 0 ? (
        <EmptyState
          title="No check-ins yet"
          description="Be the first to share progress — it sets the rhythm for the whole cohort."
        />
      ) : (
        <div className="space-y-4">
          {checkins.map((c: Checkin) => (
            <article
              key={c.id}
              className="rounded-[12px] border border-rule bg-paper p-5"
            >
              <div className="mb-2 flex items-center justify-between gap-3">
                <span className="text-[13px] font-medium text-ink">{c.userName}</span>
                {c.createdAt && (
                  <span className="text-[11.5px] text-ink-3">
                    {formatRelative(c.createdAt)}
                  </span>
                )}
              </div>
              <p className="text-[13px] leading-relaxed text-ink-2">{c.done}</p>
              {c.next && (
                <p className="mt-2 text-[12.5px] leading-relaxed text-ink-3">
                  <span className="font-medium text-ink-2">Next:</span> {c.next}
                </p>
              )}
              {c.blockers && (
                <p className="mt-2 rounded-[7px] bg-terra-soft px-3 py-2 text-[12.5px] leading-relaxed text-terra-2">
                  <span className="font-medium">Blocker:</span> {c.blockers}
                </p>
              )}
            </article>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={confirmLeave}
        onOpenChange={setConfirmLeave}
        title="Leave this cohort?"
        description="You'll stop seeing its check-ins. You can join again later if there's room."
        confirmLabel="Leave"
        destructive
        pending={leaveMutation.isPending}
        onConfirm={() => leaveMutation.mutate()}
      />
    </div>
  );
}
