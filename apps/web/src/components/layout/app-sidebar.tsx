"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ChevronUp, CreditCard, HelpCircle, LogOut, Settings } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth.store";
import { useUIStore } from "@/store/ui.store";
import { useAuth } from "@/hooks/use-auth";
import { opportunitiesApi } from "@/lib/api/opportunities";
import { billingApi } from "@/lib/api/billing";
import { autopilotApi } from "@/lib/api/autopilot";
import { QUERY_KEYS, ROUTES } from "@/lib/constants";
import { useT } from "@/lib/i18n";
import { LanguageSwitcher } from "@/components/layout/language-switcher";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

// ── Logo mark ─────────────────────────────────────────────────────────────────

function LogoMark() {
  return (
    <svg viewBox="0 0 28 28" fill="none" aria-hidden="true" className="h-6 w-6 shrink-0">
      <path d="M3 22 C 8 22, 8 6, 14 6 S 20 22, 25 22" stroke="#15140F" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="3"  cy="22" r="2.2" fill="#C95A3D" />
      <circle cx="14" cy="6"  r="2.2" fill="#134E3A" />
      <circle cx="25" cy="22" r="2.2" fill="#15140F" />
    </svg>
  );
}

// ── Nav icons ─────────────────────────────────────────────────────────────────

function IconToday() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><circle cx="8" cy="8" r="3"/><path d="M8 1v2M8 13v2M1 8h2M13 8h2M3 3l1.5 1.5M11.5 11.5L13 13M3 13l1.5-1.5M11.5 4.5L13 3" strokeLinecap="round"/></svg>;
}

function IconRoadmap() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><path d="M2 13c2 0 2-8 4-8s2 8 4 8 2-8 4-8"/><circle cx="2" cy="13" r="1.4" fill="currentColor"/><circle cx="14" cy="5" r="1.4" fill="currentColor"/></svg>;
}

function IconSkillGraph() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><circle cx="4" cy="4" r="1.8"/><circle cx="12" cy="4" r="1.8"/><circle cx="8" cy="12" r="1.8"/><circle cx="13" cy="11" r="1.4"/><path d="M5.5 4h5M5 5.5l2 5M11 5.5l-2 5M9 12h2.5"/></svg>;
}

function IconCoach() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><path d="M2 4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H6l-3 2v-2H4a2 2 0 0 1-2-2z"/><path d="M8 5l1 2 2 .5-1.5 1.4.4 2L8 9.9 6.1 11l.4-2L5 7.5l2-.5z" fill="currentColor" stroke="none"/></svg>;
}

function IconMarket() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><path d="M2 12l3-4 3 2 4-6 2 3"/><circle cx="2" cy="12" r="1" fill="currentColor"/><circle cx="14" cy="7" r="1" fill="currentColor"/></svg>;
}

function IconOpportunities() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><circle cx="8" cy="8" r="6"/><circle cx="8" cy="8" r="3"/><circle cx="8" cy="8" r="1" fill="currentColor"/><path d="M8 1v2M8 13v2M1 8h2M13 8h2"/></svg>;
}

function IconNewsletter() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><rect x="2" y="3" width="12" height="10" rx="1.5"/><path d="M2 5l6 4 6-4"/></svg>;
}

function IconDiscovery() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><circle cx="8" cy="8" r="6"/><path d="M10.5 5.5L9 9l-3.5 1.5L7 7z" fill="currentColor" stroke="none"/></svg>;
}

function IconGlobe() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><circle cx="8" cy="8" r="6"/><path d="M2 8h12M8 2c2 2 2 10 0 12M8 2c-2 2-2 10 0 12"/></svg>;
}

function IconAutopilot() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><circle cx="8" cy="8" r="6"/><path d="M8 4.5l1 2.5 2.5 1-2.5 1-1 2.5-1-2.5L4.5 8 7 7z" fill="currentColor" stroke="none"/></svg>;
}

function IconCareerTwin() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><circle cx="8" cy="5.5" r="2.5"/><path d="M3.5 13.5c0-2.5 2-4 4.5-4s4.5 1.5 4.5 4"/><path d="M8 5.5v8" strokeDasharray="1.2 1.4"/></svg>;
}

