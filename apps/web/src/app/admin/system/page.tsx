"use client";

import { useState } from "react";
import { RefreshCw, Database, Play } from "lucide-react";
import { useSystemHealth, useKbOps, useKbEvalResults } from "@/hooks/use-admin";
import { formatRelative } from "@/lib/date";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { SectionCard, HealthBadge } from "@/components/admin/admin-ui";
import type { KbDocType } from "@/types/admin.types";

const DOC_TYPES: { value: KbDocType; label: string }[] = [
  { value: "career_kb", label: "Career KB" },
  { value: "esco", label: "ESCO" },
  { value: "onet", label: "O*NET" },
  { value: "market_reports", label: "Market reports" },
  { value: "role_templates", label: "Role templates" },
  { value: "swiss_eu_market", label: "Swiss/EU market" },
  { value: "global_market", label: "Global market" },
];

const OVERALL_LABEL: Record<string, string> = {
  ok: "All systems operational",
  degraded: "Some systems degraded",
  down: "Service disruption",
};

function pct(n?: number): string {
  return n === undefined || n === null ? "—" : `${Math.round(n * 100)}%`;
}

export default function AdminSystemPage() {
  const health = useSystemHealth();
  const { ingest, runEval } = useKbOps();
  const evalResults = useKbEvalResults();
  const [selected, setSelected] = useState<KbDocType[]>([]);

  const toggle = (t: KbDocType) =>
    setSelected((cur) => (cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t]));

  const results = evalResults.data;

  return (
    <div className="mx-auto max-w-[900px] px-4 pb-16 pt-6 sm:px-6 lg:px-8">
      <PageHeader
        eyebrow="Admin"
        title="System"
        description="Live health of platform dependencies and knowledge-base operations."
      />

      <div className="space-y-6">
        {/* Health */}
        <SectionCard
          title="Health"
          action={
            <button
              type="button"
              onClick={() => health.refetch()}
              disabled={health.isFetching}
              className="inline-flex items-center gap-1.5 rounded-[7px] border border-rule bg-paper px-3 py-1.5 text-[12.5px] font-medium text-ink-2 transition-colors duration-150 hover:bg-bg-2 disabled:opacity-50"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", health.isFetching && "animate-spin")} />
              Refresh
            </button>
          }
        >
          {health.isLoading && (
            <div className="px-5 py-8">
              <LoadingSpinner label="Probing services…" />
            </div>
          )}
          {health.data && (
            <>
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-rule px-4 py-3 sm:px-5">
                <span className="flex items-center gap-2">
                  <span
                    className={cn(
                      "h-2.5 w-2.5 rounded-full",
                      health.data.status === "ok"
                        ? "bg-green"
                        : health.data.status === "degraded"
                          ? "bg-amber-500"
                          : "bg-destructive",
                    )}
                  />
                  <span className="text-[13.5px] font-medium text-ink">
                    {OVERALL_LABEL[health.data.status]}
                  </span>
                </span>
                <span className="rounded-[5px] bg-bg-3 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-ink-2">
                  {health.data.environment}
                </span>
              </div>
              <ul className="divide-y divide-rule">
                {health.data.components.map((c) => (
                  <li
                    key={c.name}
                    className="flex items-center justify-between gap-3 px-4 py-3 sm:px-5"
                  >
                    <div className="min-w-0">
                      <p className="text-[13.5px] font-medium text-ink">{c.name}</p>
                      {c.detail && (
                        <p className="truncate text-[12px] text-ink-3">{c.detail}</p>
                      )}
                    </div>
                    <HealthBadge status={c.status} />
                  </li>
                ))}
              </ul>
              <p className="px-4 py-2.5 text-[11.5px] text-ink-3 sm:px-5">
                Checked {formatRelative(health.data.generatedAt)}
              </p>
            </>
          )}
        </SectionCard>

        {/* KB ingestion */}
        <SectionCard
          title="Knowledge base"
          description="Trigger background ingestion into the vector store. Idempotent (upsert)."
        >
          <div className="p-4 sm:p-5">
            <div className="flex flex-wrap gap-2">
              {DOC_TYPES.map((t) => {
                const on = selected.includes(t.value);
                return (
                  <button
                    key={t.value}
                    type="button"
                    onClick={() => toggle(t.value)}
                    className={cn(
                      "rounded-[7px] border px-3 py-1.5 text-[12.5px] font-medium transition-colors duration-150",
                      on
                        ? "border-green-2 bg-green-faint text-green-2"
                        : "border-rule bg-paper text-ink-2 hover:border-rule-strong",
                    )}
                    aria-pressed={on}
                  >
                    {t.label}
                  </button>
                );
              })}
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-2.5">
              <button
                type="button"
                onClick={() => ingest.mutate(selected)}
                disabled={selected.length === 0 || ingest.isPending}
                className="inline-flex items-center gap-2 rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-40"
              >
                <Database className="h-3.5 w-3.5" />
                Ingest selected ({selected.length})
              </button>
              <button
                type="button"
                onClick={() => ingest.mutate([])}
                disabled={ingest.isPending}
                className="inline-flex items-center gap-2 rounded-[7px] border border-rule-strong bg-paper px-4 py-2 text-[13px] font-medium text-ink-2 transition-colors duration-150 hover:bg-bg-2 disabled:opacity-50"
              >
                Ingest full corpus
              </button>
              {ingest.isPending && <span className="text-[12.5px] text-ink-3">Dispatching…</span>}
            </div>
          </div>
        </SectionCard>

        {/* RAG eval */}
        <SectionCard
          title="Retrieval quality"
          description="Offline RAG evaluation against the curated ground-truth set."
          action={
            <button
              type="button"
              onClick={() => runEval.mutate()}
              disabled={runEval.isPending}
              className="inline-flex items-center gap-1.5 rounded-[7px] bg-ink px-3.5 py-1.5 text-[12.5px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-50"
            >
              <Play className="h-3.5 w-3.5" />
              {runEval.isPending ? "Starting…" : "Run eval"}
            </button>
          }
        >
          {evalResults.isLoading && (
            <div className="px-5 py-6">
              <LoadingSpinner label="Loading results…" />
            </div>
          )}
          {results && !results.found && (
            <p className="px-4 py-5 text-[13px] text-ink-3 sm:px-5">
              {results.message || "No eval results yet. Run an evaluation to populate this."}
            </p>
          )}
          {results && results.found && (
            <>
              <div className="grid grid-cols-2 gap-px bg-rule sm:grid-cols-3">
                {[
                  { label: "Recall@5", value: pct(results.meanRecallAt5) },
                  { label: "Recall@10", value: pct(results.meanRecallAt10) },
                  { label: "MRR", value: pct(results.meanMrr) },
                  { label: "NDCG@5", value: pct(results.meanNdcgAt5) },
                  { label: "NDCG@10", value: pct(results.meanNdcgAt10) },
                  {
                    label: "p95 latency",
                    value:
                      results.p95LatencySeconds === undefined
                        ? "—"
                        : `${results.p95LatencySeconds.toFixed(2)}s`,
                  },
                ].map((m) => (
                  <div key={m.label} className="bg-paper px-4 py-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-3">
                      {m.label}
                    </p>
                    <p className="mt-1 font-serif text-[18px] font-medium text-ink">{m.value}</p>
                  </div>
                ))}
              </div>
              <p className="px-4 py-2.5 text-[11.5px] text-ink-3 sm:px-5">
                {results.totalQueries ?? 0} queries
                {results.timestamp ? ` · ${formatRelative(results.timestamp)}` : ""}
              </p>
            </>
          )}
        </SectionCard>
      </div>
    </div>
  );
}
