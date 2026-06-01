import { cn } from "@/lib/utils";
import type { Contact, ContactStatus } from "@/types/networking.types";

export interface ContactCardProps {
  contact: Contact;
  className?: string;
}

const STATUS_META: Record<ContactStatus, { label: string; chip: string }> = {
  to_reach: { label: "To reach", chip: "bg-bg-3 text-ink-2" },
  contacted: { label: "Contacted", chip: "bg-gold-soft text-gold" },
  responded: { label: "Responded", chip: "bg-terra-soft text-terra-2" },
  connected: { label: "Connected", chip: "bg-green-soft text-green-2" },
};

function initials(name: string): string {
  return name
    .split(" ")
    .map((p) => p[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

export function ContactCard({ contact, className }: ContactCardProps) {
  const meta = STATUS_META[contact.status];

  return (
    <article className={cn("flex gap-3.5 rounded-[12px] border border-rule bg-paper p-5", className)}>
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] bg-green font-serif text-[14px] font-medium text-white">
        {initials(contact.name)}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="truncate text-[14px] font-semibold text-ink">{contact.name}</h3>
            <p className="truncate text-[12.5px] text-ink-2">
              {contact.role} · {contact.company}
            </p>
          </div>
          <span className={cn("shrink-0 rounded-[5px] px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.04em]", meta.chip)}>
            {meta.label}
          </span>
        </div>
        {contact.reason && (
          <p className="mt-2 text-[12.5px] leading-snug text-ink-3">{contact.reason}</p>
        )}
        {contact.lastTouchLabel && (
          <p className="mt-2 text-[11.5px] text-ink-3">Last touch · {contact.lastTouchLabel}</p>
        )}
      </div>
    </article>
  );
}
