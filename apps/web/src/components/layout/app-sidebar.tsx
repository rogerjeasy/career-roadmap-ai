"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ChevronUp, CreditCard, HelpCircle, LogOut, Settings } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth.store";
import { useAuth } from "@/hooks/use-auth";
import { ROUTES } from "@/lib/constants";
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

function IconCV() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><rect x="3" y="2" width="10" height="12" rx="1.5"/><path d="M5 5h6M5 8h6M5 11h4"/></svg>;
}

function IconEvidenceVault() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><rect x="2" y="4" width="12" height="9" rx="1.2"/><path d="M2 7h12M5 4V2.5h6V4"/><circle cx="8" cy="10" r="1" fill="currentColor"/></svg>;
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

function IconHelp() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" className="h-4 w-4"><circle cx="8" cy="8" r="6"/><path d="M6.5 6.5C6.5 5.5 7 5 8 5s1.5.5 1.5 1.5S8 7.5 8 8.5M8 11h.01" strokeLinecap="round"/></svg>;
}

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
      { label: "Today",       href: ROUTES.dashboard,  icon: <IconToday /> },
      { label: "Roadmap",     href: ROUTES.roadmap,    icon: <IconRoadmap /> },
      { label: "Skill Graph", href: ROUTES.roadmap,    icon: <IconSkillGraph /> },
      { label: "AI Coach",    href: ROUTES.coach,      icon: <IconCoach />, badge: "2" },
    ],
  },
  {
    title: "Intelligence",
    items: [
      { label: "Market Pulse",   href: ROUTES.market,        icon: <IconMarket /> },
      { label: "Opportunities",  href: ROUTES.opportunities,  icon: <IconOpportunities />, badge: "5" },
      { label: "Newsletter",     href: "#",                   icon: <IconNewsletter />, dimmed: true },
    ],
  },
  {
    title: "Assets",
    items: [
      { label: "CV & Profile",    href: ROUTES.cvAnalysis,  icon: <IconCV /> },
      { label: "Evidence Vault",  href: "#",                icon: <IconEvidenceVault />, dimmed: true },
      { label: "Portfolio",       href: "#",                icon: <IconPortfolio />, dimmed: true },
      { label: "Network",         href: ROUTES.networking,  icon: <IconNetwork /> },
    ],
  },
  {
    title: "Account",
    items: [
      { label: "Settings",        href: ROUTES.settings,  icon: <IconSettings />, dimmed: true },
      { label: "Help & feedback", href: "#",              icon: <IconHelp />, dimmed: true },
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
  const user = useAuthStore((s) => s.user);
  const { logout } = useAuth();

  const isActive = (href: string) =>
    href !== "#" && (pathname === href || pathname.startsWith(`${href}/`));

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
        {NAV_SECTIONS.map((section) => (
          <div key={section.title}>
            <p className="px-[10px] pb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-3 select-none">
              {section.title}
            </p>
            <ul className="space-y-px" role="list">
              {section.items.map((item) => {
                const active = isActive(item.href);
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
                      <span className="min-w-0 truncate">{item.label}</span>
                      {item.badge && (
                        <span className="ml-auto shrink-0 rounded-[3px] bg-terra px-[5px] py-px text-[10px] font-semibold leading-[1.5] text-white">
                          {item.badge}
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
              <p className="mt-px text-[11px] text-ink-3">Pro plan</p>
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
                    <span className="mt-1 inline-block rounded-[3px] bg-terra px-[5px] py-px text-[10px] font-semibold leading-[1.5] text-white">
                      Pro
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

            <DropdownMenuItem onClick={() => router.push(ROUTES.settingsProfile)}>
              <CreditCard className="h-4 w-4" />
              Manage plan
            </DropdownMenuItem>

            <DropdownMenuItem>
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
