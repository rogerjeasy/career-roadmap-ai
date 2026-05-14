import type { RoadmapData } from "./roadmap.types";

export type AgentEventType =
  | "orchestration_started"
  | "orchestration_completed"
  | "orchestration_failed"
  | "agent_started"
  | "agent_completed"
  | "agent_failed"
  | "clarification_required"
  | "clarification_resolved"
  | "stream_token"
  | "stream_done"
  | "step_progress";

export type AgentResultStatus = "completed" | "failed" | "partial" | "timeout";

export interface AgentEvent {
  event_id: string;
  event_type: AgentEventType;
  session_id: string;
  user_id: string;
  correlation_id: string;
  timestamp: string;
  payload: Record<string, unknown>;
}

export interface StepProgressPayload {
  step_name: string;
  step_index: number;
  total_steps: number;
  pct: number;
}

export interface AgentStartedPayload {
  agent: string;
  max_attempts: number;
}

export interface AgentCompletedPayload {
  agent: string;
  status: "completed" | "failed";
  duration_ms: number;
  is_required: boolean;
}

export interface ClarificationQuestion {
  id?: string;
  question: string;
  type?: "text" | "choice";
  options?: string[];
}

export interface ClarificationPayload {
  questions: ClarificationQuestion[];
  round: number;
}

export interface OrchestratorCompletedPayload {
  request_id: string;
  session_id: string;
  user_id: string;
  status: AgentResultStatus;
  roadmap: RoadmapData | null;
  agent_results: Record<string, unknown>;
  confidence: number;
  validation_passed: boolean;
  clarification_required: boolean;
  clarification_questions: ClarificationQuestion[];
  error_message: string | null;
  duration_ms: number;
}
