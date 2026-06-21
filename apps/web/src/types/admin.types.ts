// Admin domain types. All fields are camelCase — the API client converts the
// backend's snake_case automatically. These mirror src/domains/admin/schemas.py.

import type { UserRole } from "./api.types";

export type AssignableRole = UserRole;
export type InboxStatus = "new" | "in_progress" | "resolved" | "archived";
export type BroadcastAudience = "all" | "active" | "admins";
export type BroadcastTone = "info" | "success" | "warn";
export type HealthStatus = "ok" | "degraded" | "down" | "disabled";

// ── Users ────────────────────────────────────────────────────────────────────

export interface AdminUserItem {
  uid: string;
  email: string;
  displayName: string | null;
  photoUrl: string | null;
  provider: string;
  role: UserRole;
  isActive: boolean;
  emailVerified: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface AdminUserListResponse {
  items: AdminUserItem[];
  total: number;
  page: number;
  pageSize: number;
  hasNext: boolean;
}

export interface AdminUserDetail extends AdminUserItem {
  roadmapCount: number;
  feedbackCount: number;
  notificationCount: number;
  lastRoadmapAt: string | null;
}

export interface UserListParams {
  page?: number;
  pageSize?: number;
  search?: string;
  role?: string;
  status?: string;
}

// ── Overview ─────────────────────────────────────────────────────────────────

export interface TimeseriesPoint {
  date: string;
  count: number;
}

export interface AdminOverview {
  totalUsers: number;
  activeUsers: number;
  adminUsers: number;
  newUsers7d: number;
  newUsers30d: number;
  verifiedUsers: number;
  totalRoadmaps: number;
  roadmaps7d: number;
  totalFeedback: number;
  openFeedback: number;
  totalContactRequests: number;
  openContactRequests: number;
  newsletterSubscribers: number;
  roleBreakdown: Record<string, number>;
  providerBreakdown: Record<string, number>;
  signupsLast14Days: TimeseriesPoint[];
  recentUsers: AdminUserItem[];
  generatedAt: string;
}

// ── Inbox ────────────────────────────────────────────────────────────────────

export interface AdminFeedbackItem {
  id: string;
  userId: string;
  userEmail: string | null;
  category: string;
  subject: string;
  message: string;
  rating: number | null;
  status: InboxStatus;
  createdAt: string;
}

export interface AdminContactItem {
  id: string;
  name: string;
  email: string;
  company: string;
  topic: string;
  message: string;
  status: InboxStatus;
  createdAt: string;
}

// ── Newsletter ───────────────────────────────────────────────────────────────

export interface NewsletterSubscriberItem {
  userId: string;
  email: string | null;
  displayName: string | null;
  frequency: string;
  topics: string[];
  subscribed: boolean;
  updatedAt: string | null;
}

// ── Broadcast ────────────────────────────────────────────────────────────────

export interface BroadcastInput {
  title: string;
  body: string;
  tone: BroadcastTone;
  link?: string | null;
  audience: BroadcastAudience;
}

export interface BroadcastResult {
  delivered: number;
  audience: BroadcastAudience;
  title: string;
}

// ── Audit ────────────────────────────────────────────────────────────────────

export interface AdminAuditItem {
  id: string;
  action: string;
  actorUid: string;
  actorEmail: string | null;
  targetUid: string | null;
  targetLabel: string | null;
  detail: string;
  createdAt: string;
}

// ── System health ────────────────────────────────────────────────────────────

export interface HealthComponent {
  name: string;
  status: HealthStatus;
  detail: string;
}

export interface SystemHealth {
  status: "ok" | "degraded" | "down";
  environment: string;
  components: HealthComponent[];
  generatedAt: string;
}

// ── KB ops ───────────────────────────────────────────────────────────────────

export type KbDocType =
  | "career_kb"
  | "esco"
  | "onet"
  | "market_reports"
  | "role_templates"
  | "swiss_eu_market"
  | "global_market";

export interface KbDispatchResponse {
  taskIds: string[];
  docTypes: string[];
  message: string;
}

export interface KbTaskStatus {
  taskId: string;
  state: string;
  result?: unknown;
  error?: string;
}

export interface KbEvalResults {
  found: boolean;
  message?: string;
  timestamp?: string;
  meanRecallAt5?: number;
  meanRecallAt10?: number;
  meanMrr?: number;
  meanNdcgAt5?: number;
  meanNdcgAt10?: number;
  p95LatencySeconds?: number;
  totalQueries?: number;
  failedQueries?: number;
}
