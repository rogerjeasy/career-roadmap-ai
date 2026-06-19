"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { mentorshipApi, type MentorSession, type SessionStatus } from "@/lib/api/mentorship";
import { QUERY_KEYS } from "@/lib/constants";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { cn } from "@/lib/utils";

const STATUS_TONE: Record<SessionStatus, string> = {
  requested: "bg-bg-2 text-ink-2",
  accepted: "bg-green-soft text-green-2",
  declined: "bg-terra-soft text-terra-2",
  completed: "bg-bg-2 text-ink-3",
};

const STATUS_LABEL: Record<SessionStatus, string> = {
  requested: "Requested",
  accepted: "Accepted",
  declined: "Declined",
  completed: "Completed",
};

export interface MySessionsProps {
  className?: string;
}

export function MySessions(_props: MySessionsProps): React.ReactElement {
  const queryClient = useQueryClient();

  const { data: sessions, isLoading } = useQuery({
    queryKey: QUERY_KEYS.mentorSessions,
    queryFn: mentorshipApi.listSessions,
    staleTime: 20 * 1000,
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: QUERY_KEYS.mentorSessions });

  const respondMutation = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: "accepted" | "declined" }) =>
      mentorshipApi.respondSession(id, { decision }),
    onSuccess: () => {
      invalidate();
      toast.success("Response sent");
    },
    onError: () => toast.error("Couldn't respond."),
  });

  const completeMutation = useMutation({
    mutationFn: (id: string) => mentorshipApi.completeSession(id),
    onSuccess: () => {
      invalidate();
      toast.success("Marked completed");
    },
    onError: () => toast.error("Couldn't update that session."),
  });

  if (isLoading) return <LoadingSpinner fullPage label="Loading sessions…" />;

  if (!sessions || sessions.length === 0) {
    return (
      <EmptyState
        title="No sessions yet"
        description="Request a session from “Find a mentor”, or opt in as a mentor to receive requests."
      />
    );
  }

  return (
    <div className="space-y-4">
      {sessions.map((s: MentorSession) => {
        const counterpart = s.role === "mentor" ? s.menteeName : s.mentorName;
        return (
          <article key={s.id} className="rounded-[12px] border border-rule bg-paper p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-[5px] bg-bg-2 px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.04em] text-ink-2">
                    {s.role === "mentor" ? "You're mentoring" : "Your mentor"}
                  </span>
                  <h3 className="font-serif text-[15.5px] font-medium tracking-[-0.01em] text-ink">
                    {s.topic}
                  </h3>
                </div>
                <p className="mt-1 text-[12.5px] text-ink-3">with {counterpart}</p>
              </div>
              <span
                className={cn(
                  "shrink-0 rounded-[6px] px-2.5 py-1 text-[11.5px] font-semibold",
                  STATUS_TONE[s.status],
                )}
              >
                {STATUS_LABEL[s.status]}
              </span>
            </div>
            {s.message && (
              <p className="mt-3 text-[13px] leading-relaxed text-ink-2">{s.message}</p>
            )}
            {s.reply && (
              <p className="mt-2 rounded-[7px] bg-bg-2 px-3 py-2 text-[12.5px] leading-relaxed text-ink-2">
                <span className="font-medium">Reply:</span> {s.reply}
              </p>
            )}

            {s.role === "mentor" && s.status === "requested" && (
              <div className="mt-4 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => respondMutation.mutate({ id: s.id, decision: "declined" })}
                  disabled={respondMutation.isPending}
                  className="rounded-[7px] border border-rule px-3.5 py-1.5 text-[12.5px] font-medium text-ink-2 transition-colors hover:border-rule-strong disabled:opacity-50"
                >
                  Decline
                </button>
                <button
                  type="button"
                  onClick={() => respondMutation.mutate({ id: s.id, decision: "accepted" })}
                  disabled={respondMutation.isPending}
                  className="rounded-[7px] bg-ink px-3.5 py-1.5 text-[12.5px] font-medium text-bg transition-colors hover:bg-green-2 disabled:opacity-50"
                >
                  Accept
                </button>
              </div>
            )}

            {s.status === "accepted" && (
              <div className="mt-4 flex justify-end">
                <button
                  type="button"
                  onClick={() => completeMutation.mutate(s.id)}
                  disabled={completeMutation.isPending}
                  className="rounded-[7px] border border-rule px-3.5 py-1.5 text-[12.5px] font-medium text-ink transition-colors hover:border-rule-strong disabled:opacity-50"
                >
                  Mark completed
                </button>
              </div>
            )}
          </article>
        );
      })}
    </div>
  );
}
