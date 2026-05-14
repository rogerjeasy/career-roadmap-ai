"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

type AltTab = "linkedin" | "github" | "url";

const TABS: { id: AltTab; label: string; placeholder: string }[] = [
  { id: "linkedin", label: "LinkedIn", placeholder: "linkedin.com/in/your-handle" },
  { id: "github", label: "GitHub", placeholder: "github.com/your-username" },
  { id: "url", label: "URL", placeholder: "https://your-portfolio.com" },
];

export interface CvAltInputsProps {
  onUrlSubmit: (url: string, type: AltTab) => void;
  isLoading?: boolean;
}

export function CvAltInputs({ onUrlSubmit, isLoading }: CvAltInputsProps) {
  const [activeTab, setActiveTab] = useState<AltTab>("linkedin");
  const [url, setUrl] = useState("");

  const tab = TABS.find((t) => t.id === activeTab)!;

  return (
    <div className="flex min-h-[360px] flex-col rounded-2xl border border-rule bg-paper p-6">
      <h4 className="mb-1.5 font-serif text-[17px] font-medium tracking-[-0.005em] text-ink">
        No CV handy?
      </h4>
      <p className="mb-[18px] text-[12.5px] leading-relaxed text-ink-3">
        Pull your profile from one of these instead. We&apos;ll fetch public information only.
      </p>

      {/* Tab switcher */}
      <div className="mb-4 flex gap-1 rounded-lg bg-bg-2 p-[3px]">
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            onClick={() => {
              setActiveTab(id);
              setUrl("");
            }}
            className={cn(
              "flex flex-1 items-center justify-center gap-1.5 rounded-md px-2.5 py-2 text-[12px] font-medium transition-all duration-150",
              activeTab === id
                ? "bg-paper text-ink shadow-sm"
                : "text-ink-3 hover:text-ink",
            )}
          >
            <TabIcon type={id} />
            {label}
          </button>
        ))}
      </div>

      {/* URL input */}
      <input
        type="url"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder={tab.placeholder}
        className="mb-3.5 w-full rounded-lg border border-rule bg-bg px-3.5 py-3 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none"
      />

      <button
        type="button"
        disabled={!url.trim() || isLoading}
        onClick={() => url.trim() && onUrlSubmit(url.trim(), activeTab)}
        className="flex w-fit items-center gap-2 rounded-lg border border-rule-strong bg-paper px-4 py-2.5 text-[13px] font-medium text-ink-2 transition-all hover:border-ink hover:bg-bg-2 hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
      >
        <svg
          width="13"
          height="13"
          viewBox="0 0 14 14"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M2 7h10M8 3l4 4-4 4" />
        </svg>
        Pull profile
      </button>

      <p className="mt-auto border-t border-dashed border-rule pt-3.5 text-[11.5px] leading-relaxed text-ink-3">
        <strong className="font-semibold text-ink-2">Privacy:</strong> we read public info only.
        We never store your password and never post on your behalf.
      </p>
    </div>
  );
}

function TabIcon({ type }: { type: AltTab }) {
  if (type === "linkedin") {
    return (
      <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" className="h-3 w-3" aria-hidden="true">
        <rect x="2" y="2" width="10" height="10" rx="1.5" />
        <path d="M5 5h4M5 7h4M5 9h2" />
      </svg>
    );
  }
  if (type === "github") {
    return (
      <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" className="h-3 w-3" aria-hidden="true">
        <circle cx="7" cy="7" r="5.5" />
        <path d="M2.5 7c2 1.5 7 1.5 9 0M7 1.5c1.5 2 1.5 9 0 11M7 1.5c-1.5 2-1.5 9 0 11" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" className="h-3 w-3" aria-hidden="true">
      <path d="M2 11V3l5 4 5-4v8M2 3l5 4 5-4" />
    </svg>
  );
}

