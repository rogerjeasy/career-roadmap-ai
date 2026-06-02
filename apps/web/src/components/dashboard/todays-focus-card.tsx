"use client";

import { useState } from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import type { TodayTask, TaskCategory } from "@/types/dashboard.types";
import { ROUTES } from "@/lib/constants";

// ── Category styles ───────────────────────────────────────────────────────────

const CATEGORY_STYLES: Record<TaskCategory, string> = {
  build:   "bg-green-soft text-green-2",
  network: "bg-terra-soft text-terra-2",
  review:  "bg-gold-soft text-gold",
  read:    "bg-bg-3 text-ink-2",
};

const CATEGORY_LABELS: Record<TaskCategory, string> = {
  build:   "Build",
  network: "Network",
  review:  "Review",
  read:    "Read",
};

// ── Checkbox icon ─────────────────────────────────────────────────────────────

function CheckMark() {
  return (
    <svg viewBox="0 0 12 12" fill="none" className="h-[11px] w-[11px]" aria-hidden="true">
      <path d="M2 6.5l3 3 5-7" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

// ── Task item ─────────────────────────────────────────────────────────────────

interface TaskItemProps {
  task: TodayTask;
  onToggle: (id: string) => void;
}

function TaskItem({ task, onToggle }: TaskItemProps) {
  return (
    <li
      className={cn(
        "grid cursor-pointer grid-cols-[22px_1fr_auto] items-center gap-3.5 border-b border-rule px-1 py-3.5 transition-all duration-[120ms]",
        "last:border-b-0 last:pb-1",
        "hover:rounded-[6px] hover:bg-bg hover:px-2.5",
      )}
      onClick={() => onToggle(task.id)}
      role="checkbox"
      aria-checked={task.isDone}
      tabIndex={0}
      onKeyDown={(e) => e.key === " " && onToggle(task.id)}
    >
      {/* Checkbox */}
      <span
        className={cn(
          "flex h-[18px] w-[18px] items-center justify-center rounded-[5px] border-[1.5px] transition-all duration-150",
          task.isDone
            ? "border-green bg-green text-white"
            : "border-rule-strong bg-paper hover:border-green",
        )}
      >
        {task.isDone && <CheckMark />}
      </span>

      {/* Body */}
      <div className="flex min-w-0 flex-col gap-[3px]">
        <span
          className={cn(
            "text-[13.5px] font-medium leading-[1.35] text-ink",
            task.isDone && "text-ink-3 line-through decoration-rule-strong",
          )}
        >
          {task.title}
        </span>
        <div className="flex items-center gap-2 text-[11.5px] text-ink-3">
          <span
            className={cn(
              "inline-flex items-center rounded-[4px] px-[7px] py-px text-[10.5px] font-semibold uppercase tracking-[0.04em]",
              CATEGORY_STYLES[task.category],
            )}
          >
            {CATEGORY_LABELS[task.category]}
          </span>
          {task.meta && (
            <>
              <span className="text-rule-strong" aria-hidden="true">·</span>
              <span dangerouslySetInnerHTML={{ __html: task.meta }} />
            </>
          )}
        </div>
      </div>

      {/* Estimate */}
      {task.estimateMinutes > 0 && (
        <span className="shrink-0 rounded-[5px] bg-bg-2 px-2 py-1 font-mono text-[11px] text-ink-3">
          {task.estimateMinutes} min
        </span>
      )}
    </li>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyFocus() {
  return (
    <div className="flex flex-col items-center justify-center py-8 text-center">
      <p className="mb-1 text-[13px] font-medium text-ink-2">No tasks scheduled for today</p>
      <p className="max-w-[260px] text-[12px] text-ink-3">
        Generate your roadmap and the coach will fill your daily focus list automatically.
      </p>
    </div>
  );
}

// ── Today's Focus card ────────────────────────────────────────────────────────

export interface TodaysFocusCardProps {
  tasks: TodayTask[];
  isLoading: boolean;
}

export function TodaysFocusCard({ tasks, isLoading }: TodaysFocusCardProps) {
  const [items, setItems] = useState<TodayTask[]>(tasks);

  // Sync external prop changes
  if (tasks !== items && tasks.length !== items.length) {
    setItems(tasks);
  }

  const toggle = (id: string) => {
    setItems((prev) =>
      prev.map((t) => (t.id === id ? { ...t, isDone: !t.isDone } : t)),
    );
  };

  const doneCount = items.filter((t) => t.isDone).length;
  const totalMinutes = items.filter((t) => !t.isDone).reduce((s, t) => s + t.estimateMinutes, 0);
  const remainingHours = (totalMinutes / 60).toFixed(1).replace(/\.0$/, "");

  return (
    <div className="rounded-[12px] border border-rule bg-paper p-6">
      {/* Card header */}
      <div className="mb-[18px] flex items-start justify-between border-b border-rule pb-3.5">
        <div>
          <h2 className="font-serif text-[17px] font-medium tracking-[-0.01em] text-ink">
            Today&apos;s focus
          </h2>
          {!isLoading && (
            <p className="mt-[3px] text-[11.5px] text-ink-3">
              {items.length} thing{items.length !== 1 ? "s" : ""} planned
              {items.reduce((s, t) => s + t.estimateMinutes, 0) > 0 && (
                <>
                  {" · "}
                  <em className="font-serif italic text-terra">
                    {(items.reduce((s, t) => s + t.estimateMinutes, 0) / 60).toFixed(1).replace(/\.0$/, "")} h estimated
                  </em>
                </>
              )}
            </p>
          )}
        </div>
        <Link
          href={ROUTES.schedule}
          className="inline-flex items-center gap-1 text-[12px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
        >
          View week →
        </Link>
      </div>

      {/* Task list */}
      {isLoading ? (
        <div className="animate-pulse space-y-4 py-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="flex items-center gap-3.5">
              <div className="h-[18px] w-[18px] rounded-[5px] bg-bg-3" />
              <div className="flex-1 space-y-1.5">
                <div className="h-3.5 w-3/4 rounded bg-bg-3" />
                <div className="h-3 w-1/2 rounded bg-bg-2" />
              </div>
              <div className="h-6 w-14 rounded bg-bg-2" />
            </div>
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyFocus />
      ) : (
        <ul role="list" className="flex flex-col">
          {items.map((task) => (
            <TaskItem key={task.id} task={task} onToggle={toggle} />
          ))}
        </ul>
      )}

      {/* Footer */}
      {!isLoading && items.length > 0 && (
        <div className="mt-3.5 flex items-center justify-between border-t border-rule pt-3.5 text-[12px]">
          <p className="text-ink-2">
            <strong className="font-semibold text-ink">{doneCount} of {items.length}</strong> done
            {totalMinutes > 0 && (
              <>
                {" · "}
                <strong className="font-semibold text-ink">{remainingHours} h</strong> remaining today
              </>
            )}
          </p>
          <button
            type="button"
            className="font-semibold text-terra transition-colors duration-150 hover:text-terra-2"
          >
            + Add task
          </button>
        </div>
      )}
    </div>
  );
}
