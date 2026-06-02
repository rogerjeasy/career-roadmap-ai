"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { userApi } from "@/lib/api/user";
import { opportunitiesApi, type AlertsResponse } from "@/lib/api/opportunities";
import { getSession } from "@/lib/api/session";
import { progressApi, type WeeklyReview } from "@/lib/api/progress";
import { scheduleApi, type Habit } from "@/lib/api/schedule";
import { marketApi } from "@/lib/api/market";
import { QUERY_KEYS, ROUTES } from "@/lib/constants";
import { fixMojibake } from "@/lib/utils";
import { formatRelative } from "@/lib/date";
import { useRoadmap } from "@/hooks/use-roadmap";
import { useRoadmapProgress } from "@/hooks/use-roadmap-progress";
import type { UserProfile } from "@/types/api.types";
import type { SessionState } from "@/types/session.types";
import type {
  ActivityStats,
  DashboardKpis,
  HealthSignal,
  NextBestAction,
  PhaseTag,
  RoadmapPhase,
  RoadmapPhaseStatus,
  SkillTrend,
  TodayTask,
  WeeklyBudgetCategory,
} from "@/types/dashboard.types";

/** Weeks shown in the activity heatmap. */
const HEATMAP_WEEKS = 16;
const DAY_MS = 86_400_000;

/** Whole-calendar-days between `date` and `today` (0 = today, positive = past). */
function calendarDaysAgo(date: Date, today: Date): number {
  const a = Date.UTC(date.getFullYear(), date.getMonth(), date.getDate());
  const b = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.round((b - a) / DAY_MS);
}

/**
 * Build a real activity grid from dated signals: each habit completion on a day
 * adds intensity to that day, and a filed weekly review adds a little more. Each
 * cell is a 0–4 level, indexed `week * 7 + dayOfWeek` to match the heatmap grid
 * (last cell = today).
 */
function buildActivityCells(habits: Habit[], reviews: WeeklyReview[]): number[] {
  const total = HEATMAP_WEEKS * 7;
  const cells = new Array<number>(total).fill(0);
  const today = new Date();

  const bump = (daysAgo: number, by: number) => {
    if (daysAgo < 0 || daysAgo >= total) return;
    const idx = total - 1 - daysAgo;
    cells[idx] = Math.min(4, cells[idx] + by);
  };

  // Habit completions — the primary signal (one ISO date per completion).
  for (const habit of habits) {
    for (const iso of habit.completedDates) {
      const [y, m, d] = iso.split("-").map(Number);
      if (!y || !m || !d) continue;
      bump(calendarDaysAgo(new Date(y, m - 1, d), today), 1);
    }
  }

  // Filed weekly reviews — a secondary signal.
  for (const review of reviews) {
    const t = Date.parse(review.createdAt);
    if (Number.isNaN(t)) continue;
    bump(calendarDaysAgo(new Date(t), today), 1);
  }

  return cells;
}

function maxStreak(habits: Habit[]): number {
  return habits.reduce((m, h) => Math.max(m, h.streak), 0);
}

export interface DashboardView {
  user: UserProfile | null;
  session: SessionState | null;
  isLoading: boolean;
  userError: unknown;
  sessionError: unknown;

  // Greeting
  targetRole: string | null;
  trackLabel: string;
  hasRoadmap: boolean;
  phaseTag: PhaseTag | null;
  nextAction: NextBestAction;

  // KPIs
  kpis: DashboardKpis;

  // Roadmap snippet
  phases: RoadmapPhase[];

  // Today's focus + budget
  todayTasks: TodayTask[];
  budgetCategories: WeeklyBudgetCategory[];
  budgetHours: number;

  // Career health
  healthScore: number;
  healthDelta: number;
  healthSignals: HealthSignal[];
  healthUpdatedLabel: string;

  // Market pulse
  marketTargetRole: string | null;
  salaryLabel: string | null;
  marketTrends: SkillTrend[];
  coachInsight: string | null;

  // Opportunity radar
  opportunityAlerts: AlertsResponse | null;

  // Activity
  activityStats: ActivityStats;
  activityCells: number[];
}

