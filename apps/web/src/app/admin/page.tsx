"use client";

import type { CSSProperties } from "react";
import Link from "next/link";
import { Users, UserCheck, Map, Inbox, Mail, ShieldCheck } from "lucide-react";
import { useAdminOverview } from "@/hooks/use-admin";
import { ROUTES } from "@/lib/constants";
import { formatRelative } from "@/lib/date";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import {
  StatCard,
  RoleBadge,
  SectionCard,
} from "@/components/admin/admin-ui";
import type { TimeseriesPoint } from "@/types/admin.types";

function SignupsChart({ data }: { data: TimeseriesPoint[] }) {
  const max = Math.max(1, ...data.map((d) => d.count));
  return (
    <div className="flex h-[140px] items-end gap-1.5 px-4 pb-4 pt-2 sm:gap-2 sm:px-5">
      {data.map((d) => {
        const pct = Math.round((d.count / max) * 100);
        return (
          <div key={d.date} className="group flex min-w-0 flex-1 flex-col items-center gap-1.5">
            <div className="flex w-full flex-1 items-end">
              <div
                // Dynamic bar height via CSS custom property consumed by a
                // Tailwind arbitrary value (the sanctioned no-inline-CSS path).
                style={{ "--bar-h": `${Math.max(pct, 3)}%` } as CSSProperties}
                className="h-[var(--bar-h)] w-full rounded-t-[3px] bg-green/70 transition-colors duration-150 group-hover:bg-green"
                title={`${d.count} signup${d.count === 1 ? "" : "s"} on ${d.date}`}
              />
            </div>
            <span className="text-[9px] text-ink-3">{d.date.slice(8)}</span>
          </div>
        );
      })}
    </div>
  );
}

function Breakdown({ data }: { data: Record<string, number> }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((sum, [, n]) => sum + n, 0) || 1;
  if (entries.length === 0) {
    return <p className="px-5 py-4 text-[13px] text-ink-3">No data yet.</p>;
  }
  return (
    <ul className="divide-y divide-rule">
      {entries.map(([key, count]) => (
        <li key={key} className="flex items-center justify-between gap-3 px-4 py-2.5 sm:px-5">
          <span className="truncate text-[13px] capitalize text-ink-2">{key || "unknown"}</span>
          <span className="flex items-center gap-2 text-[12.5px] text-ink-3">
            <span className="tabular-nums">{count}</span>
            <span className="text-ink-3/70">·</span>
            <span className="tabular-nums">{Math.round((count / total) * 100)}%</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

export default function AdminOverviewPage() {
  const { data, isLoading, isError } = useAdminOverview();

  return (
    <div className="mx-auto max-w-[1100px] px-4 pb-16 pt-6 sm:px-6 lg:px-8">
      <PageHeader
        eyebrow="Admin"
        title="Overview"
        description="Live platform metrics aggregated from Firestore. Updated each visit."
      />

      {isLoading && <LoadingSpinner fullPage label="Loading metrics…" />}

      {isError && (
        <EmptyState
          title="Couldn't load metrics"
          description="The admin overview failed to load. Check that the API is reachable and you still have admin access."
        />
      )}

      {data && (
        <div className="space-y-6">
          {/* Stat grid */}
          <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
            <StatCard
              label="Total users"
              value={data.totalUsers}
              sublabel={`${data.newUsers7d} new this week`}
              icon={<Users className="h-4 w-4" />}
            />
            <StatCard
              label="Active"
              value={data.activeUsers}
              sublabel={`${data.verifiedUsers} email-verified`}
              accent="green"
              icon={<UserCheck className="h-4 w-4" />}
            />
            <StatCard
              label="Roadmaps"
              value={data.totalRoadmaps}
              sublabel={`${data.roadmaps7d} this week`}
              icon={<Map className="h-4 w-4" />}
            />
            <StatCard
              label="Admins"
              value={data.adminUsers}
              sublabel="With console access"
              accent="terra"
              icon={<ShieldCheck className="h-4 w-4" />}
            />
            <StatCard
              label="Open feedback"
              value={data.openFeedback}
              sublabel={`${data.totalFeedback} total`}
              icon={<Inbox className="h-4 w-4" />}
            />
            <StatCard
              label="Open contact"
              value={data.openContactRequests}
              sublabel={`${data.totalContactRequests} total`}
              icon={<Inbox className="h-4 w-4" />}
            />
            <StatCard
              label="Subscribers"
              value={data.newsletterSubscribers}
              sublabel="Newsletter"
              icon={<Mail className="h-4 w-4" />}
            />
            <StatCard
              label="New (30d)"
              value={data.newUsers30d}
              sublabel="Sign-ups, last 30 days"
              accent="green"
            />
          </div>

          {/* Signups chart */}
          <SectionCard title="Sign-ups" description="New accounts over the last 14 days">
            <SignupsChart data={data.signupsLast14Days} />
          </SectionCard>

          {/* Breakdowns + recent users */}
          <div className="grid gap-6 lg:grid-cols-2">
            <SectionCard title="By role">
              <Breakdown data={data.roleBreakdown} />
            </SectionCard>
            <SectionCard title="By sign-in provider">
              <Breakdown data={data.providerBreakdown} />
            </SectionCard>
          </div>

          <SectionCard
            title="Recent sign-ups"
            action={
              <Link
                href={ROUTES.adminUsers}
                className="text-[12.5px] font-medium text-green-2 hover:underline"
              >
                View all users →
              </Link>
            }
          >
            {data.recentUsers.length === 0 ? (
              <p className="px-5 py-4 text-[13px] text-ink-3">No users yet.</p>
            ) : (
              <ul className="divide-y divide-rule">
                {data.recentUsers.map((u) => (
                  <li key={u.uid}>
                    <Link
                      href={ROUTES.adminUser(u.uid)}
                      className="flex items-center justify-between gap-3 px-4 py-3 transition-colors duration-150 hover:bg-bg-2 sm:px-5"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-[13.5px] font-medium text-ink">
                          {u.displayName || u.email}
                        </p>
                        <p className="truncate text-[12px] text-ink-3">{u.email}</p>
                      </div>
                      <div className="flex shrink-0 items-center gap-3">
                        <RoleBadge role={u.role} />
                        <span className="hidden text-[12px] text-ink-3 sm:block">
                          {formatRelative(u.createdAt)}
                        </span>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </SectionCard>
        </div>
      )}
    </div>
  );
}
