"use client";

import { useState, type FormEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  feedbackApi,
  type Feedback,
  type FeedbackCategory,
} from "@/lib/api/feedback";
import { QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { formatRelative } from "@/lib/date";

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

const CATEGORY_OPTIONS: { value: FeedbackCategory; label: string }[] = [
  { value: "idea", label: "Idea / feature request" },
  { value: "bug", label: "Bug report" },
  { value: "question", label: "Question" },
  { value: "praise", label: "Praise" },
  { value: "other", label: "Other" },
];

const CATEGORY_LABEL: Record<FeedbackCategory, string> = {
  idea: "Idea",
  bug: "Bug",
  question: "Question",
  praise: "Praise",
  other: "Other",
};

const CATEGORY_CHIP: Record<FeedbackCategory, string> = {
  idea: "bg-green-soft text-green-2",
  bug: "bg-terra-soft text-terra-2",
  question: "bg-bg-3 text-ink-2",
  praise: "bg-green-soft text-green-2",
  other: "bg-bg-3 text-ink-2",
};

export default function HelpPage() {
  const queryClient = useQueryClient();
  const [category, setCategory] = useState<FeedbackCategory>("idea");
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");

  const { data: history, isLoading } = useQuery({
    queryKey: QUERY_KEYS.feedback,
    queryFn: feedbackApi.list,
    staleTime: 60 * 1000,
  });

  const createMutation = useMutation({
    mutationFn: feedbackApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.feedback });
      toast.success("Thanks — your feedback was sent");
      setSubject("");
      setMessage("");
      setCategory("idea");
    },
    onError: () => toast.error("Couldn't send that. Please try again."),
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!subject.trim() || !message.trim()) return;
    createMutation.mutate({
      category,
      subject: subject.trim(),
      message: message.trim(),
    });
  };

  const canSubmit =
    subject.trim().length > 0 && message.trim().length > 0 && !createMutation.isPending;

  return (
    <div className="mx-auto max-w-[900px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Account"
        title="Help & feedback"
        description="Found a bug, have an idea, or need a hand? Send it our way — we read every message, and you can track what you've sent below."
      />

      <form
        onSubmit={onSubmit}
        className="mb-8 space-y-3 rounded-[12px] border border-rule bg-paper p-5"
      >
        <div className="grid gap-3 sm:grid-cols-[200px_1fr]">
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value as FeedbackCategory)}
            className={FIELD_CLASS}
          >
            {CATEGORY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <input
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="Subject"
            maxLength={200}
            className={FIELD_CLASS}
          />
        </div>
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Tell us what's on your mind…"
          rows={5}
          maxLength={4000}
          className={`${FIELD_CLASS} resize-y`}
        />
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={!canSubmit}
            className="rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-50"
          >
            {createMutation.isPending ? "Sending…" : "Send feedback"}
          </button>
        </div>
      </form>

      <h2 className="mb-3 text-[12px] font-semibold uppercase tracking-[0.14em] text-ink-3">
        Your submissions
      </h2>

      {isLoading ? (
        <LoadingSpinner label="Loading your submissions…" />
      ) : !history || history.length === 0 ? (
        <EmptyState
          title="Nothing sent yet"
          description="Your feedback history will appear here once you send your first message."
        />
      ) : (
        <ul className="space-y-3" role="list">
          {history.map((item: Feedback) => (
            <li
              key={item.id}
              className="flex flex-col gap-2 rounded-[12px] border border-rule bg-paper p-5"
            >
              <div className="flex items-center justify-between gap-3">
                <span
                  className={`rounded-[5px] px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.04em] ${CATEGORY_CHIP[item.category]}`}
                >
                  {CATEGORY_LABEL[item.category]}
                </span>
                <span className="text-[12px] text-ink-3">
                  {formatRelative(item.createdAt)}
                </span>
              </div>
              <h3 className="font-serif text-[15px] font-medium leading-snug tracking-[-0.01em] text-ink">
                {item.subject}
              </h3>
              <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-ink-2">
                {item.message}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