function IconAnalytics() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><path d="M2 2v12h12" strokeLinecap="round"/><rect x="4.5" y="8" width="2" height="4"/><rect x="7.5" y="5.5" width="2" height="6.5"/><rect x="10.5" y="3.5" width="2" height="8.5"/></svg>;
}

function IconWellness() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><path d="M8 13.5S2.5 10 2.5 6.2A2.7 2.7 0 018 4.5a2.7 2.7 0 015.5 1.7C13.5 10 8 13.5 8 13.5z"/></svg>;
}

function IconInterview() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><path d="M2.5 3.5h11v7h-6l-3 2.5v-2.5h-2z"/><path d="M5.5 6h5M5.5 8h3"/></svg>;
}

function IconNegotiation() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><path d="M8 2v12M4.5 5h5.5a2 2 0 010 4H6a2 2 0 000 4h5.5" strokeLinecap="round"/></svg>;
}

function IconCV() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><rect x="3" y="2" width="10" height="12" rx="1.5"/><path d="M5 5h6M5 8h6M5 11h4"/></svg>;
}

function IconStrategies() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><path d="M2 12.5L6 4l2.5 5L11 5.5l3 7" strokeLinecap="round" strokeLinejoin="round"/></svg>;
}

function IconApplications() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><rect x="2.5" y="4" width="11" height="9.5" rx="1.3"/><path d="M6 4V2.8h4V4M5.5 7.5h5M5.5 10h3"/></svg>;
}

function IconEvidenceVault() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><rect x="2" y="4" width="12" height="9" rx="1.2"/><path d="M2 7h12M5 4V2.5h6V4"/><circle cx="8" cy="10" r="1" fill="currentColor"/></svg>;
}

function IconCredential() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><circle cx="8" cy="6" r="3"/><path d="M6 8.6L5 14l3-1.6L11 14l-1-5.4" strokeLinejoin="round"/></svg>;
}

function IconOpenSource() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><circle cx="4" cy="4" r="2"/><circle cx="4" cy="12" r="2"/><circle cx="12" cy="8" r="2"/><path d="M4 6v4M5.7 11l4.5-2M5.7 5l4.5 2"/></svg>;
}

function IconLearningRoi() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><path d="M2 13h12M3 13V9M6.5 13V6M10 13V8M13.5 13V4" strokeLinecap="round"/></svg>;
}

function IconCohorts() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><circle cx="5" cy="6" r="2"/><circle cx="11" cy="6" r="2"/><path d="M1.5 13c0-2 1.6-3.2 3.5-3.2M14.5 13c0-2-1.6-3.2-3.5-3.2M6 13c0-1.4 1-2.3 2-2.3s2 .9 2 2.3"/></svg>;
}

function IconOutreach() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><path d="M2 7.5L14 2.5l-4 11-2.5-4.5z" strokeLinejoin="round"/><path d="M7.5 9L10 6.5"/></svg>;
}

function IconMentorship() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><circle cx="8" cy="5" r="2.4"/><path d="M3.5 13c0-2.6 2-4.2 4.5-4.2s4.5 1.6 4.5 4.2"/><path d="M11.5 2.8l1.2 1.2-1.2 1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>;
}

function IconStorytelling() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><path d="M3 2.5h7l3 3V13a.5.5 0 01-.5.5h-9A.5.5 0 013 13z"/><path d="M9.5 2.5V6h3.5M5.5 9h5M5.5 11h3"/></svg>;
}

function IconPortfolio() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><rect x="2" y="3" width="12" height="10" rx="1.5"/><path d="M2 10l3-3 3 3 5-5"/></svg>;
}

function IconNetwork() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><circle cx="6" cy="6" r="2.4"/><circle cx="11" cy="5" r="1.8"/><path d="M2 13c0-2.2 2-3.6 4-3.6s4 1.4 4 3.6M9 13c0-1.6 1.5-2.6 3-2.6s2 .8 2 2.4"/></svg>;
}

function IconSettings() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><circle cx="8" cy="8" r="2"/><path d="M13 8.7l1.4-.4-.4-1.4-1.4-.2-.4-1.4 1-1L11.6 3l-1 1-1.4-.4-.2-1.4-1.4-.4L7.2 3l-1.4.4-1-1L3.4 3.6l1 1-.4 1.4L2.6 6.4 2.2 7.8l1.4.4.4 1.4-1 1L4.4 12l1-1 1.4.4.2 1.4 1.4.4.4-1.4 1.4-.4 1 1L12.6 11.4l-1-1z"/></svg>;
}

