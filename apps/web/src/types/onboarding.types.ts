export type OnboardingStep = 1 | 2 | 3 | 4 | 5;

export interface CvRole {
  title: string;
  company: string | null;
  durationMonths: number | null;
}

export interface CvSkill {
  name: string;
  level: "strong" | "supporting";
}

export interface CvProject {
  name: string;
  description: string | null;
  impact: string | null;
}

export interface CvEducation {
  degree: string;
  field: string | null;
  institution: string | null;
  year: number | null;
}

export interface CvAnalysisResult {
  roles: CvRole[];
  skills: CvSkill[];
  projects: CvProject[];
  education: CvEducation[];
  leadershipSignals: number;
  yearsOfExperience: number;
  currentRole: string | null;
  summary: string | null;
  strongSkillsCount: number;
  supportingSkillsCount: number;
  /** City/country extracted from the CV, or null when not found. */
  location?: string | null;
  /** AI-generated next-step / career-transition suggestions derived from the CV. */
  careerPathSuggestions?: string[];
}

export interface OnboardingDirection {
  goal: string;
  timelineMonths: number | null;
}

export type LocationPreference = "remote" | "relocate_eu" | "relocate_global" | "local";

export interface OnboardingConstraints {
  weeklyHours: number;
  location: string;
  locationPreference: LocationPreference;
  compensationTarget: number;
  workStyles: string[];
  lifeContext: string;
  lifeContextPrivate: boolean;
}

export interface OnboardingChatMessage {
  id: string;
  from: "twin" | "user";
  content: string;
  chips?: string[];
  selectedChip?: string | null;
  timestamp: string;
}

export interface IntakeClarificationQuestion {
  id?: string;
  question: string;
  /** snake_case — SSE payloads bypass the camelCase middleware */
  field_name?: string;
  priority?: number;
}

export interface IntakeClarificationPayload {
  questions: IntakeClarificationQuestion[];
  round: number;
  /** snake_case — SSE payloads bypass the camelCase middleware */
  career_path_suggestions?: string[];
  completeness?: number;
}

export interface IntakeResolvedPayload {
  completeness: number;
  /** snake_case — SSE payloads bypass the camelCase middleware */
  career_path_suggestions?: string[];
  applied_fields?: string[];
}
