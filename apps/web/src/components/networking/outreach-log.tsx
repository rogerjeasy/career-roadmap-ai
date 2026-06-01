import { cn } from "@/lib/utils";
import type { OutreachEntry } from "@/types/networking.types";

export interface OutreachLogProps {
  entries: OutreachEntry[];
  className?: string;
}

const CHANNEL_LABEL: Record<OutreachEntry["channel"], string> = {
  email: "Email",
  linkedin: "LinkedIn",
  in_person: "In person",
  other: "Other",
};

export function OutreachLog({ entries, className }: OutreachLogProps) {
  if (entries.length === 0) {
    return (
      <p className="rounded-[10px] border border-dashed border-rule-strong bg-paper px-4 py-6 text-center text-[13px] text-ink-3">
        No outreach logged yet.
      </p>
    );
  }

  return (
    <ul className={cn("space-y-px", className)}>
      {entries.map((entry) => (
        <li key={entry.id} className="flex items-start gap-3 border-b border-rule px-1 py-3 last:border-b-0">
          <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-green" aria-hidden="true" />
          <div className="min-w-0 flex-1">
            <p className="text-[13px] text-ink">
              <span className="font-semibold">{entry.contactName}</span>
              <span className="text-ink-3"> · {CHANNEL_LABEL[entry.channel]}</span>
            </p>
            <p className="mt-0.5 text-[12.5px] leading-snug text-ink-2">{entry.note}</p>
          </div>
          <span className="shrink-0 text-[11.5px] text-ink-3">{entry.timeLabel}</span>
        </li>
      ))}
    </ul>
  );
}
