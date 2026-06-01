"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { networkingApi } from "@/lib/api/networking";
import { ROUTES, QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EventCalendar } from "@/components/networking/event-calendar";
import type { NetworkingEvent } from "@/types/networking.types";

const SAMPLE_EVENTS: NetworkingEvent[] = [
  { id: "e1", title: "Agentic Systems Meetup", kind: "meetup", dateLabel: "Jun 12", location: "Zürich", isOnline: false },
  { id: "e2", title: "LLM Eval Deep-Dive", kind: "webinar", dateLabel: "Jun 18", location: "Online", isOnline: true },
  { id: "e3", title: "AI Engineer Summit", kind: "conference", dateLabel: "Jun 26", location: "London", isOnline: false },
  { id: "e4", title: "Ask-Me-Anything: Career switching into ML", kind: "ama", dateLabel: "Jul 02", location: "Online", isOnline: true },
];

export default function NetworkingEventsPage() {
  const { data: events, isLoading } = useQuery({
    queryKey: QUERY_KEYS.networkingEvents,
    queryFn: networkingApi.listEvents,
    staleTime: 60 * 1000,
  });

  const list: NetworkingEvent[] =
    events && events.length > 0
      ? events.map((e) => ({
          id: e.id,
          title: e.title,
          kind: e.kind,
          dateLabel: e.dateLabel,
          location: e.location,
          isOnline: e.isOnline,
        }))
      : SAMPLE_EVENTS;

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
      {isLoading ? <LoadingSpinner fullPage label="Loading events…" /> : <EventCalendar events={list} />}
    </div>
  );
}
