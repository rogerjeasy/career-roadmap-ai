import { cn } from "@/lib/utils";
import type { CoachMessage } from "@/hooks/use-coach";
import { AgentTypingIndicator } from "./agent-typing-indicator";

export interface ChatMessageProps {
  message: CoachMessage;
}

/**
 * Renders one chat turn. Assistant content may contain newlines from the
 * coach's markdown narrative — we preserve paragraph breaks without pulling in
 * a full markdown renderer.
 */
export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === "user";
  const showTyping = !isUser && message.streaming && message.content.length === 0;

  return (
    <div className={cn("flex gap-3", isUser ? "flex-row-reverse" : "flex-row")}>
      {/* Avatar */}
      <span
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-[8px] font-serif text-[13px] font-medium",
          isUser ? "bg-bg-3 text-ink-2" : "bg-green text-white",
        )}
        aria-hidden="true"
      >
        {isUser ? "You" : "AI"}
      </span>

      {/* Bubble */}
      <div
        className={cn(
          "max-w-[78%] rounded-[12px] px-4 py-2.5 text-[13.5px] leading-relaxed",
          isUser
            ? "bg-ink text-bg"
            : "border border-rule bg-paper text-ink",
        )}
      >
        {showTyping ? (
          <AgentTypingIndicator />
        ) : (
          message.content.split("\n").map((line, i) =>
            line.trim() === "" ? (
              <br key={i} />
            ) : (
              <p key={i} className={cn(i > 0 && "mt-2")}>
                {line}
              </p>
            ),
          )
        )}
      </div>
    </div>
  );
}
