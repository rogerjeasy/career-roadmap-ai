"use client";

import { useDashboard } from "@/hooks/use-dashboard";
import { fixMojibake } from "@/lib/utils";
import { GreetingSection }       from "@/components/dashboard/greeting-section";
import { KpiRow }                from "@/components/dashboard/kpi-row";
import { TodaysFocusCard }       from "@/components/dashboard/todays-focus-card";
import { RoadmapSnippetCard }    from "@/components/dashboard/roadmap-snippet-card";
import { WeeklyBudgetCard }      from "@/components/dashboard/weekly-budget-card";
import { CareerHealthCard }      from "@/components/dashboard/career-health-card";
import { MarketPulseCard }       from "@/components/dashboard/market-pulse-card";
import { OpportunityRadarCard }  from "@/components/dashboard/opportunity-radar-card";
import { ActivityHeatmapCard }   from "@/components/dashboard/activity-heatmap-card";
import { CoachFab }              from "@/components/dashboard/coach-fab";
import type { DashboardKpis, TodayTask, RoadmapPhase, WeeklyBudgetCategory, HealthSignal } from "@/types/dashboard.types";

// ── Demo / derived data helpers ───────────────────────────────────────────────
// These build from session data where available, falling back to sensible
// defaults so the page renders meaningfully before the roadmap is generated.

function deriveKpis(): DashboardKpis {
  return {
    healthScore:         76,
    healthScoreDelta:    8,
    activeStreakDays:    23,
    hoursThisWeek:       9.5,
    weeklyBudgetHours:   12,
    nextMilestoneDays:   14,
    nextMilestoneName:   "M-08 · Eval framework demo",
  };
}

const SAMPLE_TASKS: TodayTask[] = [
  {
    id: "t1",
    title: "Morning study block · LangGraph deep-dive",
    category: "read",
    estimateMinutes: 45,
    isDone: true,
    meta: "Completed at <strong>08:42</strong>",
  },
  {
    id: "t2",
    title: "Push RAG retriever & close milestone M-07",
    category: "build",
    estimateMinutes: 25,
    isDone: false,
    meta: "Due <strong>today</strong>",
  },
  {
    id: "t3",
    title: "Reply to 2 ML engineers from yesterday's meetup",
    category: "network",
    estimateMinutes: 20,
    isDone: false,
    meta: "From <strong>Career Twin</strong> · drafted",
  },
  {
    id: "t4",
    title: "Mock interview · Anthropic system-design round",
    category: "review",
    estimateMinutes: 60,
    isDone: false,
    meta: "Studio booked <strong>19:00</strong>",
  },
];

const SAMPLE_PHASES: RoadmapPhase[] = [
  { number: 1, label: "01", title: "Foundation in ML",              progressPercent: 100, status: "done",    milestonesCompleted: 8, milestonesTotal: 8, dateLabel: "Complete" },
  { number: 2, label: "02", title: "Specialisation in applied ML",  progressPercent: 57,  status: "current", milestonesCompleted: 4, milestonesTotal: 7, dateLabel: "4 of 7 milestones" },
  { number: 3, label: "03", title: "Portfolio & visibility",        progressPercent: 0,   status: "future",  milestonesCompleted: 0, milestonesTotal: 6, dateLabel: "Starts late June" },
  { number: 4, label: "04", title: "Interviews & offers",           progressPercent: 0,   status: "future",  milestonesCompleted: 0, milestonesTotal: 5, dateLabel: "Q4 2026" },
];

const SAMPLE_BUDGET: WeeklyBudgetCategory[] = [
  { id: "build",   hoursLogged: 4.5, hoursTarget: 5 },
  { id: "read",    hoursLogged: 2.2, hoursTarget: 3 },
  { id: "network", hoursLogged: 1.5, hoursTarget: 2 },
  { id: "review",  hoursLogged: 1.3, hoursTarget: 2 },
];

const HEALTH_SIGNALS: HealthSignal[] = [
  { label: "Roadmap progress",   score: 84 },
  { label: "Skill readiness",    score: 71 },
  { label: "Portfolio strength", score: 62 },
  { label: "Market alignment",   score: 88 },
  { label: "Network activity",   score: 42, isWarn: true },
];

// ── Page ──────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const { user, session, opportunityAlerts, isLoading } = useDashboard();

  const kpis       = deriveKpis();
  const targetRole = session?.userProfileContext?.targetRole
    ? fixMojibake(session.userProfileContext.targetRole)
    : null;

  return (
    <div className="mx-auto max-w-[1400px] px-7 pb-24 pt-7">

      {/* Greeting + NBA card */}
      <GreetingSection user={user} session={session} isLoading={isLoading} />

      {/* KPI row */}
      <div className="mb-[22px]">
        <KpiRow kpis={kpis} isLoading={isLoading} />
      </div>

      {/* Main 2-column grid */}
      <div className="mb-[22px] grid gap-[18px] xl:grid-cols-[1.55fr_1fr]">

        {/* Left column */}
        <div className="flex flex-col gap-[18px]">
          <TodaysFocusCard tasks={SAMPLE_TASKS} isLoading={isLoading} />
          <RoadmapSnippetCard
            phases={SAMPLE_PHASES}
            trackLabel={
              targetRole
                ? `Full-Stack → ${targetRole}`
                : "Full-Stack → AI Systems Engineer"
            }
            isLoading={isLoading}
          />
          <WeeklyBudgetCard
            categories={SAMPLE_BUDGET}
            totalBudgetHours={session?.userProfileContext?.weeklyHoursAvailable ?? 12}
            isLoading={isLoading}
          />
        </div>

        {/* Right column */}
        <div className="flex flex-col gap-[18px]">
          <CareerHealthCard
            score={kpis.healthScore}
            delta={kpis.healthScoreDelta}
            signals={HEALTH_SIGNALS}
            lastUpdatedLabel="2 h ago"
            isLoading={isLoading}
          />
          <MarketPulseCard
            targetRole={targetRole}
            salaryLabel={null}
            trends={[]}
            coachInsight={
              `"MCP-native" engineering roles are the fastest-growing tag in your target market. ` +
              `Two of your active milestones already cover this — keep going.`
            }
            isLoading={isLoading}
          />
          <OpportunityRadarCard
            alerts={opportunityAlerts}
            isLoading={isLoading}
          />
        </div>
      </div>

      {/* Activity heatmap — full width */}
      <ActivityHeatmapCard stats={null} isLoading={isLoading} />

      {/* AI Coach floating action button */}
      <CoachFab />
    </div>
  );
}
