"use client";

import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  autopilotApi,
  type AutopilotProposal,
} from "@/lib/api/autopilot";
import { QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { cn } from "@/lib/utils";

export default function AutopilotPage() {
  const queryClient = useQueryClient();
  const router = useRouter();

  const { data: proposals, isLoading } = useQuery({
    queryKey: QUERY_KEYS.autopilot,
    queryFn: autopilotApi.list,
    staleTime: 60 * 1000,
  });

  const refreshMutation = useMutation({
    mutationFn: autopilotApi.refresh,
    onSuccess: (data) => {
      queryClient.setQueryData(QUERY_KEYS.autopilot, data);
      toast.success(
        data.length ? `${data.length} suggestion${data.length > 1 ? "s" : ""} ready` : "You're all caught up",
      );
    },
    onError: () => toast.error("Couldn't check for suggestions. Please try again."),
  });

  const acceptMutation = useMutation({
    mutationFn: (p: AutopilotProposal) => autopilotApi.accept(p.id),
    onSuccess: (_data, p) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.autopilot });
      if (p.actionRoute) router.push(p.actionRoute);
    },
    onError: () => toast.error("Couldn't accept that suggestion."),
  });

  const dismissMutation = useMutation({
    mutationFn: (id: string) => autopilotApi.dismiss(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.autopilot });
      toast.success("Dismissed");
    },
    onError: () => toast.error("Couldn't dismiss that suggestion."),
  });

  return (
    <div className="mx-auto max-w-[820px] px-7 pb-24 pt-7">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <PageHeader
          eyebrow="Planning"
          title="Autopilot"
          description="Consent-gated suggestions to keep your plan in sync with your progress and the market. Nothing changes until you accept it."
        />
        <button
          type="button"
          onClick={() => refreshMutation.mutate()}
          disabled={refreshMutation.isPending}
          className="mb-1 shrink-0 self-start rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-50 sm:self-auto"
        >
          {refreshMutation.isPending ? "Checking…" : "Check for suggestions"}
        </button>
      </div>

      <div className="mt-6">
        {isLoading ? (
          <LoadingSpinner fullPage label="Loading your suggestions…" />
        ) : !proposals || proposals.length === 0 ? (
          <EmptyState
            title="You're on track"
            description="No suggestions right now. Autopilot watches your reviews, habits and market signals — check back, or refresh to look now."
          />
        ) : (
          <ul className="space-y-3" role="list">
            {proposals.map((p) => (
              <li key={p.id}>
                <ProposalCard
                  proposal={p}
                  onAccept={() => acceptMutation.mutate(p)}
                  onDismiss={() => dismissMutation.mutate(p.id)}
                  busy={acceptMutation.isPending || dismissMutation.isPending}
                />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

interface ProposalCardProps {
  proposal: AutopilotProposal;
  onAccept: () => void;
  onDismiss: () => void;
  busy: boolean;
}

function ProposalCard({ proposal, onAccept, onDismiss, busy }: ProposalCardProps) {
  const isWarn = proposal.severity === "warn";
  return (
    <div className="rounded-[12px] border border-rule bg-paper p-5">
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "mt-1 h-2 w-2 shrink-0 rounded-full",
            isWarn ? "bg-terra" : "bg-green",
          )}
          aria-hidden="true"
        />
        <div className="min-w-0 flex-1">
          <h2 className="font-serif text-[16px] font-medium tracking-[-0.01em] text-ink">
            {proposal.title}
          </h2>
          <p className="mt-1 text-[13.5px] leading-relaxed text-ink-2 break-words">
            {proposal.detail}
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onAccept}
              disabled={busy}
              className="rounded-[7px] bg-green px-3.5 py-1.5 text-[13px] font-medium text-white transition-colors duration-150 hover:bg-green-2 disabled:opacity-50"
            >
              {proposal.actionLabel || "Accept"}
            </button>
            <button
              type="button"
              onClick={onDismiss}
              disabled={busy}
              className="rounded-[7px] border border-rule px-3.5 py-1.5 text-[13px] font-medium text-ink-2 transition-colors duration-150 hover:border-rule-strong hover:text-ink disabled:opacity-50"
            >
              Dismiss
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