function IconDeveloper() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><path d="M5.5 5L2.5 8l3 3M10.5 5l3 3-3 3" strokeLinecap="round" strokeLinejoin="round"/></svg>;
}

function IconHelp() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><circle cx="8" cy="8" r="6"/><path d="M6.5 6.5C6.5 5.5 7 5 8 5s1.5.5 1.5 1.5S8 7.5 8 8.5M8 11h.01" strokeLinecap="round"/></svg>;
}

function IconAdmin() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><path d="M8 1.5l5 2v3.5c0 3-2.1 5.2-5 6-2.9-.8-5-3-5-6V3.5z"/><path d="M6 8l1.4 1.4L10.5 6" strokeLinecap="round" strokeLinejoin="round"/></svg>;
}

// Appended to the nav only for admins/superadmins (server still enforces access).
const ADMIN_SECTION: NavSection = {
  title: "Administration",
  items: [{ label: "Admin Console", href: ROUTES.admin, icon: <IconAdmin /> }],
};

function IconSearch() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7" className="h-[13px] w-[13px] opacity-70"><circle cx="7" cy="7" r="5"/><path d="M11 11l3 3" strokeLinecap="round"/></svg>;
}

// ── Nav data ──────────────────────────────────────────────────────────────────

interface NavItem {
  label: string;
  href: string;
  icon: React.ReactNode;
  badge?: string;
  dimmed?: boolean;
}

interface NavSection {
  title: string;
  items: NavItem[];
}

const NAV_SECTIONS: NavSection[] = [
  {
    title: "Planning",
    items: [
      { label: "Today",        href: ROUTES.dashboard,  icon: <IconToday /> },
      { label: "Analytics",    href: ROUTES.analytics,  icon: <IconAnalytics /> },
      { label: "Roadmap",      href: ROUTES.roadmap,    icon: <IconRoadmap /> },
      { label: "Strategies",   href: ROUTES.roadmapOptions, icon: <IconStrategies /> },
      { label: "Autopilot",    href: ROUTES.autopilot,  icon: <IconAutopilot /> },
      { label: "Skill Graph",  href: ROUTES.skillGraph, icon: <IconSkillGraph /> },
      { label: "Discover Paths", href: ROUTES.discovery, icon: <IconDiscovery /> },
      { label: "AI Coach",     href: ROUTES.coach,      icon: <IconCoach /> },
      { label: "Career Twin",  href: ROUTES.careerTwin, icon: <IconCareerTwin /> },
      { label: "Wellness",     href: ROUTES.wellness,   icon: <IconWellness /> },
    ],
  },
  {
    title: "Intelligence",
    items: [
      { label: "Market Pulse",   href: ROUTES.market,        icon: <IconMarket /> },
      { label: "Localisation",   href: ROUTES.localisation,  icon: <IconGlobe /> },
      { label: "Opportunities",  href: ROUTES.opportunities,  icon: <IconOpportunities /> },
      { label: "Negotiation",    href: ROUTES.negotiation,    icon: <IconNegotiation /> },
      { label: "Interview Prep", href: ROUTES.interview,      icon: <IconInterview /> },
      { label: "Newsletter",     href: ROUTES.newsletter,     icon: <IconNewsletter /> },
    ],
  },
  {
    title: "Assets",
    items: [
      { label: "CV & Profile",    href: ROUTES.cvAnalysis,  icon: <IconCV /> },
      { label: "Applications",    href: ROUTES.applications, icon: <IconApplications /> },
      { label: "Evidence Vault",  href: ROUTES.evidence,    icon: <IconEvidenceVault /> },
      { label: "Credentials",     href: ROUTES.credentials, icon: <IconCredential /> },
      { label: "Learning ROI",    href: ROUTES.learning,    icon: <IconLearningRoi /> },
      { label: "Open Source",     href: ROUTES.oss,         icon: <IconOpenSource /> },
      { label: "Storytelling",    href: ROUTES.storytelling, icon: <IconStorytelling /> },
      { label: "Portfolio",       href: ROUTES.portfolio,   icon: <IconPortfolio /> },
      { label: "Network",         href: ROUTES.networking,  icon: <IconNetwork /> },
    ],
  },
  {
    title: "Community",
    items: [
      { label: "Cohorts",         href: ROUTES.cohorts,     icon: <IconCohorts /> },
      { label: "Mentorship",      href: ROUTES.mentorship,  icon: <IconMentorship /> },
      { label: "Outreach",        href: ROUTES.outreach,    icon: <IconOutreach /> },
    ],
  },
  {
    title: "Account",
    items: [
      { label: "Settings",        href: ROUTES.settings,  icon: <IconSettings /> },
      { label: "Developer API",   href: ROUTES.developer, icon: <IconDeveloper /> },
      { label: "Help & feedback", href: ROUTES.help,      icon: <IconHelp /> },
    ],
  },
];

