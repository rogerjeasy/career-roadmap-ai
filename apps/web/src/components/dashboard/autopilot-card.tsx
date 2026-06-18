"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { autopilotApi, type AutopilotProposal } from "@/lib/api/autopilot";
import { QUERY_KEYS, ROUTES } from "@/lib/constants";
import { cn } from "@/lib/utils";

// Show at most this many proposals on the dashboard; the rest live on /autopilot.
const MAX_VISIBLE = 3;

function AutopilotSkeleton() {
  return (
    <div className="animate-pulse rounded-[9px] border border-rule p-3">
      <div className="flex items-start gap-2.5">
        <div className="mt-1 h-2 w-2 shrink-0 rounded-full bg-bg-3" />
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="h-3.5 w-2/3 rounded bg-bg-3" />
          <div className="h-2.5 w-full rounded bg-bg-2" />
        </div>
      </div>
    </div>
  );
}

function AutopilotEmpty() {
  return (
    <div className="flex flex-col items-center justify-center rounded-[9px] border border-dashed border-rule py-8 text-center">
      <p className="mb-1 text-[13px] font-medium text-ink-2">You&apos;re on track</p>
      <p className="max-w-[240px] text-[12px] text-ink-3">
        No suggestions right now. Autopilot watches your reviews, habits and market signals.
      </p>
    </div>
  );
}

interface ProposalRowProps {
  proposal: AutopilotProposal;
  onAccept: () => void;
  onDismiss: () => void;
  busy: boolean;
}

function ProposalRow({ proposal, onAccept, onDismiss, busy }: ProposalRowProps) {
  const isWarn = proposal.severity === "warn";
  return (
    <div className="rounded-[9px] border border-rule p-3 transition-colors duration-150 hover:border-rule-strong">
      <div className="flex items-start gap-2.5">
        <span
          className={cn(
            "mt-1.5 h-2 w-2 shrink-0 rounded-full",
            isWarn ? "bg-terra" : "bg-green",
          )}
          aria-hidden="true"
        />
        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-medium leading-[1.3] text-ink">{proposal.title}</p>
          <p className="mt-0.5 line-clamp-2 text-[11.5px] leading-[1.4] text-ink-3">
            {proposal.detail}
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onAccept}
              disabled={busy}
              className="rounded-[6px] bg-green px-2.5 py-1 text-[11.5px] font-medium text-white transition-colors duration-150 hover:bg-green-2 disabled:opacity-50"
            >
              {proposal.actionLabel || "Accept"}
            </button>
            <button
              type="button"
              onClick={onDismiss}
              disabled={busy}
              className="rounded-[6px] border border-rule px-2.5 py-1 text-[11.5px] font-medium text-ink-2 transition-colors duration-150 hover:border-rule-strong hover:text-ink disabled:opacity-50"
            >
              Dismiss
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function AutopilotCard() {
  const queryClient = useQueryClient();
  const router = useRouter();

  // Shares QUERY_KEYS.autopilot with the sidebar badge → dedupes rather than refetches.
  const { data: proposals, isLoading } = useQuery({
    queryKey: QUERY_KEYS.autopilot,
    queryFn: autopilotApi.list,
    staleTime: 5 * 60 * 1000,
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

  const busy = acceptMutation.isPending || dismissMutation.isPending;
  const all = proposals ?? [];
  const visible = all.slice(0, MAX_VISIBLE);

  return (
    <div className="rounded-[12px] border border-rule bg-paper p-6">
      {/* Header */}
      <div className="mb-[18px] flex items-start justify-between border-b border-rule pb-3.5">
        <div>
          <h2 className="font-serif text-[17px] font-medium tracking-[-0.01em] text-ink">
            Autopilot
          </h2>
          <p className="mt-[3px] text-[11.5px] text-ink-3">
            {all.length > 0 ? `${all.length} suggestion${all.length === 1 ? "" : "s"} · ` : ""}
            <em className="font-serif italic text-terra">accept to apply</em>
          </p>
        </div>
        <Link
          href={ROUTES.autopilot}
          className="text-[12px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
        >
          All →
        </Link>
      </div>

      <div className="flex flex-col gap-2.5">
        {isLoading ? (
          [0, 1].map((i) => <AutopilotSkeleton key={i} />)
        ) : visible.length > 0 ? (
          visible.map((p) => (
            <ProposalRow
              key={p.id}
              proposal={p}
              onAccept={() => acceptMutation.mutate(p)}
              onDismiss={() => dismissMutation.mutate(p.id)}
              busy={busy}
            />
          ))
        ) : (
          <AutopilotEmpty />
        )}
      </div>
    </div>
  );
}
