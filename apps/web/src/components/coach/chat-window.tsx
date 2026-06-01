"use client";

import { useEffect, useRef } from "react";
import type { CoachMessage } from "@/hooks/use-coach";
import { ChatMessage } from "./chat-message";

export interface ChatWindowProps {
  messages: CoachMessage[];
  /** Suggested starter prompts shown when the thread is empty. */
  suggestions?: string[];
  onSuggestion?: (text: string) => void;
}

export function ChatWindow({ messages, suggestions = [], onSuggestion }: ChatWindowProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center px-4 text-center">
        <span className="mb-4 flex h-12 w-12 items-center justify-center rounded-[12px] bg-green font-serif text-[16px] font-medium text-white">
          AI
        </span>
        <h2 className="font-serif text-[20px] font-medium tracking-[-0.01em] text-ink">
          Your career coach
        </h2>
        <p className="mt-2 max-w-[420px] text-[13.5px] leading-relaxed text-ink-2">
          Ask about your roadmap, skill gaps, the job market, or what to focus on next.
          Answers are grounded in your profile and live market data.
        </p>
        {suggestions.length > 0 && (
          <div className="mt-6 flex max-w-[520px] flex-wrap justify-center gap-2">
            {suggestions.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => onSuggestion?.(s)}
                className="rounded-full border border-rule-strong bg-paper px-3.5 py-1.5 text-[12.5px] text-ink-2 transition-colors duration-150 hover:border-green hover:text-ink"
              >
                {s}
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-y-auto px-1 py-4">
      {messages.map((m) => (
        <ChatMessage key={m.id} message={m} />
      ))}
      <div ref={endRef} />
    </div>
  );
}
