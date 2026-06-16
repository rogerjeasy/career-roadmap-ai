"use client";

import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { useRoadmapEdit } from "@/hooks/use-roadmap-edit";
import type { RoadmapPhaseDetail } from "@/types/roadmap.types";
import { cn } from "@/lib/utils";

export interface PhaseEditorProps {
  roadmapId: string;
  phase: RoadmapPhaseDetail;
  onClose: () => void;
}

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none disabled:opacity-60";

const ICON_BTN =
  "flex h-8 w-8 shrink-0 items-center justify-center rounded-[7px] border border-rule-strong bg-paper text-ink-2 transition-colors duration-150 hover:bg-bg-2 disabled:cursor-not-allowed disabled:opacity-40";

export function PhaseEditor({ roadmapId, phase, onClose }: PhaseEditorProps) {
  const { updatePhase } = useRoadmapEdit(roadmapId);
  const [title, setTitle] = useState(phase.title);
  const [description, setDescription] = useState(phase.description);
  const [durationWeeks, setDurationWeeks] = useState(String(phase.durationWeeks));
  const [milestones, setMilestones] = useState<string[]>(
    phase.milestones.length > 0 ? phase.milestones : [""],
  );

  const setMilestone = (i: number, value: string) =>
    setMilestones((prev) => prev.map((m, idx) => (idx === i ? value : m)));

  const addMilestone = () => setMilestones((prev) => [...prev, ""]);

  const removeMilestone = (i: number) =>
    setMilestones((prev) => (prev.length === 1 ? [""] : prev.filter((_, idx) => idx !== i)));

  const move = (i: number, dir: -1 | 1) =>
    setMilestones((prev) => {
      const j = i + dir;
      if (j < 0 || j >= prev.length) return prev;
      const next = [...prev];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });

  const onSave = (e: FormEvent) => {
    e.preventDefault();
    const cleaned = milestones.map((m) => m.trim()).filter(Boolean);
    updatePhase.mutate(
      {
        phaseId: phase.id,
        input: {
          title: title.trim() || phase.title,
          description: description.trim(),
          durationWeeks: Number(durationWeeks) || 0,
          milestones: cleaned,
        },
      },
      {
        onSuccess: () => {
          toast.success("Phase saved");
          onClose();
        },
      },
    );
  };

  return (
    <form
      onSubmit={onSave}
      className="space-y-5 rounded-[12px] border border-rule bg-paper p-6"
    >
      <div className="flex items-center justify-between">
        <h2 className="font-serif text-[17px] font-medium tracking-[-0.01em] text-ink">
          Edit phase
        </h2>
        <button
          type="button"
          onClick={onClose}
          className="text-[12.5px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
        >
          Cancel
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-[1fr_120px]">
        <label className="block">
          <span className="mb-1.5 block text-[12.5px] font-medium text-ink-2">Title</span>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={200}
            placeholder="Phase title"
            className={FIELD_CLASS}
          />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-[12.5px] font-medium text-ink-2">Weeks</span>
          <input
            type="number"
            min={0}
            max={520}
            inputMode="numeric"
            value={durationWeeks}
            onChange={(e) => setDurationWeeks(e.target.value)}
            className={FIELD_CLASS}
          />
        </label>
      </div>

      <label className="block">
        <span className="mb-1.5 block text-[12.5px] font-medium text-ink-2">Description</span>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
          maxLength={2000}
          placeholder="What this phase is about"
          className={cn(FIELD_CLASS, "resize-y")}
        />
      </label>

      <div>
        <span className="mb-2 block text-[12.5px] font-medium text-ink-2">Milestones</span>
        <ul className="space-y-2">
          {milestones.map((milestone, i) => (
            <li key={i} className="flex items-center gap-2">
              <input
                value={milestone}
                onChange={(e) => setMilestone(i, e.target.value)}
                placeholder={`Milestone ${i + 1}`}
                className={cn(FIELD_CLASS, "min-w-0 flex-1")}
                aria-label={`Milestone ${i + 1}`}
              />
              <button
                type="button"
                onClick={() => move(i, -1)}
                disabled={i === 0}
                className={ICON_BTN}
                aria-label={`Move milestone ${i + 1} up`}
              >
                ↑
              </button>
              <button
                type="button"
                onClick={() => move(i, 1)}
                disabled={i === milestones.length - 1}
                className={ICON_BTN}
                aria-label={`Move milestone ${i + 1} down`}
              >
                ↓
              </button>
              <button
                type="button"
                onClick={() => removeMilestone(i)}
                className={cn(ICON_BTN, "hover:border-terra hover:text-terra-2")}
                aria-label={`Delete milestone ${i + 1}`}
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
        <button
          type="button"
          onClick={addMilestone}
          className="mt-2.5 text-[12.5px] font-medium text-green-2 transition-colors duration-150 hover:text-green"
        >
          + Add milestone
        </button>
      </div>

      <div className="flex justify-end gap-2 border-t border-rule pt-4">
        <button
          type="button"
          onClick={onClose}
          className="rounded-[8px] border border-rule-strong bg-paper px-4 py-2 text-[13px] font-medium text-ink-2 transition-colors duration-150 hover:bg-bg-2"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={updatePhase.isPending}
          className="rounded-[8px] bg-ink px-5 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-50"
        >
          {updatePhase.isPending ? "Saving…" : "Save phase"}
        </button>
      </div>
    </form>
  );
}
