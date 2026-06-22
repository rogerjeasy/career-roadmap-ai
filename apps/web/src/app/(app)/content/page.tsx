"use client";

import { useState, type FormEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  contentApi,
  type ContentDraft,
  type ContentKind,
  type ContentStatus,
  type ContentTone,
} from "@/lib/api/content";
import { ROUTES, QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { cn } from "@/lib/utils";

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

const KIND_LABEL: Record<ContentKind, string> = {
  linkedin_post: "LinkedIn post",
  build_in_public: "Build in public",
  milestone_announcement: "Milestone",
};

const STATUS_TONE: Record<ContentStatus, string> = {
  draft: "bg-bg-2 text-ink-3",
  approved: "bg-gold-soft text-ink-2",
  published: "bg-green text-bg",
};

const TONES: ContentTone[] = ["professional", "conversational", "bold", "reflective"];
const KINDS: ContentKind[] = ["linkedin_post", "build_in_public", "milestone_announcement"];

async function copy(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
    toast.success("Copied");
  } catch {
    toast.error("Couldn't copy");
  }
}

export default function ContentPage() {
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<ContentKind>("linkedin_post");
  const [tone, setTone] = useState<ContentTone>("professional");
  const [milestone, setMilestone] = useState("");

  const { data: drafts, isLoading } = useQuery({
    queryKey: QUERY_KEYS.contentDrafts,
    queryFn: contentApi.list,
    staleTime: 30 * 1000,
  });

  const generateMutation = useMutation({
    mutationFn: contentApi.generate,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.contentDrafts });
      toast.success("Draft ready");
      setMilestone("");
    },
    onError: () => toast.error("Couldn't draft that. Add a milestone or context."),
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: ContentStatus }) =>
      contentApi.setStatus(id, status),
    onSuccess: (draft) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.contentDrafts });
      toast.success(draft.status === "published" ? "Published" : "Approved");
    },
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Couldn't update the draft.";
      toast.error(detail);
    },
  });

  const removeMutation = useMutation({
    mutationFn: contentApi.remove,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.contentDrafts });
      toast.success("Draft removed");
    },
  });

  const onGenerate = (e: FormEvent) => {
    e.preventDefault();
    generateMutation.mutate({
      kind,
      tone,
      source: milestone.trim() ? "freeform" : "roadmap_milestone",
      milestone: milestone.trim(),
    });
  };

  return (
    <div className="mx-auto max-w-[820px] px-4 pb-24 pt-7 sm:px-7">
      <PageHeader
        eyebrow="Personal brand"
        title="Content engine"
        description="Turn your roadmap milestones into LinkedIn posts and build-in-public updates. Drafts stay private until you approve them — and publishing is gated on connecting LinkedIn."
      />

      <form onSubmit={onGenerate} className="mb-8 space-y-3 rounded-[12px] border border-rule bg-paper p-5">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1 block text-[11.5px] font-medium text-ink-3">Format</span>
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value as ContentKind)}
              className="w-full rounded-[8px] border border-rule bg-bg px-3 py-2.5 text-[13.5px] text-ink focus:border-green focus:outline-none"
            >
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {KIND_LABEL[k]}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-[11.5px] font-medium text-ink-3">Tone</span>
            <select
              value={tone}
              onChange={(e) => setTone(e.target.value as ContentTone)}
              className="w-full rounded-[8px] border border-rule bg-bg px-3 py-2.5 text-[13.5px] capitalize text-ink focus:border-green focus:outline-none"
            >
              {TONES.map((t) => (
                <option key={t} value={t} className="capitalize">
                  {t}
                </option>
              ))}
            </select>
          </label>
        </div>
        <textarea
          value={milestone}
          onChange={(e) => setMilestone(e.target.value)}
          placeholder="Optional: a specific milestone or win to highlight. Leave blank to draw from your roadmap milestones."
          rows={2}
          className={`${FIELD_CLASS} resize-y`}
        />
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={generateMutation.isPending}
            className="rounded-[8px] bg-ink px-4 py-2.5 text-[13px] font-medium text-bg transition-colors hover:bg-green-2 disabled:opacity-50"
          >
            {generateMutation.isPending ? "Drafting…" : "Generate draft"}
          </button>
        </div>
      </form>

      {isLoading ? (
        <LoadingSpinner fullPage label="Loading your drafts…" />
      ) : !drafts || drafts.length === 0 ? (
        <EmptyState
          title="No drafts yet"
          description="Generate your first post above. We'll ground it in your real roadmap milestones — never invented achievements."
        />
      ) : (
        <div className="space-y-4">
          {drafts.map((d: ContentDraft) => (
            <article key={d.id} className="rounded-[12px] border border-rule bg-paper p-5">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-[5px] bg-bg-2 px-2 py-0.5 text-[11px] font-medium text-ink-2">
                    {KIND_LABEL[d.kind]}
                  </span>
                  <span className={cn("rounded-[5px] px-2 py-0.5 text-[11px] font-semibold capitalize", STATUS_TONE[d.status])}>
                    {d.status}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => copy(d.content + (d.hashtags.length ? "\n\n" + d.hashtags.map((h) => `#${h}`).join(" ") : ""))}
                  className="rounded-[7px] border border-rule px-3 py-1.5 text-[12px] font-medium text-ink transition-colors hover:border-rule-strong"
                >
                  Copy
                </button>
              </div>

              <p className="whitespace-pre-wrap text-[13.5px] leading-relaxed text-ink-2">{d.content}</p>

              {d.hashtags.length > 0 && (
                <div className="mt-2.5 flex flex-wrap gap-1.5">
                  {d.hashtags.map((h) => (
                    <span key={h} className="text-[12px] font-medium text-terra">
                      #{h}
                    </span>
                  ))}
                </div>
              )}

              {d.basedOn && <p className="mt-3 text-[11.5px] italic text-ink-3">Based on: {d.basedOn}</p>}

              <div className="mt-4 flex flex-wrap items-center justify-end gap-2 border-t border-rule pt-3">
                {d.status === "draft" && (
                  <button
                    type="button"
                    onClick={() => statusMutation.mutate({ id: d.id, status: "approved" })}
                    disabled={statusMutation.isPending}
                    className="rounded-[7px] border border-rule px-3 py-1.5 text-[12px] font-medium text-ink transition-colors hover:border-green disabled:opacity-50"
                  >
                    Approve
                  </button>
                )}
                {d.status !== "published" && (
                  <button
                    type="button"
                    onClick={() => statusMutation.mutate({ id: d.id, status: "published" })}
                    disabled={statusMutation.isPending}
                    className="rounded-[7px] bg-ink px-3 py-1.5 text-[12px] font-medium text-bg transition-colors hover:bg-green-2 disabled:opacity-50"
                  >
                    Mark published
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => removeMutation.mutate(d.id)}
                  className="text-[12px] font-medium text-ink-3 transition-colors hover:text-destructive"
                >
                  Delete
                </button>
              </div>
            </article>
          ))}
        </div>
      )}

      <p className="mt-6 text-center text-[11.5px] text-ink-3">
        Publishing requires connecting LinkedIn in{" "}
        <a href={ROUTES.settingsIntegrations} className="font-medium text-terra hover:text-terra-2">
          Settings → Integrations
        </a>
        .
      </p>
    </div>
  );
}
