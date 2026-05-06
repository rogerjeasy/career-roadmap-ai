import { apiClient } from "@/lib/api/client";
import type {
  AddConversationTurnPayload,
  ClarificationQuestion,
  ClarificationReplyPayload,
  SessionState,
  SetFollowUpQueuePayload,
  SetPlanContextPayload,
  UpdateClarificationFlagsPayload,
  UpdateUserProfileContextPayload,
} from "@/types/session.types";

const BASE = "/api/v1/session";

// ── Session lifecycle ────────────────────────────────────────────────────────

/** Fetch (or create) the current user session. */
export async function getSession(): Promise<SessionState> {
  const { data } = await apiClient.get<SessionState>(BASE);
  return data;
}

/** Delete the session. A fresh one is created on the next request. */
export async function clearSession(): Promise<void> {
  await apiClient.delete(BASE);
}

// ── Clarification queue ──────────────────────────────────────────────────────

/** Retrieve pending clarification questions from the follow-up queue. */
export async function getPendingClarifications(): Promise<ClarificationQuestion[]> {
  const { data } = await apiClient.get<ClarificationQuestion[]>(`${BASE}/clarification`);
  return data;
}

/** Submit user answers to clarification questions. */
export async function replyClarification(
  answers: Record<string, unknown>,
): Promise<SessionState> {
  const payload: ClarificationReplyPayload = { answers };
  const { data } = await apiClient.post<SessionState>(`${BASE}/clarification/reply`, payload);
  return data;
}

/** Push a new set of clarification questions (Clarification Engine → session). */
export async function setFollowUpQueue(
  payload: SetFollowUpQueuePayload,
): Promise<SessionState> {
  const { data } = await apiClient.post<SessionState>(`${BASE}/clarification/queue`, payload);
  return data;
}

/** Update clarification scoring metadata. */
export async function updateClarificationFlags(
  payload: UpdateClarificationFlagsPayload,
): Promise<SessionState> {
  const { data } = await apiClient.patch<SessionState>(`${BASE}/clarification/flags`, payload);
  return data;
}

// ── Conversation state ───────────────────────────────────────────────────────

/** Append a single conversation turn to the dialogue history. */
export async function addConversationTurn(
  payload: AddConversationTurnPayload,
): Promise<SessionState> {
  const { data } = await apiClient.post<SessionState>(`${BASE}/conversation`, payload);
  return data;
}

// ── Context caches ───────────────────────────────────────────────────────────

/** Merge fields into the cached user profile context. */
export async function updateUserProfileContext(
  payload: UpdateUserProfileContextPayload,
): Promise<SessionState> {
  const { data } = await apiClient.patch<SessionState>(`${BASE}/user-profile`, payload);
  return data;
}

/** Update the cached roadmap/plan context snapshot. */
export async function setPlanContext(payload: SetPlanContextPayload): Promise<SessionState> {
  const { data } = await apiClient.patch<SessionState>(`${BASE}/plan`, payload);
  return data;
}
