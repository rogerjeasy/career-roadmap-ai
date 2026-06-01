"use client";

import { useState } from "react";
import Link from "next/link";
import { ROUTES } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { HabitRow } from "@/components/schedule/habit-row";

interface HabitItem {
  id: string;
  label: string;
  cadence: string;
  streak: number;
  doneToday: boolean;
}

const INITIAL: HabitItem[] = [
  { id: "h1", label: "Morning study block", cadence: "Daily · 45 min", streak: 23, doneToday: true },
  { id: "h2", label: "Ship something small", cadence: "Daily · 25 min", streak: 11, doneToday: false },
  { id: "h3", label: "One outreach message", cadence: "Weekdays · 10 min", streak: 4, doneToday: false },
  { id: "h4", label: "Read one ML paper", cadence: "3× / week", streak: 6, doneToday: true },
  { id: "h5", label: "Reflect & log progress", cadence: "Weekly", streak: 8, doneToday: false },
];

export default function HabitsPage() {
  const [habits, setHabits] = useState<HabitItem[]>(INITIAL);

  const toggle = (id: string) =>
    setHabits((prev) =>
      prev.map((h) =>
        h.id === id
          ? {
              ...h,
              doneToday: !h.doneToday,
              streak: h.doneToday ? Math.max(0, h.streak - 1) : h.streak + 1,
            }
          : h,
      ),
    );

  const doneCount = habits.filter((h) => h.doneToday).length;

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
          <span className="rounded-[7px] border border-rule bg-paper px-3 py-1.5 text-[12.5px] text-ink-2">
            {doneCount}/{habits.length} done today
          </span>
        }
      />

      <div className="space-y-2.5">
        {habits.map((h) => (
          <HabitRow
            key={h.id}
            label={h.label}
            cadence={h.cadence}
            streak={h.streak}
            doneToday={h.doneToday}
            onToggle={() => toggle(h.id)}
          />
        ))}
      </div>
    </div>
  );
}
