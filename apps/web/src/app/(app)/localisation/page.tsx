"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  localisationApi,
  type LocalisationReport,
  type VisaDifficulty,
} from "@/lib/api/localisation";
import { QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { cn } from "@/lib/utils";

export default function LocalisationPage() {
  const [role, setRole] = useState("");
  const [countryA, setCountryA] = useState("");
  const [countryB, setCountryB] = useState("");
  // The "active" countries — only set on submit so typing doesn't trigger fetches.
  const [activeA, setActiveA] = useState("");
  const [activeB, setActiveB] = useState("");

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setActiveA(countryA.trim());
    setActiveB(countryB.trim());
  };

  return (
    <div className="mx-auto max-w-[1100px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Intelligence"
        title="Localisation"
        description="Country-aware career intelligence: visa pathways, local salary norms, language expectations and relocation steps for your target role — compare two countries side by side."
      />

      <form
        onSubmit={onSubmit}
        className="mt-6 rounded-[12px] border border-rule bg-paper p-5"
      >
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Field label="Role (optional)" hint="Defaults to your target role">
            <input
              value={role}
              onChange={(e) => setRole(e.target.value)}
              placeholder="e.g. ML Engineer"
              className="w-full rounded-[8px] border border-rule bg-bg px-3 py-2 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none"
            />
          </Field>
          <Field label="Country" hint="Required">
            <input
              value={countryA}
              onChange={(e) => setCountryA(e.target.value)}
              placeholder="e.g. Germany"
              required
              className="w-full rounded-[8px] border border-rule bg-bg px-3 py-2 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none"
            />
          </Field>
          <Field label="Compare with (optional)" hint="A second country">
            <input
              value={countryB}
              onChange={(e) => setCountryB(e.target.value)}
              placeholder="e.g. Canada"
              className="w-full rounded-[8px] border border-rule bg-bg px-3 py-2 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none"
            />
          </Field>
        </div>
        <div className="mt-4 flex justify-end">
          <button
            type="submit"
            disabled={!countryA.trim()}
            className="rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-50"
          >
            Get report
          </button>
        </div>
      </form>

      {!activeA ? (
        <div className="mt-6">
          <EmptyState
            title="Choose a country"
            description="Enter a target country (and optionally a second to compare) to generate country-aware guidance."
          />
        </div>
      ) : (
        <div
          className={cn(
            "mt-6 grid grid-cols-1 gap-5",
            activeB && "lg:grid-cols-2",
          )}
        >
          <ReportColumn country={activeA} role={role.trim() || undefined} />
          {activeB && <ReportColumn country={activeB} role={role.trim() || undefined} />}
        </div>
      )}
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[12px] font-medium text-ink-2">
        {label}
        {hint && <span className="ml-1.5 font-normal text-ink-3">· {hint}</span>}
      </span>
      {children}
    </label>
  );
}

interface ReportColumnProps {
  country: string;
  role: string | undefined;
}

function ReportColumn({ country, role }: ReportColumnProps) {
  const queryClient = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);

  const { data, isLoading, isError } = useQuery({
    queryKey: QUERY_KEYS.localisation(country, role),
    queryFn: () => localisationApi.getReport(country, { role }),
    staleTime: 30 * 60 * 1000,
  });

  const onRegenerate = async () => {
    setRefreshing(true);
    try {
      const fresh = await localisationApi.getReport(country, { role, refresh: true });
      queryClient.setQueryData(QUERY_KEYS.localisation(country, role), fresh);
    } catch {
      toast.error(`Couldn't regenerate the report for ${country}.`);
    } finally {
      setRefreshing(false);
    }
  };

  if (isLoading) {
    return (
      <div className="rounded-[12px] border border-rule bg-paper p-6">
        <LoadingSpinner label={`Generating guidance for ${country}…`} />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="rounded-[12px] border border-rule bg-paper p-6">
        <p className="text-[13.5px] text-ink-2">
          Couldn&apos;t generate a report for {country}. Make sure a target role is set,
          then try again.
        </p>
      </div>
    );
  }

  return <ReportCard report={data} refreshing={refreshing} onRegenerate={onRegenerate} />;
}

const DIFFICULTY_STYLES: Record<VisaDifficulty, string> = {
  easy: "bg-green-soft text-green-2",
  moderate: "bg-bg-3 text-ink-2",
  hard: "bg-terra-soft text-terra-2",
  unknown: "bg-bg-3 text-ink-3",
};

interface ReportCardProps {
  report: LocalisationReport;
  refreshing: boolean;
  onRegenerate: () => void;
}

