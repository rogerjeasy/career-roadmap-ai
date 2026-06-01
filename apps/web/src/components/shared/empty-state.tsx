import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface EmptyStateProps {
  /** Optional leading icon or illustration. */
  icon?: ReactNode;
  title: string;
  description?: string;
  /** Optional call-to-action rendered below the copy (e.g. a Button or Link). */
  action?: ReactNode;
  className?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-[12px] border border-dashed border-rule-strong bg-paper px-6 py-12 text-center",
        className,
      )}
    >
      {icon && (
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-bg-2 text-ink-3">
          {icon}
        </div>
      )}
      <p className="font-serif text-[16px] font-medium tracking-[-0.01em] text-ink">
        {title}
      </p>
      {description && (
        <p className="mt-1.5 max-w-[340px] text-[13px] leading-relaxed text-ink-3">
          {description}
        </p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
