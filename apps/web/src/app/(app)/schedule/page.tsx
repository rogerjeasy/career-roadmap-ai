"use client";

import Link from "next/link";
import { ROUTES } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { WeeklyGrid, type ScheduleBlock } from "@/components/schedule/weekly-grid";
import { WeeklyBudgetBar, type BudgetCategory } from "@/components/schedule/weekly-budget-bar";
import { HabitHeatmap } from "@/components/schedule/habit-heatmap";

const BLOCKS: ScheduleBlock[] = [
  { day: 0, label: "LangGraph deep-dive", category: "read" },
  { day: 0, label: "RAG retriever", category: "build" },
  { day: 1, label: "Ship milestone M-07", category: "build" },
  { day: 2, label: "Outreach · 2 contacts", category: "network" },
  { day: 3, label: "Eval framework", category: "build" },
  { day: 4, label: "Mock interview", category: "review" },
  { day: 5, label: "Portfolio polish", category: "build" },
  { day: 6, label: "Weekly review", category: "review" },
];

const BUDGET: BudgetCategory[] = [
  { id: "build", label: "Build", hoursLogged: 4.5, hoursTarget: 5, tone: "green" },
  { id: "read", label: "Read", hoursLogged: 2.2, hoursTarget: 3, tone: "ink" },
  { id: "network", label: "Network", hoursLogged: 1.5, hoursTarget: 2, tone: "terra" },
  { id: "review", label: "Review", hoursLogged: 1.3, hoursTarget: 2, tone: "gold" },
];

// Deterministic sample intensity for the consistency heatmap (12 weeks × 7 days).
const HEATMAP = Array.from({ length: 84 }, (_, i) => (i * 7 + 3) % 5);

export default function SchedulePage() {
  return (
    <div className="mx-auto max-w-[1100px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Rhythm"
        title="Schedule"
        description="Your week mapped to your roadmap — time blocks, budget, and the habits that compound."
        actions={
          <Link
            href={ROUTES.schedule + "/habits"}
            className="inline-flex items-center rounded-[7px] bg-ink px-3.5 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2"
          >
            Manage habits
          </Link>
        }
      />

      <div className="space-y-5">
        <WeeklyGrid blocks={BLOCKS} />
        <div className="grid gap-5 lg:grid-cols-2">
          <WeeklyBudgetBar categories={BUDGET} />
          <HabitHeatmap values={HEATMAP} />
        </div>
      </div>
    </div>
  );
}
