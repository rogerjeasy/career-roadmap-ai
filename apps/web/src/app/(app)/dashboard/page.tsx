"use client";

import { useDashboard } from "@/hooks/use-dashboard";
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

export default function DashboardPage() {
  const dashboard = useDashboard();
  const {
    user,
    session,
    isLoading,
    trackLabel,
    phaseTag,
    nextAction,
    kpis,
    phases,
    todayTasks,
    budgetCategories,
    budgetHours,
    healthScore,
    healthDelta,
    healthSignals,
    healthUpdatedLabel,
    marketTargetRole,
    salaryLabel,
    marketTrends,
    coachInsight,
    opportunityAlerts,
    activityStats,
    activityCells,
  } = dashboard;

  return (
    <div className="mx-auto max-w-[1400px] px-7 pb-24 pt-7">

      {/* Greeting + NBA card */}
      <GreetingSection
        user={user}
        session={session}
        phaseTag={phaseTag}
        nextAction={nextAction}
        isLoading={isLoading}
      />

      {/* KPI row */}
      <div className="mb-[22px]">
        <KpiRow kpis={kpis} isLoading={isLoading} />
      </div>

      {/* Main 2-column grid */}
      <div className="mb-[22px] grid gap-[18px] xl:grid-cols-[1.55fr_1fr]">

        {/* Left column */}
        <div className="flex flex-col gap-[18px]">
          <TodaysFocusCard tasks={todayTasks} isLoading={isLoading} />
          <RoadmapSnippetCard
            phases={phases}
            trackLabel={trackLabel}
            isLoading={isLoading}
          />
          <WeeklyBudgetCard
            categories={budgetCategories}
            totalBudgetHours={budgetHours}
            isLoading={isLoading}
          />
        </div>

        {/* Right column */}
        <div className="flex flex-col gap-[18px]">
          <CareerHealthCard
            score={healthScore}
            delta={healthDelta}
            signals={healthSignals}
            lastUpdatedLabel={healthUpdatedLabel}
            isLoading={isLoading}
          />
          <MarketPulseCard
            targetRole={marketTargetRole}
            salaryLabel={salaryLabel}
            trends={marketTrends}
            coachInsight={coachInsight}
            isLoading={isLoading}
          />
          <OpportunityRadarCard
            alerts={opportunityAlerts}
            isLoading={isLoading}
          />
        </div>
      </div>

      {/* Activity heatmap — full width */}
      <ActivityHeatmapCard
        stats={activityStats}
        activity={activityCells}
        isLoading={isLoading}
      />

      {/* AI Coach floating action button */}
      <CoachFab />
    </div>
  );
}
