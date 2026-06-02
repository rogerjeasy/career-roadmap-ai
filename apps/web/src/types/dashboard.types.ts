// ── Dashboard-specific types ─────────────────────────────────────────────────

export type TaskCategory = "build" | "read" | "network" | "review";

export interface TodayTask {
  id: string;
  title: string;
  category: TaskCategory;
  estimateMinutes: number;
  isDone: boolean;
  meta: string;
}

export type RoadmapPhaseStatus = "done" | "current" | "future";

export interface RoadmapPhase {
  number: number;
  label: string;
  title: string;
  progressPercent: number;
  status: RoadmapPhaseStatus;
  milestonesCompleted: number;
  milestonesTotal: number;
  dateLabel: string;
}

export interface HealthSignal {
  label: string;
  score: number;
  isWarn?: boolean;
}

export interface SkillTrend {
  name: string;
  changePercent: number;
  isInPlan: boolean;
  isSteady?: boolean;
  sparkPoints: number[];
}

export type OpportunityType = "job" | "mentor" | "event" | "opensource";

export interface OpportunityItem {
  id: string;
  type: OpportunityType;
  tag: string;
  title: string;
  meta: string;
  matchScore: number;
  matchLabel: string;
}

export type ActivityLevel = 0 | 1 | 2 | 3 | 4;

export interface ActivityCell {
  level: ActivityLevel;
  isMilestone: boolean;
  dateLabel: string;
  sessions: number;
}

export interface ActivityStats {
  longestStreakDays: number;
  totalDeepWorkHours: number;
  milestonesCompleted: number;
  milestonesTotal: number;
  weeklyReviewsFiled: number;
  totalWeeks: number;
}

export interface WeeklyBudgetCategory {
  id: TaskCategory;
  hoursLogged: number;
  hoursTarget: number;
}

export interface DashboardKpis {
  healthScore: number;
  healthScoreDelta: number;
  activeStreakDays: number;
  hoursThisWeek: number;
  weeklyBudgetHours: number;
  /** null when no roadmap exists or no schedule data ties a milestone to a date. */
  nextMilestoneDays: number | null;
  nextMilestoneName: string;
}

export interface NextBestAction {
  title: string;
  description: string;
  estimateMinutes: number;
  milestoneLabel?: string;
  /** Where "Start now" links. Defaults to the coach when omitted. */
  href?: string;
}

export interface PhaseTag {
  currentPhase: number;
  totalPhases: number;
  phaseName: string;
}
