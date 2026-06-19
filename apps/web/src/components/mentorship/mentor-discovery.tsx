"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { mentorshipApi, type MentorProfile } from "@/lib/api/mentorship";
import { QUERY_KEYS } from "@/lib/constants";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

export interface MentorDiscoveryProps {
  className?: string;
}

export function MentorDiscovery(_props: MentorDiscoveryProps): React.ReactElement {
  const queryClient = useQueryClient();
  const [activeMentor, setActiveMentor] = useState<MentorProfile | null>(null);
  const [topic, setTopic] = useState("");
  const [message, setMessage] = useState("");

  const { data: mentors, isLoading } = useQuery({
    queryKey: QUERY_KEYS.mentors,
    queryFn: mentorshipApi.discoverMentors,
    staleTime: 30 * 1000,
  });

  const requestMutation = useMutation({
    mutationFn: mentorshipApi.requestSession,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.mentorSessions });
      toast.success("Request sent — the mentor will be asked to accept");
      setActiveMentor(null);
      setTopic("");
      setMessage("");
    },
    onError: () => toast.error("Couldn't send that request."),
  });

  if (isLoading) return <LoadingSpinner fullPage label="Finding mentors…" />;

  if (!mentors || mentors.length === 0) {
    return (
      <EmptyState
        title="No mentors available yet"
        description="Be the first to opt in from the “Become a mentor” tab — others matched to your expertise will find you here."
      />
    );
  }

  return (
    <div className="space-y-4">
      {mentors.map((m: MentorProfile) => (
        <article key={m.userId} className="rounded-[12px] border border-rule bg-paper p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="font-serif text-[16px] font-medium tracking-[-0.01em] text-ink">
                {m.name}
              </h3>
              <p className="mt-0.5 text-[13px] text-ink-2">{m.headline}</p>
            </div>
            {m.matchScore > 0 && (
              <span className="shrink-0 rounded-[6px] bg-green-soft px-2.5 py-1 text-[12px] font-semibold text-green-2">
                {m.matchScore}% match
              </span>
            )}
          </div>
          {m.bio && <p className="mt-3 text-[13px] leading-relaxed text-ink-2">{m.bio}</p>}
          {m.matchReason && (
            <p className="mt-2 text-[12.5px] italic text-ink-3">{m.matchReason}</p>
          )}
          {m.expertise.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {m.expertise.map((e) => (
                <span
                  key={e}
                  className="rounded-[5px] bg-bg-2 px-2 py-0.5 text-[11px] font-medium text-ink-2"
                >
                  {e}
                </span>
              ))}
            </div>
          )}

          {activeMentor?.userId === m.userId ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (!topic.trim()) return;
                requestMutation.mutate({
                  mentorId: m.userId,
                  topic: topic.trim(),
                  message: message.trim(),
                });
              }}
              className="mt-4 space-y-3 border-t border-rule pt-4"
            >
              <input
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="What do you want to discuss?"
                className={FIELD_CLASS}
              />
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="A short note (optional)"
                rows={2}
                className={`${FIELD_CLASS} resize-y`}
              />
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setActiveMentor(null)}
                  className="rounded-[7px] border border-rule px-3.5 py-2 text-[13px] font-medium text-ink-2 transition-colors hover:border-rule-strong"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!topic.trim() || requestMutation.isPending}
                  className="rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors hover:bg-green-2 disabled:opacity-50"
                >
                  {requestMutation.isPending ? "Sending…" : "Send request"}
                </button>
              </div>
            </form>
          ) : (
            <div className="mt-4 flex justify-end">
              <button
                type="button"
                onClick={() => setActiveMentor(m)}
                className="rounded-[7px] bg-ink px-3.5 py-1.5 text-[12.5px] font-medium text-bg transition-colors hover:bg-green-2"
              >
                Request a session
              </button>
            </div>
          )}
        </article>
      ))}
    </div>
  );
}
