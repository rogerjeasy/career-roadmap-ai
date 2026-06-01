import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface PageHeaderProps {
  /** Small uppercase label rendered above the title. */
  eyebrow?: string;
  title: string;
  description?: string;
  /** Right-aligned actions (buttons, filters). Wraps below title on mobile. */
  actions?: ReactNode;
  className?: string;
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  className,
}: PageHeaderProps) {
  return (
    <div
      className={cn(
        "mb-7 flex flex-col gap-4 border-b border-rule pb-6 sm:flex-row sm:items-end sm:justify-between",
        className,
      )}
    >
      <div className="min-w-0">
        {eyebrow && (
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-terra">
            {eyebrow}
          </p>
        )}
        <h1 className="font-serif text-[26px] font-medium leading-[1.1] tracking-[-0.02em] text-ink sm:text-[30px]">
          {title}
        </h1>
        {description && (
          <p className="mt-2 max-w-[560px] text-[13.5px] leading-relaxed text-ink-2">
            {description}
          </p>
        )}
      </div>
      {actions && (
        <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
      )}
    </div>
  );
}
