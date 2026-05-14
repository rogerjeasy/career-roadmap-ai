"use client";

import Link from "next/link";
import { ROUTES } from "@/lib/constants";

function StarIcon() {
  return (
    <svg viewBox="0 0 14 14" fill="currentColor" className="h-[13px] w-[13px] text-white" aria-hidden="true">
      <path d="M7 1l1.5 4 4 1.5-4 1.5L7 12l-1.5-4L1.5 6.5l4-1.5z"/>
    </svg>
  );
}

export function CoachFab() {
  return (
    <Link
      href={ROUTES.coach}
      className={[
        "fixed bottom-6 right-7 z-50",
        "inline-flex items-center gap-[9px]",
        "rounded-full bg-ink px-[18px] py-[13px] pl-[14px]",
        "text-[13.5px] font-medium text-bg",
        "shadow-[0_12px_32px_-8px_rgba(21,20,15,0.35),0_4px_10px_-4px_rgba(21,20,15,0.2)]",
        "transition-all duration-200 hover:bg-green-2 hover:-translate-y-0.5",
        "hover:shadow-[0_18px_42px_-10px_rgba(19,78,58,0.5)]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green",
      ].join(" ")}
      aria-label="Ask Career Twin AI coach"
    >
      {/* Pulse ring */}
      <span
        className="pointer-events-none absolute inset-0 animate-[ringpulse_2.4s_ease-out_infinite] rounded-full border-2 border-terra opacity-0"
        aria-hidden="true"
      />

      {/* Icon circle */}
      <span className="flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-full bg-terra">
        <StarIcon />
      </span>

      Ask Career Twin

      {/* New dot */}
      <span className="ml-0.5 h-[7px] w-[7px] shrink-0 rounded-full bg-terra-soft" aria-hidden="true" />

      <style>{`
        @keyframes ringpulse {
          0%   { opacity: 0.7; transform: scale(1); }
          100% { opacity: 0;   transform: scale(1.25); }
        }
      `}</style>
    </Link>
  );
}
