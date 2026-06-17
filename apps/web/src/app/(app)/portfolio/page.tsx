"use client";

import { useState, type FormEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  portfolioApi,
  type PortfolioItem,
  type ProjectStatus,
} from "@/lib/api/portfolio";
import { QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

const STATUS_OPTIONS: { value: ProjectStatus; label: string }[] = [
  { value: "live", label: "Live" },
  { value: "in_progress", label: "In progress" },
  { value: "archived", label: "Archived" },
];

const STATUS_CHIP: Record<ProjectStatus, string> = {
  live: "bg-green-soft text-green-2",
  in_progress: "bg-terra-soft text-terra-2",
  archived: "bg-bg-3 text-ink-2",
};

const STATUS_LABEL: Record<ProjectStatus, string> = {
  live: "Live",
  in_progress: "In progress",
  archived: "Archived",
};

export default function PortfolioPage() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState<ProjectStatus>("live");
  const [url, setUrl] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [tech, setTech] = useState("");
  const [description, setDescription] = useState("");
  const [pendingDelete, setPendingDelete] = useState<PortfolioItem | null>(null);

  const { data: items, isLoading } = useQuery({
    queryKey: QUERY_KEYS.portfolio,
    queryFn: portfolioApi.list,
    staleTime: 60 * 1000,
  });

  const resetForm = () => {
    setTitle("");
    setRole("");
    setStatus("live");
    setUrl("");
    setRepoUrl("");
    setTech("");
    setDescription("");
    setShowForm(false);
  };

  const createMutation = useMutation({
    mutationFn: portfolioApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.portfolio });
      toast.success("Project added");
      resetForm();
    },
    onError: () => toast.error("Couldn't save that. Please try again."),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => portfolioApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.portfolio });
      toast.success("Project removed");
      setPendingDelete(null);
    },
    onError: () => toast.error("Couldn't remove that. Please try again."),
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    createMutation.mutate({
      title: title.trim(),
      role: role.trim(),
      status,
      url: url.trim(),
      repoUrl: repoUrl.trim(),
      description: description.trim(),
      tech: tech
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
    });
  };

  return (
    <div className="mx-auto max-w-[900px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Assets"
        title="Portfolio"
        description="A showcase of work you've shipped — projects, case studies and demos. Record the tech and your role so each entry doubles as evidence for your target roles."
        actions={
          <button
            type="button"
            onClick={() => setShowForm((v) => !v)}
            className="inline-flex items-center rounded-[7px] bg-ink px-3.5 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2"
          >
            {showForm ? "Close" : "+ Add project"}
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
              placeholder="Project name"
              className={FIELD_CLASS}
            />
            <input
              value={role}
              onChange={(e) => setRole(e.target.value)}
              placeholder="Your role (optional)"
              className={FIELD_CLASS}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="Live URL (optional)"
              className={FIELD_CLASS}
            />
            <input
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              placeholder="Repository URL (optional)"
              className={FIELD_CLASS}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <input
              value={tech}
              onChange={(e) => setTech(e.target.value)}
              placeholder="Tech / skills — comma separated"
              className={FIELD_CLASS}
            />
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as ProjectStatus)}
              className={FIELD_CLASS}
            >
              {STATUS_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What is it, and what did you build? (optional)"
            rows={3}
            className={`${FIELD_CLASS} resize-y`}
          />
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={!title.trim() || createMutation.isPending}
              className="rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-50"
            >
              {createMutation.isPending ? "Saving…" : "Save project"}
            </button>
          </div>
        </form>
      )}

      {isLoading ? (
        <LoadingSpinner fullPage label="Loading your portfolio…" />
      ) : !items || items.length === 0 ? (
        <EmptyState
          title="No projects yet"
          description="Add the work you're proudest of. A strong portfolio turns your roadmap progress into proof recruiters can see."
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {items.map((item: PortfolioItem) => (
            <article
              key={item.id}
              className="flex flex-col gap-3 rounded-[12px] border border-rule bg-paper p-5"
            >
              <div className="flex items-start justify-between gap-3">
                <span
                  className={`rounded-[5px] px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.04em] ${STATUS_CHIP[item.status]}`}
                >
                  {STATUS_LABEL[item.status]}
                </span>
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
                {item.role && (
                  <p className="mt-0.5 text-[12.5px] text-ink-3">{item.role}</p>
                )}
                {item.description && (
                  <p className="mt-1.5 line-clamp-3 text-[13px] leading-relaxed text-ink-2">
                    {item.description}
                  </p>
                )}
              </div>
              {item.tech.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {item.tech.map((t) => (
                    <span
                      key={t}
                      className="rounded-[5px] bg-bg-2 px-2 py-0.5 text-[11px] font-medium text-ink-2"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              )}
              <div className="mt-auto flex flex-wrap gap-4 pt-1">
                {item.url && (
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[12px] font-medium text-terra transition-colors hover:text-terra-2"
                  >
                    Live →
                  </a>
                )}
                {item.repoUrl && (
                  <a
                    href={item.repoUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[12px] font-medium text-ink-2 transition-colors hover:text-ink"
                  >
                    Code →
                  </a>
                )}
              </div>
            </article>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title="Remove this project?"
        description={
          pendingDelete
            ? `"${pendingDelete.title}" will be permanently deleted from your portfolio.`
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
