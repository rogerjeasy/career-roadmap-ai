"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  discoveryApi,
  type CareerPathOption,
  type EffortLevel,
} from "@/lib/api/discovery";
import { updateUserProfileContext } from "@/lib/api/session";
import { QUERY_KEYS, ROUTES } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { cn } from "@/lib/utils";

const EFFORT_STYLES: Record<EffortLevel, string> = {
  low: "bg-green-soft text-green-2",
  medium: "bg-bg-3 text-ink-2",
  high: "bg-terra-soft text-terra-2",
};

export default function DiscoveryPage() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const [selected, setSelected] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: QUERY_KEYS.discovery,
    queryFn: discoveryApi.get,
    staleTime: 5 * 60 * 1000,
  });

  const generateMutation = useMutation({
    mutationFn: discoveryApi.generate,
    onSuccess: (result) => {
      queryClient.setQueryData(QUERY_KEYS.discovery, result);
      if (!result.hasData) {
        toast.info("Upload a CV or set your skills first, then try again.");
      }
    },
    onError: () => toast.error("Couldn't generate paths. Please try again."),
  });

  const useMutationPath = useMutation({
    mutationFn: (title: string) => updateUserProfileContext({ targetRole: title }),
    onSuccess: () => {
      toast.success("Target set — let's build your roadmap.");
      router.push(ROUTES.roadmapGenerate);
    },
    onError: () => toast.error("Couldn't set that as your target. Please try again."),
  });

  const paths = data?.paths ?? [];

  return (
    <div className="mx-auto max-w-[1100px] px-7 pb-24 pt-7">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <PageHeader
          eyebrow="Planning"
          title="Discover Paths"
          description="Not sure which direction to take? We read your profile and surface comparable career paths — each with fit, effort, salary and a sample roadmap. Pick one to turn it into a plan."
        />
        <button
          type="button"
          onClick={() => generateMutation.mutate()}
          disabled={generateMutation.isPending}
          className="mb-1 shrink-0 self-start rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-50 sm:self-auto"
        >
          {generateMutation.isPending
            ? "Analysing…"
            : paths.length
              ? "Regenerate"
              : "Discover paths"}
        </button>
      </div>

      {data?.basedOn && paths.length > 0 && (
        <p className="mt-4 text-[12.5px] text-ink-3">Based on: {data.basedOn}</p>
      )}

      <div className="mt-6">
        {isLoading || generateMutation.isPending ? (
          <LoadingSpinner fullPage label="Mapping your options…" />
        ) : paths.length === 0 ? (
          <EmptyState
            title="No paths yet"
            description="Generate a set of career paths from your CV and profile. Make sure you've uploaded a CV or added your skills first."
          />
        ) : (
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
            {paths.map((path) => (
              <PathCard
                key={path.title}
                path={path}
                expanded={selected === path.title}
                onToggle={() =>
                  setSelected((cur) => (cur === path.title ? null : path.title))
                }
                onUse={() => useMutationPath.mutate(path.title)}
                useBusy={useMutationPath.isPending}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

interface PathCardProps {
  path: CareerPathOption;
  expanded: boolean;
  onToggle: () => void;
  onUse: () => void;
  useBusy: boolean;
}

function PathCard({ path, expanded, onToggle, onUse, useBusy }: PathCardProps) {
  const fmt = (n: number) => (n > 0 ? new Intl.NumberFormat().format(n) : "—");
  return (
    <article className="flex min-w-0 flex-col rounded-[12px] border border-rule bg-paper p-5">
      <header className="flex items-start justify-between gap-3">
        <h2 className="min-w-0 font-serif text-[17px] font-medium tracking-[-0.01em] text-ink">
          {path.title}
        </h2>
        <div className="flex shrink-0 items-center gap-2">
          <span
            className="rounded-[5px] bg-green-soft px-2 py-1 text-[11px] font-semibold text-green-2"
            title="How well your current profile fits"
          >
            {path.fitScore}% fit
          </span>
        </div>
      </header>

      {path.summary && (
        <p className="mt-2 text-[13.5px] leading-relaxed text-ink-2 break-words">
          {path.summary}
        </p>
      )}

      {/* Comparable stats */}
      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2.5">
        <Stat label="Effort to switch">
          <span
            className={cn(
              "rounded-[4px] px-1.5 py-px text-[11px] font-semibold uppercase",
              EFFORT_STYLES[path.effortToSwitch],
            )}
          >
            {path.effortToSwitch}
          </span>
        </Stat>
        <Stat label="Timeline">
          <span className="text-[13px] font-medium text-ink">
            {path.timelineMonths > 0 ? `${path.timelineMonths} mo` : "—"}
          </span>
        </Stat>
        <Stat label="Salary range">
          <span className="text-[13px] font-medium text-ink">
            {path.salaryLow > 0
              ? `${path.salaryCurrency} ${fmt(path.salaryLow)}–${fmt(path.salaryHigh)}`
              : "—"}
          </span>
        </Stat>
        <Stat label="Outlook">
          <span className="text-[12.5px] text-ink-2">{path.growthOutlook || "—"}</span>
        </Stat>
      </dl>

      {path.keySkillsToGain.length > 0 && (
        <div className="mt-4">
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-ink-3">
            Skills to gain
          </p>
          <div className="flex flex-wrap gap-1.5">
            {path.keySkillsToGain.map((s) => (
              <span
                key={s}
                className="rounded-[5px] border border-rule bg-bg px-2 py-px text-[12px] text-ink-2"
              >
                {s}
              </span>
            ))}
          </div>
        </div>
      )}

      {expanded && (
        <div className="mt-4 space-y-4 border-t border-rule pt-4">
          {path.transferableStrengths.length > 0 && (
            <DetailBlock title="Transferable strengths" items={path.transferableStrengths} />
          )}
          {path.samplePhases.length > 0 && (
            <div>
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-ink-3">
                Sample roadmap
              </p>
              <ol className="space-y-1.5" role="list">
                {path.samplePhases.map((ph, i) => (
                  <li key={`${ph.title}-${i}`} className="flex gap-2.5 text-[13px] text-ink-2">
                    <span className="mt-px flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full bg-bg-2 text-[10px] font-semibold text-ink-3">
                      {i + 1}
                    </span>
                    <span className="min-w-0">
                      <span className="font-medium text-ink">{ph.title}</span>
                      {ph.durationWeeks > 0 && (
                        <span className="text-ink-3"> · {ph.durationWeeks}w</span>
                      )}
                      {ph.focus && <span className="block text-ink-3">{ph.focus}</span>}
                    </span>
                  </li>
                ))}
              </ol>
            </div>
          )}
          {path.rationale && (
            <p className="text-[12.5px] leading-relaxed text-ink-3">
              <span className="font-semibold text-ink-2">Why this fits: </span>
              {path.rationale}
            </p>
          )}
        </div>
      )}

      <div className="mt-auto flex items-center justify-between gap-3 pt-4">
        <button
          type="button"
          onClick={onToggle}
          className="text-[12.5px] font-medium text-ink-3 transition-colors hover:text-ink"
        >
          {expanded ? "Show less" : "Show details"}
        </button>
        <button
          type="button"
          onClick={onUse}
          disabled={useBusy}
          className="rounded-[7px] bg-green px-3.5 py-1.5 text-[13px] font-medium text-white transition-colors duration-150 hover:bg-green-2 disabled:opacity-50"
        >
          Use this path →
        </button>
      </div>
    </article>
  );
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] text-ink-3">{label}</dt>
      <dd className="mt-0.5">{children}</dd>
    </div>
  );
}

function DetailBlock({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-ink-3">
        {title}
      </p>
      <ul className="space-y-1" role="list">
        {items.map((item) => (
          <li key={item} className="flex gap-2 text-[13px] text-ink-2">
            <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-rule-strong" aria-hidden="true" />
            <span className="min-w-0 break-words">{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