export function useDashboard(): DashboardView {
  const userQuery = useQuery({
    queryKey: QUERY_KEYS.me,
    queryFn: userApi.getMe,
    staleTime: 5 * 60 * 1000,
  });

  const sessionQuery = useQuery({
    queryKey: QUERY_KEYS.session,
    queryFn: getSession,
    staleTime: 60 * 1000,
  });

  const opportunityAlertsQuery = useQuery({
    queryKey: QUERY_KEYS.opportunityAlerts,
    queryFn: opportunitiesApi.getAlerts,
    staleTime: 5 * 60 * 1000,
  });

  const healthQuery = useQuery({
    queryKey: QUERY_KEYS.health,
    queryFn: progressApi.getHealth,
    staleTime: 60 * 1000,
  });

  const habitsQuery = useQuery({
    queryKey: QUERY_KEYS.habits,
    queryFn: scheduleApi.listHabits,
    staleTime: 60 * 1000,
  });

  const blocksQuery = useQuery({
    queryKey: QUERY_KEYS.scheduleBlocks,
    queryFn: scheduleApi.listBlocks,
    staleTime: 60 * 1000,
  });

  const reviewsQuery = useQuery({
    queryKey: QUERY_KEYS.weeklyReviews,
    queryFn: () => progressApi.listReviews(HEATMAP_WEEKS),
    staleTime: 60 * 1000,
  });

  const marketQuery = useQuery({
    queryKey: QUERY_KEYS.marketOverview,
    queryFn: marketApi.getOverview,
    staleTime: 5 * 60 * 1000,
  });

  const { roadmap, isLoading: roadmapLoading } = useRoadmap();
  const roadmapId = roadmap?.id ?? null;
  const { completedKeys } = useRoadmapProgress(roadmapId);

  const session = sessionQuery.data ?? null;
  const health = healthQuery.data ?? null;
  const habits = useMemo(() => habitsQuery.data ?? [], [habitsQuery.data]);
  const blocks = useMemo(() => blocksQuery.data ?? [], [blocksQuery.data]);
  const reviews = useMemo(() => reviewsQuery.data ?? [], [reviewsQuery.data]);
  const market = marketQuery.data ?? null;

  // ── Roadmap phases with real per-phase milestone progress ──────────────────
  const phases = useMemo<RoadmapPhase[]>(() => {
    if (!roadmap) return [];
    const sorted = [...roadmap.phases].sort((a, b) => a.order - b.order);
    let currentTaken = false;

    return sorted.map((p, i) => {
      const total = p.milestones.length;
      let completed = 0;
      for (let m = 0; m < total; m += 1) {
        if (completedKeys.has(`${p.id}:${m}`)) completed += 1;
      }
      const isDone = total > 0 && completed >= total;
      let status: RoadmapPhaseStatus;
      if (isDone) {
        status = "done";
      } else if (!currentTaken) {
        status = "current";
        currentTaken = true;
      } else {
        status = "future";
      }
      const num = p.order || i + 1;
      return {
        number: num,
        label: String(num).padStart(2, "0"),
        title: fixMojibake(p.title),
        progressPercent: total > 0 ? Math.round((completed / total) * 100) : 0,
        status,
        milestonesCompleted: completed,
        milestonesTotal: total,
        dateLabel: `${p.durationWeeks} wk${p.durationWeeks === 1 ? "" : "s"}`,
      };
    });
  }, [roadmap, completedKeys]);

  // ── Next incomplete milestone (drives KPI + NBA) ───────────────────────────
  const nextMilestone = useMemo(() => {
    if (!roadmap) return null;
    const sorted = [...roadmap.phases].sort((a, b) => a.order - b.order);
    for (const p of sorted) {
      for (let m = 0; m < p.milestones.length; m += 1) {
        if (!completedKeys.has(`${p.id}:${m}`)) {
          return { name: fixMojibake(p.milestones[m]), phaseTitle: fixMojibake(p.title) };
        }
      }
    }
    return null;
  }, [roadmap, completedKeys]);

  const targetRole = session?.userProfileContext?.targetRole
    ? fixMojibake(session.userProfileContext.targetRole)
    : null;
  const currentRole = session?.userProfileContext?.currentRole
    ? fixMojibake(session.userProfileContext.currentRole)
    : null;
  const trackLabel = targetRole
    ? currentRole
      ? `${currentRole} → ${targetRole}`
      : targetRole
    : "";

  const hasRoadmap = Boolean(roadmap) || Boolean(session?.planContext?.roadmapId);

  const currentIdx = phases.findIndex((p) => p.status === "current");
  const phaseTag: PhaseTag | null =
    roadmap && phases.length > 0
      ? {
          currentPhase: (currentIdx >= 0 ? currentIdx : phases.length - 1) + 1,
          totalPhases: phases.length,
          phaseName: phases[currentIdx >= 0 ? currentIdx : phases.length - 1].title,
        }
      : null;

  const nextAction: NextBestAction = !hasRoadmap
    ? {
        title: "Generate your personalised career roadmap",
        description:
          "Chat with the Career Twin to map your goal, current skills, and timeline. Your week-by-week plan will be ready in minutes.",
        estimateMinutes: 0,
        href: ROUTES.roadmapGenerate,
      }
    : nextMilestone
      ? {
          title: nextMilestone.name,
          description: `Your next milestone in the ${nextMilestone.phaseTitle} phase.`,
          estimateMinutes: 0,
        }
      : {
          title: "All milestones complete",
          description:
            "You've checked off every milestone — review your roadmap or generate the next phase.",
          estimateMinutes: 0,
          href: ROUTES.roadmap,
        };

  // ── KPIs ───────────────────────────────────────────────────────────────────
  const kpis: DashboardKpis = {
    healthScore: health?.score ?? 0,
    healthScoreDelta: health?.delta ?? 0,
    activeStreakDays: maxStreak(habits),
    // No time-logging feature yet — surfaced as "—" by KpiRow.
    hoursThisWeek: 0,
    weeklyBudgetHours: session?.userProfileContext?.weeklyHoursAvailable ?? 0,
    // Roadmap milestones aren't tied to calendar dates, so a day countdown
    // would be fabricated — show the milestone name without a fake number.
    nextMilestoneDays: null,
    nextMilestoneName: nextMilestone?.name ?? "",
  };

  // ── Today's focus: today's schedule blocks ─────────────────────────────────
  const todayWeekday = (new Date().getDay() + 6) % 7; // 0 = Mon … 6 = Sun
  const todayTasks: TodayTask[] = blocks
    .filter((b) => b.day === todayWeekday)
    .map((b) => ({
      id: b.id,
      title: fixMojibake(b.label),
      category: b.category,
      estimateMinutes: 0,
      isDone: false,
      meta: "",
    }));

  // ── Career health signals ──────────────────────────────────────────────────
  const healthSignals: HealthSignal[] = (health?.signals ?? []).map((s) => ({
    label: s.label,
    score: s.score,
    isWarn: s.score < 50,
  }));

  // ── Market pulse ────────────────────────────────────────────────────────────
  const roadmapSkills = useMemo(() => {
    const set = new Set<string>();
    roadmap?.phases.forEach((p) =>
      p.skillsToGain.forEach((s) => set.add(s.toLowerCase())),
    );
    return set;
  }, [roadmap]);

  const marketTrends: SkillTrend[] = (market?.trendingSkills ?? []).slice(0, 5).map((t) => {
    const name = t.name.toLowerCase();
    const isInPlan = [...roadmapSkills].some(
      (s) => s.includes(name) || name.includes(s),
    );
    return {
      name: t.name,
      changePercent: t.deltaPct,
      isInPlan,
      isSteady: Math.abs(t.deltaPct) < 5,
      sparkPoints: [],
    };
  });

  const sb = market?.salaryBenchmark ?? null;
  const salaryLabel = sb ? `${sb.currency}${Math.round(sb.p50 / 1000)}k` : null;
  const coachInsight = market?.summary?.trim() ? market.summary.trim() : null;

  // ── Activity ────────────────────────────────────────────────────────────────
  const milestonesTotal = phases.reduce((s, p) => s + p.milestonesTotal, 0);
  const milestonesCompleted = phases.reduce((s, p) => s + p.milestonesCompleted, 0);
  const totalWeeks = roadmap
    ? roadmap.phases.reduce((s, p) => s + p.durationWeeks, 0)
    : 0;

  const activityStats: ActivityStats = {
    longestStreakDays: maxStreak(habits),
    // No deep-work time tracking yet — surfaced as "—" by the card.
    totalDeepWorkHours: 0,
    milestonesCompleted,
    milestonesTotal,
    weeklyReviewsFiled: reviews.length,
    totalWeeks,
  };

  const activityCells = useMemo(
    () => buildActivityCells(habits, reviews),
    [habits, reviews],
  );

  const isLoading =
    userQuery.isLoading || sessionQuery.isLoading || roadmapLoading;

  return {
    user: userQuery.data ?? null,
    session,
    isLoading,
    userError: userQuery.error,
    sessionError: sessionQuery.error,

    targetRole,
    trackLabel,
    hasRoadmap,
    phaseTag,
    nextAction,

    kpis,
    phases,

    todayTasks,
    budgetCategories: [],
    budgetHours: session?.userProfileContext?.weeklyHoursAvailable ?? 0,

    healthScore: health?.score ?? 0,
    healthDelta: health?.delta ?? 0,
    healthSignals,
    healthUpdatedLabel: health?.updatedAt ? formatRelative(health.updatedAt) : "",

    marketTargetRole: targetRole,
    salaryLabel,
    marketTrends,
    coachInsight,

    opportunityAlerts: opportunityAlertsQuery.data ?? null,

    activityStats,
    activityCells,
  };
}
