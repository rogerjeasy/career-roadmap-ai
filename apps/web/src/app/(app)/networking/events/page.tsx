"use client";

import Link from "next/link";
import { ROUTES } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { EventCalendar } from "@/components/networking/event-calendar";
import type { NetworkingEvent } from "@/types/networking.types";

const EVENTS: NetworkingEvent[] = [
  { id: "e1", title: "Agentic Systems Meetup", kind: "meetup", dateLabel: "Jun 12", location: "Zürich", isOnline: false },
  { id: "e2", title: "LLM Eval Deep-Dive", kind: "webinar", dateLabel: "Jun 18", location: "Online", isOnline: true },
  { id: "e3", title: "AI Engineer Summit", kind: "conference", dateLabel: "Jun 26", location: "London", isOnline: false },
  { id: "e4", title: "Ask-Me-Anything: Career switching into ML", kind: "ama", dateLabel: "Jul 02", location: "Online", isOnline: true },
];

export default function NetworkingEventsPage() {
  return (
    <div className="mx-auto max-w-[760px] px-7 pb-24 pt-7">
      <Link
        href={ROUTES.networking}
        className="mb-4 inline-flex items-center gap-1 text-[12.5px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
      >
        ← Network
      </Link>
      <PageHeader
        eyebrow="Relationships"
        title="Events"
        description="Meetups, conferences, and sessions relevant to your target role."
      />
      <EventCalendar events={EVENTS} />
    </div>
  );
}
