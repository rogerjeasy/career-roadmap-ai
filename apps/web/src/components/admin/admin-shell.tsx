"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Users,
  Inbox,
  Megaphone,
  Activity,
  ScrollText,
  ArrowLeft,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ROUTES } from "@/lib/constants";
import { useAuthStore } from "@/store/auth.store";

interface AdminNavItem {
  label: string;
  href: string;
  icon: React.ReactNode;
}

const NAV_ITEMS: AdminNavItem[] = [
  { label: "Overview", href: ROUTES.admin, icon: <LayoutDashboard className="h-4 w-4" /> },
  { label: "Users", href: ROUTES.adminUsers, icon: <Users className="h-4 w-4" /> },
  { label: "Inbox", href: ROUTES.adminInbox, icon: <Inbox className="h-4 w-4" /> },
  { label: "Broadcast", href: ROUTES.adminBroadcast, icon: <Megaphone className="h-4 w-4" /> },
  { label: "System", href: ROUTES.adminSystem, icon: <Activity className="h-4 w-4" /> },
  { label: "Audit log", href: ROUTES.adminAudit, icon: <ScrollText className="h-4 w-4" /> },
];

function useIsActive() {
  const pathname = usePathname();
  return (href: string) =>
    href === ROUTES.admin
      ? pathname === ROUTES.admin
      : pathname === href || pathname.startsWith(`${href}/`);
}

export interface AdminShellProps {
  children: React.ReactNode;
}

export function AdminShell({ children }: AdminShellProps) {
  const isActive = useIsActive();
  const user = useAuthStore((s) => s.user);
  const roleLabel = user?.role === "superadmin" ? "Superadmin" : "Admin";

  return (
    <div className="flex min-h-screen bg-bg">
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex w-[230px] shrink-0 flex-col border-r border-rule bg-bg-2 sticky top-0 h-screen">
        <div className="flex items-center gap-2 px-5 pt-5 pb-4">
          <span className="flex h-7 w-7 items-center justify-center rounded-[7px] bg-ink text-[12px] font-bold text-bg">
            A
          </span>
          <div className="min-w-0">
            <p className="font-serif text-[15px] font-medium leading-tight text-ink">Admin</p>
            <p className="truncate text-[11px] text-ink-3">Career Roadmap AI</p>
          </div>
        </div>

        <nav className="flex-1 px-3 py-2 space-y-px" aria-label="Admin navigation">
          {NAV_ITEMS.map((item) => {
            const active = isActive(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-2.5 rounded-[7px] px-3 py-2 text-[13.5px] font-medium transition-colors duration-[120ms]",
                  active
                    ? "bg-ink text-bg"
                    : "text-ink-2 hover:bg-bg-3 hover:text-ink",
                )}
                aria-current={active ? "page" : undefined}
              >
                <span className={active ? "text-terra-soft" : "opacity-80"}>{item.icon}</span>
                <span className="min-w-0 truncate">{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-rule p-3">
          <Link
            href={ROUTES.dashboard}
            className="flex items-center gap-2 rounded-[7px] px-3 py-2 text-[13px] font-medium text-ink-2 transition-colors duration-150 hover:bg-bg-3 hover:text-ink"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to app
          </Link>
        </div>
      </aside>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Topbar */}
        <header className="sticky top-0 z-40 flex h-[56px] shrink-0 items-center justify-between gap-3 border-b border-rule bg-bg px-4 sm:px-6">
          <Link
            href={ROUTES.dashboard}
            className="flex items-center gap-1.5 text-[13px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink lg:hidden"
          >
            <ArrowLeft className="h-4 w-4" />
            <span className="hidden sm:inline">App</span>
          </Link>

          <div className="hidden lg:block text-[13px] font-semibold text-ink">
            Administration
          </div>

          <div className="ml-auto flex items-center gap-2.5 min-w-0">
            <span className="rounded-[5px] bg-terra/10 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-terra">
              {roleLabel}
            </span>
            <span className="hidden truncate text-[12.5px] text-ink-2 sm:block max-w-[180px]">
              {user?.email}
            </span>
          </div>
        </header>

        {/* Mobile nav — horizontal scroll */}
        <nav
          className="lg:hidden flex gap-1 overflow-x-auto border-b border-rule bg-bg-2 px-3 py-2 [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden"
          aria-label="Admin navigation"
        >
          {NAV_ITEMS.map((item) => {
            const active = isActive(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex shrink-0 items-center gap-1.5 rounded-[7px] px-3 py-1.5 text-[13px] font-medium transition-colors duration-[120ms]",
                  active ? "bg-ink text-bg" : "text-ink-2 hover:bg-bg-3",
                )}
                aria-current={active ? "page" : undefined}
              >
                {item.icon}
                {item.label}
              </Link>
            );
          })}
        </nav>

        <main className="flex-1 overflow-auto">{children}</main>
      </div>
    </div>
  );
}
