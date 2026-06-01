import { cn } from "@/lib/utils";
import type { NetworkingEvent } from "@/types/networking.types";

export interface EventCalendarProps {
  events: NetworkingEvent[];
  className?: string;
}

const KIND_CHIP: Record<NetworkingEvent["kind"], string> = {
  meetup: "bg-green-soft text-green-2",
  conference: "bg-terra-soft text-terra-2",
  webinar: "bg-gold-soft text-gold",
  ama: "bg-bg-3 text-ink-2",
};

export function EventCalendar({ events, className }: EventCalendarProps) {
  if (events.length === 0) {
    return (
      <p className="rounded-[10px] border border-dashed border-rule-strong bg-paper px-4 py-6 text-center text-[13px] text-ink-3">
        No upcoming events.
      </p>
    );
  }

  return (
    <ul className={cn("space-y-3", className)}>
      {events.map((event) => (
        <li key={event.id} className="flex items-start gap-3.5 rounded-[12px] border border-rule bg-paper p-4">
          <div className="flex h-12 w-12 shrink-0 flex-col items-center justify-center rounded-[9px] bg-bg-2 text-center">
            <span className="font-mono text-[10px] uppercase text-ink-3">{event.dateLabel.split(" ")[0]}</span>
            <span className="font-serif text-[16px] font-medium leading-none text-ink">
              {event.dateLabel.split(" ")[1] ?? ""}
            </span>
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-2">
              <h3 className="min-w-0 text-[14px] font-semibold leading-snug text-ink">{event.title}</h3>
              <span className={cn("shrink-0 rounded-[5px] px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.04em]", KIND_CHIP[event.kind])}>
                {event.kind}
              </span>
            </div>
            <p className="mt-1 text-[12.5px] text-ink-3">
              {event.isOnline ? "Online" : event.location} · {event.dateLabel}
            </p>
          </div>
        </li>
      ))}
    </ul>
  );
}
