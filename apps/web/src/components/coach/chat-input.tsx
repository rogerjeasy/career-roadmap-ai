"use client";

import { useRef, useState, type KeyboardEvent } from "react";
import { cn } from "@/lib/utils";

export interface ChatInputProps {
  onSend: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function ChatInput({ onSend, disabled = false, placeholder }: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="flex items-end gap-2 rounded-[12px] border border-rule-strong bg-paper p-2 focus-within:border-green">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => {
          setValue(e.target.value);
          e.target.style.height = "auto";
          e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
        }}
        onKeyDown={onKeyDown}
        rows={1}
        disabled={disabled}
        placeholder={placeholder ?? "Ask your career coach anything…"}
        className="max-h-40 min-h-[24px] flex-1 resize-none bg-transparent px-2 py-1.5 text-[14px] leading-relaxed text-ink placeholder:text-ink-3 focus:outline-none disabled:opacity-60"
      />
      <button
        type="button"
        onClick={submit}
        disabled={disabled || value.trim().length === 0}
        aria-label="Send message"
        className={cn(
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-[9px] transition-colors duration-150",
          disabled || value.trim().length === 0
            ? "bg-bg-3 text-ink-3"
            : "bg-ink text-bg hover:bg-green-2",
        )}
      >
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" className="h-4 w-4" aria-hidden="true">
          <path d="M2 8l12-5-5 12-2-5z" strokeLinejoin="round" />
        </svg>
      </button>
    </div>
  );
}
