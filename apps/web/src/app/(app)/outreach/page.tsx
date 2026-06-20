"use client";

import { useState, type FormEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  outreachApi,
  type OutreachDraft,
  type OutreachChannel,
  type OutreachTone,
  type DraftStatus,
} from "@/lib/api/outreach";
import { QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { cn } from "@/lib/utils";

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

const STATUS_TONE: Record<DraftStatus, string> = {
  draft: "bg-bg-2 text-ink-2",
  approved: "bg-green-soft text-green-2",
  sent: "bg-green text-bg",
};

export default function OutreachPage() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [recipientName, setRecipientName] = useState("");
  const [recipientRole, setRecipientRole] = useState("");
  const [channel, setChannel] = useState<OutreachChannel>("email");
  const [tone, setTone] = useState<OutreachTone>("warm");
  const [goal, setGoal] = useState("");
  const [context, setContext] = useState("");

  const { data: drafts, isLoading } = useQuery({
    queryKey: QUERY_KEYS.outreachDrafts,
    queryFn: outreachApi.list,
    staleTime: 30 * 1000,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: QUERY_KEYS.outreachDrafts });

  const draftMutation = useMutation({
    mutationFn: outreachApi.draft,
    onSuccess: () => {
      invalidate();
      toast.success("Draft ready — review before sending");
      setRecipientName("");
      setRecipientRole("");
      setGoal("");
      setContext("");
      setShowForm(false);
    },
    onError: () => toast.error("Couldn't draft that message."),
  });

  const editMutation = useMutation({
    mutationFn: ({ id, subject, body }: { id: string; subject: string; body: string }) =>
      outreachApi.edit(id, { subject, body }),
    onSuccess: () => {
      invalidate();
      toast.success("Saved — re-approve to send");
    },
  });

  const approveMutation = useMutation({
    mutationFn: (id: string) => outreachApi.approve(id),
    onSuccess: () => {
      invalidate();
      toast.success("Approved");
    },
  });

  const sentMutation = useMutation({
    mutationFn: (id: string) => outreachApi.markSent(id),
    onSuccess: () => {
      invalidate();
      toast.success("Marked as sent");
    },
    onError: () => toast.error("Approve it first."),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => outreachApi.remove(id),
    onSuccess: () => invalidate(),
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!goal.trim()) return;
    draftMutation.mutate({
      recipientName: recipientName.trim(),
      recipientRole: recipientRole.trim(),
      channel,
      tone,
      goal: goal.trim(),
      context: context.trim(),
    });
  };

  return (
    <div className="mx-auto max-w-[820px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Networking"
        title="Outreach Drafts"
        description="Draft warm, personalised messages with AI — then review, edit, and approve before you send. Nothing goes out automatically."
        actions={
          <button
            type="button"
            onClick={() => setShowForm((v) => !v)}
            className="inline-flex items-center rounded-[7px] bg-ink px-3.5 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2"
          >
            {showForm ? "Close" : "+ New draft"}
          </button>
        }
      />

      {showForm && (
        <form onSubmit={onSubmit} className="mb-6 space-y-3 rounded-[12px] border border-rule bg-paper p-5">
          <div className="grid gap-3 sm:grid-cols-2">
            <input value={recipientName} onChange={(e) => setRecipientName(e.target.value)} placeholder="Recipient name (optional)" className={FIELD_CLASS} />
            <input value={recipientRole} onChange={(e) => setRecipientRole(e.target.value)} placeholder="Their role (optional)" className={FIELD_CLASS} />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <select value={channel} onChange={(e) => setChannel(e.target.value as OutreachChannel)} className={FIELD_CLASS}>
              <option value="email">Email</option>
              <option value="linkedin">LinkedIn</option>
              <option value="other">Other</option>
            </select>
            <select value={tone} onChange={(e) => setTone(e.target.value as OutreachTone)} className={FIELD_CLASS}>
              <option value="warm">Warm</option>
              <option value="professional">Professional</option>
              <option value="concise">Concise</option>
              <option value="enthusiastic">Enthusiastic</option>
            </select>
          </div>
          <input value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="What do you want from this message?" className={FIELD_CLASS} />
          <textarea value={context} onChange={(e) => setContext(e.target.value)} placeholder="Anything to mention — shared connection, their work… (optional)" rows={2} className={`${FIELD_CLASS} resize-y`} />
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={!goal.trim() || draftMutation.isPending}
              className="rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors hover:bg-green-2 disabled:opacity-50"
            >
              {draftMutation.isPending ? "Drafting…" : "Draft message"}
            </button>
          </div>
        </form>
      )}

      {isLoading ? (
        <LoadingSpinner fullPage label="Loading drafts…" />
      ) : !drafts || drafts.length === 0 ? (
        <EmptyState
          title="No drafts yet"
          description="Draft your first outreach message. You stay in control — review and approve before anything is sent."
        />
      ) : (
        <div className="space-y-4">
          {drafts.map((d: OutreachDraft) => (
            <DraftCard
              key={d.id}
              draft={d}
              statusTone={STATUS_TONE[d.status]}
              onSave={(subject, body) => editMutation.mutate({ id: d.id, subject, body })}
              onApprove={() => approveMutation.mutate(d.id)}
              onSent={() => sentMutation.mutate(d.id)}
              onDelete={() => deleteMutation.mutate(d.id)}
              saving={editMutation.isPending}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface DraftCardProps {
  draft: OutreachDraft;
  statusTone: string;
  onSave: (subject: string, body: string) => void;
  onApprove: () => void;
  onSent: () => void;
  onDelete: () => void;
  saving: boolean;
}

function DraftCard({ draft, statusTone, onSave, onApprove, onSent, onDelete, saving }: DraftCardProps) {
  const [subject, setSubject] = useState(draft.subject);
  const [body, setBody] = useState(draft.body);
  const dirty = subject !== draft.subject || body !== draft.body;

  return (
    <article className="rounded-[12px] border border-rule bg-paper p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-[13px] font-medium text-ink">
            {draft.recipientName || "Recipient"}
            {draft.recipientRole ? ` · ${draft.recipientRole}` : ""}
          </p>
          <p className="text-[11.5px] text-ink-3">
            {draft.channel} · {draft.tone} · {draft.goal}
          </p>
        </div>
        <span className={cn("shrink-0 rounded-[5px] px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.04em]", statusTone)}>
          {draft.status}
        </span>
      </div>
      {draft.channel === "email" && (
        <input
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          placeholder="Subject"
          className={`${FIELD_CLASS} mb-2`}
        />
      )}
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        rows={6}
        className={`${FIELD_CLASS} resize-y`}
      />
      <div className="mt-3 flex flex-wrap items-center justify-end gap-2">
        <button
          type="button"
          onClick={onDelete}
          className="mr-auto text-[12px] font-medium text-ink-3 transition-colors hover:text-destructive"
        >
          Delete
        </button>
        {dirty && (
          <button
            type="button"
            onClick={() => onSave(subject, body)}
            disabled={saving}
            className="rounded-[7px] border border-rule px-3.5 py-1.5 text-[12.5px] font-medium text-ink transition-colors hover:border-rule-strong disabled:opacity-50"
          >
            Save edits
          </button>
        )}
        {draft.status === "draft" && (
          <button
            type="button"
            onClick={onApprove}
            className="rounded-[7px] border border-green px-3.5 py-1.5 text-[12.5px] font-medium text-green-2 transition-colors hover:bg-green-soft"
          >
            Approve
          </button>
        )}
        {draft.status === "approved" && (
          <button
            type="button"
            onClick={onSent}
            className="rounded-[7px] bg-ink px-3.5 py-1.5 text-[12.5px] font-medium text-bg transition-colors hover:bg-green-2"
          >
            Mark sent
          </button>
        )}
      </div>
    </article>
  );
}
