"use client";

import { useState, type FormEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  learningApi,
  type LearningItem,
  type LearningType,
  type LearningStatus,
} from "@/lib/api/learning";
import { QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { cn } from "@/lib/utils";

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

const TYPE_OPTIONS: { value: LearningType; label: string }[] = [
  { value: "course", label: "Course" },
  { value: "book", label: "Book" },
  { value: "certification", label: "Certification" },
  { value: "bootcamp", label: "Bootcamp" },
  { value: "degree", label: "Degree" },
  { value: "article", label: "Article" },
  { value: "other", label: "Other" },
];

const STATUS_OPTIONS: { value: LearningStatus; label: string }[] = [
  { value: "planned", label: "Planned" },
  { value: "in_progress", label: "In progress" },
  { value: "completed", label: "Completed" },
  { value: "abandoned", label: "Abandoned" },
];

const STATUS_LABEL: Record<LearningStatus, string> = {
  planned: "Planned",
  in_progress: "In progress",
  completed: "Completed",
  abandoned: "Abandoned",
};

function roiTone(score: number): string {
  if (score >= 66) return "bg-green-soft text-green-2";
  if (score >= 33) return "bg-bg-2 text-ink-2";
  return "bg-terra-soft text-terra-2";
}

export default function LearningRoiPage() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [type, setType] = useState<LearningType>("course");
  const [provider, setProvider] = useState("");
  const [cost, setCost] = useState("");
  const [hours, setHours] = useState("");
  const [status, setStatus] = useState<LearningStatus>("planned");
  const [skills, setSkills] = useState("");
  const [link, setLink] = useState("");
  const [pendingDelete, setPendingDelete] = useState<LearningItem | null>(null);

  const { data: items, isLoading } = useQuery({
    queryKey: QUERY_KEYS.learning,
    queryFn: learningApi.list,
    staleTime: 60 * 1000,
  });

  const { data: summary } = useQuery({
    queryKey: QUERY_KEYS.learningSummary,
    queryFn: learningApi.summary,
    staleTime: 60 * 1000,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: QUERY_KEYS.learning });
    queryClient.invalidateQueries({ queryKey: QUERY_KEYS.learningSummary });
  };

  const resetForm = () => {
    setTitle("");
    setType("course");
    setProvider("");
    setCost("");
    setHours("");
    setStatus("planned");
    setSkills("");
    setLink("");
    setShowForm(false);
  };

  const createMutation = useMutation({
    mutationFn: learningApi.create,
    onSuccess: () => {
      invalidate();
      toast.success("Learning investment logged");
      resetForm();
    },
    onError: () => toast.error("Couldn't save that. Please try again."),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => learningApi.remove(id),
    onSuccess: () => {
      invalidate();
      toast.success("Removed");
      setPendingDelete(null);
    },
    onError: () => toast.error("Couldn't remove that."),
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    createMutation.mutate({
      title: title.trim(),
      type,
      provider: provider.trim(),
      cost: cost ? Number(cost) : 0,
      hours: hours ? Number(hours) : 0,
      status,
      link: link.trim(),
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
        title="Learning ROI"
        description="Log the courses, books, and certifications you're investing in. Each is ranked by expected career impact per hour and dollar — aligned to the skills your target market actually rewards."
        actions={
          <button
            type="button"
            onClick={() => setShowForm((v) => !v)}
            className="inline-flex items-center rounded-[7px] bg-ink px-3.5 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2"
          >
            {showForm ? "Close" : "+ Log investment"}
          </button>
        }
      />

      {summary && summary.totalItems > 0 && (
        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <SummaryStat label="Items" value={String(summary.totalItems)} />
          <SummaryStat label="Invested" value={`$${summary.totalCost.toLocaleString()}`} />
          <SummaryStat label="Hours" value={String(summary.totalHours)} />
          <SummaryStat label="Avg ROI" value={String(summary.averageRoi)} />
        </div>
      )}

      {summary && !summary.hasMarketSignals && (
        <p className="mb-6 rounded-[10px] border border-rule bg-bg-2 px-4 py-3 text-[12.5px] leading-relaxed text-ink-2">
          No market snapshot yet — items are ranked on effort and format only.
          Generate a roadmap to unlock market-aligned impact scoring.
        </p>
      )}

      {showForm && (
        <form
          onSubmit={onSubmit}
          className="mb-6 space-y-3 rounded-[12px] border border-rule bg-paper p-5"
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="What are you learning?"
              className={FIELD_CLASS}
            />
            <select
              value={type}
              onChange={(e) => setType(e.target.value as LearningType)}
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
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              placeholder="Provider (e.g. Coursera, O'Reilly)"
              className={FIELD_CLASS}
            />
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as LearningStatus)}
              className={FIELD_CLASS}
            >
              {STATUS_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <input
              value={cost}
              onChange={(e) => setCost(e.target.value)}
              type="number"
              min="0"
              placeholder="Cost (USD)"
              className={FIELD_CLASS}
            />
            <input
              value={hours}
              onChange={(e) => setHours(e.target.value)}
              type="number"
              min="0"
              placeholder="Estimated hours"
              className={FIELD_CLASS}
            />
          </div>
          <input
            value={skills}
            onChange={(e) => setSkills(e.target.value)}
            placeholder="Skills it builds — comma separated"
            className={FIELD_CLASS}
          />
          <input
            value={link}
            onChange={(e) => setLink(e.target.value)}
            placeholder="Link (optional)"
            className={FIELD_CLASS}
          />
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={!title.trim() || createMutation.isPending}
              className="rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-50"
            >
              {createMutation.isPending ? "Saving…" : "Save"}
            </button>
          </div>
        </form>
      )}

      {isLoading ? (
        <LoadingSpinner fullPage label="Scoring your learning…" />
      ) : !items || items.length === 0 ? (
        <EmptyState
          title="Nothing logged yet"
          description="Add the courses and books you're considering. We'll rank them by expected impact so your study time compounds toward your goal."
        />
      ) : (
        <div className="space-y-4">
          {items.map((item: LearningItem) => (
            <article
              key={item.id}
              className="flex flex-col gap-3 rounded-[12px] border border-rule bg-paper p-5"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-start gap-3">
                  <span className="mt-0.5 shrink-0 font-serif text-[15px] font-medium text-ink-3">
                    #{item.rank}
                  </span>
                  <div className="min-w-0">
                    <h3 className="font-serif text-[16px] font-medium leading-snug tracking-[-0.01em] text-ink">
                      {item.title}
                    </h3>
                    <p className="mt-1 text-[12px] text-ink-3">
                      {item.provider && `${item.provider} · `}
                      {STATUS_LABEL[item.status]}
                      {item.cost > 0 && ` · $${item.cost.toLocaleString()}`}
                      {item.hours > 0 && ` · ${item.hours}h`}
                    </p>
                  </div>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <span
                    className={cn(
                      "rounded-[6px] px-2.5 py-1 text-[12px] font-semibold tabular-nums",
                      roiTone(item.roiScore),
                    )}
                  >
                    ROI {item.roiScore}
                  </span>
                  <span className="text-[10.5px] text-ink-3">
                    impact {item.impactScore}
                  </span>
                </div>
              </div>
              {item.rationale && (
                <p className="text-[13px] leading-relaxed text-ink-2">{item.rationale}</p>
              )}
              {item.matchedSkills.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {item.matchedSkills.map((s) => (
                    <span
                      key={s}
                      className="rounded-[5px] bg-green-soft px-2 py-0.5 text-[11px] font-medium text-green-2"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              )}
              <div className="flex items-center justify-end gap-3">
                {item.link && (
                  <a
                    href={item.link}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[12px] font-medium text-terra transition-colors hover:text-terra-2"
                  >
                    Open →
                  </a>
                )}
                <button
                  type="button"
                  onClick={() => setPendingDelete(item)}
                  className="text-[12px] font-medium text-ink-3 transition-colors hover:text-destructive"
                >
                  Remove
                </button>
              </div>
            </article>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title="Remove this item?"
        description={
          pendingDelete
            ? `"${pendingDelete.title}" will be removed from your tracker.`
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

interface SummaryStatProps {
  label: string;
  value: string;
}

function SummaryStat({ label, value }: SummaryStatProps) {
  return (
    <div className="rounded-[10px] border border-rule bg-paper px-4 py-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-3">
        {label}
      </p>
      <p className="mt-1 font-serif text-[20px] font-medium tabular-nums text-ink">
        {value}
      </p>
    </div>
  );
}
