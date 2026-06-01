"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { networkingApi } from "@/lib/api/networking";
import { ROUTES, QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { ContactCard } from "@/components/networking/contact-card";
import { ContactForm } from "@/components/networking/contact-form";
import type { Contact } from "@/types/networking.types";

export default function ContactsPage() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);

  const { data: contacts, isLoading } = useQuery({
    queryKey: QUERY_KEYS.contacts,
    queryFn: networkingApi.listContacts,
    staleTime: 60 * 1000,
  });

  const createMutation = useMutation({
    mutationFn: networkingApi.createContact,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.contacts });
      toast.success("Contact added");
      setShowForm(false);
    },
    onError: () => toast.error("Couldn't add the contact."),
  });

  const addContact = (data: Omit<Contact, "id" | "status">) => {
    createMutation.mutate({
      name: data.name,
      role: data.role,
      company: data.company,
      reason: data.reason ?? null,
    });
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

      {isLoading ? (
        <LoadingSpinner fullPage label="Loading contacts…" />
      ) : !contacts || contacts.length === 0 ? (
        <EmptyState title="No contacts yet" description="Add the people who can help you reach your goal." />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {contacts.map((c) => (
            <ContactCard key={c.id} contact={{ ...c, reason: c.reason ?? undefined }} />
          ))}
        </div>
      )}
    </div>
  );
}
