"use client";

import { useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { contactApi, type ContactTopic } from "@/lib/api/contact";

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[14px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

const TOPICS: { value: ContactTopic; label: string }[] = [
  { value: "general", label: "General enquiry" },
  { value: "sales", label: "Sales — teams & cohorts" },
  { value: "support", label: "Support" },
  { value: "partnership", label: "Partnership" },
];

export default function ContactPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [company, setCompany] = useState("");
  const [topic, setTopic] = useState<ContactTopic>("general");
  const [message, setMessage] = useState("");
  const [sent, setSent] = useState(false);

  const mutation = useMutation({
    mutationFn: contactApi.submit,
    onSuccess: (ack) => {
      setSent(true);
      toast.success(ack.message);
    },
    onError: () => toast.error("Couldn't send your message. Please try again."),
  });

  const canSubmit =
    name.trim().length > 0 &&
    email.trim().length > 0 &&
    message.trim().length > 0 &&
    !mutation.isPending;

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    mutation.mutate({
      name: name.trim(),
      email: email.trim(),
      company: company.trim(),
      topic,
      message: message.trim(),
    });
  };

  return (
    <main className="bg-bg px-6 py-20 sm:px-10 sm:py-24 lg:px-12">
      <div className="mx-auto grid max-w-[1000px] gap-12 lg:grid-cols-[0.85fr_1fr] lg:gap-16">
        {/* Intro */}
        <div>
          <p className="mb-4 text-[12px] font-semibold uppercase tracking-[0.14em] text-terra">
            Contact
          </p>
          <h1 className="font-serif text-[34px] font-[350] leading-[1.05] tracking-[-0.03em] text-ink sm:text-[44px]">
            Let&apos;s talk about your <em className="italic text-green">next move</em>.
          </h1>
          <p className="mt-5 max-w-[420px] text-[15px] leading-[1.6] text-ink-2">
            Questions about the product, pricing for teams and cohorts, or a partnership? Send a note and a real person will get back to you.
          </p>

          <dl className="mt-8 space-y-4 text-[14px]">
            <div>
              <dt className="font-semibold text-ink">Sales &amp; teams</dt>
              <dd>
                <a
                  href="mailto:sales@careerroadmap.ai"
                  className="text-terra underline-offset-2 hover:underline"
                >
                  sales@careerroadmap.ai
                </a>
              </dd>
            </div>
            <div>
              <dt className="font-semibold text-ink">Support</dt>
              <dd>
                <a
                  href="mailto:support@careerroadmap.ai"
                  className="text-terra underline-offset-2 hover:underline"
                >
                  support@careerroadmap.ai
                </a>
              </dd>
            </div>
          </dl>
        </div>

        {/* Form / confirmation */}
        <div className="rounded-[14px] border border-rule bg-paper p-6 sm:p-8">
          {sent ? (
            <div className="flex min-h-[320px] flex-col items-center justify-center text-center">
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-green-soft text-[20px] text-green-2">
                ✓
              </div>
              <h2 className="font-serif text-[22px] font-medium tracking-[-0.01em] text-ink">
                Message sent
              </h2>
              <p className="mt-2 max-w-[320px] text-[14px] leading-relaxed text-ink-2">
                Thanks for reaching out — we&apos;ll be in touch at{" "}
                <span className="font-medium text-ink">{email}</span> shortly.
              </p>
              <button
                type="button"
                onClick={() => {
                  setSent(false);
                  setName("");
                  setEmail("");
                  setCompany("");
                  setTopic("general");
                  setMessage("");
                }}
                className="mt-6 text-[13px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
              >
                Send another message
              </button>
            </div>
          ) : (
            <form onSubmit={onSubmit} className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block">
                  <span className="mb-1.5 block text-[12.5px] font-medium text-ink-2">Name</span>
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Ada Lovelace"
                    maxLength={200}
                    className={FIELD_CLASS}
                  />
                </label>
                <label className="block">
                  <span className="mb-1.5 block text-[12.5px] font-medium text-ink-2">Email</span>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    className={FIELD_CLASS}
                  />
                </label>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block">
                  <span className="mb-1.5 block text-[12.5px] font-medium text-ink-2">
                    Company <span className="text-ink-3">(optional)</span>
                  </span>
                  <input
                    value={company}
                    onChange={(e) => setCompany(e.target.value)}
                    placeholder="Acme Inc."
                    maxLength={200}
                    className={FIELD_CLASS}
                  />
                </label>
                <label className="block">
                  <span className="mb-1.5 block text-[12.5px] font-medium text-ink-2">Topic</span>
                  <select
                    value={topic}
                    onChange={(e) => setTopic(e.target.value as ContactTopic)}
                    className={FIELD_CLASS}
                  >
                    {TOPICS.map((t) => (
                      <option key={t.value} value={t.value}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <label className="block">
                <span className="mb-1.5 block text-[12.5px] font-medium text-ink-2">Message</span>
                <textarea
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder="How can we help?"
                  rows={5}
                  maxLength={4000}
                  className={`${FIELD_CLASS} resize-y`}
                />
              </label>
              <button
                type="submit"
                disabled={!canSubmit}
                className="inline-flex w-full items-center justify-center rounded-full bg-ink px-6 py-3 text-[14px] font-medium text-bg transition-colors duration-200 hover:bg-green-2 disabled:opacity-50 sm:w-auto"
              >
                {mutation.isPending ? "Sending…" : "Send message"}
              </button>
            </form>
          )}
        </div>
      </div>
    </main>
  );
}
