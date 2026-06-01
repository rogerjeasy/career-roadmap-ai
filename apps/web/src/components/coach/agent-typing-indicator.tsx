import { cn } from "@/lib/utils";

export interface AgentTypingIndicatorProps {
  className?: string;
}

export function AgentTypingIndicator({ className }: AgentTypingIndicatorProps) {
  return (
    <span
      className={cn("inline-flex items-center gap-1", className)}
      role="status"
      aria-label="Coach is typing"
    >
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className={cn(
            "h-1.5 w-1.5 rounded-full bg-ink-3",
            i === 0 && "animate-bounce [animation-delay:-0.3s]",
            i === 1 && "animate-bounce [animation-delay:-0.15s]",
            i === 2 && "animate-bounce",
          )}
        />
      ))}
    </span>
  );
}
