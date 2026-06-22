"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { Menu, X } from "lucide-react";
import { cn } from "@/lib/utils";

// ─── Logo mark ────────────────────────────────────────────────────────
// Standalone SVG also available at /public/logo-mark.svg
function LogoMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 28 28"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      className={className}
    >
      <path
        d="M3 22 C 8 22, 8 6, 14 6 S 20 22, 25 22"
        stroke="#15140F"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      {/* Start — terracotta */}
      <circle cx="3"  cy="22" r="2.2" fill="#C95A3D" />
      {/* Peak — forest green */}
      <circle cx="14" cy="6"  r="2.2" fill="#134E3A" />
      {/* End — ink */}
      <circle cx="25" cy="22" r="2.2" fill="#15140F" />
    </svg>
  );
}

// ─── Types ────────────────────────────────────────────────────────────
interface NavLink {
  label: string;
  href:  string;
  badge?: string;    // optional — only "Career Twin" carries one
}

// ─── Nav links config ─────────────────────────────────────────────────
const NAV_LINKS: NavLink[] = [
  { label: "Product",      href: "#pillars"      },
  { label: "How it works", href: "#how-it-works" },
  { label: "Features",     href: "#features"     },
  { label: "Career Twin",  href: "#career-twin", badge: "Beta" },
  { label: "Pricing",      href: "#pricing"      },
];

// ─── Header ───────────────────────────────────────────────────────────
export function Header() {
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header className="sticky top-0 z-50">

      {/* ── Announcement bar ─────────────────────────────────────── */}
      <div className="bg-ink text-bg text-[13px] tracking-[0.01em] text-center py-[10px] px-4 font-normal">
        <span className="text-terra-soft">●</span>{" "}
        New:{" "}
        <strong className="font-semibold">Career Twin</strong>{" "}
        is now in beta — meet the AI persona that knows your full plan.
        <Link
          href="#career-twin"
          className="underline underline-offset-[3px] ml-1.5 transition-colors duration-150 hover:text-terra-soft"
        >
          Read the announcement →
        </Link>
      </div>

      {/* ── Navigation bar ───────────────────────────────────────── */}
      <nav
        className={cn(
          "flex items-center justify-between",
          "px-12 py-[18px]",
          "bg-bg border-b border-rule",
          "transition-[background,box-shadow,border-color] duration-300",
          scrolled && [
            "bg-[rgba(247,242,232,0.88)]",
            "backdrop-blur-[18px] saturate-[1.4]",
            "shadow-[0_1px_0_var(--color-rule),0_4px_24px_-8px_rgba(21,20,15,0.08)]",
          ],
          "max-md:px-6",
        )}
        aria-label="Main navigation"
      >

        {/* ── Brand ──────────────────────────────────────────────── */}
        <Link
          href="/"
          className="flex min-w-0 items-center gap-2.5 font-serif text-[19px] font-medium tracking-[-0.01em] text-ink no-underline sm:text-[22px]"
          aria-label="Career Roadmap AI — home"
        >
          <LogoMark className="w-7 h-7 shrink-0" />
          <span className="truncate">Career Roadmap AI</span>
        </Link>

        {/* ── Nav links (hidden on mobile) ─────────────────────── */}
        <div className="hidden md:flex items-center gap-9">
          {NAV_LINKS.map(({ label, href, badge }: NavLink) => (
            <Link
              key={label}
              href={href}
              className="text-sm font-medium text-ink-2 transition-colors duration-150 hover:text-ink whitespace-nowrap"
            >
              {label}
              {badge !== undefined && (
                <span className="ml-1.5 align-middle text-[9px] font-semibold tracking-[0.05em] bg-terra-soft text-terra-2 px-[5px] py-[2px] rounded-[3px]">
                  {badge}
                </span>
              )}
            </Link>
          ))}
        </div>

        {/* ── CTA group ───────────────────────────────────────────── */}
        <div className="flex shrink-0 items-center gap-3 sm:gap-6">
          <Link
            href="/login"
            className="hidden text-sm font-medium text-ink-2 transition-colors duration-150 hover:text-ink sm:inline"
          >
            Sign in
          </Link>

          <Link
            href="/register"
            className={cn(
              "group hidden items-center gap-2 sm:inline-flex",
              "bg-ink text-bg",
              "text-sm font-medium",
              "px-[18px] py-[10px] rounded-full",
              "cursor-pointer no-underline",
              "transition-all duration-200 ease-out",
              "hover:bg-green-2 hover:-translate-y-px",
              "hover:shadow-[0_4px_16px_-4px_rgba(19,78,58,0.4)]",
            )}
          >
            Get started
            <span className="transition-transform duration-200 group-hover:translate-x-[3px]">
              →
            </span>
          </Link>

          {/* Mobile menu toggle */}
          <button
            type="button"
            onClick={() => setMobileOpen((v) => !v)}
            aria-label={mobileOpen ? "Close menu" : "Open menu"}
            aria-expanded={mobileOpen}
            className="flex h-9 w-9 items-center justify-center rounded-[8px] text-ink transition-colors duration-150 hover:bg-bg-2 md:hidden"
          >
            {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>

      </nav>

      {/* ── Mobile menu panel ────────────────────────────────────── */}
      {mobileOpen && (
        <div className="border-b border-rule bg-bg md:hidden">
          <nav className="flex flex-col gap-1 px-6 py-4" aria-label="Mobile navigation">
            {NAV_LINKS.map(({ label, href, badge }: NavLink) => (
              <Link
                key={label}
                href={href}
                onClick={() => setMobileOpen(false)}
                className="flex items-center gap-2 rounded-[8px] px-2 py-2.5 text-[15px] font-medium text-ink-2 transition-colors duration-150 hover:bg-bg-2 hover:text-ink"
              >
                {label}
                {badge !== undefined && (
                  <span className="align-middle text-[9px] font-semibold tracking-[0.05em] bg-terra-soft text-terra-2 px-[5px] py-[2px] rounded-[3px]">
                    {badge}
                  </span>
                )}
              </Link>
            ))}
            <div className="mt-2 flex flex-col gap-2 border-t border-rule pt-3">
              <Link
                href="/login"
                onClick={() => setMobileOpen(false)}
                className="rounded-[8px] px-2 py-2.5 text-[15px] font-medium text-ink-2 transition-colors duration-150 hover:bg-bg-2 hover:text-ink"
              >
                Sign in
              </Link>
              <Link
                href="/register"
                onClick={() => setMobileOpen(false)}
                className="inline-flex items-center justify-center gap-2 rounded-full bg-ink px-[18px] py-[11px] text-sm font-medium text-bg transition-colors duration-200 hover:bg-green-2"
              >
                Get started →
              </Link>
            </div>
          </nav>
        </div>
      )}
    </header>
  );
}