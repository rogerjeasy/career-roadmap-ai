"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { scheduleApi } from "@/lib/api/schedule";
import { ROUTES, QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { HabitRow } from "@/components/schedule/habit-row";

export default function HabitsPage() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [label, setLabel] = useState("");
  const [cadence, setCadence] = useState("Daily");

  const { data: habits, isLoading } = useQuery({
    queryKey: QUERY_KEYS.habits,
    queryFn: scheduleApi.listHabits,
    staleTime: 30 * 1000,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: QUERY_KEYS.habits });

  const toggleMutation = useMutation({
    mutationFn: scheduleApi.toggleHabit,
    onSuccess: invalidate,
    onError: () => toast.error("Couldn't update the habit."),
  });

  const createMutation = useMutation({
    mutationFn: scheduleApi.createHabit,
    onSuccess: () => {
      invalidate();
      toast.success("Habit added");
      setLabel("");
      setCadence("Daily");
      setShowForm(false);
    },
    onError: () => toast.error("Couldn't add the habit."),
  });

  const deleteMutation = useMutation({
    mutationFn: scheduleApi.deleteHabit,
    onSuccess: invalidate,
    onError: () => toast.error("Couldn't delete the habit."),
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!label.trim()) return;
    createMutation.mutate({ label: label.trim(), cadence: cadence.trim() || "Daily" });
  };

  const doneCount = habits?.filter((h) => h.doneToday).length ?? 0;

  return (
    <div className="mx-auto max-w-[720px] px-7 pb-24 pt-7">
      <Link
        href={ROUTES.schedule}
        className="mb-4 inline-flex items-center gap-1 text-[12.5px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
      >
        ← Schedule
      </Link>
      <PageHeader
        eyebrow="Rhythm"
        title="Habits"
        description="Small, repeatable actions are what actually move your roadmap. Check them off as you go."
        actions={
          <div className="flex items-center gap-2">
            {habits && habits.length > 0 && (
              <span className="rounded-[7px] border border-rule bg-paper px-3 py-1.5 text-[12.5px] text-ink-2">
                {doneCount}/{habits.length} done today
              </span>
            )}
            <button
              type="button"
              onClick={() => setShowForm((v) => !v)}
              className="inline-flex items-center rounded-[7px] bg-ink px-3.5 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2"
            >
              {showForm ? "Close" : "+ Add"}
            </button>
          </div>
        }
      />

      {showForm && (
        <form onSubmit={onSubmit} className="mb-6 flex flex-col gap-2.5 rounded-[12px] border border-rule bg-paper p-4 sm:flex-row">
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Habit (e.g. Morning study block)"
            className="min-w-0 flex-1 rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none"
          />
          <input
            value={cadence}
            onChange={(e) => setCadence(e.target.value)}
            placeholder="Cadence"
            className="w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none sm:w-40"
          />
          <button
            type="submit"
            disabled={!label.trim() || createMutation.isPending}
            className="shrink-0 rounded-[8px] bg-ink px-4 py-2.5 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-50"
          >
            Add
          </button>
        </form>
      )}

      {isLoading ? (
        <LoadingSpinner fullPage label="Loading habits…" />
      ) : !habits || habits.length === 0 ? (
        <EmptyState
          title="No habits yet"
          description="Add the small daily actions that compound toward your goal."
        />
      ) : (
        <div className="space-y-2.5">
          {habits.map((h) => (
            <div key={h.id} className="group flex items-center gap-2">
              <div className="min-w-0 flex-1">
                <HabitRow
                  label={h.label}
                  cadence={h.cadence}
                  streak={h.streak}
                  doneToday={h.doneToday}
                  onToggle={() => toggleMutation.mutate(h.id)}
                />
              </div>
              <button
                type="button"
                onClick={() => deleteMutation.mutate(h.id)}
                aria-label={`Delete ${h.label}`}
                className="shrink-0 rounded-[7px] px-2 py-2 text-ink-3 opacity-0 transition-all duration-150 hover:bg-bg-2 hover:text-terra-2 focus:opacity-100 group-hover:opacity-100"
              >
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" className="h-4 w-4" aria-hidden="true">
                  <path d="M3 4h10M6 4V2.5h4V4M5 4l.5 9h5L11 4" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
