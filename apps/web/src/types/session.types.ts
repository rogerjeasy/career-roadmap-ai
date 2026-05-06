export type ConversationRole = "user" | "assistant";

export interface ConversationTurn {
  role: ConversationRole;
  content: string;
  timestamp: string; // ISO-8601
}

export interface ClarificationQuestion {
  id: string;
  question: string;
  fieldName: string;
  priority: number;
}

export interface ClarificationFlags {
  completenessScore: number; // 0.0–1.0
  missingSlots: string[];
  roundNumber: number; // max 3
  isComplete: boolean;
}

export interface UserProfileContext {
  targetRole: string | null;
  currentRole: string | null;
  skills: string[];
  goals: string[];
  constraints: string[];
  location: string | null;
  timelineMonths: number | null;
  weeklyHoursAvailable: number | null;
  salaryGoal: number | null;
  additional: Record<string, unknown>;
}

export interface PlanContext {
  roadmapId: string | null;
  snapshot: Record<string, unknown>;
  generatedAt: string | null; // ISO-8601
}

export interface SessionState {
  userId: string;
  email: string | null;
  createdAt: string; // ISO-8601
  lastActiveAt: string; // ISO-8601
  conversationState: ConversationTurn[];
  followUpQueue: ClarificationQuestion[];
  clarificationFlags: ClarificationFlags;
  userProfileContext: UserProfileContext | null;
  planContext: PlanContext | null;
}

// ── Request payloads (sent to API) ───────────────────────────────────────────

export interface ClarificationReplyPayload {
  answers: Record<string, unknown>;
}

export interface AddConversationTurnPayload {
  role: ConversationRole;
  content: string;
}

export interface UpdateUserProfileContextPayload {
  targetRole?: string | null;
  currentRole?: string | null;
  skills?: string[];
  goals?: string[];
  constraints?: string[];
  location?: string | null;
  timelineMonths?: number | null;
  weeklyHoursAvailable?: number | null;
  salaryGoal?: number | null;
  additional?: Record<string, unknown>;
}

export interface SetPlanContextPayload {
  roadmapId?: string | null;
  snapshot?: Record<string, unknown>;
}

export interface SetFollowUpQueuePayload {
  questions: ClarificationQuestion[];
}

export interface UpdateClarificationFlagsPayload {
  completenessScore?: number;
  missingSlots?: string[];
  roundNumber?: number;
  isComplete?: boolean;
}
