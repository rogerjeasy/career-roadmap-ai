"use client";

import { useAdminAudit } from "@/hooks/use-admin";
import { formatDateTime } from "@/lib/date";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { SectionCard } from "@/components/admin/admin-ui";

const ACTION_LABELS: Record<string, string> = {
  "user.role_changed": "Role changed",
  "user.status_changed": "Status changed",
  "user.deleted": "User deleted",
  "feedback.status_changed": "Feedback updated",
  "contact.status_changed": "Contact updated",
  "broadcast.sent": "Broadcast sent",
};

export default function AdminAuditPage() {
  const { data, isLoading, isError } = useAdminAudit();

  return (
    <div className="mx-auto max-w-[900px] px-4 pb-16 pt-6 sm:px-6 lg:px-8">
      <PageHeader
        eyebrow="Admin"
        title="Audit log"
        description="A record of every administrative action, newest first."
      />

      {isLoading && <LoadingSpinner fullPage label="Loading audit log…" />}

      {isError && (
        <EmptyState title="Couldn't load the audit log" description="Please try again shortly." />
      )}

      {data && data.length === 0 && !isLoading && (
        <EmptyState
          title="No actions yet"
          description="Administrative actions (role changes, broadcasts, deletions) will be recorded here."
        />
      )}

      {data && data.length > 0 && (
        <SectionCard>
          <ul className="divide-y divide-rule">
            {data.map((a) => (
              <li key={a.id} className="px-4 py-3.5 sm:px-5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="flex items-center gap-2">
                    <span className="rounded-[5px] bg-bg-3 px-2 py-0.5 text-[11px] font-semibold text-ink-2">
                      {ACTION_LABELS[a.action] ?? a.action}
                    </span>
                    {a.detail && (
                      <span className="text-[12.5px] text-ink-2">{a.detail}</span>
                    )}
                  </span>
                  <span className="text-[11.5px] text-ink-3">{formatDateTime(a.createdAt)}</span>
                </div>
                <p className="mt-1.5 text-[12px] text-ink-3">
                  by {a.actorEmail ?? a.actorUid}
                  {a.targetLabel ? ` · target: ${a.targetLabel}` : a.targetUid ? ` · target: ${a.targetUid}` : ""}
                </p>
              </li>
            ))}
          </ul>
        </SectionCard>
      )}
    </div>
  );
}
