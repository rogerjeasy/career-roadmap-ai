"use client";

import Link from "next/link";
import { ROUTES } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { RoadmapProgressBar } from "@/components/roadmap/roadmap-progress-bar";

interface MonthPlan {
  id: string;
  month: string;
  theme: string;
  status: "done" | "current" | "future";
  goalsDone: number;
  goalsTotal: number;
}

const MONTHS: MonthPlan[] = [
  { id: "2026-04", month: "April 2026", theme: "Foundations in applied ML", status: "done", goalsDone: 4, goalsTotal: 4 },
  { id: "2026-05", month: "May 2026", theme: "Build an agentic project", status: "done", goalsDone: 3, goalsTotal: 3 },
  { id: "2026-06", month: "June 2026", theme: "Evaluation & observability", status: "current", goalsDone: 2, goalsTotal: 4 },
  { id: "2026-07", month: "July 2026", theme: "Portfolio & visibility", status: "future", goalsDone: 0, goalsTotal: 3 },
  { id: "2026-08", month: "August 2026", theme: "Interview preparation", status: "future", goalsDone: 0, goalsTotal: 4 },
];

const STATUS_CHIP: Record<MonthPlan["status"], string> = {
  done: "bg-green-soft text-green-2",
  current: "bg-terra-soft text-terra-2",
  future: "bg-bg-3 text-ink-2",
};

export default function MonthlyPlanPage() {
  return (
    <div className="mx-auto max-w-[900px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Long view"
        title="Monthly Plan"
        description="Your roadmap rolled up into monthly themes and goals, so you can see the bigger arc."
      />

      <ul className="space-y-3">
        {MONTHS.map((m) => {
          const pct = m.goalsTotal > 0 ? (m.goalsDone / m.goalsTotal) * 100 : 0;
          return (
            <li key={m.id}>
              <Link
                href={`${ROUTES.monthlyPlan}/${m.id}`}
                className="group flex items-center gap-4 rounded-[12px] border border-rule bg-paper p-5 transition-all duration-150 hover:border-rule-strong hover:shadow-sm"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2.5">
                    <h3 className="font-serif text-[16px] font-medium tracking-[-0.01em] text-ink">{m.month}</h3>
                    <span className={`rounded-[5px] px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.04em] ${STATUS_CHIP[m.status]}`}>
                      {m.status === "current" ? "Now" : m.status}
                    </span>
                  </div>
                  <p className="mt-1 text-[13px] text-ink-2">{m.theme}</p>
                  <div className="mt-3 flex items-center gap-3">
                    <RoadmapProgressBar
                      value={pct}
                      showValue={false}
                      size="sm"
                      tone={m.status === "current" ? "terra" : "green"}
                      className="max-w-[220px]"
                    />
                    <span className="font-mono text-[11.5px] text-ink-3">
                      {m.goalsDone}/{m.goalsTotal} goals
                    </span>
                  </div>
                </div>
                <span className="shrink-0 text-[13px] font-medium text-ink-3 transition-colors group-hover:text-ink">
                  →
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
