"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { getSession } from "@/lib/api/session";
import { marketApi } from "@/lib/api/market";
import { fixMojibake } from "@/lib/utils";
import { ROUTES, QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { MarketSignalCard } from "@/components/market/market-signal-card";
import { SalaryBenchmarkCard } from "@/components/market/salary-benchmark-card";
import { TrendingSkillsChart } from "@/components/market/trending-skills-chart";

export default function MarketPage() {
  const { data: session } = useQuery({
    queryKey: QUERY_KEYS.session,
    queryFn: getSession,
    staleTime: 60 * 1000,
  });

  const { data: overview, isLoading } = useQuery({
    queryKey: QUERY_KEYS.marketOverview,
    queryFn: marketApi.getOverview,
    staleTime: 5 * 60 * 1000,
  });

  const targetRole = session?.userProfileContext?.targetRole
    ? fixMojibake(session.userProfileContext.targetRole)
    : null;

  const hasLive = Boolean(overview?.hasData);
  const signals = overview?.signals ?? [];
  const benchmark = overview?.salaryBenchmark ?? null;
  const skills = overview?.trendingSkills ?? [];

  return (
    <div className="mx-auto max-w-[1100px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Intelligence"
        title="Market Pulse"
        description={
          targetRole
            ? `Live signals, salary benchmarks, and trending skills for your move into ${targetRole}.`
            : "Live signals, salary benchmarks, and trending skills for your target market."
        }
      />

      {isLoading ? (
        <LoadingSpinner fullPage label="Loading market intelligence…" />
      ) : !hasLive ? (
        <EmptyState
          title="No market intelligence yet"
          description="Generate a roadmap and the market-intelligence agent will surface live signals, salary benchmarks, and trending skills for your target role here."
          action={
            <Link
              href={ROUTES.roadmap + "/generate"}
              className="inline-flex items-center rounded-[7px] bg-ink px-3.5 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2"
            >
              Generate roadmap
            </Link>
          }
        />
      ) : (
        <div className="grid gap-5 lg:grid-cols-[1fr_340px]">
          {/* Signals */}
          <section>
            <h2 className="mb-3.5 font-serif text-[18px] font-medium tracking-[-0.01em] text-ink">
              Market signals
            </h2>
            {signals.length > 0 ? (
              <div className="grid gap-4 sm:grid-cols-2">
                {signals.map((s) => (
                  <MarketSignalCard key={s.id} signal={s} />
                ))}
              </div>
            ) : (
              <p className="rounded-[10px] border border-dashed border-rule-strong bg-paper px-4 py-8 text-center text-[13px] text-ink-3">
                No market signals for your target role yet.
              </p>
            )}
          </section>

          {/* Side rail */}
          <div className="flex flex-col gap-5">
            {benchmark && <SalaryBenchmarkCard benchmark={benchmark} />}
            {skills.length > 0 && <TrendingSkillsChart skills={skills} />}
          </div>
        </div>
      )}
    </div>
  );
}
