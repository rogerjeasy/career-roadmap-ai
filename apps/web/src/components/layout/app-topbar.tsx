"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { ROUTES, QUERY_KEYS } from "@/lib/constants";
import { notificationsApi } from "@/lib/api/notifications";
import { formatRelative } from "@/lib/date";
import { NotificationBell, type NotificationItem } from "@/components/shared/notification-bell";
import { LogActivityDialog } from "@/components/schedule/log-activity-dialog";
import { useUIStore } from "@/store/ui.store";
import { Menu } from "lucide-react";

// ── Page label map ─────────────────────────────────────────────────────────────

const PAGE_LABELS: Record<string, string> = {
  "/dashboard":    "Today",
  "/analytics":    "Analytics",
  "/roadmap":      "Roadmap",
  "/roadmap-options": "Roadmap Strategies",
  "/skill-graph":  "Skill Graph",
  "/coach":        "AI Coach",
  "/market":       "Market Pulse",
  "/opportunities":"Opportunities",
  "/negotiation":  "Negotiation Coach",
  "/interview":    "Interview Prep",
  "/newsletter":   "Newsletter",
  "/cv-analysis":  "CV & Profile",
  "/applications": "Applications",
  "/evidence":     "Evidence Vault",
  "/credentials":  "Skill Credentials",
  "/learning":     "Learning ROI",
  "/open-source":  "Open-Source Finder",
  "/storytelling": "Storytelling Studio",
  "/cohorts":      "Accountability Cohorts",
  "/mentorship":   "Mentorship",
  "/outreach":     "Outreach Drafts",
  "/portfolio":    "Portfolio",
  "/networking":   "Network",
  "/progress":     "Progress",
  "/schedule":     "Schedule",
  "/books":        "Books",
  "/settings":     "Settings",
  "/monthly-plan": "Monthly Plan",
  "/help":         "Help & feedback",
  "/discovery":    "Discover Paths",
  "/localisation": "Localisation",
  "/autopilot":    "Autopilot",
  "/wellness":     "Wellness Monitor",
  "/career-twin":  "Career Twin",
  "/developer":    "Developer API",
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

// ── Live notification bell ────────────────────────────────────────────────────

function LiveBell() {
  const queryClient = useQueryClient();

  const { data } = useQuery({
    queryKey: QUERY_KEYS.notifications,
    queryFn: () => notificationsApi.list(20),
    staleTime: 60 * 1000,
    refetchInterval: 2 * 60 * 1000,
  });

  const markAll = useMutation({
    mutationFn: notificationsApi.markAllRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: QUERY_KEYS.notifications }),
  });

  const items: NotificationItem[] = (data?.items ?? []).map((n) => ({
    id: n.id,
    title: n.title,
    body: n.body || undefined,
    timeLabel: formatRelative(n.createdAt),
    read: n.read,
    tone: n.tone,
  }));

  return <NotificationBell notifications={items} onMarkAllRead={() => markAll.mutate()} />;
}

// ── Topbar ────────────────────────────────────────────────────────────────────

export interface AppTopbarProps {
  className?: string;
}

export function AppTopbar({ className }: AppTopbarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const segment = "/" + pathname.split("/")[1];
  const pageLabel = PAGE_LABELS[segment] ?? "Page";
  const [logOpen, setLogOpen] = useState(false);
  const setCommandOpen = useUIStore((s) => s.setCommandOpen);
  const setMobileNavOpen = useUIStore((s) => s.setMobileNavOpen);

  const today = new Date().toLocaleDateString("en-US", {
    weekday: "long",
    month:   "long",
    day:     "numeric",
    year:    "numeric",
  });

  return (
    <header
      className={cn(
        "sticky top-0 z-40 flex h-[60px] shrink-0 items-center justify-between gap-2 bg-bg px-4 sm:px-6 lg:px-7 border-b border-rule",
        className,
      )}
    >
      {/* Hamburger (mobile) + breadcrumbs + date */}
      <div className="flex items-center gap-2 text-[13px] min-w-0">
        <button
          type="button"
          onClick={() => setMobileNavOpen(true)}
          aria-label="Open navigation menu"
          className="-ml-1 flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-[7px] text-ink-2 transition-colors duration-150 hover:bg-bg-2 hover:text-ink md:hidden"
        >
          <Menu className="h-5 w-5" aria-hidden="true" />
        </button>
        <Link
          href={ROUTES.dashboard}
          className="hidden text-ink-3 hover:text-ink transition-colors duration-150 shrink-0 sm:inline"
        >
          Home
        </Link>
        <span className="hidden text-rule-strong shrink-0 sm:inline" aria-hidden="true">/</span>
        <span className="font-semibold text-ink truncate">{pageLabel}</span>
        <span className="ml-[18px] hidden border-l border-rule pl-[18px] font-serif italic text-ink-2 lg:block shrink-0">
          {today}
        </span>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1 sm:gap-2 shrink-0">
        <IconBtn title="Search (⌘K)" onClick={() => setCommandOpen(true)}>
          <IconSearch />
        </IconBtn>
        <LiveBell />
        <IconBtn title="Schedule" onClick={() => router.push(ROUTES.schedule)}>
          <IconCalendar />
        </IconBtn>
        <button
          type="button"
          onClick={() => setLogOpen(true)}
          aria-label="Log activity"
          className="ml-0.5 inline-flex items-center gap-[7px] rounded-[7px] bg-ink px-2.5 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 sm:ml-1 sm:px-[14px]"
        >
          <IconPlus />
          <span className="hidden sm:inline">Log activity</span>
        </button>
      </div>

      <LogActivityDialog open={logOpen} onOpenChange={setLogOpen} />
    </header>
  );
}
