"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  cohortsApi,
  type Cohort,
  type CohortCadence,
} from "@/lib/api/cohorts";
import { ROUTES, QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { cn } from "@/lib/utils";

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

type Tab = "mine" | "discover";

export default function CohortsPage() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("mine");
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [focus, setFocus] = useState("");
  const [description, setDescription] = useState("");
  const [capacity, setCapacity] = useState("6");
  const [cadence, setCadence] = useState<CohortCadence>("weekly");

  const { data: mine, isLoading: mineLoading } = useQuery({
    queryKey: QUERY_KEYS.cohorts,
    queryFn: cohortsApi.listMine,
    staleTime: 30 * 1000,
  });

  const { data: discover, isLoading: discoverLoading } = useQuery({
    queryKey: QUERY_KEYS.cohortsDiscover,
    queryFn: cohortsApi.discover,
    staleTime: 30 * 1000,
    enabled: tab === "discover",
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: QUERY_KEYS.cohorts });
    queryClient.invalidateQueries({ queryKey: QUERY_KEYS.cohortsDiscover });
  };

  const createMutation = useMutation({
    mutationFn: cohortsApi.create,
    onSuccess: () => {
      invalidate();
      toast.success("Cohort created");
      setName("");
      setFocus("");
      setDescription("");
      setCapacity("6");
      setCadence("weekly");
      setShowForm(false);
      setTab("mine");
    },
    onError: () => toast.error("Couldn't create that cohort."),
  });

  const joinMutation = useMutation({
    mutationFn: (id: string) => cohortsApi.join(id),
    onSuccess: () => {
      invalidate();
      toast.success("Joined cohort");
    },
    onError: () => toast.error("Couldn't join — it may be full."),
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !focus.trim()) return;
    createMutation.mutate({
      name: name.trim(),
      focus: focus.trim(),
      description: description.trim(),
      capacity: Number(capacity) || 6,
      cadence,
    });
  };

  const loading = tab === "mine" ? mineLoading : discoverLoading;
  const list = tab === "mine" ? mine : discover;

  return (
    <div className="mx-auto max-w-[900px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Community"
        title="Accountability Cohorts"
        description="Small peer groups working toward similar goals. Join one matched to your focus, share weekly check-ins, and keep each other moving."
        actions={
          <button
            type="button"
            onClick={() => setShowForm((v) => !v)}
            className="inline-flex items-center rounded-[7px] bg-ink px-3.5 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2"
          >
            {showForm ? "Close" : "+ New cohort"}
          </button>
        }
      />

      {showForm && (
        <form
          onSubmit={onSubmit}
          className="mb-6 space-y-3 rounded-[12px] border border-rule bg-paper p-5"
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Cohort name"
              className={FIELD_CLASS}
            />
            <input
              value={focus}
              onChange={(e) => setFocus(e.target.value)}
              placeholder="Focus (e.g. Breaking into PM)"
              className={FIELD_CLASS}
            />
          </div>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What's this cohort about? (optional)"
            rows={2}
            className={`${FIELD_CLASS} resize-y`}
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <input
              value={capacity}
              onChange={(e) => setCapacity(e.target.value)}
              type="number"
              min="2"
              max="20"
              placeholder="Capacity"
              className={FIELD_CLASS}
            />
            <select
              value={cadence}
              onChange={(e) => setCadence(e.target.value as CohortCadence)}
              className={FIELD_CLASS}
            >
              <option value="weekly">Weekly check-ins</option>
              <option value="biweekly">Biweekly check-ins</option>
            </select>
          </div>
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={!name.trim() || !focus.trim() || createMutation.isPending}
              className="rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-50"
            >
              {createMutation.isPending ? "Creating…" : "Create cohort"}
            </button>
          </div>
        </form>
      )}

      <div className="mb-5 flex gap-1 rounded-[9px] border border-rule bg-bg-2 p-1">
        {(["mine", "discover"] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={cn(
              "flex-1 rounded-[7px] px-3 py-1.5 text-[13px] font-medium transition-colors duration-150",
              tab === t ? "bg-paper text-ink shadow-sm" : "text-ink-3 hover:text-ink",
            )}
          >
            {t === "mine" ? "My cohorts" : "Discover"}
          </button>
        ))}
      </div>

      {loading ? (
        <LoadingSpinner fullPage label="Loading cohorts…" />
      ) : !list || list.length === 0 ? (
        <EmptyState
          title={tab === "mine" ? "You're not in a cohort yet" : "No open cohorts right now"}
          description={
            tab === "mine"
              ? "Join one from Discover, or start your own and invite peers chasing the same goal."
              : "Be the first — create a cohort and others matched to your focus will find it here."
          }
        />
      ) : (
        <div className="space-y-4">
          {list.map((c: Cohort) => (
            <article
              key={c.id}
              className="flex flex-col gap-3 rounded-[12px] border border-rule bg-paper p-5"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="font-serif text-[17px] font-medium tracking-[-0.01em] text-ink">
                    {c.name}
                  </h3>
                  <p className="mt-0.5 text-[12.5px] text-ink-2">{c.focus}</p>
                </div>
                {tab === "discover" && c.matchScore > 0 && (
                  <span className="shrink-0 rounded-[6px] bg-green-soft px-2.5 py-1 text-[12px] font-semibold text-green-2">
                    {c.matchScore}% match
                  </span>
                )}
              </div>
              {c.description && (
                <p className="text-[13px] leading-relaxed text-ink-2">{c.description}</p>
              )}
              {tab === "discover" && c.matchReason && (
                <p className="text-[12.5px] italic leading-relaxed text-ink-3">
                  {c.matchReason}
                </p>
              )}
              <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
                <span className="text-[12px] text-ink-3">
                  {c.memberCount}/{c.capacity} members · {c.cadence}
                </span>
                {tab === "mine" ? (
                  <Link
                    href={ROUTES.cohort(c.id)}
                    className="rounded-[7px] bg-ink px-3.5 py-1.5 text-[12.5px] font-medium text-bg transition-colors hover:bg-green-2"
                  >
                    Open dashboard
                  </Link>
                ) : (
                  <button
                    type="button"
                    onClick={() => joinMutation.mutate(c.id)}
                    disabled={joinMutation.isPending}
                    className="rounded-[7px] border border-rule px-3.5 py-1.5 text-[12.5px] font-medium text-ink transition-colors hover:border-rule-strong disabled:opacity-50"
                  >
                    Join
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
