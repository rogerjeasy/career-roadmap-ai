"use client";

import { useQuery } from "@tanstack/react-query";
import { getSession } from "@/lib/api/session";
import { marketApi } from "@/lib/api/market";
import { fixMojibake } from "@/lib/utils";
import { QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { MarketSignalCard } from "@/components/market/market-signal-card";
import { SalaryBenchmarkCard } from "@/components/market/salary-benchmark-card";
import { TrendingSkillsChart } from "@/components/market/trending-skills-chart";
import type { MarketSignal, SalaryBenchmark, TrendingSkill } from "@/types/market.types";

const SIGNALS: MarketSignal[] = [
  {
    id: "s1",
    title: "MCP-native engineering roles up 38% this quarter",
    summary:
      "Postings mentioning the Model Context Protocol and agentic tooling are growing fastest among AI infrastructure teams.",
    source: "Aggregated job-board index",
    sentiment: "positive",
    tag: "Hiring",
    timeLabel: "2d ago",
  },
  {
    id: "s2",
    title: "Evaluation & observability skills now expected at senior level",
    summary:
      "Senior AI engineering listings increasingly require experience with eval frameworks, tracing, and LLM observability.",
    source: "Industry-news digest",
    sentiment: "neutral",
    tag: "Skills",
    timeLabel: "4d ago",
  },
  {
    id: "s3",
    title: "Generalist prompt-only roles declining",
    summary:
      "Demand is shifting from prompt-only positions toward roles that combine systems engineering with applied ML.",
    source: "Social-signals tracker",
    sentiment: "negative",
    tag: "Trend",
    timeLabel: "1w ago",
  },
];

const BENCHMARK: SalaryBenchmark = {
  role: "AI Systems Engineer",
  location: "Remote · EU",
  currency: "€",
  p25: 78000,
  p50: 98000,
  p75: 125000,
};

const SKILLS: TrendingSkill[] = [
  { name: "LangGraph / agent orchestration", demandIndex: 92, deltaPct: 24 },
  { name: "RAG & vector search", demandIndex: 84, deltaPct: 11 },
  { name: "LLM evaluation", demandIndex: 76, deltaPct: 18 },
  { name: "MCP tool servers", demandIndex: 71, deltaPct: 38 },
  { name: "Distributed systems", demandIndex: 64, deltaPct: -3 },
];

export default function MarketPage() {
  const { data: session } = useQuery({
    queryKey: QUERY_KEYS.session,
    queryFn: getSession,
    staleTime: 60 * 1000,
  });

  const { data: overview } = useQuery({
    queryKey: QUERY_KEYS.marketOverview,
    queryFn: marketApi.getOverview,
    staleTime: 5 * 60 * 1000,
  });

  const targetRole = session?.userProfileContext?.targetRole
    ? fixMojibake(session.userProfileContext.targetRole)
    : null;

  // Use live agent data when available; otherwise show illustrative samples.
  const hasLive = Boolean(overview?.hasData);
  const signals = hasLive && overview!.signals.length > 0 ? overview!.signals : SIGNALS;
  const benchmark = hasLive && overview!.salaryBenchmark ? overview!.salaryBenchmark : BENCHMARK;
  const skills = hasLive && overview!.trendingSkills.length > 0 ? overview!.trendingSkills : SKILLS;

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

      {!hasLive && (
        <div className="mb-5 rounded-[8px] border border-gold-soft bg-gold-soft/40 px-4 py-2.5 text-[12px] text-gold">
          Showing illustrative market intelligence — generate a roadmap to ground these in your live target market.
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-[1fr_340px]">
        {/* Signals */}
        <section>
          <h2 className="mb-3.5 font-serif text-[18px] font-medium tracking-[-0.01em] text-ink">
            Market signals
          </h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {signals.map((s) => (
              <MarketSignalCard key={s.id} signal={s} />
            ))}
          </div>
        </section>

        {/* Side rail */}
        <div className="flex flex-col gap-5">
          <SalaryBenchmarkCard benchmark={benchmark} />
          <TrendingSkillsChart skills={skills} />
        </div>
      </div>
    </div>
  );
}
