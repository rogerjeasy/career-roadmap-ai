"use client";

import { useCoach } from "@/hooks/use-coach";
import { ChatWindow } from "@/components/coach/chat-window";
import { ChatInput } from "@/components/coach/chat-input";
import { LoadingSpinner } from "@/components/shared/loading-spinner";

const SUGGESTIONS = [
  "What should I focus on this week?",
  "Where are my biggest skill gaps?",
  "Is my timeline realistic?",
  "How's the market for my target role?",
];

export default function CoachPage() {
  const { messages, send, isThinking, isLoadingHistory, error } = useCoach();

  return (
    <div className="mx-auto flex h-[calc(100vh-60px)] max-w-[820px] flex-col px-4 sm:px-7">
      {isLoadingHistory ? (
        <LoadingSpinner fullPage label="Loading your conversation…" />
      ) : (
        <ChatWindow messages={messages} suggestions={SUGGESTIONS} onSuggestion={send} />
      )}

      <div className="shrink-0 pb-5 pt-2">
        {error && (
          <p className="mb-2 text-center text-[12px] text-terra-2" role="alert">
            {error}
          </p>
        )}
        <ChatInput onSend={send} disabled={isThinking} />
        <p className="mt-2 text-center text-[11px] text-ink-3">
          The coach can make mistakes. Verify important career decisions.
        </p>
      </div>
    </div>
  );
}
