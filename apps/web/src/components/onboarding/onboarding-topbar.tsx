"use client";

import Link from "next/link";
import { ROUTES } from "@/lib/constants";

function LogoMark() {
  return (
    <svg
      viewBox="0 0 28 28"
      fill="none"
      className="h-[26px] w-[26px] shrink-0"
      aria-hidden="true"
    >
      <path
        d="M3 22 C 8 22, 8 6, 14 6 S 20 22, 25 22"
        stroke="#15140F"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      <circle cx="3" cy="22" r="2.2" fill="#C95A3D" />
      <circle cx="14" cy="6" r="2.2" fill="#134E3A" />
      <circle cx="25" cy="22" r="2.2" fill="#15140F" />
    </svg>
  );
}

export interface OnboardingTopbarProps {
  onExit?: () => void;
}

export function OnboardingTopbar({ onExit }: OnboardingTopbarProps) {
  return (
    <header className="sticky top-0 z-50 flex items-center justify-between border-b border-rule bg-bg px-5 py-4 sm:px-9">
      <Link
        href={ROUTES.dashboard}
        className="flex items-center gap-2.5 font-serif text-[19px] font-medium tracking-[-0.01em] text-ink no-underline"
        aria-label="Career Roadmap AI"
      >
        <LogoMark />
        <span className="hidden sm:inline">Career Roadmap AI</span>
      </Link>

      <div className="flex items-center gap-2.5 text-[12.5px] text-ink-3">
        <span className="hidden items-center gap-[5px] sm:flex">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-green" aria-hidden="true" />
          Saved automatically
        </span>
        <button
          type="button"
          onClick={onExit}
          className="border-l border-rule pl-3.5 text-[12.5px] text-ink-3 transition-colors hover:text-ink sm:pl-3.5"
        >
          Exit setup
        </button>
      </div>
    </header>
  );
}

