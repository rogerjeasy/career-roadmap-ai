"use client";

import { useState, type FormEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  scheduleApi,
  type BlockCategory,
  type Budget,
  type BudgetTargetsInput,
} from "@/lib/api/schedule";
import { QUERY_KEYS } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { WeeklyBudgetBar } from "@/components/schedule/weekly-budget-bar";

const CATEGORIES: { id: BlockCategory; label: string }[] = [
  { id: "build", label: "Build" },
  { id: "read", label: "Read" },
  { id: "network", label: "Network" },
  { id: "review", label: "Review" },
];

const FIELD_CLASS =
  "rounded-[8px] border border-rule bg-bg px-3 py-2 text-[13px] text-ink focus:border-green focus:bg-paper focus:outline-none";

function emptyTargets(budget: Budget | undefined): BudgetTargetsInput {
  const by = (id: BlockCategory) =>
    budget?.categories.find((c) => c.id === id)?.hoursTarget ?? 0;
  return { build: by("build"), read: by("read"), network: by("network"), review: by("review") };
}

export interface WeeklyBudgetPanelProps {
  className?: string;
}

export function WeeklyBudgetPanel({ className }: WeeklyBudgetPanelProps) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [targets, setTargets] = useState<BudgetTargetsInput | null>(null);
  const [logCategory, setLogCategory] = useState<BlockCategory>("build");
  const [logHours, setLogHours] = useState("");

  const { data: budget, isLoading } = useQuery({
    queryKey: QUERY_KEYS.scheduleBudget,
    queryFn: scheduleApi.getBudget,
    staleTime: 30 * 1000,
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: QUERY_KEYS.scheduleBudget });
    queryClient.invalidateQueries({ queryKey: QUERY_KEYS.scheduleTimeLogs });
  };

  const targetsMutation = useMutation({
    mutationFn: scheduleApi.setBudgetTargets,
    onSuccess: () => {
      refresh();
      toast.success("Weekly targets saved");
      setEditing(false);
    },
    onError: () => toast.error("Couldn't save targets. Please try again."),
  });

  const logMutation = useMutation({
    mutationFn: scheduleApi.logTime,
    onSuccess: () => {
      refresh();
      toast.success("Time logged");
      setLogHours("");
    },
    onError: () => toast.error("Couldn't log time. Please try again."),
  });

  const startEditing = () => {
    setTargets(emptyTargets(budget));
    setEditing(true);
  };

  const onSaveTargets = (e: FormEvent) => {
    e.preventDefault();
    if (targets) targetsMutation.mutate(targets);
  };

  const onLog = (e: FormEvent) => {
    e.preventDefault();
    const hours = Number(logHours);
    if (!Number.isFinite(hours) || hours <= 0) return;
    logMutation.mutate({ category: logCategory, hours });
  };

  if (isLoading || !budget) {
    return (
      <div className={cn("rounded-[12px] border border-rule bg-paper p-6", className)}>
        <p className="text-[13px] text-ink-3">Loading your weekly budget…</p>
      </div>
    );
  }

  const hasTargets = budget.categories.some((c) => c.hoursTarget > 0);

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      {hasTargets ? (
        <WeeklyBudgetBar categories={budget.categories} />
      ) : (
        <div className="rounded-[12px] border border-dashed border-rule-strong bg-paper p-6 text-center">
          <p className="mb-1 text-[13px] font-medium text-ink-2">No weekly targets set</p>
          <p className="mx-auto max-w-[280px] text-[12px] text-ink-3">
            Set target hours per category to track how your week measures up against your plan.
          </p>
        </div>
      )}

      {/* Log time */}
      <form
        onSubmit={onLog}
        className="flex flex-col gap-2 rounded-[12px] border border-rule bg-paper p-4 sm:flex-row sm:items-center"
      >
        <select
          value={logCategory}
          onChange={(e) => setLogCategory(e.target.value as BlockCategory)}
          className={cn(FIELD_CLASS, "sm:w-36")}
          aria-label="Category"
        >
          {CATEGORIES.map((c) => (
            <option key={c.id} value={c.id}>
              {c.label}
            </option>
          ))}
        </select>
        <input
          type="number"
          inputMode="decimal"
          min="0.25"
          max="24"
          step="0.25"
          value={logHours}
          onChange={(e) => setLogHours(e.target.value)}
          placeholder="Hours"
          className={cn(FIELD_CLASS, "min-w-0 flex-1")}
          aria-label="Hours"
        />
        <button
          type="submit"
          disabled={!logHours || logMutation.isPending}
          className="shrink-0 rounded-[8px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-50"
        >
          Log time
        </button>
      </form>

      {/* Targets editor */}
      {editing ? (
        <form onSubmit={onSaveTargets} className="rounded-[12px] border border-rule bg-paper p-4">
          <p className="mb-3 text-[12.5px] font-medium text-ink-2">Weekly target hours</p>
          <div className="grid grid-cols-2 gap-2.5">
            {CATEGORIES.map((c) => (
              <label key={c.id} className="flex flex-col gap-1 text-[12px] text-ink-3">
                {c.label}
                <input
                  type="number"
                  min="0"
                  max="168"
                  step="0.5"
                  value={targets ? targets[c.id] : 0}
                  onChange={(e) =>
                    setTargets((prev) =>
                      prev ? { ...prev, [c.id]: Number(e.target.value) } : prev,
                    )
                  }
                  className={FIELD_CLASS}
                />
              </label>
            ))}
          </div>
          <div className="mt-3 flex gap-2">
            <button
              type="submit"
              disabled={targetsMutation.isPending}
              className="rounded-[8px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-50"
            >
              Save targets
            </button>
            <button
              type="button"
              onClick={() => setEditing(false)}
              className="rounded-[8px] border border-rule-strong bg-paper px-4 py-2 text-[13px] font-medium text-ink-2 transition-colors duration-150 hover:bg-bg-2"
            >
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <button
          type="button"
          onClick={startEditing}
          className="self-start text-[12.5px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
        >
          {hasTargets ? "Edit weekly targets" : "Set weekly targets"}
        </button>
      )}
    </div>
  );
}
