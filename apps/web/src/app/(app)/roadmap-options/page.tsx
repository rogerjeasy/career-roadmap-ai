"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  roadmapOptionsApi,
  type RoadmapStrategyOption,
  type StrategyType,
} from "@/lib/api/roadmap-options";
import { QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { cn } from "@/lib/utils";

const STRATEGY_LABEL: Record<StrategyType, string> = {
  aggressive: "Aggressive",
  balanced: "Balanced",
  long_term: "Long-term",
};

const STRATEGY_ACCENT: Record<StrategyType, string> = {
  aggressive: "border-terra",
  balanced: "border-green",
  long_term: "border-rule-strong",
};

export default function RoadmapOptionsPage() {
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: QUERY_KEYS.roadmapOptions,
    queryFn: roadmapOptionsApi.get,
    staleTime: 60 * 1000,
  });

  const generateMutation = useMutation({
    mutationFn: roadmapOptionsApi.generate,
    onSuccess: (res) => {
      queryClient.setQueryData(QUERY_KEYS.roadmapOptions, res);
      toast.success("Three strategies ready");
    },
    onError: () => toast.error("Couldn't generate strategies. Add your goal first."),
  });

  const selectMutation = useMutation({
    mutationFn: (strategy: StrategyType) => roadmapOptionsApi.select(strategy),
    onSuccess: (res) => {
      queryClient.setQueryData(QUERY_KEYS.roadmapOptions, res);
      toast.success("Strategy selected — your plan will pace to it");
    },
    onError: () => toast.error("Couldn't select that strategy."),
  });

  const options = data?.options ?? [];

  return (
    <div className="mx-auto max-w-[1040px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Planning"
        title="Roadmap Strategies"
        description="Pick the shape of your journey before committing. Compare an aggressive sprint, a balanced path, and a sustainable long-term plan — all built from your goal and background."
        actions={
          <button
            type="button"
            onClick={() => generateMutation.mutate()}
            disabled={generateMutation.isPending}
            className="inline-flex items-center rounded-[7px] bg-ink px-3.5 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-50"
          >
            {generateMutation.isPending
              ? "Generating…"
              : options.length
                ? "Regenerate"
                : "Generate strategies"}
          </button>
        }
      />

      {data?.basedOn && (
        <p className="mb-6 text-[12.5px] italic text-ink-3">{data.basedOn}</p>
      )}

      {isLoading || generateMutation.isPending ? (
        <LoadingSpinner fullPage label="Mapping your options…" />
      ) : options.length === 0 ? (
        <EmptyState
          title="No strategies yet"
          description="Generate three comparable plans to your goal. You can switch strategies any time."
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-3">
          {options.map((o: RoadmapStrategyOption) => (
            <article
              key={o.id}
              className={cn(
                "flex flex-col rounded-[14px] border-2 bg-paper p-5",
                o.selected ? STRATEGY_ACCENT[o.strategy] : "border-rule",
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-terra">
                  {STRATEGY_LABEL[o.strategy]}
                </span>
                {o.selected && (
                  <span className="rounded-[5px] bg-green px-2 py-0.5 text-[10.5px] font-semibold text-bg">
                    Selected
                  </span>
                )}
              </div>
              <h3 className="mt-1.5 font-serif text-[18px] font-medium leading-tight tracking-[-0.01em] text-ink">
                {o.title}
              </h3>

              <div className="mt-3 flex gap-4 border-y border-rule py-3">
                <div>
                  <p className="text-[10.5px] font-semibold uppercase tracking-[0.06em] text-ink-3">
                    Timeline
                  </p>
                  <p className="font-serif text-[16px] font-medium tabular-nums text-ink">
                    {o.timelineMonths} mo
                  </p>
                </div>
                <div>
                  <p className="text-[10.5px] font-semibold uppercase tracking-[0.06em] text-ink-3">
                    Weekly
                  </p>
                  <p className="font-serif text-[16px] font-medium tabular-nums text-ink">
                    {o.weeklyHours} h
                  </p>
                </div>
              </div>

              <p className="mt-3 text-[13px] leading-relaxed text-ink-2">{o.summary}</p>

              {o.phases.length > 0 && (
                <ol className="mt-3 space-y-1.5">
                  {o.phases.map((p, i) => (
                    <li key={i} className="flex gap-2 text-[12.5px] text-ink-2">
                      <span className="shrink-0 font-medium text-ink-3">{i + 1}.</span>
                      <span>
                        <span className="font-medium text-ink">{p.title}</span>
                        {p.durationWeeks > 0 && (
                          <span className="text-ink-3"> · {p.durationWeeks}w</span>
                        )}
                      </span>
                    </li>
                  ))}
                </ol>
              )}

              {o.tradeoffs.length > 0 && (
                <div className="mt-3">
                  <p className="text-[10.5px] font-semibold uppercase tracking-[0.06em] text-ink-3">
                    Trade-offs
                  </p>
                  <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[12px] text-ink-2">
                    {o.tradeoffs.map((t, i) => (
                      <li key={i}>{t}</li>
                    ))}
                  </ul>
                </div>
              )}

              {o.bestFor && (
                <p className="mt-3 rounded-[8px] bg-bg-2 px-3 py-2 text-[12px] leading-relaxed text-ink-2">
                  <span className="font-medium text-ink">Best for: </span>
                  {o.bestFor}
                </p>
              )}

              <button
                type="button"
                onClick={() => selectMutation.mutate(o.strategy)}
                disabled={o.selected || selectMutation.isPending}
                className={cn(
                  "mt-4 rounded-[7px] px-4 py-2 text-[13px] font-medium transition-colors duration-150",
                  o.selected
                    ? "cursor-default border border-rule text-ink-3"
                    : "bg-ink text-bg hover:bg-green-2",
                )}
              >
                {o.selected ? "Current strategy" : "Choose this"}
              </button>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
