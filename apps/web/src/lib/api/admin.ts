import type {
  AdminAuditItem,
  AdminContactItem,
  AdminFeedbackItem,
  AdminOverview,
  AdminUserDetail,
  AdminUserListResponse,
  AssignableRole,
  BroadcastInput,
  BroadcastResult,
  InboxStatus,
  KbDispatchResponse,
  KbDocType,
  KbEvalResults,
  KbTaskStatus,
  NewsletterSubscriberItem,
  SystemHealth,
  UserListParams,
} from "@/types/admin.types";
import { apiClient } from "./client";

const BASE = "/api/v1/admin";

export const adminApi = {
  // ── Overview ───────────────────────────────────────────────────────────────
  async getOverview(): Promise<AdminOverview> {
    const { data } = await apiClient.get<AdminOverview>(`${BASE}/overview`);
    return data;
  },

  // ── Users ──────────────────────────────────────────────────────────────────
  async listUsers(params: UserListParams = {}): Promise<AdminUserListResponse> {
    const { data } = await apiClient.get<AdminUserListResponse>(`${BASE}/users`, {
      params: {
        page: params.page,
        pageSize: params.pageSize,
        search: params.search || undefined,
        role: params.role && params.role !== "all" ? params.role : undefined,
        status: params.status && params.status !== "all" ? params.status : undefined,
      },
    });
    return data;
  },

  async getUser(uid: string): Promise<AdminUserDetail> {
    const { data } = await apiClient.get<AdminUserDetail>(`${BASE}/users/${uid}`);
    return data;
  },

  async setUserRole(uid: string, role: AssignableRole): Promise<AdminUserDetail> {
    const { data } = await apiClient.patch<AdminUserDetail>(`${BASE}/users/${uid}/role`, {
      role,
    });
    return data;
  },

  async setUserStatus(uid: string, isActive: boolean): Promise<AdminUserDetail> {
    const { data } = await apiClient.patch<AdminUserDetail>(`${BASE}/users/${uid}/status`, {
      isActive,
    });
    return data;
  },

  async deleteUser(uid: string): Promise<void> {
    await apiClient.delete(`${BASE}/users/${uid}`);
  },

  // ── Inbox ──────────────────────────────────────────────────────────────────
  async listFeedback(status?: string): Promise<AdminFeedbackItem[]> {
    const { data } = await apiClient.get<AdminFeedbackItem[]>(`${BASE}/feedback`, {
      params: { status: status && status !== "all" ? status : undefined },
    });
    return data;
  },

  async setFeedbackStatus(id: string, status: InboxStatus): Promise<AdminFeedbackItem> {
    const { data } = await apiClient.patch<AdminFeedbackItem>(`${BASE}/feedback/${id}/status`, {
      status,
    });
    return data;
  },

  async listContact(status?: string): Promise<AdminContactItem[]> {
    const { data } = await apiClient.get<AdminContactItem[]>(`${BASE}/contact`, {
      params: { status: status && status !== "all" ? status : undefined },
    });
    return data;
  },

  async setContactStatus(id: string, status: InboxStatus): Promise<AdminContactItem> {
    const { data } = await apiClient.patch<AdminContactItem>(`${BASE}/contact/${id}/status`, {
      status,
    });
    return data;
  },

  // ── Newsletter + broadcast ───────────────────────────────────────────────────
  async listSubscribers(): Promise<NewsletterSubscriberItem[]> {
    const { data } = await apiClient.get<NewsletterSubscriberItem[]>(
      `${BASE}/newsletter/subscribers`,
    );
    return data;
  },

  async broadcast(input: BroadcastInput): Promise<BroadcastResult> {
    const { data } = await apiClient.post<BroadcastResult>(`${BASE}/broadcast`, input);
    return data;
  },

  // ── Audit ────────────────────────────────────────────────────────────────────
  async listAudit(limit = 100): Promise<AdminAuditItem[]> {
    const { data } = await apiClient.get<AdminAuditItem[]>(`${BASE}/audit`, {
      params: { limit },
    });
    return data;
  },

  // ── System ────────────────────────────────────────────────────────────────────
  async getHealth(): Promise<SystemHealth> {
    const { data } = await apiClient.get<SystemHealth>(`${BASE}/system/health`);
    return data;
  },

  async kbIngest(docTypes: KbDocType[]): Promise<KbDispatchResponse> {
    const { data } = await apiClient.post<KbDispatchResponse>(`${BASE}/system/kb/ingest`, {
      docTypes,
    });
    return data;
  },

  async kbTaskStatus(taskId: string): Promise<KbTaskStatus> {
    const { data } = await apiClient.get<KbTaskStatus>(`${BASE}/system/kb/status/${taskId}`);
    return data;
  },

  async kbEvalRun(): Promise<{ taskId: string; queriesCount: number; message: string }> {
    const { data } = await apiClient.post(`${BASE}/system/kb/eval/run`);
    return data;
  },

  async kbEvalResults(): Promise<KbEvalResults> {
    const { data } = await apiClient.get<KbEvalResults>(`${BASE}/system/kb/eval/results`);
    return data;
  },
};
