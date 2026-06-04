"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { monthlyPlanApi } from "@/lib/api/monthly-plan";
import { ROUTES, QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";

export default function MonthDetailPage() {
  const params = useParams<{ monthId: string }>();
  const monthId = params.monthId;

  const {
    data: live,
    isLoading,
    isError,
  } = useQuery({
    queryKey: QUERY_KEYS.monthlyPlan(monthId),
    queryFn: () => monthlyPlanApi.get(monthId),
    enabled: Boolean(monthId),
    retry: false,
  });

  if (isLoading) {
    return (
      <div className="mx-auto max-w-[820px] px-7 pb-24 pt-7">
        <LoadingSpinner fullPage label="Loading this month's plan…" />
      </div>
    );
  }

  if (isError || !live) {
    return (
      <div className="mx-auto max-w-[820px] px-7 pb-24 pt-7">
        <Link
          href={ROUTES.monthlyPlan}
          className="mb-4 inline-flex items-center gap-1 text-[12.5px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
        >
          ← Monthly plan
        </Link>
        <EmptyState
          title="No plan for this month yet"
          description="A detailed monthly breakdown will appear here once your roadmap generates goals for this month."
        />
      </div>
    );
  }

  const detail = {
    month: live.month,
    theme: live.theme,
    summary: live.summary,
    weeks: live.weeks,
  };

  return (
    <div className="mx-auto max-w-[820px] px-7 pb-24 pt-7">
      <Link
        href={ROUTES.monthlyPlan}
        className="mb-4 inline-flex items-center gap-1 text-[12.5px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
      >
        ← Monthly plan
      </Link>
      <PageHeader eyebrow={detail.theme} title={detail.month} description={detail.summary} />

      {detail.weeks.length === 0 ? (
        <p className="rounded-[10px] border border-dashed border-rule-strong bg-paper px-4 py-8 text-center text-[13px] text-ink-3">
          No weekly breakdown for this month yet.
        </p>
      ) : (
        <ol className="space-y-3">
          {detail.weeks.map((w) => (
            <li key={w.week} className="rounded-[12px] border border-rule bg-paper p-5">
              <div className="mb-2.5 flex items-center gap-2.5">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-green font-mono text-[12px] font-semibold text-white">
                  {w.week}
                </span>
                <p className="text-[14px] font-semibold text-ink">Week {w.week}</p>
                <span className="text-[12.5px] text-ink-3">· {w.focus}</span>
              </div>
              <ul className="space-y-1.5 pl-1">
                {w.goals.map((g, i) => (
                  <li key={i} className="flex gap-2 text-[13px] leading-snug text-ink-2">
                    <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-terra" aria-hidden="true" />
                    <span className="min-w-0">{g}</span>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