// ── Sidebar ───────────────────────────────────────────────────────────────────

export interface AppSidebarProps {
  className?: string;
}

export function AppSidebar({ className }: AppSidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const t = useT();
  const user = useAuthStore((s) => s.user);
  const setCommandOpen = useUIStore((s) => s.setCommandOpen);
  const { logout } = useAuth();

  const isAdmin = user?.role === "admin" || user?.role === "superadmin";
  const navSections = isAdmin ? [...NAV_SECTIONS, ADMIN_SECTION] : NAV_SECTIONS;

  // Live high-match opportunity count drives the Opportunities badge.
  // Shares the query key with the dashboard, so this dedupes rather than refetches.
  const { data: alerts } = useQuery({
    queryKey: QUERY_KEYS.opportunityAlerts,
    queryFn: opportunitiesApi.getAlerts,
    staleTime: 5 * 60 * 1000,
  });
  const highMatchCount = alerts?.highMatchCount ?? 0;

  // Open autopilot proposals drive the Autopilot badge.
  const { data: proposals } = useQuery({
    queryKey: QUERY_KEYS.autopilot,
    queryFn: autopilotApi.list,
    staleTime: 5 * 60 * 1000,
  });
  const openProposalCount = proposals?.length ?? 0;

  // Real plan label for the user card (no more hardcoded "Pro").
  const { data: subscription } = useQuery({
    queryKey: QUERY_KEYS.subscription,
    queryFn: billingApi.getSubscription,
    staleTime: 5 * 60 * 1000,
  });
  const planLabel =
    subscription?.plan === "pro"
      ? "Pro"
      : subscription?.plan === "teams"
        ? "Teams"
        : "Free";
  const isPaidPlan = planLabel !== "Free";

  const isActive = (href: string) =>
    href !== "#" && (pathname === href || pathname.startsWith(`${href}/`));

  /** Resolve a live badge for a nav item — only the real signals we have. */
  const badgeFor = (item: NavItem): string | undefined => {
    if (item.href === ROUTES.opportunities && highMatchCount > 0) {
      return highMatchCount > 99 ? "99+" : String(highMatchCount);
    }
    if (item.href === ROUTES.autopilot && openProposalCount > 0) {
      return openProposalCount > 99 ? "99+" : String(openProposalCount);
    }
    return item.badge;
  };

  const initials =
    user?.displayName
      ? user.displayName.split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase()
      : user?.email?.[0]?.toUpperCase() ?? "U";

  return (
    <aside
      className={cn(
        "hidden md:flex w-[248px] shrink-0 flex-col bg-bg-2 border-r border-rule",
        "sticky top-0 h-screen overflow-y-auto",
        "scrollbar-thin scrollbar-thumb-rule-strong",
        className,
      )}
    >
      {/* Brand */}
      <Link
        href={ROUTES.dashboard}
        className="flex items-center gap-2.5 px-6 pt-[22px] pb-1 mb-[18px] font-serif text-[18px] font-medium tracking-[-0.01em] text-ink hover:no-underline"
        aria-label="Career Roadmap AI dashboard"
      >
        <LogoMark />
        Roadmap
      </Link>

      {/* Command search */}
      <button
        type="button"
        onClick={() => setCommandOpen(true)}
        className="mx-4 mb-[22px] flex items-center gap-2 rounded-[7px] border border-rule bg-paper px-3 py-2 text-[13px] text-ink-3 transition-colors duration-150 hover:border-rule-strong"
        aria-label="Open command search"
      >
        <IconSearch />
        <span>Search anything…</span>
        <kbd className="ml-auto font-mono text-[11px] bg-bg-2 border border-rule px-1.5 py-px rounded text-ink-3 leading-none">
          ⌘K
        </kbd>
      </button>

      {/* Navigation */}
      <nav className="flex-1 px-4 space-y-[22px]" aria-label="App navigation">
        {navSections.map((section) => (
          <div key={section.title}>
            <p className="px-[10px] pb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-3 select-none">
              {t(section.title)}
            </p>
            <ul className="space-y-px" role="list">
              {section.items.map((item) => {
                const active = isActive(item.href);
                const badge = badgeFor(item);
                return (
                  <li key={item.label}>
                    <Link
                      href={item.href}
                      className={cn(
                        "flex items-center gap-[11px] rounded-[6px] px-[10px] py-[7px] text-[13.5px] font-medium transition-all duration-[120ms]",
                        active
                          ? "bg-ink text-bg"
                          : item.dimmed
                          ? "text-ink-3 hover:bg-bg-3 hover:text-ink"
                          : "text-ink-2 hover:bg-bg-3 hover:text-ink",
                      )}
                      aria-current={active ? "page" : undefined}
                    >
                      <span
                        className={cn(
                          "flex h-4 w-4 shrink-0 items-center justify-center",
                          active ? "text-terra-soft" : "opacity-85",
                        )}
                      >
                        {item.icon}
                      </span>
                      <span className="min-w-0 truncate">{t(item.label)}</span>
                      {badge && (
                        <span className="ml-auto shrink-0 rounded-[3px] bg-terra px-[5px] py-px text-[10px] font-semibold leading-[1.5] text-white">
                          {badge}
                        </span>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Language switcher */}
      <div className="px-4 pb-1">
        <LanguageSwitcher />
      </div>

      {/* User card — dropdown */}
      <div className="p-4">
        <DropdownMenu>
          <DropdownMenuTrigger
            className={cn(
              "w-full flex items-center gap-2.5 rounded-[9px] border border-rule bg-paper p-2.5",
              "transition-colors duration-150 hover:border-rule-strong",
              "text-left cursor-pointer outline-none",
            )}
          >
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[7px] bg-green font-serif text-sm font-medium text-white">
              {initials}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-semibold text-ink">
                {user?.displayName ?? user?.email ?? "User"}
              </p>
              <p className="mt-px text-[11px] text-ink-3">{planLabel} plan</p>
            </div>
            <ChevronUp className="shrink-0 h-3.5 w-3.5 text-ink-3" aria-hidden="true" />
          </DropdownMenuTrigger>

          <DropdownMenuContent side="top" sideOffset={8} align="start">
            {/* Identity block */}
            <DropdownMenuGroup>
              <DropdownMenuLabel>
                <div className="flex items-center gap-2.5 py-0.5">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[7px] bg-green font-serif text-sm font-medium text-white">
                    {initials}
                  </div>
                  <div className="min-w-0">
                    <p className="truncate text-[13px] font-semibold text-ink leading-tight">
                      {user?.displayName ?? "User"}
                    </p>
                    <p className="truncate text-[11px] text-ink-3 leading-tight mt-px">
                      {user?.email}
                    </p>
                    <span
                      className={cn(
                        "mt-1 inline-block rounded-[3px] px-[5px] py-px text-[10px] font-semibold leading-[1.5]",
                        isPaidPlan ? "bg-terra text-white" : "bg-bg-3 text-ink-2",
                      )}
                    >
                      {planLabel}
                    </span>
                  </div>
                </div>
              </DropdownMenuLabel>
            </DropdownMenuGroup>

            <DropdownMenuSeparator />

            <DropdownMenuItem onClick={() => router.push(ROUTES.settings)}>
              <Settings className="h-4 w-4" />
              Settings
            </DropdownMenuItem>

            <DropdownMenuItem onClick={() => router.push(ROUTES.settingsBilling)}>
              <CreditCard className="h-4 w-4" />
              Plan &amp; billing
            </DropdownMenuItem>

            <DropdownMenuItem onClick={() => router.push(ROUTES.help)}>
              <HelpCircle className="h-4 w-4" />
              Help &amp; Feedback
            </DropdownMenuItem>

            <DropdownMenuSeparator />

            <DropdownMenuItem variant="destructive" onClick={logout}>
              <LogOut className="h-4 w-4" />
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </aside>
  );
}
