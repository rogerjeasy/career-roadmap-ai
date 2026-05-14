"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import type { OnboardingChatMessage } from "@/types/onboarding.types";

export interface DirectionChatProps {
  messages: OnboardingChatMessage[];
  userName?: string | null;
  onSend: (text: string) => void;
  onSelectChip: (messageId: string, chip: string) => void;
  isBotTyping?: boolean;
}

export function DirectionChat({
  messages,
  userName,
  onSend,
  onSelectChip,
  isBotTyping,
}: DirectionChatProps) {
  const [input, setInput] = useState("");
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [messages, isBotTyping]);

  const handleSend = () => {
    const text = input.trim();
    if (!text) return;
    onSend(text);
    setInput("");
  };

  const initials = userName
    ? userName
        .split(" ")
        .map((n) => n[0])
        .join("")
        .slice(0, 2)
        .toUpperCase()
    : "U";

  return (
    <div className="overflow-hidden rounded-2xl border border-rule bg-paper shadow-[0_12px_40px_-20px_rgba(21,20,15,0.1)]">
      {/* Chat header */}
      <div className="flex items-center gap-3 border-b border-rule bg-bg-2 px-5 py-4">
        <div className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-ink">
          <svg
            viewBox="0 0 18 18"
            fill="currentColor"
            className="h-[18px] w-[18px] text-terra-soft"
            aria-hidden="true"
          >
            <path d="M9 1l1.8 5 5 1.8-5 1.8L9 14.5l-1.8-5L2.2 7.8l5-1.8z" />
          </svg>
          <span
            aria-hidden="true"
            className="absolute -bottom-px -right-px h-2.5 w-2.5 rounded-full border-2 border-bg-2 bg-green"
          />
        </div>
        <div>
          <p className="text-[14px] font-semibold text-ink">Career Twin</p>
          <p className="mt-0.5 flex items-center gap-1.5 text-[11.5px] text-ink-3">
            <span className="h-[5px] w-[5px] rounded-full bg-green" aria-hidden="true" />
            Online · context loaded from your CV
          </p>
        </div>
        <div className="ml-auto flex items-center gap-1.5 rounded-md border border-rule bg-paper px-2.5 py-1.5 text-[11.5px] text-ink-2">
          <svg
            viewBox="0 0 12 12"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            className="h-3 w-3 opacity-60"
            aria-hidden="true"
          >
            <circle cx="6" cy="6" r="5" />
            <path d="M1 6h10M6 1c2 1.5 2 8.5 0 10M6 1c-2 1.5-2 8.5 0 10" />
          </svg>
          English
        </div>
      </div>

      {/* Messages */}
      <div
        ref={bodyRef}
        className="flex min-h-[360px] max-h-[460px] flex-col gap-[18px] overflow-y-auto bg-paper px-7 pb-3 pt-7 scroll-smooth"
      >
        {messages.map((msg) => (
          <ChatMessage
            key={msg.id}
            msg={msg}
            initials={initials}
            onSelectChip={onSelectChip}
          />
        ))}

        {isBotTyping && (
          <div className="flex max-w-[86%] items-start gap-3 self-start">
            <TwinAvatar />
            <div className="rounded-2xl rounded-tl-[4px] bg-bg px-4 py-3">
              <TypingDots />
            </div>
          </div>
        )}
      </div>

      {/* Composer */}
      <div className="flex items-center gap-2.5 border-t border-rule bg-bg px-5 py-3.5">
        <div className="flex flex-1 items-center gap-2.5 rounded-full border border-rule bg-paper px-4 py-1.5 focus-within:border-green">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="Type your reply… (or press Enter)"
            className="flex-1 border-none bg-transparent py-1.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:outline-none"
          />
        </div>
        <button
          type="button"
          onClick={handleSend}
          disabled={!input.trim()}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-ink text-bg transition-colors hover:bg-green-2 disabled:opacity-40"
          aria-label="Send"
        >
          <svg
            viewBox="0 0 14 14"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="h-3.5 w-3.5"
            aria-hidden="true"
          >
            <path d="M2 12L12 2M12 2H5M12 2v7" />
          </svg>
        </button>
      </div>
    </div>
  );
}

function ChatMessage({
  msg,
  initials,
  onSelectChip,
}: {
  msg: OnboardingChatMessage;
  initials: string;
  onSelectChip: (messageId: string, chip: string) => void;
}) {
  const isTwin = msg.from === "twin";

  return (
    <div
      className={cn(
        "flex max-w-[86%] gap-3",
        isTwin ? "self-start" : "self-end flex-row-reverse",
      )}
    >
      {isTwin ? <TwinAvatar /> : <UserAvatar initials={initials} />}
      <div>
        <div
          className={cn(
            "rounded-2xl px-4 py-3 text-[14px] leading-relaxed",
            isTwin ? "rounded-tl-[4px] bg-bg text-ink" : "rounded-tr-[4px] bg-green text-white",
          )}
        >
          {isTwin ? (
            <span dangerouslySetInnerHTML={{ __html: msg.content }} />
          ) : (
            <span>{msg.content}</span>
          )}

          {/* Choice chips */}
          {msg.chips && msg.chips.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {msg.chips.map((chip) => (
                <button
                  key={chip}
                  type="button"
                  onClick={() => onSelectChip(msg.id, chip)}
                  className={cn(
                    "rounded-full border px-3.5 py-2 text-[12.5px] font-medium transition-all duration-150",
                    msg.selectedChip === chip
                      ? "border-green bg-green text-white"
                      : "border-rule-strong bg-paper text-ink-2 hover:border-green hover:bg-green-faint hover:text-ink",
                  )}
                >
                  {chip}
                </button>
              ))}
            </div>
          )}
        </div>
        <p className="mt-1 font-mono text-[10px] tracking-[0.04em] text-ink-3">
          {msg.timestamp}
        </p>
      </div>
    </div>
  );
}

function TwinAvatar() {
  return (
    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-ink">
      <svg
        viewBox="0 0 14 14"
        fill="currentColor"
        className="h-[13px] w-[13px] text-terra-soft"
        aria-hidden="true"
      >
        <path d="M7 1l1.4 4 4 1.4-4 1.4L7 11.5l-1.4-4L1.6 6.4l4-1.4z" />
      </svg>
    </div>
  );
}

function UserAvatar({ initials }: { initials: string }) {
  return (
    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-green font-serif text-[11px] font-semibold text-white">
      {initials}
    </div>
  );
}

function TypingDots() {
  return (
    <div className="flex gap-1 py-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-ink-3"
          style={{ animationDelay: `${i * 0.2}s` }}
        />
      ))}
    </div>
  );
}

