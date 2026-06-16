"use client";

import { useState, type FormEvent } from "react";
import { useRoadmapEdit } from "@/hooks/use-roadmap-edit";
import { fixMojibake } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import type { RoadmapPhaseDetail } from "@/types/roadmap.types";

export interface PhaseManagerProps {
  roadmapId: string;
  /** Phases in their current display order. */
  phases: RoadmapPhaseDetail[];
}

const FIELD_CLASS =
  "rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

const ICON_BTN =
  "flex h-8 w-8 shrink-0 items-center justify-center rounded-[7px] border border-rule-strong bg-paper text-ink-2 transition-colors duration-150 hover:bg-bg-2 disabled:cursor-not-allowed disabled:opacity-40";

export function PhaseManager({ roadmapId, phases }: PhaseManagerProps) {
  const { addPhase, deletePhase, reorderPhases } = useRoadmapEdit(roadmapId);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [newWeeks, setNewWeeks] = useState("4");

  const ids = phases.map((p) => p.id);
  const busy = reorderPhases.isPending || deletePhase.isPending || addPhase.isPending;

  const move = (index: number, dir: -1 | 1) => {
    const target = index + dir;
    if (target < 0 || target >= ids.length) return;
    const next = [...ids];
    [next[index], next[target]] = [next[target], next[index]];
    reorderPhases.mutate(next);
  };

  const onAdd = (e: FormEvent) => {
    e.preventDefault();
    const title = newTitle.trim();
    if (!title) return;
    addPhase.mutate(
      { title, durationWeeks: Number(newWeeks) || 0 },
      {
        onSuccess: () => {
          setNewTitle("");
          setNewWeeks("4");
        },
      },
    );
  };

  const confirmPhase = phases.find((p) => p.id === confirmId) ?? null;

  return (
    <section className="rounded-[12px] border border-rule bg-paper p-6">
      <h2 className="mb-1 font-serif text-[17px] font-medium tracking-[-0.01em] text-ink">
        Edit your plan
      </h2>
      <p className="mb-4 text-[12.5px] text-ink-3">
        Reorder, rename, or remove phases. Open a phase to edit its milestones.
      </p>

      <ul className="space-y-2">
        {phases.map((phase, i) => (
          <li
            key={phase.id}
            className="flex items-center gap-2 rounded-[10px] border border-rule bg-bg px-3 py-2.5"
          >
            <span className="font-mono text-[11.5px] text-ink-3">
              {String(i + 1).padStart(2, "0")}
            </span>
            <span className="min-w-0 flex-1 truncate text-[13.5px] font-medium text-ink">
              {fixMojibake(phase.title)}
            </span>
            <span className="hidden shrink-0 text-[11.5px] text-ink-3 sm:inline">
              {phase.milestones.length} milestone{phase.milestones.length === 1 ? "" : "s"}
            </span>
            <button
              type="button"
              onClick={() => move(i, -1)}
              disabled={i === 0 || busy}
              className={ICON_BTN}
              aria-label={`Move ${phase.title} up`}
            >
              ↑
            </button>
            <button
              type="button"
              onClick={() => move(i, 1)}
              disabled={i === phases.length - 1 || busy}
              className={ICON_BTN}
              aria-label={`Move ${phase.title} down`}
            >
              ↓
            </button>
            <button
              type="button"
              onClick={() => setConfirmId(phase.id)}
              disabled={busy}
              className={cn(ICON_BTN, "hover:border-terra hover:text-terra-2")}
              aria-label={`Delete ${phase.title}`}
            >
              ✕
            </button>
          </li>
        ))}
      </ul>

      <form onSubmit={onAdd} className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center">
        <input
          value={newTitle}
          onChange={(e) => setNewTitle(e.target.value)}
          maxLength={200}
          placeholder="New phase title"
          className={cn(FIELD_CLASS, "min-w-0 flex-1")}
          aria-label="New phase title"
        />
        <input
          type="number"
          min={0}
          max={520}
          inputMode="numeric"
          value={newWeeks}
          onChange={(e) => setNewWeeks(e.target.value)}
          className={cn(FIELD_CLASS, "sm:w-24")}
          aria-label="Phase duration in weeks"
        />
        <button
          type="submit"
          disabled={!newTitle.trim() || addPhase.isPending}
          className="shrink-0 rounded-[8px] bg-ink px-4 py-2.5 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-50"
        >
          Add phase
        </button>
      </form>

      <ConfirmDialog
        open={confirmId !== null}
        onOpenChange={(open) => !open && setConfirmId(null)}
        title="Delete this phase?"
        description={
          confirmPhase
            ? `"${fixMojibake(confirmPhase.title)}" and its milestones will be removed from your roadmap. This can't be undone.`
            : undefined
        }
        confirmLabel="Delete phase"
        destructive
        pending={deletePhase.isPending}
        onConfirm={() => {
          if (confirmId) {
            deletePhase.mutate(confirmId, { onSuccess: () => setConfirmId(null) });
          }
        }}
      />
    </section>
  );
}
