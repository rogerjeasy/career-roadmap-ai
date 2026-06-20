"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { portfolioApi, type ArtefactSuggestion } from "@/lib/api/portfolio";
import { QUERY_KEYS } from "@/lib/constants";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { cn } from "@/lib/utils";

const EFFORT_TONE: Record<string, string> = {
  small: "bg-green-soft text-green-2",
  medium: "bg-bg-2 text-ink-2",
  large: "bg-terra-soft text-terra-2",
};

export interface PortfolioBuildPlanProps {
  className?: string;
}

export function PortfolioBuildPlan(_props: PortfolioBuildPlanProps): React.ReactElement {
  const queryClient = useQueryClient();

  const { data: plan, isLoading } = useQuery({
    queryKey: QUERY_KEYS.portfolioPlan,
    queryFn: portfolioApi.getPlan,
    staleTime: 5 * 60 * 1000,
  });

  const generateMutation = useMutation({
    mutationFn: portfolioApi.generatePlan,
    onSuccess: (data) => {
      queryClient.setQueryData(QUERY_KEYS.portfolioPlan, data);
      toast.success("Build plan ready");
    },
    onError: () => toast.error("Couldn't generate a plan. Add a target role first."),
  });

  const suggestions = plan?.suggestions ?? [];

  return (
    <div className="rounded-[12px] border border-rule bg-paper p-5">
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="font-serif text-[16px] font-medium tracking-[-0.01em] text-ink">
            AI build plan
          </h2>
          <p className="text-[12.5px] text-ink-3">
            A prioritised sequence of artefacts to build for your target role.
          </p>
        </div>
        <button
          type="button"
          onClick={() => generateMutation.mutate()}
          disabled={generateMutation.isPending}
          className="shrink-0 rounded-[7px] bg-ink px-3.5 py-2 text-[12.5px] font-medium text-bg transition-colors hover:bg-green-2 disabled:opacity-50"
        >
          {generateMutation.isPending
            ? "Planning…"
            : suggestions.length
              ? "Regenerate"
              : "Generate plan"}
        </button>
      </div>

      {plan?.basedOn && <p className="mb-3 text-[12px] italic text-ink-3">{plan.basedOn}</p>}

      {isLoading || generateMutation.isPending ? (
        <LoadingSpinner label="Sequencing your portfolio…" />
      ) : suggestions.length === 0 ? (
        <p className="rounded-[9px] border border-dashed border-rule-strong bg-bg px-4 py-6 text-center text-[12.5px] text-ink-3">
          No plan yet — generate one to see what to build next and in what order.
        </p>
      ) : (
        <ol className="space-y-3">
          {suggestions.map((s: ArtefactSuggestion) => (
            <li key={s.id} className="rounded-[10px] border border-rule bg-bg p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="flex min-w-0 items-start gap-2.5">
                  <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-ink text-[12px] font-semibold text-bg">
                    {s.priority}
                  </span>
                  <div className="min-w-0">
                    <h3 className="font-serif text-[15px] font-medium tracking-[-0.01em] text-ink">
                      {s.title}
                    </h3>
                    <p className="text-[11.5px] uppercase tracking-[0.04em] text-ink-3">
                      {s.artefactType.replace("_", " ")}
                    </p>
                  </div>
                </div>
                <span
                  className={cn(
                    "shrink-0 rounded-[5px] px-2 py-0.5 text-[10.5px] font-semibold",
                    EFFORT_TONE[s.effort] ?? EFFORT_TONE.medium,
                  )}
                >
                  {s.effort}
                </span>
              </div>
              {s.summary && (
                <p className="mt-2 text-[13px] leading-relaxed text-ink-2">{s.summary}</p>
              )}
              {s.closesGap && (
                <p className="mt-2 text-[12.5px] text-ink-3">
                  <span className="font-medium text-ink-2">Closes: </span>
                  {s.closesGap}
                </p>
              )}
              {s.skillsDemonstrated.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {s.skillsDemonstrated.map((k) => (
                    <span
                      key={k}
                      className="rounded-[5px] bg-green-soft px-2 py-0.5 text-[11px] font-medium text-green-2"
                    >
                      {k}
                    </span>
                  ))}
                </div>
              )}
              {s.starterSteps.length > 0 && (
                <ul className="mt-2.5 list-disc space-y-0.5 pl-5 text-[12.5px] text-ink-2">
                  {s.starterSteps.map((step, i) => (
                    <li key={i}>{step}</li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
