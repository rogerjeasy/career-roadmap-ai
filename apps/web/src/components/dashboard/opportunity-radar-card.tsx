"use client";

import Link from "next/link";
import { cn } from "@/lib/utils";
import type { OpportunityItem, OpportunityType } from "@/types/dashboard.types";
import type { AlertsResponse } from "@/lib/api/opportunities";
import { ROUTES } from "@/lib/constants";

// ── Icons ─────────────────────────────────────────────────────────────────────

function JobIcon() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" className="h-[15px] w-[15px]" aria-hidden="true"><rect x="2" y="5" width="12" height="9" rx="1.2"/><path d="M5 5V3.5h6V5"/></svg>;
}
function MentorIcon() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" className="h-[15px] w-[15px]" aria-hidden="true"><circle cx="8" cy="5" r="2.5"/><path d="M3 14c0-2.5 2.5-4 5-4s5 1.5 5 4"/></svg>;
}
function EventIcon() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" className="h-[15px] w-[15px]" aria-hidden="true"><rect x="2" y="3" width="12" height="11" rx="1.2"/><path d="M2 6h12M5 1v3M11 1v3"/></svg>;
}
function OpenSourceIcon() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" className="h-[15px] w-[15px]" aria-hidden="true"><circle cx="8" cy="8" r="6"/><path d="M8 4v4l3 2" strokeLinecap="round"/></svg>;
}

const OPP_ICONS: Record<OpportunityType, React.ReactNode> = {
  job:        <JobIcon />,
  mentor:     <MentorIcon />,
  event:      <EventIcon />,
  opensource: <OpenSourceIcon />,
};

const OPP_ICON_STYLES: Record<OpportunityType, string> = {
  job:        "bg-green-soft text-green",
  mentor:     "bg-gold-soft text-gold",
  event:      "bg-terra-soft text-terra-2",
  opensource: "bg-bg-3 text-ink-2",
};

// ── Single opportunity item ───────────────────────────────────────────────────

function OppItem({ opp }: { opp: OpportunityItem }) {
  return (
    <Link
      href={ROUTES.opportunities}
      className={cn(
        "grid cursor-pointer grid-cols-[32px_1fr_auto] items-center gap-3 rounded-[9px] border border-rule p-3 transition-all duration-150",
        "hover:border-rule-strong hover:bg-bg",
      )}
    >
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-[7px]",
          OPP_ICON_STYLES[opp.type],
        )}
      >
        {OPP_ICONS[opp.type]}
      </div>

      <div className="min-w-0">
        <p className="mb-0.5 text-[9.5px] font-semibold uppercase tracking-[0.1em] text-ink-3">
          {opp.tag}
        </p>
        <p className="truncate text-[13px] font-medium leading-[1.3] text-ink">
          {opp.title}
        </p>
        <p className="text-[11px] text-ink-3">
          {opp.meta}
        </p>
      </div>

      <div className="shrink-0 text-right">
        <p className="font-serif text-[17px] font-medium leading-none text-green [font-variant-numeric:tabular-nums]">
          {opp.matchScore}
          <span className="text-[11px] text-ink-3">%</span>
        </p>
        <p className="mt-0.5 text-[9.5px] font-semibold uppercase tracking-[0.08em] text-ink-3">
          {opp.matchLabel}
        </p>
      </div>
    </Link>
  );
}

// ── Parse alerts into opportunity items ───────────────────────────────────────

