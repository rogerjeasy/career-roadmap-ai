"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Map, MessageSquare, Bell } from "lucide-react";
import {
  useAdminUser,
  useUserAdminActions,
  useIsSuperadmin,
} from "@/hooks/use-admin";
import { useAuthStore } from "@/store/auth.store";
import { ROUTES } from "@/lib/constants";
import { formatDateTime, formatRelative } from "@/lib/date";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import {
  RoleBadge,
  ActiveBadge,
  SectionCard,
  FilterSelect,
} from "@/components/admin/admin-ui";
import type { AssignableRole } from "@/types/admin.types";

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 px-4 py-3 sm:px-5">
      <span className="shrink-0 text-[12.5px] text-ink-3">{label}</span>
      <span className="min-w-0 break-words text-right text-[13px] font-medium text-ink">
        {value}
      </span>
    </div>
  );
}

function MiniStat({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <div className="flex items-center gap-3 rounded-[10px] border border-rule bg-paper p-3.5">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[8px] bg-bg-2 text-ink-2">
        {icon}
      </span>
      <div className="min-w-0">
        <p className="font-serif text-[18px] font-medium leading-none text-ink">{value}</p>
        <p className="mt-1 text-[12px] text-ink-3">{label}</p>
      </div>
    </div>
  );
}

