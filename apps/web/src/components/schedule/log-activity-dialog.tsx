"use client";

import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { scheduleApi, type BlockCategory } from "@/lib/api/schedule";
import { QUERY_KEYS } from "@/lib/constants";
import { cn } from "@/lib/utils";

const CATEGORIES: { id: BlockCategory; label: string }[] = [
  { id: "build", label: "Build" },
  { id: "read", label: "Read" },
  { id: "network", label: "Network" },
  { id: "review", label: "Review" },
];

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

/** Local YYYY-MM-DD for today (not UTC, so "today" matches the user's calendar). */
function todayLocalIso(): string {
  const d = new Date();
  const offset = d.getTimezoneOffset() * 60_000;
  return new Date(d.getTime() - offset).toISOString().slice(0, 10);
}

export interface LogActivityDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function LogActivityDialog({ open, onOpenChange }: LogActivityDialogProps) {
  const queryClient = useQueryClient();
  const [category, setCategory] = useState<BlockCategory>("build");
  const [hours, setHours] = useState("");
  const [loggedOn, setLoggedOn] = useState(todayLocalIso);

  const reset = () => {
    setCategory("build");
    setHours("");
    setLoggedOn(todayLocalIso());
  };

  const logMutation = useMutation({
    mutationFn: scheduleApi.logTime,
    onSuccess: () => {
      // Budget + time-log queries also feed the dashboard, so the KPIs and
      // heatmap pick this up immediately.
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.scheduleBudget });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.scheduleTimeLogs });
      toast.success("Activity logged");
      reset();
      onOpenChange(false);
    },
    onError: () => toast.error("Couldn't log your activity. Please try again."),
  });

  const numericHours = Number(hours);
  const canSubmit =
    Number.isFinite(numericHours) && numericHours > 0 && !logMutation.isPending;

  const handleOpenChange = (next: boolean) => {
    if (!next) reset();
    onOpenChange(next);
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    logMutation.mutate({ category, hours: numericHours, loggedOn });
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="font-serif text-[18px] tracking-[-0.01em] text-ink">
            Log activity
          </DialogTitle>
          <DialogDescription className="text-[13.5px] leading-relaxed text-ink-2">
            Record deep-work hours toward your weekly plan. They roll up into your budget and dashboard.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={onSubmit} className="mt-1 space-y-4">
          {/* Category */}
          <div>
            <span className="mb-1.5 block text-[12.5px] font-medium text-ink-2">
              Category
            </span>
            <div className="flex flex-wrap gap-2">
              {CATEGORIES.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => setCategory(c.id)}
                  aria-pressed={category === c.id}
                  className={cn(
                    "rounded-[7px] border px-3.5 py-2 text-[13px] font-medium transition-colors duration-150",
                    category === c.id
                      ? "border-green bg-green-soft text-green-2"
                      : "border-rule bg-bg text-ink-2 hover:border-rule-strong",
                  )}
                >
                  {c.label}
                </button>
              ))}
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1.5 block text-[12.5px] font-medium text-ink-2">
                Hours
              </span>
              <input
                type="number"
                inputMode="decimal"
                min="0.25"
                max="24"
                step="0.25"
                value={hours}
                onChange={(e) => setHours(e.target.value)}
                placeholder="e.g. 1.5"
                autoFocus
                className={FIELD_CLASS}
              />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-[12.5px] font-medium text-ink-2">
                Date
              </span>
              <input
                type="date"
                value={loggedOn}
                max={todayLocalIso()}
                onChange={(e) => setLoggedOn(e.target.value)}
                className={FIELD_CLASS}
              />
            </label>
          </div>

          <div className="flex flex-col-reverse gap-2 pt-1 sm:flex-row sm:justify-end">
            <button
              type="button"
              onClick={() => handleOpenChange(false)}
              disabled={logMutation.isPending}
              className="inline-flex items-center justify-center rounded-[7px] border border-rule-strong bg-paper px-4 py-2 text-[13px] font-medium text-ink-2 transition-colors duration-150 hover:bg-bg-2 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!canSubmit}
              className="inline-flex items-center justify-center rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-50"
            >
              {logMutation.isPending ? "Logging…" : "Log activity"}
            </button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
