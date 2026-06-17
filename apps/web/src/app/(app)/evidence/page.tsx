"use client";

import { useState, type FormEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  evidenceApi,
  type Evidence,
  type EvidenceType,
} from "@/lib/api/evidence";
import { QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

const TYPE_OPTIONS: { value: EvidenceType; label: string }[] = [
  { value: "achievement", label: "Achievement" },
  { value: "certification", label: "Certification" },
  { value: "project", label: "Project" },
  { value: "recommendation", label: "Recommendation" },
  { value: "metric", label: "Metric" },
  { value: "other", label: "Other" },
];

const TYPE_LABEL: Record<EvidenceType, string> = {
  achievement: "Achievement",
  certification: "Certification",
  project: "Project",
  recommendation: "Recommendation",
  metric: "Metric",
  other: "Other",
};

export default function EvidenceVaultPage() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [type, setType] = useState<EvidenceType>("achievement");
  const [dateLabel, setDateLabel] = useState("");
  const [link, setLink] = useState("");
  const [skills, setSkills] = useState("");
  const [description, setDescription] = useState("");
  const [pendingDelete, setPendingDelete] = useState<Evidence | null>(null);

  const { data: items, isLoading } = useQuery({
    queryKey: QUERY_KEYS.evidence,
    queryFn: evidenceApi.list,
    staleTime: 60 * 1000,
  });

  const resetForm = () => {
    setTitle("");
    setType("achievement");
    setDateLabel("");
    setLink("");
    setSkills("");
    setDescription("");
    setShowForm(false);
  };

  const createMutation = useMutation({
    mutationFn: evidenceApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.evidence });
      toast.success("Evidence added");
      resetForm();
    },
    onError: () => toast.error("Couldn't save that. Please try again."),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => evidenceApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.evidence });
      toast.success("Evidence removed");
      setPendingDelete(null);
    },
    onError: () => toast.error("Couldn't remove that. Please try again."),
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    createMutation.mutate({
      title: title.trim(),
      type,
      dateLabel: dateLabel.trim(),
      link: link.trim(),
      description: description.trim(),
      skills: skills
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    });
  };

  return (
    <div className="mx-auto max-w-[900px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Assets"
        title="Evidence Vault"
        description="A private record of concrete proof — achievements, certifications, metrics and recommendations — that backs up your roadmap and CV with real, dated evidence."
        actions={
          <button
            type="button"
            onClick={() => setShowForm((v) => !v)}
            className="inline-flex items-center rounded-[7px] bg-ink px-3.5 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2"
          >
            {showForm ? "Close" : "+ Add evidence"}
          </button>
        }
      />

      {showForm && (
        <form
          onSubmit={onSubmit}
          className="mb-6 space-y-3 rounded-[12px] border border-rule bg-paper p-5"
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="What did you achieve?"
              className={FIELD_CLASS}
            />
            <select
              value={type}
              onChange={(e) => setType(e.target.value as EvidenceType)}
              className={FIELD_CLASS}
            >
              {TYPE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <input
              value={dateLabel}
              onChange={(e) => setDateLabel(e.target.value)}
              placeholder="When? (e.g. Mar 2026)"
              className={FIELD_CLASS}
            />
            <input
              value={link}
              onChange={(e) => setLink(e.target.value)}
              placeholder="Proof link (optional)"
              className={FIELD_CLASS}
            />
          </div>
          <input
            value={skills}
            onChange={(e) => setSkills(e.target.value)}
            placeholder="Skills evidenced — comma separated (optional)"
            className={FIELD_CLASS}
          />
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe the impact (optional)"
            rows={3}
            className={`${FIELD_CLASS} resize-y`}
          />
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={!title.trim() || createMutation.isPending}
              className="rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-50"
            >
              {createMutation.isPending ? "Saving…" : "Save evidence"}
            </button>
          </div>
        </form>
      )}

      {isLoading ? (
        <LoadingSpinner fullPage label="Loading your evidence…" />
      ) : !items || items.length === 0 ? (
        <EmptyState
          title="Your vault is empty"
          description="Capture wins as they happen — a shipped project, a certification, a metric you moved. Each one strengthens your case for the next role."
        />
      ) : (
        <div className="space-y-4">
          {items.map((item: Evidence) => (
            <article
              key={item.id}
              className="flex flex-col gap-3 rounded-[12px] border border-rule bg-paper p-5"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <span className="rounded-[5px] bg-bg-2 px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.04em] text-ink-2">
                    {TYPE_LABEL[item.type]}
                  </span>
                  {item.dateLabel && (
                    <span className="text-[12px] text-ink-3">{item.dateLabel}</span>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => setPendingDelete(item)}
                  className="shrink-0 text-[12px] font-medium text-ink-3 transition-colors hover:text-destructive"
                >
                  Remove
                </button>
              </div>
              <div className="min-w-0">
                <h3 className="font-serif text-[16px] font-medium leading-snug tracking-[-0.01em] text-ink">
                  {item.title}
                </h3>
                {item.description && (
                  <p className="mt-1.5 text-[13px] leading-relaxed text-ink-2">
                    {item.description}
                  </p>
                )}
              </div>
              {item.skills.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {item.skills.map((s) => (
                    <span
                      key={s}
                      className="rounded-[5px] bg-green-soft px-2 py-0.5 text-[11px] font-medium text-green-2"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              )}
              {item.link && (
                <a
                  href={item.link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="w-fit text-[12px] font-medium text-terra transition-colors hover:text-terra-2"
                >
                  View proof →
                </a>
              )}
            </article>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title="Remove this evidence?"
        description={
          pendingDelete
            ? `"${pendingDelete.title}" will be permanently deleted from your vault.`
            : undefined
        }
        confirmLabel="Remove"
        destructive
        pending={deleteMutation.isPending}
        onConfirm={() => pendingDelete && deleteMutation.mutate(pendingDelete.id)}
      />
    </div>
  );
}