function parseAlerts(alerts: AlertsResponse): OpportunityItem[] {
  const items: OpportunityItem[] = [];

  // Try to build structured items from target companies
  alerts.targetCompanies.slice(0, 2).forEach((company, i) => {
    items.push({
      id:          `company-${i}`,
      type:        "job",
      tag:         "Job · Top match",
      title:       String(company.name ?? "Position"),
      meta:        alerts.searchQuery ?? "Matched to your profile",
      matchScore:  85 + i * 3,
      matchLabel:  "Match",
    });
  });

  // Fill remaining slots with alert strings (max 4 total)
  alerts.alerts.slice(0, 4 - items.length).forEach((alert, i) => {
    const truncated = alert.length > 60 ? `${alert.slice(0, 57)}…` : alert;
    items.push({
      id:          `alert-${i}`,
      type:        "job",
      tag:         "Opportunity",
      title:       truncated,
      meta:        alerts.searchQuery ?? "",
      matchScore:  alerts.highMatchCount > 0 ? 80 + i : 0,
      matchLabel:  "Match",
    });
  });

  return items.slice(0, 4);
}

// ── Fallback items ────────────────────────────────────────────────────────────

const FALLBACK_OPPS: OpportunityItem[] = [
  {
    id: "1", type: "job",
    tag: "Job · Top match",
    title: "AI Systems Engineer · Anthropic",
    meta: "London · Hybrid",
    matchScore: 92,
    matchLabel: "Match",
  },
  {
    id: "2", type: "mentor",
    tag: "Mentor match",
    title: "Staff ML Engineer mentorship",
    meta: "Available now · 2 slots open",
    matchScore: 88,
    matchLabel: "Fit",
  },
  {
    id: "3", type: "event",
    tag: "Event · This week",
    title: "AI Systems meetup",
    meta: "In-person · community event",
    matchScore: 81,
    matchLabel: "Match",
  },
  {
    id: "4", type: "opensource",
    tag: "Open-source · Good first issue",
    title: "llamaindex · improve RAG eval suite",
    meta: "Python · ~3 h work",
    matchScore: 86,
    matchLabel: "Match",
  },
];

// ── Skeleton ──────────────────────────────────────────────────────────────────

function OppSkeleton() {
  return (
    <div className="animate-pulse grid grid-cols-[32px_1fr_auto] items-center gap-3 rounded-[9px] border border-rule p-3">
      <div className="h-8 w-8 rounded-[7px] bg-bg-3" />
      <div className="space-y-1.5">
        <div className="h-2.5 w-16 rounded bg-bg-2" />
        <div className="h-3.5 w-3/4 rounded bg-bg-3" />
        <div className="h-2.5 w-1/2 rounded bg-bg-2" />
      </div>
      <div className="space-y-1">
        <div className="h-5 w-8 rounded bg-bg-3" />
        <div className="h-2.5 w-10 rounded bg-bg-2" />
      </div>
    </div>
  );
}

// ── Opportunity Radar card ─────────────────────────────────────────────────────

export interface OpportunityRadarCardProps {
  alerts: AlertsResponse | null;
  isLoading: boolean;
}

export function OpportunityRadarCard({ alerts, isLoading }: OpportunityRadarCardProps) {
  const hasAlerts = alerts && (alerts.alerts.length > 0 || alerts.targetCompanies.length > 0);
  const items = hasAlerts ? parseAlerts(alerts) : FALLBACK_OPPS;
  const newCount = alerts?.highMatchCount ?? 5;

  return (
    <div className="rounded-[12px] border border-rule bg-paper p-6">
      {/* Header */}
      <div className="mb-[18px] flex items-start justify-between border-b border-rule pb-3.5">
        <div>
          <h2 className="font-serif text-[17px] font-medium tracking-[-0.01em] text-ink">
            Opportunity radar
          </h2>
          <p className="mt-[3px] text-[11.5px] text-ink-3">
            {newCount} new this week ·{" "}
            <em className="font-serif italic text-terra">matched to your plan</em>
          </p>
        </div>
        <Link
          href={ROUTES.opportunities}
          className="text-[12px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
        >
          All →
        </Link>
      </div>

      <div className="flex flex-col gap-2.5">
        {isLoading
          ? [0,1,2,3].map((i) => <OppSkeleton key={i} />)
          : items.map((opp) => <OppItem key={opp.id} opp={opp} />)
        }
      </div>
    </div>
  );
}
