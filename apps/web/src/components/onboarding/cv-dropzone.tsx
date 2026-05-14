"use client";

import { useCallback, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import type { CvAnalysisResult } from "@/types/onboarding.types";

export interface CvDropzoneProps {
  file: File | null;
  isAnalyzing: boolean;
  cvResult: CvAnalysisResult | null;
  onFileSelect: (file: File) => void;
  onReplace: () => void;
}

function UploadIcon() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 4v12M7 9l5-5 5 5M4 19h16" />
    </svg>
  );
}

function FileTypeIcon({ ext }: { ext: string }) {
  return (
    <div className="relative flex h-[50px] w-10 shrink-0 items-center justify-center rounded-[5px] border border-rule bg-bg-2 font-serif text-[13px] font-medium italic text-terra-2">
      {ext.toUpperCase().slice(0, 4)}
      <span
        aria-hidden="true"
        className="absolute right-0 top-0 h-2.5 w-2.5"
        style={{
          background: "linear-gradient(225deg, #C9BFA7 50%, transparent 50%)",
        }}
      />
    </div>
  );
}

function CheckTick() {
  return (
    <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-green">
      <svg viewBox="0 0 12 12" fill="none" className="h-[9px] w-[9px]">
        <path
          d="M2 6.5l3 3 5-7"
          stroke="#fff"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}

const PARSE_STEPS = [
  (r: CvAnalysisResult) =>
    `Found <b>${r.roles.length} role${r.roles.length !== 1 ? "s" : ""}</b> across <b>${r.yearsOfExperience} year${r.yearsOfExperience !== 1 ? "s" : ""}</b> of experience`,
  (r: CvAnalysisResult) =>
    `Detected <b>${r.skills.length} skills</b> · ${r.strongSkillsCount} strong, ${r.supportingSkillsCount} supporting`,
  (r: CvAnalysisResult) =>
    `Identified <b>${r.projects.length} standout project${r.projects.length !== 1 ? "s" : ""}</b>${r.leadershipSignals > 0 ? ` and <b>${r.leadershipSignals} leadership signal${r.leadershipSignals !== 1 ? "s" : ""}</b>` : ""}`,
  (r: CvAnalysisResult) => {
    const edu = r.education[0];
    if (!edu) return null;
    const parts = [edu.field, edu.institution, edu.year].filter(Boolean).join(" · ");
    return `Education in <b>${edu.degree}${parts ? ` · ${parts}` : ""}</b>`;
  },
];

export function CvDropzone({
  file,
  isAnalyzing,
  cvResult,
  onFileSelect,
  onReplace,
}: CvDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => setIsDragging(false), []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const dropped = e.dataTransfer.files[0];
      if (dropped) onFileSelect(dropped);
    },
    [onFileSelect],
  );

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const picked = e.target.files?.[0];
      if (picked) onFileSelect(picked);
    },
    [onFileSelect],
  );

  const ext = file?.name.split(".").pop()?.toUpperCase() ?? "FILE";
  const sizeKb = file ? Math.round(file.size / 1024) : 0;
  const hasFile = !!file;

  return (
    <div
      className={cn(
        "relative min-h-[360px] overflow-hidden rounded-2xl border bg-paper transition-all duration-200",
        !hasFile && "flex cursor-pointer flex-col items-center justify-center p-7 text-center",
        !hasFile && !isDragging && "border-dashed border-rule-strong hover:border-green hover:bg-green-faint",
        !hasFile && isDragging && "border-green bg-green-faint",
        hasFile && "flex flex-col gap-4 border-green p-6",
      )}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onClick={!hasFile ? () => inputRef.current?.click() : undefined}
      role={!hasFile ? "button" : undefined}
      tabIndex={!hasFile ? 0 : undefined}
      onKeyDown={
        !hasFile
          ? (e) => e.key === "Enter" && inputRef.current?.click()
          : undefined
      }
      aria-label={!hasFile ? "Upload your CV" : undefined}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.docx,.txt,.md"
        className="sr-only"
        onChange={handleInputChange}
      />

      {/* â”€â”€ Empty state â”€â”€ */}
      {!hasFile && (
        <div className="flex flex-col items-center">
          <div
            className={cn(
              "mb-[18px] flex h-14 w-14 items-center justify-center rounded-2xl text-ink-2 transition-all duration-200",
              isDragging ? "bg-green text-white" : "bg-bg-2",
            )}
          >
            <UploadIcon />
          </div>
          <p className="mb-2 font-serif text-[22px] font-[450] tracking-[-0.01em] text-ink">
            Drop your CV here
          </p>
          <p className="mb-[18px] max-w-[280px] text-[13px] leading-relaxed text-ink-3">
            Drag &amp; drop your file, or pick from your computer.
          </p>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              inputRef.current?.click();
            }}
            className="mb-3.5 rounded-[7px] bg-ink px-[18px] py-[9px] text-[13px] font-medium text-bg"
          >
            Choose a file
          </button>
          <p className="font-mono text-[10.5px] tracking-[0.08em] text-ink-3">
            PDF · DOCX · TXT · max 10 MB
          </p>
        </div>
      )}

      {/* â”€â”€ File state â”€â”€ */}
      {hasFile && (
        <>
          {/* File row */}
          <div className="grid grid-cols-[40px_1fr_auto] items-center gap-3.5 border-b border-rule pb-4">
            <FileTypeIcon ext={ext} />
            <div className="min-w-0">
              <p className="truncate text-[13.5px] font-semibold text-ink">{file?.name}</p>
              <p className="mt-0.5 flex flex-wrap items-center gap-2 text-[11.5px] text-ink-3">
                <span>{sizeKb} KB</span>
                {cvResult && (
                  <>
                    <span className="text-rule-strong">·</span>
                    <span className="flex items-center gap-1 font-semibold text-green">
                      âœ“ Parsed
                    </span>
                  </>
                )}
                {isAnalyzing && (
                  <>
                    <span className="text-rule-strong">·</span>
                    <span className="text-ink-3">Analysing…</span>
                  </>
                )}
              </p>
            </div>
            <button
              type="button"
              onClick={onReplace}
              className="flex items-center gap-1 text-[12px] font-medium text-ink-3 transition-colors hover:text-ink"
            >
              Replace
            </button>
          </div>

          {/* Progress bar */}
          {isAnalyzing && (
            <div>
              <div className="mb-2 flex items-center justify-between text-[11.5px]">
                <span className="font-medium text-ink-2">Extracting your professional profile…</span>
                <span className="font-mono font-semibold text-green">
                  <ProgressPct />
                </span>
              </div>
              <div className="h-1 overflow-hidden rounded-full bg-bg-2">
                <div className="h-full animate-[parseBar_2.4s_ease-out_forwards] rounded-full bg-green" />
              </div>
            </div>
          )}

          {/* Completed progress bar */}
          {cvResult && !isAnalyzing && (
            <div>
              <div className="mb-2 flex items-center justify-between text-[11.5px]">
                <span className="font-medium text-ink-2">Profile extracted successfully</span>
                <span className="font-mono font-semibold text-green">100%</span>
              </div>
              <div className="h-1 overflow-hidden rounded-full bg-bg-2">
                <div className="h-full w-full rounded-full bg-green" />
              </div>
            </div>
          )}

          {/* Parse steps */}
          {cvResult && (
            <div className="flex flex-col gap-2.5">
              {PARSE_STEPS.map((getLabel, i) => {
                const html = getLabel(cvResult);
                if (!html) return null;
                return (
                  <div
                    key={i}
                    className="flex items-center gap-2.5 text-[12.5px] text-ink-2"
                    style={{
                      animation: `slideIn 0.4s ease-out ${i * 0.3}s both`,
                    }}
                  >
                    <CheckTick />
                    <span dangerouslySetInnerHTML={{ __html: html }} />
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      <style>{`
        @keyframes parseBar { from { width: 0; } to { width: 100%; } }
        @keyframes slideIn {
          from { opacity: 0; transform: translateX(-8px); }
          to   { opacity: 1; transform: translateX(0); }
        }
      `}</style>
    </div>
  );
}

function ProgressPct() {
  return <>…</>;
}

