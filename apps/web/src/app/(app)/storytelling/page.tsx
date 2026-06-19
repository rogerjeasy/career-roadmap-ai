"use client";

import { useState, type FormEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  storytellingApi,
  type StoryDraft,
  type StoryFormat,
  type StoryTone,
} from "@/lib/api/storytelling";
import { evidenceApi, type Evidence } from "@/lib/api/evidence";
import { QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { cn } from "@/lib/utils";

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

const FORMATS: { value: StoryFormat; label: string }[] = [
  { value: "resume_bullets", label: "Résumé bullets" },
  { value: "linkedin_about", label: "LinkedIn About" },
  { value: "cover_letter", label: "Cover letter" },
  { value: "interview_story", label: "Interview story" },
];

const FORMAT_LABEL: Record<StoryFormat, string> = {
  resume_bullets: "Résumé bullets",
  linkedin_about: "LinkedIn About",
  cover_letter: "Cover letter",
  interview_story: "Interview story",
};

const TONES: StoryTone[] = ["professional", "confident", "warm", "concise"];

export default function StorytellingPage() {
  const queryClient = useQueryClient();
  const [format, setFormat] = useState<StoryFormat>("resume_bullets");
  const [tone, setTone] = useState<StoryTone>("professional");
  const [targetRole, setTargetRole] = useState("");
  const [targetCompany, setTargetCompany] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [extra, setExtra] = useState("");
  const [result, setResult] = useState<StoryDraft | null>(null);
  const [pendingDelete, setPendingDelete] = useState<StoryDraft | null>(null);

  const { data: evidence } = useQuery({
    queryKey: QUERY_KEYS.evidence,
    queryFn: evidenceApi.list,
    staleTime: 60 * 1000,
  });

  const { data: drafts } = useQuery({
    queryKey: QUERY_KEYS.storyDrafts,
    queryFn: storytellingApi.listDrafts,
    staleTime: 30 * 1000,
  });

  const generateMutation = useMutation({
    mutationFn: storytellingApi.generate,
    onSuccess: (data) => {
      setResult(data);
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.storyDrafts });
      toast.success("Narrative ready");
    },
    onError: () => toast.error("Couldn't generate that. Please try again."),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => storytellingApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.storyDrafts });
      toast.success("Draft deleted");
      setPendingDelete(null);
    },
  });

  const toggle = (id: string) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((e) => e !== id) : [...prev, id]));

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (selected.length === 0) return;
    generateMutation.mutate({
      format,
      tone,
      targetRole: targetRole.trim(),
      targetCompany: targetCompany.trim(),
      evidenceIds: selected,
      extraContext: extra.trim(),
    });
  };

  const copyContent = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success("Copied");
    } catch {
      toast.error("Couldn't copy");
    }
  };

  const hasEvidence = Boolean(evidence && evidence.length > 0);

  return (
    <div className="mx-auto max-w-[900px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Narrative"
        title="Storytelling Studio"
        description="Turn the proof in your Evidence Vault into polished résumé bullets, a LinkedIn About, a cover letter, or an interview story — grounded only in what you've actually done."
      />

      {!hasEvidence && (
        <p className="mb-6 rounded-[10px] border border-rule bg-bg-2 px-4 py-3 text-[12.5px] leading-relaxed text-ink-2">
          Add a few wins to your <span className="font-medium text-ink">Evidence Vault</span>{" "}
          first — narratives are written strictly from real evidence.
        </p>
      )}

      {hasEvidence && (
        <form onSubmit={onSubmit} className="mb-6 space-y-4 rounded-[12px] border border-rule bg-paper p-5">
          <div className="flex flex-wrap gap-2">
            {FORMATS.map((f) => (
              <button
                key={f.value}
                type="button"
                onClick={() => setFormat(f.value)}
                className={cn(
                  "rounded-[7px] border px-3 py-1.5 text-[12.5px] font-medium transition-colors duration-150",
                  format === f.value
                    ? "border-green bg-green-soft text-green-2"
                    : "border-rule bg-bg text-ink-2 hover:border-rule-strong",
                )}
              >
                {f.label}
              </button>
            ))}
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <input
              value={targetRole}
              onChange={(e) => setTargetRole(e.target.value)}
              placeholder="Target role (optional)"
              className={FIELD_CLASS}
            />
            <input
              value={targetCompany}
              onChange={(e) => setTargetCompany(e.target.value)}
              placeholder="Target company (optional)"
              className={FIELD_CLASS}
            />
          </div>

          <select
            value={tone}
            onChange={(e) => setTone(e.target.value as StoryTone)}
            className={FIELD_CLASS}
          >
            {TONES.map((t) => (
              <option key={t} value={t}>
                {t.charAt(0).toUpperCase() + t.slice(1)} tone
              </option>
            ))}
          </select>

          <div>
            <p className="mb-2 text-[12px] font-semibold uppercase tracking-[0.06em] text-ink-3">
              Evidence to draw from ({selected.length})
            </p>
            <div className="space-y-2">
              {(evidence ?? []).map((item: Evidence) => {
                const checked = selected.includes(item.id);
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => toggle(item.id)}
                    className={cn(
                      "flex w-full items-start gap-3 rounded-[9px] border px-3.5 py-2.5 text-left transition-colors duration-150",
                      checked ? "border-green bg-green-soft" : "border-rule bg-bg hover:border-rule-strong",
                    )}
                  >
                    <span
                      className={cn(
                        "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-[4px] border text-[10px] font-bold text-bg",
                        checked ? "border-green bg-green" : "border-rule-strong bg-paper",
                      )}
                    >
                      {checked ? "✓" : ""}
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate text-[13px] font-medium text-ink">
                        {item.title}
                      </span>
                      <span className="block text-[11.5px] text-ink-3">{item.type}</span>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          <textarea
            value={extra}
            onChange={(e) => setExtra(e.target.value)}
            placeholder="Anything else to weave in? (optional)"
            rows={2}
            className={`${FIELD_CLASS} resize-y`}
          />

          <div className="flex justify-end">
            <button
              type="submit"
              disabled={selected.length === 0 || generateMutation.isPending}
              className="rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors hover:bg-green-2 disabled:opacity-50"
            >
              {generateMutation.isPending ? "Writing…" : "Generate narrative"}
            </button>
          </div>
        </form>
      )}

      {generateMutation.isPending && <LoadingSpinner label="Crafting your story…" />}

      {result && (
        <div className="mb-8 space-y-3 rounded-[12px] border border-green bg-paper p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-serif text-[18px] font-medium tracking-[-0.01em] text-ink">
              {result.title}
            </h2>
            <button
              type="button"
              onClick={() => copyContent(result.content)}
              className="rounded-[7px] border border-rule px-3 py-1.5 text-[12px] font-medium text-ink transition-colors hover:border-rule-strong"
            >
              Copy
            </button>
          </div>
          <p className="whitespace-pre-wrap text-[13.5px] leading-relaxed text-ink-2">
            {result.content}
          </p>
          {result.tips.length > 0 && (
            <div className="border-t border-rule pt-3">
              <p className="text-[11.5px] font-semibold uppercase tracking-[0.06em] text-ink-3">
                To make it stronger
              </p>
              <ul className="mt-1.5 list-disc space-y-1 pl-5 text-[12.5px] text-ink-2">
                {result.tips.map((t, i) => (
                  <li key={i}>{t}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {drafts && drafts.length > 0 && (
        <div>
          <p className="mb-3 text-[12px] font-semibold uppercase tracking-[0.06em] text-ink-3">
            Saved drafts
          </p>
          <div className="space-y-3">
            {drafts.map((d: StoryDraft) => (
              <article key={d.id} className="rounded-[12px] border border-rule bg-paper p-5">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <span className="rounded-[5px] bg-bg-2 px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.04em] text-ink-2">
                      {FORMAT_LABEL[d.format]}
                    </span>
                    <h3 className="mt-1.5 font-serif text-[15.5px] font-medium tracking-[-0.01em] text-ink">
                      {d.title}
                    </h3>
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    <button
                      type="button"
                      onClick={() => copyContent(d.content)}
                      className="text-[12px] font-medium text-ink-2 transition-colors hover:text-ink"
                    >
                      Copy
                    </button>
                    <button
                      type="button"
                      onClick={() => setPendingDelete(d)}
                      className="text-[12px] font-medium text-ink-3 transition-colors hover:text-destructive"
                    >
                      Delete
                    </button>
                  </div>
                </div>
                <p className="mt-3 line-clamp-4 whitespace-pre-wrap text-[13px] leading-relaxed text-ink-2">
                  {d.content}
                </p>
              </article>
            ))}
          </div>
        </div>
      )}

      {hasEvidence && (!drafts || drafts.length === 0) && !result && !generateMutation.isPending && (
        <EmptyState
          title="No narratives yet"
          description="Pick a format and the evidence to draw from, then generate your first story."
        />
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title="Delete this draft?"
        description={pendingDelete ? `"${pendingDelete.title}" will be permanently removed.` : undefined}
        confirmLabel="Delete"
        destructive
        pending={deleteMutation.isPending}
        onConfirm={() => pendingDelete && deleteMutation.mutate(pendingDelete.id)}
      />
    </div>
  );
}
