import { cn } from "@/lib/utils";
import type { SkillStatus } from "@/types/skill-graph.types";

const STATUS_STYLE: Record<SkillStatus, string> = {
  have: "border-green/30 bg-green-soft text-green-2",
  acquired: "border-green/30 bg-green-soft text-green-2",
  learning: "border-terra/30 bg-terra-soft text-terra-2",
  planned: "border-rule bg-bg-2 text-ink-2",
};

// A small leading glyph reinforces status without relying on colour alone.
const STATUS_MARK: Record<SkillStatus, string> = {
  have: "✓",
  acquired: "✓",
  learning: "◐",
  planned: "○",
};

export interface SkillChipProps {
  label: string;
  status: SkillStatus;
  className?: string;
}

export function SkillChip({ label, status, className }: SkillChipProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-[6px] border px-2.5 py-1 text-[12.5px] font-medium",
        STATUS_STYLE[status],
        className,
      )}
    >
      <span aria-hidden="true" className="text-[10px] leading-none opacity-80">
        {STATUS_MARK[status]}
      </span>
      <span className="min-w-0 break-words">{label}</span>
    </span>
  );
}
