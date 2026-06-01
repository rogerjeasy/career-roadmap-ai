import { cn } from "@/lib/utils";

const SIZES = {
  sm: "h-4 w-4 border-2",
  md: "h-6 w-6 border-2",
  lg: "h-9 w-9 border-[3px]",
} as const;

export interface LoadingSpinnerProps {
  size?: keyof typeof SIZES;
  label?: string;
  /** Centre the spinner (and label) in a full-height flex column. */
  fullPage?: boolean;
  className?: string;
}

export function LoadingSpinner({
  size = "md",
  label,
  fullPage = false,
  className,
}: LoadingSpinnerProps) {
  const spinner = (
    <span
      role="status"
      aria-live="polite"
      className={cn("inline-flex items-center gap-2.5", className)}
    >
      <span
        className={cn(
          "inline-block animate-spin rounded-full border-rule-strong border-t-green",
          SIZES[size],
        )}
        aria-hidden="true"
      />
      {label ? (
        <span className="text-[13px] text-ink-3">{label}</span>
      ) : (
        <span className="sr-only">Loading</span>
      )}
    </span>
  );

  if (!fullPage) return spinner;

  return (
    <div className="flex min-h-[240px] w-full flex-col items-center justify-center gap-3 py-12">
      {spinner}
    </div>
  );
}
