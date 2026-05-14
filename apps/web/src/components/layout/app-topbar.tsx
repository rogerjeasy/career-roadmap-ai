"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { ROUTES } from "@/lib/constants";

// ── Page label map ─────────────────────────────────────────────────────────────

const PAGE_LABELS: Record<string, string> = {
  "/dashboard":    "Today",
  "/roadmap":      "Roadmap",
  "/coach":        "AI Coach",
  "/market":       "Market Pulse",
  "/opportunities":"Opportunities",
  "/cv-analysis":  "CV & Profile",
  "/networking":   "Network",
  "/progress":     "Progress",
  "/schedule":     "Schedule",
  "/books":        "Books",
  "/settings":     "Settings",
  "/monthly-plan": "Monthly Plan",
};

// ── Icons ─────────────────────────────────────────────────────────────────────

function IconSearch() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" className="h-4 w-4" aria-hidden="true">
      <circle cx="7" cy="7" r="5"/>
      <path d="M11 11l3 3" strokeLinecap="round"/>
    </svg>
  );
}

function IconBell() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" className="h-4 w-4" aria-hidden="true">
      <path d="M8 2v1M3 12h10l-1-2V7a4 4 0 0 0-8 0v3l-1 2zM6 13a2 2 0 0 0 4 0"/>
    </svg>
  );
}

function IconCalendar() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" className="h-4 w-4" aria-hidden="true">
      <rect x="2" y="3" width="12" height="11" rx="1.5"/>
      <path d="M2 6h12M5 1v3M11 1v3"/>
    </svg>
  );
}

function IconPlus() {
  return (
    <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2.2" className="h-3 w-3" aria-hidden="true">
      <path d="M6 1v10M1 6h10" strokeLinecap="round"/>
    </svg>
  );
}

// ── Icon button ───────────────────────────────────────────────────────────────

interface IconBtnProps {
  title: string;
  children: React.ReactNode;
  hasNotification?: boolean;
  onClick?: () => void;
}

function IconBtn({ title, children, hasNotification = false, onClick }: IconBtnProps) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className="relative flex h-[34px] w-[34px] items-center justify-center rounded-[7px] text-ink-2 transition-all duration-[120ms] hover:bg-bg-2 hover:text-ink"
    >
      {children}
      {hasNotification && (
        <span className="absolute right-[7px] top-[7px] h-[7px] w-[7px] rounded-full bg-terra ring-2 ring-bg" />
      )}
    </button>
  );
}

// ── Topbar ────────────────────────────────────────────────────────────────────

export interface AppTopbarProps {
  className?: string;
}

export function AppTopbar({ className }: AppTopbarProps) {
  const pathname = usePathname();
  const segment = "/" + pathname.split("/")[1];
  const pageLabel = PAGE_LABELS[segment] ?? "Page";

  const today = new Date().toLocaleDateString("en-US", {
    weekday: "long",
    month:   "long",
    day:     "numeric",
    year:    "numeric",
  });

  return (
    <header
      className={cn(
        "sticky top-0 z-40 flex h-[60px] shrink-0 items-center justify-between bg-bg px-7 border-b border-rule",
        className,
      )}
    >
      {/* Breadcrumbs + date */}
      <div className="flex items-center gap-3 text-[13px] min-w-0">
        <Link href={ROUTES.dashboard} className="text-ink-3 hover:text-ink transition-colors duration-150 shrink-0">
          Home
        </Link>
        <span className="text-rule-strong shrink-0" aria-hidden="true">/</span>
        <span className="font-semibold text-ink shrink-0">{pageLabel}</span>
        <span className="ml-[18px] hidden border-l border-rule pl-[18px] font-serif italic text-ink-2 sm:block shrink-0">
          {today}
        </span>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 shrink-0">
        <IconBtn title="Search">
          <IconSearch />
        </IconBtn>
        <IconBtn title="Notifications" hasNotification>
          <IconBell />
        </IconBtn>
        <IconBtn title="Calendar">
          <IconCalendar />
        </IconBtn>
        <button
          type="button"
          className="ml-1 inline-flex items-center gap-[7px] rounded-[7px] bg-ink px-[14px] py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2"
        >
          <IconPlus />
          Log activity
        </button>
      </div>
    </header>
  );
}
