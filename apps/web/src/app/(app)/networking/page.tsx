"use client";

import Link from "next/link";
import { ROUTES } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { ContactCard } from "@/components/networking/contact-card";
import { EventCalendar } from "@/components/networking/event-calendar";
import { OutreachLog } from "@/components/networking/outreach-log";
import type { Contact, NetworkingEvent, OutreachEntry } from "@/types/networking.types";

const CONTACTS: Contact[] = [
  { id: "c1", name: "Maya Chen", role: "Staff ML Engineer", company: "Anthropic", status: "responded", reason: "Works on agent evaluation — could advise on your eval milestone.", lastTouchLabel: "2d ago" },
  { id: "c2", name: "Tomás Rivera", role: "Eng Manager", company: "Hugging Face", status: "to_reach", reason: "Hiring for applied ML roles in your target band." },
  { id: "c3", name: "Priya Nair", role: "AI Researcher", company: "DeepMind", status: "connected", reason: "Met at the LangGraph meetup.", lastTouchLabel: "1w ago" },
];

const EVENTS: NetworkingEvent[] = [
  { id: "e1", title: "Agentic Systems Meetup", kind: "meetup", dateLabel: "Jun 12", location: "Zürich", isOnline: false },
  { id: "e2", title: "LLM Eval Deep-Dive (webinar)", kind: "webinar", dateLabel: "Jun 18", location: "Online", isOnline: true },
];

const OUTREACH: OutreachEntry[] = [
  { id: "o1", contactName: "Maya Chen", channel: "linkedin", note: "Asked about her eval framework talk — she shared slides.", timeLabel: "2d ago" },
  { id: "o2", contactName: "Priya Nair", channel: "in_person", note: "Chatted at the meetup about agent orchestration patterns.", timeLabel: "1w ago" },
];

export default function NetworkingPage() {
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
          <div className="grid gap-4 sm:grid-cols-2">
            {CONTACTS.map((c) => (
              <ContactCard key={c.id} contact={c} />
            ))}
          </div>

          <h2 className="mb-3 mt-8 font-serif text-[18px] font-medium tracking-[-0.01em] text-ink">Recent outreach</h2>
          <div className="rounded-[12px] border border-rule bg-paper px-5 py-2">
            <OutreachLog entries={OUTREACH} />
          </div>
        </section>

        <aside>
          <div className="mb-3.5 flex items-center justify-between">
            <h2 className="font-serif text-[18px] font-medium tracking-[-0.01em] text-ink">Upcoming events</h2>
            <Link href={ROUTES.networking + "/events"} className="text-[12px] font-medium text-ink-3 hover:text-ink">
              All →
            </Link>
          </div>
          <EventCalendar events={EVENTS} />
        </aside>
      </div>
    </div>
  );
}
