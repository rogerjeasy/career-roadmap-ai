"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { networkingApi } from "@/lib/api/networking";
import { formatRelative } from "@/lib/date";
import { ROUTES, QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { ContactCard } from "@/components/networking/contact-card";
import { EventCalendar } from "@/components/networking/event-calendar";
import { OutreachLog } from "@/components/networking/outreach-log";
import type { Contact, NetworkingEvent, OutreachEntry } from "@/types/networking.types";

function SectionHint({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-[12px] border border-dashed border-rule bg-paper px-5 py-8 text-center text-[12.5px] text-ink-3">
      {children}
    </div>
  );
}

export default function NetworkingPage() {
  const { data: liveContacts, isLoading: contactsLoading } = useQuery({
    queryKey: QUERY_KEYS.contacts,
    queryFn: networkingApi.listContacts,
    staleTime: 60 * 1000,
  });
  const { data: liveEvents, isLoading: eventsLoading } = useQuery({
    queryKey: QUERY_KEYS.networkingEvents,
    queryFn: networkingApi.listEvents,
    staleTime: 60 * 1000,
  });
  const { data: liveOutreach, isLoading: outreachLoading } = useQuery({
    queryKey: QUERY_KEYS.outreach,
    queryFn: () => networkingApi.listOutreach(10),
    staleTime: 60 * 1000,
  });

  const contacts: Contact[] = (liveContacts ?? []).slice(0, 4).map((c) => ({
    id: c.id,
    name: c.name,
    role: c.role,
    company: c.company,
    status: c.status,
    reason: c.reason ?? undefined,
  }));

  const events: NetworkingEvent[] = (liveEvents ?? []).slice(0, 4).map((e) => ({
    id: e.id,
    title: e.title,
    kind: e.kind,
    dateLabel: e.dateLabel,
    location: e.location,
    isOnline: e.isOnline,
  }));

  const outreach: OutreachEntry[] = (liveOutreach ?? []).map((o) => ({
    id: o.id,
    contactName: o.contactName,
    channel: o.channel,
    note: o.note,
    timeLabel: formatRelative(o.createdAt),
  }));

  return (
    <div className="mx-auto max-w-[1100px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Relationships"
        title="Network"
        description="The people and events that move your career forward — tracked alongside your roadmap."
        actions={
          <Link
            href={ROUTES.networking + "/contacts"}
            className="inline-flex items-center rounded-[7px] bg-ink px-3.5 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2"
          >
            Manage contacts
          </Link>
        }
      />

      <div className="grid gap-7 lg:grid-cols-[1fr_320px]">
        <section>
          <div className="mb-3.5 flex items-center justify-between">
            <h2 className="font-serif text-[18px] font-medium tracking-[-0.01em] text-ink">Key contacts</h2>
            <Link href={ROUTES.networking + "/contacts"} className="text-[12px] font-medium text-ink-3 hover:text-ink">
              View all →
            </Link>
          </div>
          {contactsLoading ? (
            <SectionHint>Loading contacts…</SectionHint>
          ) : contacts.length > 0 ? (
            <div className="grid gap-4 sm:grid-cols-2">
              {contacts.map((c) => (
                <ContactCard key={c.id} contact={c} />
              ))}
            </div>
          ) : (
            <SectionHint>
              No contacts yet.{" "}
              <Link href={ROUTES.networking + "/contacts"} className="font-medium text-ink-2 hover:text-ink">
                Add the people who can help you reach your goal →
              </Link>
            </SectionHint>
          )}

          <h2 className="mb-3 mt-8 font-serif text-[18px] font-medium tracking-[-0.01em] text-ink">Recent outreach</h2>
          {outreachLoading ? (
            <SectionHint>Loading outreach…</SectionHint>
          ) : outreach.length > 0 ? (
            <div className="rounded-[12px] border border-rule bg-paper px-5 py-2">
              <OutreachLog entries={outreach} />
            </div>
          ) : (
            <SectionHint>Log a message or conversation to start building your outreach history.</SectionHint>
          )}
        </section>

        <aside>
          <div className="mb-3.5 flex items-center justify-between">
            <h2 className="font-serif text-[18px] font-medium tracking-[-0.01em] text-ink">Upcoming events</h2>
            <Link href={ROUTES.networking + "/events"} className="text-[12px] font-medium text-ink-3 hover:text-ink">
              All →
            </Link>
          </div>
          {eventsLoading ? (
            <SectionHint>Loading events…</SectionHint>
          ) : events.length > 0 ? (
            <EventCalendar events={events} />
          ) : (
            <SectionHint>No events tracked yet. Add meetups and conferences relevant to your target role.</SectionHint>
          )}
        </aside>
      </div>
    </div>
  );
}
