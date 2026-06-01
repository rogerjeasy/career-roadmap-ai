"use client";

import { useState, type FormEvent } from "react";
import type { Contact } from "@/types/networking.types";

export interface ContactFormProps {
  onAdd: (contact: Omit<Contact, "id" | "status">) => void;
  onCancel?: () => void;
}

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

export function ContactForm({ onAdd, onCancel }: ContactFormProps) {
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [company, setCompany] = useState("");
  const [reason, setReason] = useState("");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    onAdd({
      name: name.trim(),
      role: role.trim(),
      company: company.trim(),
      reason: reason.trim() || undefined,
    });
    setName("");
    setRole("");
    setCompany("");
    setReason("");
  };

  return (
    <form onSubmit={submit} className="space-y-3 rounded-[12px] border border-rule bg-paper p-5">
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="block">
          <span className="mb-1 block text-[12px] font-medium text-ink-2">Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Ada Lovelace" className={FIELD_CLASS} />
        </label>
        <label className="block">
          <span className="mb-1 block text-[12px] font-medium text-ink-2">Role</span>
          <input value={role} onChange={(e) => setRole(e.target.value)} placeholder="ML Engineer" className={FIELD_CLASS} />
        </label>
        <label className="block">
          <span className="mb-1 block text-[12px] font-medium text-ink-2">Company</span>
          <input value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Anthropic" className={FIELD_CLASS} />
        </label>
      </div>
      <label className="block">
        <span className="mb-1 block text-[12px] font-medium text-ink-2">Why connect? (optional)</span>
        <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Met at the AI meetup — works on agent eval" className={FIELD_CLASS} />
      </label>
      <div className="flex justify-end gap-2 pt-1">
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="rounded-[7px] border border-rule-strong bg-paper px-4 py-2 text-[13px] font-medium text-ink-2 transition-colors duration-150 hover:bg-bg-2"
          >
            Cancel
          </button>
        )}
        <button
          type="submit"
          disabled={!name.trim()}
          className="rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-50"
        >
          Add contact
        </button>
      </div>
    </form>
  );
}
