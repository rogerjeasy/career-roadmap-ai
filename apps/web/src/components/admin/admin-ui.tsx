"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import type { InboxStatus, HealthStatus } from "@/types/admin.types";
import type { UserRole } from "@/types/api.types";

// ── Stat card ────────────────────────────────────────────────────────────────

export interface StatCardProps {
  label: string;
  value: string | number;
  sublabel?: string;
  icon?: ReactNode;
  accent?: "ink" | "green" | "terra";
}

const ACCENTS: Record<NonNullable<StatCardProps["accent"]>, string> = {
  ink: "text-ink",
  green: "text-green-2",
  terra: "text-terra",
};

export function StatCard({ label, value, sublabel, icon, accent = "ink" }: StatCardProps) {
  return (
    <div className="flex flex-col gap-2 rounded-[12px] border border-rule bg-paper p-4 sm:p-5">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11.5px] font-semibold uppercase tracking-[0.1em] text-ink-3">
          {label}
        </p>
        {icon && <span className="text-ink-3">{icon}</span>}
      </div>
      <p className={cn("font-serif text-[26px] font-medium leading-none tracking-[-0.01em]", ACCENTS[accent])}>
        {value}
      </p>
      {sublabel && <p className="text-[12px] leading-snug text-ink-3">{sublabel}</p>}
    </div>
  );
}

// ── Role badge ───────────────────────────────────────────────────────────────

const ROLE_STYLES: Record<UserRole, string> = {
  user: "bg-bg-3 text-ink-2",
  admin: "bg-green-faint text-green-2",
  superadmin: "bg-terra/12 text-terra",
};

export function RoleBadge({ role }: { role: UserRole }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-[5px] px-2 py-0.5 text-[11px] font-semibold capitalize",
        ROLE_STYLES[role] ?? ROLE_STYLES.user,
      )}
    >
      {role}
    </span>
  );
}

// ── Active / inactive badge ──────────────────────────────────────────────────

export function ActiveBadge({ active }: { active: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-[5px] px-2 py-0.5 text-[11px] font-semibold",
        active ? "bg-green-faint text-green-2" : "bg-bg-3 text-ink-3",
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", active ? "bg-green" : "bg-ink-3")} />
      {active ? "Active" : "Disabled"}
    </span>
  );
}

// ── Inbox status badge ───────────────────────────────────────────────────────

const STATUS_STYLES: Record<InboxStatus, string> = {
  new: "bg-terra/12 text-terra",
  in_progress: "bg-amber-100 text-amber-700",
  resolved: "bg-green-faint text-green-2",
  archived: "bg-bg-3 text-ink-3",
};

const STATUS_LABELS: Record<InboxStatus, string> = {
  new: "New",
  in_progress: "In progress",
  resolved: "Resolved",
  archived: "Archived",
};

export function StatusBadge({ status }: { status: InboxStatus }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-[5px] px-2 py-0.5 text-[11px] font-semibold",
        STATUS_STYLES[status] ?? STATUS_STYLES.new,
      )}
    >
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

// ── Health dot ───────────────────────────────────────────────────────────────

const HEALTH_DOT: Record<HealthStatus, string> = {
  ok: "bg-green",
  degraded: "bg-amber-500",
  down: "bg-destructive",
  disabled: "bg-ink-3",
};

const HEALTH_LABEL: Record<HealthStatus, string> = {
  ok: "Operational",
  degraded: "Degraded",
  down: "Down",
  disabled: "Not configured",
};

export function HealthBadge({ status }: { status: HealthStatus }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[12.5px] font-medium text-ink-2">
      <span className={cn("h-2 w-2 rounded-full", HEALTH_DOT[status])} />
      {HEALTH_LABEL[status]}
    </span>
  );
}

// ── Filter select (native, fully responsive) ─────────────────────────────────

export interface FilterSelectProps {
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  label?: string;
  className?: string;
}

export function FilterSelect({ value, onChange, options, label, className }: FilterSelectProps) {
  return (
    <label className={cn("inline-flex items-center gap-2", className)}>
      {label && <span className="text-[12px] font-medium text-ink-3">{label}</span>}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-[7px] border border-rule bg-paper px-2.5 py-1.5 text-[13px] text-ink outline-none transition-colors duration-150 hover:border-rule-strong focus:border-rule-strong"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

// ── Section card ─────────────────────────────────────────────────────────────

export function SectionCard({
  title,
  description,
  action,
  children,
  className,
}: {
  title?: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-[12px] border border-rule bg-paper", className)}>
      {(title || action) && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-rule px-4 py-3.5 sm:px-5">
          <div className="min-w-0">
            {title && (
              <h2 className="font-serif text-[15px] font-medium tracking-[-0.01em] text-ink">
                {title}
              </h2>
            )}
            {description && <p className="mt-0.5 text-[12.5px] text-ink-3">{description}</p>}
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </div>
      )}
      {children}
    </section>
  );
}
