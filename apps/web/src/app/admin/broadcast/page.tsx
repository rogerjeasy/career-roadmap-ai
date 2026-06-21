"use client";

import { useState } from "react";
import { Send } from "lucide-react";
import { useBroadcast, useSubscribers } from "@/hooks/use-admin";
import { formatRelative } from "@/lib/date";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { SectionCard, FilterSelect } from "@/components/admin/admin-ui";
import type { BroadcastAudience, BroadcastTone } from "@/types/admin.types";

const FIELD =
  "w-full rounded-[8px] border border-rule bg-paper px-3 py-2 text-[13.5px] text-ink outline-none transition-colors duration-150 placeholder:text-ink-3 hover:border-rule-strong focus:border-rule-strong";

export default function AdminBroadcastPage() {
  const subscribers = useSubscribers();
  const broadcast = useBroadcast();

  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [link, setLink] = useState("");
  const [tone, setTone] = useState<BroadcastTone>("info");
  const [audience, setAudience] = useState<BroadcastAudience>("active");

  const canSend = title.trim().length > 0 && !broadcast.isPending;

  const send = () => {
    if (!canSend) return;
    broadcast.mutate(
      {
        title: title.trim(),
        body: body.trim(),
        tone,
        link: link.trim() || null,
        audience,
      },
      {
        onSuccess: () => {
          setTitle("");
          setBody("");
          setLink("");
        },
      },
    );
  };

  return (
    <div className="mx-auto max-w-[900px] px-4 pb-16 pt-6 sm:px-6 lg:px-8">
      <PageHeader
        eyebrow="Admin"
        title="Broadcast"
        description="Send an in-app notification to a segment of users, and review newsletter subscribers."
      />

      <div className="space-y-6">
        <SectionCard title="Compose notification">
          <div className="space-y-4 p-4 sm:p-5">
            <div>
              <label className="mb-1.5 block text-[12.5px] font-medium text-ink-2">Title</label>
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                maxLength={200}
                placeholder="e.g. New: AI Coach now supports voice"
                className={FIELD}
              />
            </div>

            <div>
              <label className="mb-1.5 block text-[12.5px] font-medium text-ink-2">
                Message <span className="text-ink-3">(optional)</span>
              </label>
              <textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                maxLength={1000}
                rows={3}
                placeholder="A short message shown in the notification bell."
                className={`${FIELD} resize-y`}
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-1.5 block text-[12.5px] font-medium text-ink-2">
                  Link <span className="text-ink-3">(optional)</span>
                </label>
                <input
                  value={link}
                  onChange={(e) => setLink(e.target.value)}
                  maxLength={500}
                  placeholder="/roadmap or https://…"
                  className={FIELD}
                />
              </div>
              <div className="flex items-end gap-3">
                <FilterSelect
                  label="Tone"
                  value={tone}
                  onChange={(v) => setTone(v as BroadcastTone)}
                  options={[
                    { value: "info", label: "Info" },
                    { value: "success", label: "Success" },
                    { value: "warn", label: "Warning" },
                  ]}
                />
                <FilterSelect
                  label="Audience"
                  value={audience}
                  onChange={(v) => setAudience(v as BroadcastAudience)}
                  options={[
                    { value: "active", label: "Active users" },
                    { value: "all", label: "All users" },
                    { value: "admins", label: "Admins only" },
                  ]}
                />
              </div>
            </div>

            <div className="flex items-center justify-between gap-3 border-t border-rule pt-4">
              <p className="text-[12px] text-ink-3">
                Delivered to the in-app notification bell of every recipient.
              </p>
              <button
                type="button"
                onClick={send}
                disabled={!canSend}
                className="inline-flex shrink-0 items-center gap-2 rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-40"
              >
                <Send className="h-3.5 w-3.5" />
                {broadcast.isPending ? "Sending…" : "Send broadcast"}
              </button>
            </div>
          </div>
        </SectionCard>

        <SectionCard
          title="Newsletter subscribers"
          description={
            subscribers.data ? `${subscribers.data.length} opted-in` : undefined
          }
        >
          {subscribers.isLoading && (
            <div className="px-5 py-8">
              <LoadingSpinner label="Loading subscribers…" />
            </div>
          )}
          {subscribers.isError && (
            <p className="px-5 py-6 text-[13px] text-ink-3">Couldn&apos;t load subscribers.</p>
          )}
          {subscribers.data && subscribers.data.length === 0 && (
            <div className="p-5">
              <EmptyState
                title="No subscribers yet"
                description="Users who opt into the newsletter will appear here."
              />
            </div>
          )}
          {subscribers.data && subscribers.data.length > 0 && (
            <ul className="divide-y divide-rule">
              {subscribers.data.map((s) => (
                <li
                  key={s.userId}
                  className="flex items-center justify-between gap-3 px-4 py-3 sm:px-5"
                >
                  <div className="min-w-0">
                    <p className="truncate text-[13.5px] font-medium text-ink">
                      {s.displayName || s.email || s.userId}
                    </p>
                    <p className="truncate text-[12px] text-ink-3">
                      {s.email} · {s.frequency}
                      {s.topics.length > 0 ? ` · ${s.topics.length} topics` : ""}
                    </p>
                  </div>
                  <span className="hidden shrink-0 text-[12px] text-ink-3 sm:block">
                    {s.updatedAt ? formatRelative(s.updatedAt) : ""}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>
    </div>
  );
}