function ReportCard({ report, refreshing, onRegenerate }: ReportCardProps) {
  const fmt = (n: number) =>
    n > 0 ? new Intl.NumberFormat().format(n) : "—";
  const confidencePct = Math.round(report.confidence * 100);

  return (
    <article className="min-w-0 space-y-4 rounded-[12px] border border-rule bg-paper p-5">
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-serif text-[18px] font-medium tracking-[-0.01em] text-ink">
            {report.country}
          </h2>
          <p className="mt-0.5 text-[12.5px] text-ink-3">{report.role}</p>
        </div>
        <span
          className={cn(
            "shrink-0 rounded-[5px] px-2 py-1 text-[11px] font-semibold",
            confidencePct >= 60
              ? "bg-green-soft text-green-2"
              : confidencePct >= 30
                ? "bg-bg-3 text-ink-2"
                : "bg-terra-soft text-terra-2",
          )}
          title="How confident the model is in this guidance"
        >
          {confidencePct}% confidence
        </span>
      </header>

      {report.summary && (
        <p className="text-[13.5px] leading-relaxed text-ink-2 break-words">
          {report.summary}
        </p>
      )}

      {/* Salary */}
      <Section title="Salary (annual, local)">
        <p className="text-[15px] font-semibold text-ink">
          {report.salary.currency} {fmt(report.salary.low)} – {fmt(report.salary.high)}
          {report.salary.median > 0 && (
            <span className="ml-2 text-[12.5px] font-normal text-ink-3">
              median {report.salary.currency} {fmt(report.salary.median)}
            </span>
          )}
        </p>
        {report.salary.note && (
          <p className="mt-1 text-[12.5px] text-ink-3">{report.salary.note}</p>
        )}
        {report.costOfLiving && (
          <p className="mt-1 text-[12.5px] text-ink-3">{report.costOfLiving}</p>
        )}
      </Section>

      {report.visaPathways.length > 0 && (
        <Section title="Visa & work permits">
          <ul className="space-y-2" role="list">
            {report.visaPathways.map((v) => (
              <li key={v.name} className="rounded-[8px] border border-rule p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[13.5px] font-medium text-ink">{v.name}</span>
                  <span
                    className={cn(
                      "shrink-0 rounded-[4px] px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide",
                      DIFFICULTY_STYLES[v.difficulty],
                    )}
                  >
                    {v.difficulty}
                  </span>
                </div>
                <p className="mt-1 text-[12.5px] leading-relaxed text-ink-2">{v.summary}</p>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {report.languageRequirements && (
        <Section title="Language">
          <p className="text-[13px] leading-relaxed text-ink-2">
            {report.languageRequirements}
          </p>
        </Section>
      )}

      {report.hiringCulture.length > 0 && (
        <Section title="Hiring culture">
          <BulletList items={report.hiringCulture} />
        </Section>
      )}

      {report.networkingChannels.length > 0 && (
        <Section title="Where to network">
          <BulletList items={report.networkingChannels} />
        </Section>
      )}

      {report.relocationSteps.length > 0 && (
        <Section title="Relocation steps">
          <ol className="space-y-1.5" role="list">
            {report.relocationSteps.map((step, i) => (
              <li key={step} className="flex gap-2.5 text-[13px] leading-relaxed text-ink-2">
                <span className="mt-px flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full bg-bg-2 text-[10px] font-semibold text-ink-3">
                  {i + 1}
                </span>
                <span className="min-w-0">{step}</span>
              </li>
            ))}
          </ol>
        </Section>
      )}

      {report.assumptions.length > 0 && (
        <Section title="Assumptions & limits">
          <BulletList items={report.assumptions} muted />
        </Section>
      )}

      <div className="flex justify-end border-t border-rule pt-3">
        <button
          type="button"
          onClick={onRegenerate}
          disabled={refreshing}
          className="text-[12.5px] font-medium text-green transition-colors hover:text-green-2 disabled:opacity-50"
        >
          {refreshing ? "Regenerating…" : "Regenerate"}
        </button>
      </div>
    </article>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-ink-3">
        {title}
      </h3>
      {children}
    </div>
  );
}

function BulletList({ items, muted }: { items: string[]; muted?: boolean }) {
  return (
    <ul className="space-y-1.5" role="list">
      {items.map((item) => (
        <li
          key={item}
          className={cn(
            "flex gap-2 text-[13px] leading-relaxed",
            muted ? "text-ink-3" : "text-ink-2",
          )}
        >
          <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-rule-strong" aria-hidden="true" />
          <span className="min-w-0 break-words">{item}</span>
        </li>
      ))}
    </ul>
  );
}
