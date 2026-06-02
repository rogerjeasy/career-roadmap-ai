"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { networkingApi } from "@/lib/api/networking";
import { ROUTES, QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { EventCalendar } from "@/components/networking/event-calendar";
import type { NetworkingEvent } from "@/types/networking.types";

export default function NetworkingEventsPage() {
  const { data: events, isLoading } = useQuery({
    queryKey: QUERY_KEYS.networkingEvents,
    queryFn: networkingApi.listEvents,
    staleTime: 60 * 1000,
  });

  const list: NetworkingEvent[] = (events ?? []).map((e) => ({
    id: e.id,
    title: e.title,
    kind: e.kind,
    dateLabel: e.dateLabel,
    location: e.location,
    isOnline: e.isOnline,
  }));

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
      {isLoading ? (
        <LoadingSpinner fullPage label="Loading events…" />
      ) : list.length > 0 ? (
        <EventCalendar events={list} />
      ) : (
        <EmptyState
          title="No events yet"
          description="Track meetups, conferences, and webinars relevant to your target role."
        />
      )}
    </div>
  );
}
