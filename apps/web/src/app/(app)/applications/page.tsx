"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  applicationsApi,
  type Application,
  type ApplicationStatus,
} from "@/lib/api/applications";
import { ROUTES, QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { cn } from "@/lib/utils";

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

export const STATUS_LABEL: Record<ApplicationStatus, string> = {
  saved: "Saved",
  applied: "Applied",
  interviewing: "Interviewing",
  offer: "Offer",
  accepted: "Accepted",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

export const STATUS_TONE: Record<ApplicationStatus, string> = {
  saved: "bg-bg-2 text-ink-2",
  applied: "bg-green-soft text-green-2",
  interviewing: "bg-green-soft text-green-2",
  offer: "bg-green text-bg",
  accepted: "bg-green text-bg",
  rejected: "bg-terra-soft text-terra-2",
  withdrawn: "bg-bg-2 text-ink-3",
};

const PIPELINE: ApplicationStatus[] = [
  "saved",
  "applied",
  "interviewing",
  "offer",
  "accepted",
  "rejected",
];

export default function ApplicationsPage() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [company, setCompany] = useState("");
  const [role, setRole] = useState("");
  const [jobUrl, setJobUrl] = useState("");
  const [location, setLocation] = useState("");

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

  const grouped = (status: ApplicationStatus): Application[] =>
    (apps ?? []).filter((a) => a.status === status);

  return (
    <div className="mx-auto max-w-[1000px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Job search"
        title="Applications"
        description="Track every role through your pipeline, and for each one generate a CV tailored to the job and a cover letter — grounded in your real CV and evidence."
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
        <div className="space-y-6">
          {PIPELINE.map((status) => {
            const items = grouped(status);
            if (items.length === 0) return null;
            return (
              <section key={status}>
                <h2 className="mb-3 flex items-center gap-2 text-[12px] font-semibold uppercase tracking-[0.08em] text-ink-3">
                  {STATUS_LABEL[status]}
                  <span className="rounded-full bg-bg-2 px-2 py-0.5 text-[11px] text-ink-3">
                    {items.length}
                  </span>
                </h2>
                <div className="grid gap-3 sm:grid-cols-2">
                  {items.map((a) => (
                    <Link
                      key={a.id}
                      href={ROUTES.application(a.id)}
                      className="group flex flex-col gap-2 rounded-[12px] border border-rule bg-paper p-4 transition-colors hover:border-rule-strong"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <h3 className="truncate font-serif text-[15px] font-medium tracking-[-0.01em] text-ink">
                            {a.role}
                          </h3>
                          <p className="truncate text-[12.5px] text-ink-2">{a.company}</p>
                        </div>
                        <span className={cn("shrink-0 rounded-[5px] px-2 py-0.5 text-[10.5px] font-semibold", STATUS_TONE[a.status])}>
                          {STATUS_LABEL[a.status]}
                        </span>
                      </div>
                      <div className="flex flex-wrap items-center gap-1.5">
                        {a.tailoredCv && (
                          <span className="rounded-[4px] bg-green-soft px-1.5 py-0.5 text-[10px] font-medium text-green-2">
                            CV tailored
                          </span>
                        )}
                        {a.coverLetter && (
                          <span className="rounded-[4px] bg-green-soft px-1.5 py-0.5 text-[10px] font-medium text-green-2">
                            Cover letter
                          </span>
                        )}
                        {a.location && (
                          <span className="text-[11px] text-ink-3">{a.location}</span>
                        )}
                      </div>
                    </Link>
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
