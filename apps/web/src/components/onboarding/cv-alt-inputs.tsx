"use client";

import { useRef, useState } from "react";
import { cn } from "@/lib/utils";

type AltTab = "linkedin" | "github" | "url";

const TABS: { id: AltTab; label: string }[] = [
  { id: "linkedin", label: "LinkedIn" },
  { id: "github", label: "GitHub" },
  { id: "url", label: "URL" },
];

// GitHub and URL tabs share a single text-input flow; LinkedIn uses a guided
// PDF-export upload instead (LinkedIn's API does not expose work history).
const URL_TABS: Record<"github" | "url", { placeholder: string }> = {
  github: { placeholder: "github.com/your-username" },
  url: { placeholder: "https://link-to-your-cv.pdf" },
};

const LINKEDIN_STEPS = [
  'Open your LinkedIn profile',
  'Click the "More" button under your name',
  'Choose "Save to PDF"',
  "Upload the downloaded file below",
];

export interface CvAltInputsProps {
  onUrlSubmit: (url: string, type: "github" | "url") => void;
  /** Used by the LinkedIn tab — the exported PDF flows through the normal upload path. */
  onFileSelect: (file: File) => void;
  isLoading?: boolean;
}

export function CvAltInputs({ onUrlSubmit, onFileSelect, isLoading }: CvAltInputsProps) {
  const [activeTab, setActiveTab] = useState<AltTab>("linkedin");
  const [url, setUrl] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  return (
    <div className="flex min-h-[360px] flex-col rounded-2xl border border-rule bg-paper p-6">
      <h4 className="mb-1.5 font-serif text-[17px] font-medium tracking-[-0.005em] text-ink">
        No CV handy?
      </h4>
      <p className="mb-[18px] text-[12.5px] leading-relaxed text-ink-3">
        Bring your profile from one of these instead.
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

      {activeTab === "linkedin" ? (
        <div className="min-w-0">
          <p className="mb-3 text-[12.5px] leading-relaxed text-ink-3">
            LinkedIn doesn&apos;t share your full history over its API, so export
            your profile as a PDF — it includes your experience, education and
            skills — and we&apos;ll analyse it like any other CV.
          </p>
          <ol className="mb-4 space-y-1.5">
            {LINKEDIN_STEPS.map((step, i) => (
              <li key={step} className="flex gap-2.5 text-[12.5px] leading-relaxed text-ink-2">
                <span className="mt-px flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full bg-bg-2 text-[10px] font-semibold text-ink-3">
                  {i + 1}
                </span>
                <span className="min-w-0">{step}</span>
              </li>
            ))}
          </ol>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,application/pdf"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) onFileSelect(file);
              e.target.value = "";
            }}
          />
          <button
            type="button"
            disabled={isLoading}
            onClick={() => fileInputRef.current?.click()}
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
              <path d="M7 9.5V2M4 5l3-3 3 3M2 9.5v1.5a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V9.5" />
            </svg>
            Upload LinkedIn PDF
          </button>
        </div>
      ) : (
        <>
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder={URL_TABS[activeTab].placeholder}
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
            {activeTab === "github" ? "Pull profile" : "Import CV"}
          </button>
        </>
      )}

      <p className="mt-auto border-t border-dashed border-rule pt-3.5 text-[11.5px] leading-relaxed text-ink-3">
        <strong className="font-semibold text-ink-2">Privacy:</strong> we read
        only what you provide to extract your skills and experience. We never
        post on your behalf.
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
