"use client";

import { useState } from "react";
import { useAdminFeedback, useAdminContact, useInboxActions } from "@/hooks/use-admin";
import { formatRelative } from "@/lib/date";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { StatusBadge, FilterSelect } from "@/components/admin/admin-ui";
import type { InboxStatus } from "@/types/admin.types";

type Tab = "feedback" | "contact";

const STATUS_OPTIONS = [
  { value: "new", label: "New" },
  { value: "in_progress", label: "In progress" },
  { value: "resolved", label: "Resolved" },
  { value: "archived", label: "Archived" },
];

const FILTER_OPTIONS = [{ value: "all", label: "All statuses" }, ...STATUS_OPTIONS];

function StatusControl({
  status,
  pending,
  onChange,
}: {
  status: InboxStatus;
  pending: boolean;
  onChange: (s: InboxStatus) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <StatusBadge status={status} />
      <select
        value={status}
        disabled={pending}
        onChange={(e) => onChange(e.target.value as InboxStatus)}
        aria-label="Update status"
        className="rounded-[6px] border border-rule bg-paper px-2 py-1 text-[12px] text-ink outline-none transition-colors duration-150 hover:border-rule-strong disabled:opacity-50"
      >
        {STATUS_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function MessageCard({
  title,
  meta,
  badge,
  message,
  control,
}: {
  title: string;
  meta: string;
  badge?: React.ReactNode;
  message: string;
  control: React.ReactNode;
}) {
  return (
    <li className="rounded-[12px] border border-rule bg-paper p-4 sm:p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[14px] font-medium text-ink">{title}</h3>
            {badge}
          </div>
          <p className="mt-0.5 text-[12px] text-ink-3">{meta}</p>
        </div>
        <div className="shrink-0">{control}</div>
      </div>
      <p className="mt-3 whitespace-pre-wrap break-words text-[13px] leading-relaxed text-ink-2">
        {message}
      </p>
    </li>
  );
}

export default function AdminInboxPage() {
  const [tab, setTab] = useState<Tab>("feedback");
  const [statusFilter, setStatusFilter] = useState("all");

  const feedback = useAdminFeedback(statusFilter);
  const contact = useAdminContact(statusFilter);
  const { setFeedbackStatus, setContactStatus } = useInboxActions();

  const active = tab === "feedback" ? feedback : contact;
  const isEmpty = !active.isLoading && (active.data?.length ?? 0) === 0;

  return (
    <div className="mx-auto max-w-[900px] px-4 pb-16 pt-6 sm:px-6 lg:px-8">
      <PageHeader
        eyebrow="Admin"
        title="Inbox"
        description="User feedback and contact-form enquiries, with status tracking."
      />

      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="inline-flex rounded-[9px] border border-rule bg-bg-2 p-0.5">
          {(["feedback", "contact"] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={cn(
                "rounded-[7px] px-4 py-1.5 text-[13px] font-medium capitalize transition-colors duration-150",
                tab === t ? "bg-paper text-ink shadow-sm" : "text-ink-3 hover:text-ink",
              )}
            >
              {t}
              {t === "feedback" && feedback.data ? ` (${feedback.data.length})` : ""}
              {t === "contact" && contact.data ? ` (${contact.data.length})` : ""}
            </button>
          ))}
        </div>
        <FilterSelect value={statusFilter} onChange={setStatusFilter} options={FILTER_OPTIONS} />
      </div>

      {active.isLoading && <LoadingSpinner fullPage label="Loading inbox…" />}

      {active.isError && (
        <EmptyState title="Couldn't load the inbox" description="Please try again shortly." />
      )}

      {isEmpty && (
        <EmptyState
          title={`No ${tab} messages`}
          description={
            statusFilter === "all"
              ? "Nothing here yet."
              : "No messages match the selected status."
          }
        />
      )}

      {tab === "feedback" && feedback.data && feedback.data.length > 0 && (
        <ul className="space-y-3">
          {feedback.data.map((f) => (
            <MessageCard
              key={f.id}
              title={f.subject || "(no subject)"}
              meta={`${f.userEmail ?? f.userId} · ${f.category}${
                f.rating ? ` · ★ ${f.rating}/5` : ""
              } · ${formatRelative(f.createdAt)}`}
              message={f.message}
              control={
                <StatusControl
                  status={f.status}
                  pending={setFeedbackStatus.isPending}
                  onChange={(status) => setFeedbackStatus.mutate({ id: f.id, status })}
                />
              }
            />
          ))}
        </ul>
      )}

      {tab === "contact" && contact.data && contact.data.length > 0 && (
        <ul className="space-y-3">
          {contact.data.map((c) => (
            <MessageCard
              key={c.id}
              title={c.name || c.email}
              meta={`${c.email}${c.company ? ` · ${c.company}` : ""} · ${c.topic} · ${formatRelative(
                c.createdAt,
              )}`}
              message={c.message}
              control={
                <StatusControl
                  status={c.status}
                  pending={setContactStatus.isPending}
                  onChange={(status) => setContactStatus.mutate({ id: c.id, status })}
                />
              }
            />
          ))}
        </ul>
      )}
    </div>
  );
}
