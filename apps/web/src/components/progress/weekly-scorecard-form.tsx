"use client";

import { useState, type FormEvent } from "react";
import { cn } from "@/lib/utils";

export interface WeeklyScorecardValues {
  energy: number;
  focus: number;
  wins: string;
  blockers: string;
  hoursInvested: number;
  milestonesClosed: number;
}

export interface WeeklyScorecardFormProps {
  onSubmit: (values: WeeklyScorecardValues) => void;
  className?: string;
}

function Rating({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div>
      <span className="mb-1.5 block text-[12.5px] font-medium text-ink-2">{label}</span>
      <div className="flex gap-1.5">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            onClick={() => onChange(n)}
            aria-label={`${label}: ${n}`}
            aria-pressed={value === n}
            className={cn(
              "h-9 flex-1 rounded-[7px] text-[13px] font-semibold transition-colors duration-150",
              value >= n ? "bg-green text-white" : "bg-bg-2 text-ink-3 hover:bg-bg-3",
            )}
          >
            {n}
          </button>
        ))}
      </div>
    </div>
  );
}

const TEXTAREA_CLASS =
  "w-full resize-y rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] leading-relaxed text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

const NUMBER_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

export function WeeklyScorecardForm({ onSubmit, className }: WeeklyScorecardFormProps) {
  const [energy, setEnergy] = useState(3);
  const [focus, setFocus] = useState(3);
  const [wins, setWins] = useState("");
  const [blockers, setBlockers] = useState("");
  const [hours, setHours] = useState("");
  const [milestones, setMilestones] = useState("");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit({
      energy,
      focus,
      wins: wins.trim(),
      blockers: blockers.trim(),
      hoursInvested: Math.max(0, Number(hours) || 0),
      milestonesClosed: Math.max(0, Math.round(Number(milestones) || 0)),
    });
  };

  return (
    <form onSubmit={submit} className={cn("space-y-5 rounded-[12px] border border-rule bg-paper p-6", className)}>
      <div className="grid gap-5 sm:grid-cols-2">
        <Rating label="Energy this week" value={energy} onChange={setEnergy} />
        <Rating label="Focus this week" value={focus} onChange={setFocus} />
      </div>
      <div className="grid gap-5 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1.5 block text-[12.5px] font-medium text-ink-2">Hours invested</span>
          <input
            type="number"
            min={0}
            max={168}
            step="0.5"
            inputMode="decimal"
            value={hours}
            onChange={(e) => setHours(e.target.value)}
            placeholder="e.g. 10"
            className={NUMBER_CLASS}
          />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-[12.5px] font-medium text-ink-2">Milestones closed</span>
          <input
            type="number"
            min={0}
            max={100}
            step="1"
            inputMode="numeric"
            value={milestones}
            onChange={(e) => setMilestones(e.target.value)}
            placeholder="e.g. 2"
            className={NUMBER_CLASS}
          />
        </label>
      </div>
      <label className="block">
        <span className="mb-1.5 block text-[12.5px] font-medium text-ink-2">Wins</span>
        <textarea value={wins} onChange={(e) => setWins(e.target.value)} rows={3} placeholder="What went well? What did you ship?" className={TEXTAREA_CLASS} />
      </label>
      <label className="block">
        <span className="mb-1.5 block text-[12.5px] font-medium text-ink-2">Blockers</span>
        <textarea value={blockers} onChange={(e) => setBlockers(e.target.value)} rows={3} placeholder="What got in the way? What will you change?" className={TEXTAREA_CLASS} />
      </label>
      <div className="flex justify-end">
        <button
          type="submit"
          className="rounded-[7px] bg-ink px-5 py-2.5 text-[13.5px] font-medium text-bg transition-colors duration-150 hover:bg-green-2"
        >
          Save review
        </button>
      </div>
    </form>
  );
}
