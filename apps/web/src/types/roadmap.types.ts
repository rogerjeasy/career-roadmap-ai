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
