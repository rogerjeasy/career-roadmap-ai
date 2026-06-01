"use client";

import { useState, type FormEvent } from "react";
import { useOpportunities } from "@/hooks/use-opportunities";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { JobCard } from "@/components/opportunities/job-card";

export default function OpportunitiesPage() {
  const {
    alerts,
    isLoadingAlerts,
    jobs,
    isSearching,
    searchError,
    hasSearched,
    runSearch,
  } = useOpportunities();

  const [role, setRole] = useState("");
  const [location, setLocation] = useState("");

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    runSearch({ role: role.trim() || undefined, location: location.trim() || undefined });
  };

  return (
    <div className="mx-auto max-w-[1100px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Intelligence"
        title="Opportunities"
        description="Live job matches scored against your profile, plus the companies hiring most for your target role."
      />

      {/* Search */}
      <form
        onSubmit={onSubmit}
        className="mb-7 flex flex-col gap-2.5 rounded-[12px] border border-rule bg-paper p-4 sm:flex-row sm:items-center"
      >
        <input
          value={role}
          onChange={(e) => setRole(e.target.value)}
          placeholder="Role (defaults to your target)"
          className="min-w-0 flex-1 rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none"
        />
        <input
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          placeholder="Location"
          className="min-w-0 flex-1 rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none"
        />
        <button
          type="submit"
          disabled={isSearching}
          className="inline-flex shrink-0 items-center justify-center rounded-[8px] bg-ink px-5 py-2.5 text-[13.5px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-60"
        >
          {isSearching ? "Searching…" : "Search jobs"}
        </button>
      </form>

      {searchError && (
        <p className="mb-5 text-[13px] text-terra-2" role="alert">
          {searchError}
        </p>
      )}

      {/* Alert summary */}
      {!isLoadingAlerts && alerts && (alerts.alerts.length > 0 || alerts.targetCompanies.length > 0) && (
        <div className="mb-7 grid gap-5 lg:grid-cols-[1fr_1fr]">
          {alerts.alerts.length > 0 && (
            <section className="rounded-[12px] border border-rule bg-paper p-5">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="font-serif text-[16px] font-medium tracking-[-0.01em] text-ink">
                  Match alerts
                </h2>
                {alerts.highMatchCount > 0 && (
                  <span className="rounded-[5px] bg-terra-soft px-2 py-0.5 text-[11px] font-semibold text-terra-2">
                    {alerts.highMatchCount} high matches
                  </span>
                )}
              </div>
              <ul className="space-y-2">
                {alerts.alerts.map((a, i) => (
                  <li key={i} className="flex gap-2.5 text-[13px] leading-snug text-ink-2">
                    <span className="mt-[6px] h-1.5 w-1.5 shrink-0 rounded-full bg-terra" aria-hidden="true" />
                    <span className="min-w-0">{a}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {alerts.targetCompanies.length > 0 && (
            <section className="rounded-[12px] border border-rule bg-paper p-5">
              <h2 className="mb-3 font-serif text-[16px] font-medium tracking-[-0.01em] text-ink">
                Companies to watch
              </h2>
              <ul className="space-y-2.5">
                {alerts.targetCompanies.slice(0, 5).map((c) => (
                  <li key={c.name} className="flex items-start justify-between gap-3 border-b border-rule pb-2.5 last:border-b-0 last:pb-0">
                    <div className="min-w-0">
                      <p className="truncate text-[13.5px] font-medium text-ink">{c.name}</p>
                      {c.topRoles && c.topRoles.length > 0 && (
                        <p className="truncate text-[12px] text-ink-3">{c.topRoles.join(" · ")}</p>
                      )}
                    </div>
                    {typeof c.avgMatchScore === "number" && (
                      <span className="shrink-0 rounded-[5px] bg-green-soft px-2 py-0.5 text-[11px] font-semibold text-green-2">
                        {Math.round(c.avgMatchScore * 100)}%
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}

      {/* Results */}
      <h2 className="mb-3.5 font-serif text-[18px] font-medium tracking-[-0.01em] text-ink">
        {jobs.length > 0 ? `${jobs.length} matched roles` : "Matched roles"}
      </h2>

      {isSearching ? (
        <LoadingSpinner fullPage label="Scanning the job market…" />
      ) : jobs.length > 0 ? (
        <div className="grid gap-4 md:grid-cols-2">
          {jobs.map((job) => (
            <JobCard key={job.id} job={job} />
          ))}
        </div>
      ) : (
        <EmptyState
          title={hasSearched ? "No matches found" : "Run a search to see matches"}
          description={
            hasSearched
              ? "We couldn't find strong matches this time. Try a broader role or different location."
              : "Search above, or generate your roadmap first so matches are scored against your profile."
          }
        />
      )}
    </div>
  );
}
