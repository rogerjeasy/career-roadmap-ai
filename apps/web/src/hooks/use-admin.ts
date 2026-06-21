"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { adminApi } from "@/lib/api/admin";
import { QUERY_KEYS } from "@/lib/constants";
import { useAuthStore } from "@/store/auth.store";
import { ApiError } from "@/types/api.types";
import type {
  AssignableRole,
  BroadcastInput,
  InboxStatus,
  KbDocType,
  UserListParams,
} from "@/types/admin.types";

/** True when the signed-in user may access the admin area. */
export function useIsAdmin(): boolean {
  const role = useAuthStore((s) => s.user?.role);
  return role === "admin" || role === "superadmin";
}

export function useIsSuperadmin(): boolean {
  return useAuthStore((s) => s.user?.role) === "superadmin";
}

// ── Overview ───────────────────────────────────────────────────────────────────

export function useAdminOverview() {
  return useQuery({
    queryKey: QUERY_KEYS.adminOverview,
    queryFn: adminApi.getOverview,
    staleTime: 60 * 1000,
  });
}

// ── Users ──────────────────────────────────────────────────────────────────────

export function useAdminUsers(params: UserListParams) {
  return useQuery({
    queryKey: QUERY_KEYS.adminUsers(params),
    queryFn: () => adminApi.listUsers(params),
    staleTime: 30 * 1000,
  });
}

export function useAdminUser(uid: string) {
  return useQuery({
    queryKey: QUERY_KEYS.adminUser(uid),
    queryFn: () => adminApi.getUser(uid),
    enabled: Boolean(uid),
  });
}

function errMsg(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

export function useUserAdminActions(uid: string) {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: QUERY_KEYS.adminUser(uid) });
    qc.invalidateQueries({ queryKey: ["admin", "users"] });
    qc.invalidateQueries({ queryKey: QUERY_KEYS.adminOverview });
  };

  const setRole = useMutation({
    mutationFn: (role: AssignableRole) => adminApi.setUserRole(uid, role),
    onSuccess: (u) => {
      invalidate();
      toast.success(`Role updated to ${u.role}.`);
    },
    onError: (err) => toast.error(errMsg(err, "Could not update role")),
  });

  const setStatus = useMutation({
    mutationFn: (isActive: boolean) => adminApi.setUserStatus(uid, isActive),
    onSuccess: (u) => {
      invalidate();
      toast.success(u.isActive ? "Account activated." : "Account deactivated.");
    },
    onError: (err) => toast.error(errMsg(err, "Could not update status")),
  });

  const remove = useMutation({
    mutationFn: () => adminApi.deleteUser(uid),
    onSuccess: () => {
      invalidate();
      toast.success("User deleted.");
    },
    onError: (err) => toast.error(errMsg(err, "Could not delete user")),
  });

  return { setRole, setStatus, remove };
}

// ── Inbox ──────────────────────────────────────────────────────────────────────

export function useAdminFeedback(status?: string) {
  return useQuery({
    queryKey: QUERY_KEYS.adminFeedback(status),
    queryFn: () => adminApi.listFeedback(status),
    staleTime: 30 * 1000,
  });
}

export function useAdminContact(status?: string) {
  return useQuery({
    queryKey: QUERY_KEYS.adminContact(status),
    queryFn: () => adminApi.listContact(status),
    staleTime: 30 * 1000,
  });
}

export function useInboxActions() {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["admin", "feedback"] });
    qc.invalidateQueries({ queryKey: ["admin", "contact"] });
    qc.invalidateQueries({ queryKey: QUERY_KEYS.adminOverview });
  };

  const setFeedbackStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: InboxStatus }) =>
      adminApi.setFeedbackStatus(id, status),
    onSuccess: () => {
      invalidate();
      toast.success("Feedback updated.");
    },
    onError: (err) => toast.error(errMsg(err, "Could not update feedback")),
  });

  const setContactStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: InboxStatus }) =>
      adminApi.setContactStatus(id, status),
    onSuccess: () => {
      invalidate();
      toast.success("Request updated.");
    },
    onError: (err) => toast.error(errMsg(err, "Could not update request")),
  });

  return { setFeedbackStatus, setContactStatus };
}

// ── Newsletter + broadcast ───────────────────────────────────────────────────────

export function useSubscribers() {
  return useQuery({
    queryKey: QUERY_KEYS.adminSubscribers,
    queryFn: adminApi.listSubscribers,
    staleTime: 60 * 1000,
  });
}

export function useBroadcast() {
  return useMutation({
    mutationFn: (input: BroadcastInput) => adminApi.broadcast(input),
    onSuccess: (res) =>
      toast.success(`Sent to ${res.delivered} recipient${res.delivered === 1 ? "" : "s"}.`),
    onError: (err) => toast.error(errMsg(err, "Could not send broadcast")),
  });
}

// ── Audit + system ───────────────────────────────────────────────────────────────

export function useAdminAudit() {
  return useQuery({
    queryKey: QUERY_KEYS.adminAudit,
    queryFn: () => adminApi.listAudit(150),
    staleTime: 30 * 1000,
  });
}

export function useSystemHealth() {
  return useQuery({
    queryKey: QUERY_KEYS.adminHealth,
    queryFn: adminApi.getHealth,
    staleTime: 15 * 1000,
    refetchInterval: 60 * 1000,
  });
}

export function useKbEvalResults() {
  return useQuery({
    queryKey: QUERY_KEYS.adminKbEval,
    queryFn: adminApi.kbEvalResults,
    staleTime: 60 * 1000,
  });
}

export function useKbOps() {
  const qc = useQueryClient();

  const ingest = useMutation({
    mutationFn: (docTypes: KbDocType[]) => adminApi.kbIngest(docTypes),
    onSuccess: (res) => toast.success(res.message),
    onError: (err) => toast.error(errMsg(err, "Could not dispatch ingestion")),
  });

  const runEval = useMutation({
    mutationFn: () => adminApi.kbEvalRun(),
    onSuccess: (res) => {
      toast.success(res.message);
      qc.invalidateQueries({ queryKey: QUERY_KEYS.adminKbEval });
    },
    onError: (err) => toast.error(errMsg(err, "Could not start eval")),
  });

  return { ingest, runEval };
}
