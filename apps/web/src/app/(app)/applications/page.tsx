"use client";

import { useRef, useState, type DragEvent, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  applicationsApi,
  type Application,
  type ApplicationStatus,
} from "@/lib/api/applications";
import {
  STAGES,
  STATUS_LABEL,
  STATUS_TONE,
  OUTCOME_LABEL,
  OUTCOME_TONE,
} from "@/lib/applications-meta";
import { ROUTES, QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { cn } from "@/lib/utils";

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

export default function ApplicationsPage() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const [showForm, setShowForm] = useState(false);
  const [company, setCompany] = useState("");
  const [role, setRole] = useState("");
  const [jobUrl, setJobUrl] = useState("");
  const [location, setLocation] = useState("");
  const [dragId, setDragId] = useState<string | null>(null);
  const [overStatus, setOverStatus] = useState<ApplicationStatus | null>(null);
  // Suppresses the card's navigate-on-click immediately after a drag ends.
  const draggedRef = useRef(false);

  const { data: apps, isLoading } = useQuery({
    queryKey: QUERY_KEYS.applications,
    queryFn: applicationsApi.list,
    staleTime: 30 * 1000,
  });

  const createMutation = useMutation({
    mutationFn: applicationsApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.applications });
      toast.success("Application added");
      setCompany("");
      setRole("");
      setJobUrl("");
      setLocation("");
      setShowForm(false);
    },
    onError: () => toast.error("Couldn't add that application."),
  });

  const moveMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: ApplicationStatus }) =>
      applicationsApi.update(id, { status }),
    onMutate: async ({ id, status }) => {
      await queryClient.cancelQueries({ queryKey: QUERY_KEYS.applications });
      const previous = queryClient.getQueryData<Application[]>(QUERY_KEYS.applications);
      queryClient.setQueryData<Application[]>(QUERY_KEYS.applications, (old) =>
        (old ?? []).map((a) => (a.id === id ? { ...a, status } : a)),
      );
      return { previous };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.previous) queryClient.setQueryData(QUERY_KEYS.applications, ctx.previous);
      toast.error("Couldn't move that application.");
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.applications });
    },
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!company.trim() || !role.trim()) return;
    createMutation.mutate({
      company: company.trim(),
      role: role.trim(),
      jobUrl: jobUrl.trim(),
      location: location.trim(),
    });
  };

  const handleDrop = (status: ApplicationStatus) => {
    setOverStatus(null);
    if (!dragId) return;
    const current = (apps ?? []).find((a) => a.id === dragId);
    setDragId(null);
    if (!current || current.status === status) return;
    moveMutation.mutate({ id: dragId, status });
  };

  const grouped = (status: ApplicationStatus): Application[] =>
    (apps ?? []).filter((a) => a.status === status);

  const dueCount = (a: Application): number =>
    a.reminders.filter((r) => !r.done && new Date(r.dueAt) <= new Date()).length;

  return (
    <div className="mx-auto max-w-[1320px] px-4 pb-24 pt-7 sm:px-7">
      <PageHeader
        eyebrow="Job search"
        title="Applications"
        description="Drag a role across the pipeline. For each one, tailor a CV to the job, draft a cover letter, set follow-up reminders, and track every stage."
        actions={
          <button
            type="button"
            onClick={() => setShowForm((v) => !v)}
            className="inline-flex items-center rounded-[7px] bg-ink px-3.5 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2"
          >
            {showForm ? "Close" : "+ Track a job"}
          </button>
        }
      />

      {showForm && (
        <form onSubmit={onSubmit} className="mb-6 space-y-3 rounded-[12px] border border-rule bg-paper p-5">
          <div className="grid gap-3 sm:grid-cols-2">
            <input value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Company" className={FIELD_CLASS} />
            <input value={role} onChange={(e) => setRole(e.target.value)} placeholder="Role" className={FIELD_CLASS} />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Location (optional)" className={FIELD_CLASS} />
            <input value={jobUrl} onChange={(e) => setJobUrl(e.target.value)} placeholder="Job URL (optional)" className={FIELD_CLASS} />
          </div>
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={!company.trim() || !role.trim() || createMutation.isPending}
              className="rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors hover:bg-green-2 disabled:opacity-50"
            >
              {createMutation.isPending ? "Adding…" : "Add"}
            </button>
          </div>
        </form>
      )}

      {isLoading ? (
        <LoadingSpinner fullPage label="Loading your pipeline…" />
      ) : !apps || apps.length === 0 ? (
        <EmptyState
          title="No applications yet"
          description="Track your first role. Then tailor your CV and draft a cover letter for it in a couple of clicks."
        />
      ) : (
        <div className="-mx-4 flex snap-x gap-3 overflow-x-auto px-4 pb-4 sm:-mx-7 sm:px-7">
          {STAGES.map((status) => {
            const items = grouped(status);
            const isOver = overStatus === status;
            return (
              <section
                key={status}
                onDragOver={(e: DragEvent) => {
                  if (!dragId) return;
                  e.preventDefault();
                  setOverStatus(status);
                }}
                onDragLeave={() => setOverStatus((s) => (s === status ? null : s))}
                onDrop={() => handleDrop(status)}
                className={cn(
                  "flex w-[80vw] shrink-0 snap-start flex-col rounded-[12px] border bg-bg/40 p-2.5 transition-colors sm:w-[260px]",
                  isOver ? "border-green bg-green-faint" : "border-rule",
                )}
              >
                <div className="mb-2.5 flex items-center justify-between px-1.5">
                  <span className="text-[12px] font-semibold uppercase tracking-[0.08em] text-ink-2">
                    {STATUS_LABEL[status]}
                  </span>
                  <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-medium", STATUS_TONE[status])}>
                    {items.length}
                  </span>
                </div>

                <div className="flex min-h-[60px] flex-col gap-2.5">
                  {items.map((a) => {
                    const due = dueCount(a);
                    return (
                      <article
                        key={a.id}
                        draggable
                        onDragStart={() => {
                          draggedRef.current = true;
                          setDragId(a.id);
                        }}
                        onDragEnd={() => {
                          setDragId(null);
                          setOverStatus(null);
                          window.setTimeout(() => {
                            draggedRef.current = false;
                          }, 0);
                        }}
                        onClick={() => {
                          if (draggedRef.current) return;
                          router.push(ROUTES.application(a.id));
                        }}
                        className={cn(
                          "group cursor-pointer rounded-[10px] border border-rule bg-paper p-3 transition-colors hover:border-rule-strong",
                          dragId === a.id && "opacity-50",
                        )}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <h3 className="min-w-0 break-words font-serif text-[14px] font-medium leading-snug tracking-[-0.01em] text-ink">
                            {a.role}
                          </h3>
                          {a.status === "closed" && a.outcome && (
                            <span className={cn("shrink-0 rounded-[5px] px-1.5 py-0.5 text-[10px] font-semibold", OUTCOME_TONE[a.outcome])}>
                              {OUTCOME_LABEL[a.outcome]}
                            </span>
                          )}
                        </div>
                        <p className="mt-0.5 truncate text-[12px] text-ink-2">{a.company}</p>
                        <div className="mt-2 flex flex-wrap items-center gap-1.5">
                          {a.tailoredCv && (
                            <span className="rounded-[4px] bg-green-soft px-1.5 py-0.5 text-[10px] font-medium text-green-2">
                              CV {a.tailoredCv.fitScore}%
                            </span>
                          )}
                          {a.coverLetter && (
                            <span className="rounded-[4px] bg-green-soft px-1.5 py-0.5 text-[10px] font-medium text-green-2">
                              Letter
                            </span>
                          )}
                          {due > 0 && (
                            <span className="rounded-[4px] bg-terra-soft px-1.5 py-0.5 text-[10px] font-medium text-terra-2">
                              {due} due
                            </span>
                          )}
                          {a.location && (
                            <span className="truncate text-[11px] text-ink-3">{a.location}</span>
                          )}
                        </div>
                        {/* Accessible / touch fallback for moving without drag. */}
                        <select
                          aria-label={`Move ${a.role} to stage`}
                          value={a.status}
                          onClick={(e) => e.stopPropagation()}
                          onChange={(e) => {
                            const next = e.target.value as ApplicationStatus;
                            if (next !== a.status) moveMutation.mutate({ id: a.id, status: next });
                          }}
                          className="mt-2.5 w-full rounded-[6px] border border-rule bg-bg px-2 py-1 text-[11.5px] text-ink-2 focus:border-green focus:outline-none"
                        >
                          {STAGES.map((s) => (
                            <option key={s} value={s}>
                              {STATUS_LABEL[s]}
                            </option>
                          ))}
                        </select>
                      </article>
                    );
                  })}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
