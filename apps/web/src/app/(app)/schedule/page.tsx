"use client";

import { useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { scheduleApi, type BlockCategory, type Habit } from "@/lib/api/schedule";
import { ROUTES, QUERY_KEYS } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/shared/page-header";
import { WeeklyGrid } from "@/components/schedule/weekly-grid";
import { WeeklyBudgetPanel } from "@/components/schedule/weekly-budget-panel";
import { HabitHeatmap } from "@/components/schedule/habit-heatmap";

const HEATMAP_WEEKS = 12;
const HEATMAP_DAYS = HEATMAP_WEEKS * 7;

const DAY_OPTIONS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const CATEGORY_OPTIONS: { id: BlockCategory; label: string }[] = [
  { id: "build", label: "Build" },
  { id: "read", label: "Read" },
  { id: "network", label: "Network" },
  { id: "review", label: "Review" },
];

const FIELD_CLASS =
  "rounded-[8px] border border-rule bg-bg px-3 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

/** Per-day completion intensity (0–4) over the last 12 weeks, oldest → newest. */
function buildHeatmap(habits: Habit[]): number[] {
  const counts = new Map<string, number>();
  for (const habit of habits) {
    for (const iso of habit.completedDates) {
      counts.set(iso, (counts.get(iso) ?? 0) + 1);
    }
  }
  const today = new Date();
  const values: number[] = [];
  for (let i = HEATMAP_DAYS - 1; i >= 0; i -= 1) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    const iso = d.toISOString().slice(0, 10);
    values.push(Math.min(4, counts.get(iso) ?? 0));
  }
  return values;
}

export default function SchedulePage() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [day, setDay] = useState(0);
  const [label, setLabel] = useState("");
  const [category, setCategory] = useState<BlockCategory>("build");

  const { data: blocks } = useQuery({
    queryKey: QUERY_KEYS.scheduleBlocks,
    queryFn: scheduleApi.listBlocks,
    staleTime: 30 * 1000,
  });

  const { data: habits } = useQuery({
    queryKey: QUERY_KEYS.habits,
    queryFn: scheduleApi.listHabits,
    staleTime: 60 * 1000,
  });

  const invalidateBlocks = () =>
    queryClient.invalidateQueries({ queryKey: QUERY_KEYS.scheduleBlocks });

  const createBlock = useMutation({
    mutationFn: scheduleApi.createBlock,
    onSuccess: () => {
      invalidateBlocks();
      toast.success("Block added");
      setLabel("");
      setShowForm(false);
    },
    onError: () => toast.error("Couldn't add the block. Please try again."),
  });

  const deleteBlock = useMutation({
    mutationFn: scheduleApi.deleteBlock,
    onSuccess: invalidateBlocks,
    onError: () => toast.error("Couldn't delete the block."),
  });

  const heatmap = useMemo(() => buildHeatmap(habits ?? []), [habits]);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!label.trim()) return;
    createBlock.mutate({ day, label: label.trim(), category });
  };

  return (
    <div className="mx-auto max-w-[1100px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Rhythm"
        title="Schedule"
        description="Your week mapped to your roadmap — time blocks, budget, and the habits that compound."
        actions={
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setShowForm((v) => !v)}
              className="inline-flex items-center rounded-[7px] border border-rule bg-paper px-3.5 py-2 text-[13px] font-medium text-ink-2 transition-colors duration-150 hover:bg-bg-2"
            >
              {showForm ? "Close" : "+ Add block"}
            </button>
            <Link
              href={ROUTES.schedule + "/habits"}
              className="inline-flex items-center rounded-[7px] bg-ink px-3.5 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2"
            >
              Manage habits
            </Link>
          </div>
        }
      />

      {showForm && (
        <form
          onSubmit={onSubmit}
          className="mb-5 flex flex-col gap-2.5 rounded-[12px] border border-rule bg-paper p-4 sm:flex-row sm:items-center"
        >
          <select
            value={day}
            onChange={(e) => setDay(Number(e.target.value))}
            className={cn(FIELD_CLASS, "sm:w-32")}
            aria-label="Day"
          >
            {DAY_OPTIONS.map((d, i) => (
              <option key={d} value={i}>
                {d}
              </option>
            ))}
          </select>
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="What's the focus? (e.g. RAG retriever)"
            className={cn(FIELD_CLASS, "min-w-0 flex-1")}
          />
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value as BlockCategory)}
            className={cn(FIELD_CLASS, "sm:w-36")}
            aria-label="Category"
          >
            {CATEGORY_OPTIONS.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
          <button
            type="submit"
            disabled={!label.trim() || createBlock.isPending}
            className="shrink-0 rounded-[8px] bg-ink px-4 py-2.5 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-50"
          >
            Add
          </button>
        </form>
      )}

      <div className="space-y-5">
        <WeeklyGrid blocks={blocks ?? []} onDelete={(id) => deleteBlock.mutate(id)} />
        <div className="grid gap-5 lg:grid-cols-2">
          <WeeklyBudgetPanel />
          <HabitHeatmap values={heatmap} weeks={HEATMAP_WEEKS} />
        </div>
      </div>
    </div>
  );
}
