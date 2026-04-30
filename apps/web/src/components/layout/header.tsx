"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
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
  { label: "Product",      href: "#"        },
  { label: "How it works", href: "#"        },
  { label: "Features",     href: "#"        },
  { label: "Career Twin",  href: "#",       badge: "Beta" },
  { label: "Pricing",      href: "#pricing" },
];

// ─── Header ───────────────────────────────────────────────────────────
export function Header() {
  const [scrolled, setScrolled] = useState(false);

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
          href="#"
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
          className="flex items-center gap-2.5 font-serif text-[22px] font-medium tracking-[-0.01em] text-ink no-underline"
          aria-label="Career Roadmap AI — home"
        >
          <LogoMark className="w-7 h-7 shrink-0" />
          Career Roadmap AI
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
        <div className="flex items-center gap-6">
          <Link
            href="/login"
            className="text-sm font-medium text-ink-2 transition-colors duration-150 hover:text-ink"
          >
            Sign in
          </Link>

          <Link
            href="/register"
            className={cn(
              "group inline-flex items-center gap-2",
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
        </div>

      </nav>
    </header>
  );
}