export default function AdminUserDetailPage() {
  const params = useParams<{ uid: string }>();
  const uid = params.uid;
  const router = useRouter();

  const { data: user, isLoading, isError } = useAdminUser(uid);
  const { setRole, setStatus, remove } = useUserAdminActions(uid);
  const isSuperadmin = useIsSuperadmin();
  const selfUid = useAuthStore((s) => s.user?.firebaseUid);
  const isSelf = selfUid === uid;

  const [selectedRole, setSelectedRole] = useState<AssignableRole | "">("");
  const [confirmRole, setConfirmRole] = useState(false);
  const [confirmStatus, setConfirmStatus] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const backLink = (
    <Link
      href={ROUTES.adminUsers}
      className="mb-4 inline-flex items-center gap-1.5 text-[12.5px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
    >
      <ArrowLeft className="h-3.5 w-3.5" />
      Users
    </Link>
  );

  if (isLoading) {
    return (
      <div className="mx-auto max-w-[860px] px-4 pb-16 pt-6 sm:px-6 lg:px-8">
        {backLink}
        <LoadingSpinner fullPage label="Loading user…" />
      </div>
    );
  }

  if (isError || !user) {
    return (
      <div className="mx-auto max-w-[860px] px-4 pb-16 pt-6 sm:px-6 lg:px-8">
        {backLink}
        <EmptyState
          title="User not found"
          description="This account may have been deleted, or you no longer have access."
          action={
            <Link
              href={ROUTES.adminUsers}
              className="inline-flex items-center rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2"
            >
              Back to users
            </Link>
          }
        />
      </div>
    );
  }

  const currentRole = user.role;
  const effectiveSelected = selectedRole || currentRole;
  const roleChanged = effectiveSelected !== currentRole;
  // Only a superadmin may assign/modify administrator roles.
  const roleLocked =
    isSelf ||
    (!isSuperadmin && (currentRole !== "user" || effectiveSelected !== "user"));
  const initials = (user.displayName || user.email || "U")
    .split(" ")
    .map((p) => p[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="mx-auto max-w-[860px] px-4 pb-16 pt-6 sm:px-6 lg:px-8">
      {backLink}
      <PageHeader
        eyebrow="User"
        title={user.displayName || user.email}
        description={user.email}
      />

      {isSelf && (
        <div className="mb-5 rounded-[10px] border border-amber-200 bg-amber-50 px-4 py-3 text-[12.5px] text-amber-800">
          This is your own account — role, status and deletion controls are disabled here.
        </div>
      )}

      <div className="space-y-6">
        {/* Identity + activity */}
        <div className="grid gap-3 sm:grid-cols-3">
          <MiniStat icon={<Map className="h-4 w-4" />} label="Roadmaps" value={user.roadmapCount} />
          <MiniStat
            icon={<MessageSquare className="h-4 w-4" />}
            label="Feedback"
            value={user.feedbackCount}
          />
          <MiniStat
            icon={<Bell className="h-4 w-4" />}
            label="Notifications"
            value={user.notificationCount}
          />
        </div>

        <SectionCard
          title="Account"
          action={
            <span className="flex items-center gap-2">
              <RoleBadge role={user.role} />
              <ActiveBadge active={user.isActive} />
            </span>
          }
        >
          <div className="flex items-center gap-3 px-4 py-4 sm:px-5">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[10px] bg-green font-serif text-[15px] font-medium text-white">
              {initials}
            </span>
            <div className="min-w-0">
              <p className="truncate text-[14px] font-medium text-ink">
                {user.displayName || "—"}
              </p>
              <p className="truncate text-[12.5px] text-ink-3">{user.email}</p>
            </div>
          </div>
          <div className="divide-y divide-rule border-t border-rule">
            <InfoRow label="UID" value={<span className="font-mono text-[12px]">{user.uid}</span>} />
            <InfoRow label="Provider" value={<span className="capitalize">{user.provider.replace(".com", "")}</span>} />
            <InfoRow
              label="Email verified"
              value={user.emailVerified ? "Yes" : "No"}
            />
            <InfoRow label="Joined" value={formatDateTime(user.createdAt)} />
            <InfoRow label="Last updated" value={formatRelative(user.updatedAt)} />
            <InfoRow
              label="Last roadmap"
              value={user.lastRoadmapAt ? formatRelative(user.lastRoadmapAt) : "—"}
            />
          </div>
        </SectionCard>

        {/* Role management */}
        <SectionCard title="Role" description="Controls access to the admin console.">
          <div className="flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
            <FilterSelect
              label="Assign role"
              value={effectiveSelected}
              onChange={(v) => setSelectedRole(v as AssignableRole)}
              options={[
                { value: "user", label: "User" },
                { value: "admin", label: "Admin" },
                { value: "superadmin", label: "Superadmin" },
              ]}
            />
            <button
              type="button"
              disabled={!roleChanged || roleLocked || setRole.isPending}
              onClick={() => setConfirmRole(true)}
              className="inline-flex items-center justify-center rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-40"
            >
              Update role
            </button>
          </div>
          {!isSuperadmin && (
            <p className="border-t border-rule px-4 py-2.5 text-[12px] text-ink-3 sm:px-5">
              Only a superadmin can grant or modify administrator roles.
            </p>
          )}
        </SectionCard>

        {/* Status + danger zone */}
        <SectionCard title="Status">
          <div className="flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
            <p className="text-[13px] text-ink-2">
              {user.isActive
                ? "This account is active and can sign in."
                : "This account is disabled and cannot sign in."}
            </p>
            <button
              type="button"
              disabled={isSelf || setStatus.isPending}
              onClick={() => setConfirmStatus(true)}
              className="inline-flex items-center justify-center rounded-[7px] border border-rule-strong bg-paper px-4 py-2 text-[13px] font-medium text-ink-2 transition-colors duration-150 hover:bg-bg-2 disabled:opacity-40"
            >
              {user.isActive ? "Deactivate" : "Activate"}
            </button>
          </div>
        </SectionCard>

        <section className="rounded-[12px] border border-destructive/30 bg-destructive/5">
          <div className="flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
            <div className="min-w-0">
              <h2 className="font-serif text-[15px] font-medium text-ink">Delete account</h2>
              <p className="mt-0.5 text-[12.5px] text-ink-3">
                Permanently removes the Firebase user and profile. This cannot be undone.
              </p>
            </div>
            <button
              type="button"
              disabled={isSelf || remove.isPending}
              onClick={() => setConfirmDelete(true)}
              className="inline-flex shrink-0 items-center justify-center rounded-[7px] bg-destructive px-4 py-2 text-[13px] font-medium text-white transition-colors duration-150 hover:bg-destructive/90 disabled:opacity-40"
            >
              Delete user
            </button>
          </div>
        </section>
      </div>

      {/* Confirm dialogs */}
      <ConfirmDialog
        open={confirmRole}
        onOpenChange={setConfirmRole}
        title="Change role?"
        description={`Set this user's role to "${effectiveSelected}". They will need to sign in again for it to take effect.`}
        confirmLabel="Update role"
        pending={setRole.isPending}
        onConfirm={() =>
          setRole.mutate(effectiveSelected as AssignableRole, {
            onSuccess: () => setConfirmRole(false),
          })
        }
      />
      <ConfirmDialog
        open={confirmStatus}
        onOpenChange={setConfirmStatus}
        title={user.isActive ? "Deactivate account?" : "Activate account?"}
        description={
          user.isActive
            ? "The user will be signed out and blocked from signing in until reactivated."
            : "The user will be able to sign in again."
        }
        confirmLabel={user.isActive ? "Deactivate" : "Activate"}
        destructive={user.isActive}
        pending={setStatus.isPending}
        onConfirm={() =>
          setStatus.mutate(!user.isActive, { onSuccess: () => setConfirmStatus(false) })
        }
      />
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete this user?"
        description="This permanently deletes the account and cannot be undone."
        confirmLabel="Delete permanently"
        destructive
        pending={remove.isPending}
        onConfirm={() =>
          remove.mutate(undefined, {
            onSuccess: () => {
              setConfirmDelete(false);
              router.push(ROUTES.adminUsers);
            },
          })
        }
      />
    </div>
  );
}
