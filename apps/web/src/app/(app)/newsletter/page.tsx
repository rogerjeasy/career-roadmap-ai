"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  newsletterApi,
  type NewsletterFrequency,
  type NewsletterPrefs,
} from "@/lib/api/newsletter";
import { QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { cn } from "@/lib/utils";

const FREQUENCIES: { value: NewsletterFrequency; label: string }[] = [
  { value: "weekly", label: "Weekly" },
  { value: "biweekly", label: "Every 2 weeks" },
  { value: "monthly", label: "Monthly" },
];

const TOPICS: { id: string; label: string; description: string }[] = [
  {
    id: "market_trends",
    label: "Market trends",
    description: "Demand shifts and salary movement for your target role.",
  },
  {
    id: "new_opportunities",
    label: "New opportunities",
    description: "Fresh roles matched to your roadmap and skills.",
  },
  {
    id: "skill_spotlights",
    label: "Skill spotlights",
    description: "Fast-rising skills worth adding to your plan.",
  },
  {
    id: "roadmap_nudges",
    label: "Roadmap nudges",
    description: "Gentle reminders to keep your milestones on track.",
  },
  {
    id: "recommended_reading",
    label: "Recommended reading",
    description: "Books and articles mapped to your current phase.",
  },
];

export default function NewsletterPage() {
  const { data: prefs, isLoading } = useQuery({
    queryKey: QUERY_KEYS.newsletter,
    queryFn: newsletterApi.get,
    staleTime: 60 * 1000,
  });

  return (
    <div className="mx-auto max-w-[760px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Intelligence"
        title="Newsletter"
        description="A digest tailored to your career goal — market moves, matched opportunities and reading, delivered on your schedule. You're in control of every part of it."
      />

      {isLoading || !prefs ? (
        <LoadingSpinner fullPage label="Loading your preferences…" />
      ) : (
        // Mount the form only once preferences have loaded, so its local state
        // can be seeded directly from props (no state-syncing effect needed).
        <NewsletterForm prefs={prefs} />
      )}
    </div>
  );
}

interface NewsletterFormProps {
  prefs: NewsletterPrefs;
}

function NewsletterForm({ prefs }: NewsletterFormProps) {
  const queryClient = useQueryClient();
  const [subscribed, setSubscribed] = useState(prefs.subscribed);
  const [frequency, setFrequency] = useState<NewsletterFrequency>(prefs.frequency);
  const [topics, setTopics] = useState<string[]>(prefs.topics);

  const saveMutation = useMutation({
    mutationFn: newsletterApi.update,
    onSuccess: (data: NewsletterPrefs) => {
      queryClient.setQueryData(QUERY_KEYS.newsletter, data);
      toast.success(
        data.subscribed ? "Newsletter preferences saved" : "You've unsubscribed",
      );
    },
    onError: () => toast.error("Couldn't save your preferences. Please try again."),
  });

  const toggleTopic = (id: string) => {
    setTopics((prev) =>
      prev.includes(id) ? prev.filter((t) => t !== id) : [...prev, id],
    );
  };

  const onSave = () => {
    saveMutation.mutate({ subscribed, frequency, topics });
  };

  return (
        <div className="space-y-6">
          {/* Subscription toggle */}
          <div className="flex items-center justify-between gap-4 rounded-[12px] border border-rule bg-paper p-5">
            <div className="min-w-0">
              <h2 className="font-serif text-[16px] font-medium tracking-[-0.01em] text-ink">
                Career digest
              </h2>
              <p className="mt-1 text-[13px] leading-relaxed text-ink-2">
                {subscribed
                  ? "You're subscribed. Choose how often and what's included below."
                  : "Subscribe to start receiving your personalised digest."}
              </p>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={subscribed}
              aria-label="Toggle newsletter subscription"
              onClick={() => setSubscribed((v) => !v)}
              className={cn(
                "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors duration-200",
                subscribed ? "bg-green" : "bg-bg-3",
              )}
            >
              <span
                className={cn(
                  "inline-block h-5 w-5 transform rounded-full bg-paper shadow transition-transform duration-200",
                  subscribed ? "translate-x-[22px]" : "translate-x-0.5",
                )}
              />
            </button>
          </div>

          {/* Frequency + topics (only relevant when subscribed) */}
          <fieldset
            disabled={!subscribed}
            className={cn(
              "space-y-6 transition-opacity duration-200",
              !subscribed && "pointer-events-none opacity-50",
            )}
          >
            <div className="rounded-[12px] border border-rule bg-paper p-5">
              <h3 className="mb-3 text-[12px] font-semibold uppercase tracking-[0.14em] text-ink-3">
                Frequency
              </h3>
              <div className="flex flex-wrap gap-2">
                {FREQUENCIES.map((f) => (
                  <button
                    key={f.value}
                    type="button"
                    onClick={() => setFrequency(f.value)}
                    className={cn(
                      "rounded-[7px] border px-3.5 py-2 text-[13px] font-medium transition-colors duration-150",
                      frequency === f.value
                        ? "border-green bg-green-soft text-green-2"
                        : "border-rule bg-bg text-ink-2 hover:border-rule-strong",
                    )}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="rounded-[12px] border border-rule bg-paper p-5">
              <h3 className="mb-3 text-[12px] font-semibold uppercase tracking-[0.14em] text-ink-3">
                What to include
              </h3>
              <ul className="space-y-2" role="list">
                {TOPICS.map((t) => {
                  const checked = topics.includes(t.id);
                  return (
                    <li key={t.id}>
                      <label className="flex cursor-pointer items-start gap-3 rounded-[8px] border border-rule p-3 transition-colors duration-150 hover:border-rule-strong">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleTopic(t.id)}
                          className="mt-0.5 h-4 w-4 shrink-0 accent-green"
                        />
                        <span className="min-w-0">
                          <span className="block text-[13.5px] font-medium text-ink">
                            {t.label}
                          </span>
                          <span className="block text-[12.5px] leading-relaxed text-ink-3">
                            {t.description}
                          </span>
                        </span>
                      </label>
                    </li>
                  );
                })}
              </ul>
            </div>
          </fieldset>

          <div className="flex justify-end">
            <button
              type="button"
              onClick={onSave}
              disabled={saveMutation.isPending}
              className="rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-50"
            >
              {saveMutation.isPending ? "Saving…" : "Save preferences"}
            </button>
          </div>
        </div>
  );
}
