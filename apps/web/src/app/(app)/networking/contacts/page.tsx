"use client";

import { useState } from "react";
import Link from "next/link";
import { ROUTES } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { ContactCard } from "@/components/networking/contact-card";
import { ContactForm } from "@/components/networking/contact-form";
import type { Contact } from "@/types/networking.types";

const INITIAL: Contact[] = [
  { id: "c1", name: "Maya Chen", role: "Staff ML Engineer", company: "Anthropic", status: "responded", reason: "Works on agent evaluation.", lastTouchLabel: "2d ago" },
  { id: "c2", name: "Tomás Rivera", role: "Eng Manager", company: "Hugging Face", status: "to_reach", reason: "Hiring for applied ML roles." },
  { id: "c3", name: "Priya Nair", role: "AI Researcher", company: "DeepMind", status: "connected", reason: "Met at the LangGraph meetup.", lastTouchLabel: "1w ago" },
  { id: "c4", name: "Jonas Berg", role: "Recruiter", company: "Scale AI", status: "contacted", lastTouchLabel: "4d ago" },
];

export default function ContactsPage() {
  const [contacts, setContacts] = useState<Contact[]>(INITIAL);
  const [showForm, setShowForm] = useState(false);

  const addContact = (data: Omit<Contact, "id" | "status">) => {
    setContacts((prev) => [
      { ...data, id: `c-${Date.now()}`, status: "to_reach" },
      ...prev,
    ]);
    setShowForm(false);
  };

  return (
    <div className="mx-auto max-w-[1000px] px-7 pb-24 pt-7">
      <Link
        href={ROUTES.networking}
        className="mb-4 inline-flex items-center gap-1 text-[12.5px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
      >
        ← Network
      </Link>
      <PageHeader
        eyebrow="Relationships"
        title="Contacts"
        description="Everyone in your career network, with where each relationship stands."
        actions={
          <button
            type="button"
            onClick={() => setShowForm((v) => !v)}
            className="inline-flex items-center rounded-[7px] bg-ink px-3.5 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2"
          >
            {showForm ? "Close" : "+ Add contact"}
          </button>
        }
      />

      {showForm && (
        <div className="mb-6">
          <ContactForm onAdd={addContact} onCancel={() => setShowForm(false)} />
        </div>
      )}

      {contacts.length === 0 ? (
        <EmptyState title="No contacts yet" description="Add the people who can help you reach your goal." />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {contacts.map((c) => (
            <ContactCard key={c.id} contact={c} />
          ))}
        </div>
      )}
    </div>
  );
}
