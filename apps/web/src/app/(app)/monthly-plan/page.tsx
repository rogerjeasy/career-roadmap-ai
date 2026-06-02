"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { monthlyPlanApi } from "@/lib/api/monthly-plan";
import { ROUTES, QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { RoadmapProgressBar } from "@/components/roadmap/roadmap-progress-bar";

interface MonthPlan {
  id: string;
  month: string;
  theme: string;
  status: "done" | "current" | "future";
  goalsDone: number;
  goalsTotal: number;
}

const STATUS_CHIP: Record<MonthPlan["status"], string> = {
  done: "bg-green-soft text-green-2",
  current: "bg-terra-soft text-terra-2",
  future: "bg-bg-3 text-ink-2",
};

export default function MonthlyPlanPage() {
  const { data: livePlans, isLoading } = useQuery({
    queryKey: QUERY_KEYS.monthlyPlans,
    queryFn: monthlyPlanApi.list,
    staleTime: 60 * 1000,
  });

  const months: MonthPlan[] = (livePlans ?? []).map((p) => ({
    id: p.monthId,
    month: p.month,
    theme: p.theme,
    status: p.status,
    goalsDone: p.goalsDone,
    goalsTotal: p.goalsTotal,
  }));

  return (
    <div className="mx-auto max-w-[900px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Long view"
        title="Monthly Plan"
        description="Your roadmap rolled up into monthly themes and goals, so you can see the bigger arc."
      />

      {isLoading ? (
        <LoadingSpinner fullPage label="Loading your monthly plan…" />
      ) : months.length === 0 ? (
        <EmptyState
          title="No monthly plan yet"
          description="Generate your roadmap and it will roll up into monthly themes and goals here."
        />
      ) : (
      <ul className="space-y-3">
        {months.map((m) => {
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
      )}
    </div>
  );
}
