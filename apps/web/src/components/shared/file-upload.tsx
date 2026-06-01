"use client";

import { useCallback, useRef, useState, type DragEvent } from "react";
import { cn } from "@/lib/utils";

export interface FileUploadProps {
  /** Comma-separated accept string, e.g. ".pdf,.doc,.docx". */
  accept?: string;
  /** Max file size in megabytes. Rejected files trigger onError. */
  maxSizeMb?: number;
  disabled?: boolean;
  /** Helper line shown under the prompt. */
  hint?: string;
  onFileSelected: (file: File) => void;
  onError?: (message: string) => void;
  className?: string;
}

function UploadIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="h-7 w-7" aria-hidden="true">
      <path d="M12 16V4M12 4 7 9M12 4l5 5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" strokeLinecap="round" />
    </svg>
  );
}

export function FileUpload({
  accept = ".pdf,.doc,.docx",
  maxSizeMb = 10,
  disabled = false,
  hint,
  onFileSelected,
  onError,
  className,
}: FileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const handleFile = useCallback(
    (file: File | undefined) => {
      if (!file) return;
      if (file.size > maxSizeMb * 1024 * 1024) {
        onError?.(`File is larger than ${maxSizeMb} MB.`);
        return;
      }
      onFileSelected(file);
    },
    [maxSizeMb, onFileSelected, onError],
  );

  const onDrop = useCallback(
    (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setDragging(false);
      if (disabled) return;
      handleFile(e.dataTransfer.files?.[0]);
    },
    [disabled, handleFile],
  );

  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-disabled={disabled}
      onClick={() => !disabled && inputRef.current?.click()}
      onKeyDown={(e) => {
        if ((e.key === "Enter" || e.key === " ") && !disabled) inputRef.current?.click();
      }}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={cn(
        "flex w-full cursor-pointer flex-col items-center justify-center gap-3 rounded-[12px] border-2 border-dashed px-6 py-10 text-center transition-colors duration-150",
        dragging
          ? "border-green bg-green-faint"
          : "border-rule-strong bg-paper hover:border-green hover:bg-bg",
        disabled && "cursor-not-allowed opacity-60",
        className,
      )}
    >
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-bg-2 text-ink-3">
        <UploadIcon />
      </span>
      <div>
        <p className="text-[14px] font-medium text-ink">
          Drop your file here or <span className="text-terra">browse</span>
        </p>
        <p className="mt-1 text-[12px] text-ink-3">
          {hint ?? `${accept.replaceAll(".", "").toUpperCase().replaceAll(",", " · ")} · up to ${maxSizeMb} MB`}
        </p>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        disabled={disabled}
        className="hidden"
        onChange={(e) => {
          handleFile(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
    </div>
  );
}
