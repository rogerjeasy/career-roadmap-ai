"use client";

import { useQuery } from "@tanstack/react-query";
import { analyticsApi } from "@/lib/api/analytics";
import { QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { JourneyAsk } from "@/components/analytics/journey-ask";
import { cn } from "@/lib/utils";

interface StatProps {
  label: string;
  value: string;
  hint?: string;
}

function Stat({ label, value, hint }: StatProps) {
  return (
    <div className="rounded-[10px] border border-rule bg-paper px-4 py-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-3">{label}</p>
      <p className="mt-1 font-serif text-[22px] font-medium tabular-nums text-ink">{value}</p>
      {hint && <p className="mt-0.5 text-[11px] text-ink-3">{hint}</p>}
    </div>
  );
}

const LEVEL_TONE: Record<string, string> = {
  low: "text-green-2",
  moderate: "text-ink-2",
  high: "text-terra-2",
};

export default function AnalyticsPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: QUERY_KEYS.analytics,
    queryFn: analyticsApi.overview,
    staleTime: 60 * 1000,
  });

  if (isLoading) {
    return (
      <div className="mx-auto max-w-[1000px] px-7 py-7">
        <LoadingSpinner fullPage label="Crunching your numbers…" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="mx-auto max-w-[1000px] px-7 py-7">
        <EmptyState title="Couldn't load analytics" description="Please refresh and try again." />
      </div>
    );
  }

  const { applications: a, learning: l, wellness: w, assets, momentum: m } = data;

  return (
    <div className="mx-auto max-w-[1000px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Insight"
        title="Analytics"
        description="A single read on the momentum across your whole job search — funnel, learning, wellbeing, and the assets backing you up."
      />

      <JourneyAsk />

      <section className="mb-8">
        <h2 className="mb-3 text-[12px] font-semibold uppercase tracking-[0.08em] text-ink-3">
          Application funnel
        </h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Total" value={String(a.total)} />
          <Stat label="Active" value={String(a.active)} />
          <Stat label="Interview rate" value={`${Math.round(a.interviewRate * 100)}%`} hint="of applied" />
          <Stat label="Offers" value={String(a.offers)} hint={`${Math.round(a.offerRate * 100)}% offer rate`} />
        </div>
        {Object.keys(a.byStatus).length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {Object.entries(a.byStatus).map(([status, count]) => (
              <span
                key={status}
                className="rounded-[5px] bg-bg-2 px-2.5 py-1 text-[11.5px] font-medium text-ink-2"
              >
                {status}: <span className="tabular-nums">{count}</span>
              </span>
            ))}
          </div>
        )}
      </section>

      <section className="mb-8 grid gap-6 sm:grid-cols-2">
        <div>
          <h2 className="mb-3 text-[12px] font-semibold uppercase tracking-[0.08em] text-ink-3">
            Learning investment
          </h2>
          <div className="grid grid-cols-2 gap-3">
            <Stat label="Items" value={String(l.items)} />
            <Stat label="Invested" value={`$${l.totalCost.toLocaleString()}`} />
            <Stat label="Hours" value={String(l.totalHours)} />
            <Stat label="Practices" value={String(m.interviewPractices)} hint="interviews" />
          </div>
        </div>
        <div>
          <h2 className="mb-3 text-[12px] font-semibold uppercase tracking-[0.08em] text-ink-3">
            Wellbeing &amp; momentum
          </h2>
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-[10px] border border-rule bg-paper px-4 py-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-3">
                Wellness
              </p>
              <p
                className={cn(
                  "mt-1 font-serif text-[18px] font-medium capitalize",
                  w.latestLevel ? LEVEL_TONE[w.latestLevel] ?? "text-ink" : "text-ink-3",
                )}
              >
                {w.latestLevel ?? "—"}
              </p>
              <p className="mt-0.5 text-[11px] text-ink-3">{w.checkins} check-ins</p>
            </div>
            <Stat
              label="Reviews"
              value={String(m.weeklyReviews)}
              hint={m.daysSinceReview !== null ? `${m.daysSinceReview}d since last` : "none yet"}
            />
            <Stat label="Habits" value={String(m.habitsTracked)} />
          </div>
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-[12px] font-semibold uppercase tracking-[0.08em] text-ink-3">
          Evidence backing you up
        </h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <Stat label="Evidence" value={String(assets.evidence)} />
          <Stat label="Portfolio" value={String(assets.portfolio)} />
          <Stat label="Credentials" value={String(assets.credentials)} />
          <Stat label="Stories" value={String(assets.storyDrafts)} />
          <Stat label="OSS saved" value={String(assets.ossBookmarks)} />
        </div>
      </section>
    </div>
  );
}
