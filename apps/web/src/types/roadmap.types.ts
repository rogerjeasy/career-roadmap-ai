export interface RoadmapPhase {
  title: string;
  duration_weeks: number;
  milestones: string[];
  skills_to_gain: string[];
  confidence: number;
}

export interface RoadmapData {
  summary: string;
  phases: RoadmapPhase[];
  weekly_habits: string[];
  next_steps: string[];
  unverified_claims: string[];
  confidence: number;
}

// ── Full roadmap (GET /roadmaps/{id}) — camelCase via CaseConversionMiddleware ──

export interface SkillItem {
  text: string;
  isPriority: boolean;
  displayOrder: number;
}

export interface ActionItem {
  text: string;
  subText: string;
  displayOrder: number;
}

export interface LearningResource {
  title: string;
  resourceType: string;
  provider: string;
  difficulty: string;
  tags: string[];
  url: string | null;
  estimatedHours: number | null;
  isFree: boolean;
  description: string;
}

export interface WeeklyTask {
  weekNumber: number;
  focusArea: string;
  tasks: string[];
  estimatedHours: number;
  deliverable: string | null;
}

export interface RoadmapPhaseDetail {
  id: string;
  order: number;
  title: string;
  description: string;
  durationWeeks: number;
  goals: string[];
  milestones: string[];
  skillsToGain: string[];
  skills: SkillItem[];
  actions: ActionItem[];
  gapsAddressed: string[];
  marketRelevance: string;
  difficulty: string;
  deliverables: string[];
  confidence: number;
  resources: LearningResource[];
  curatedResources: LearningResource[];
  weeklyTasks: WeeklyTask[];
}

export interface WeeklyHabit {
  order: number;
  text: string;
  frequency: string;
  durationMinutes: number;
  rationale: string;
}

export interface RoadmapDetail {
  id: string;
  sessionId: string;
  summary: string;
  confidence: number;
  status: string;
  validationPassed: boolean;
  unverifiedClaims: string[];
  durationMs: number;
  marketGrounding: Record<string, unknown>;
  phases: RoadmapPhaseDetail[];
  weeklyHabits: WeeklyHabit[];
  nextSteps: string[];
  createdAt: string;
}
