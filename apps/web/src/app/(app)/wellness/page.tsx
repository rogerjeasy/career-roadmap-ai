"use client";

import { useState, type FormEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  wellnessApi,
  type WellnessCheckin,
  type RiskLevel,
} from "@/lib/api/wellness";
import { QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { formatDate } from "@/lib/date";
import { cn } from "@/lib/utils";

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink focus:border-green focus:bg-paper focus:outline-none";

const RISK_TONE: Record<RiskLevel, string> = {
  low: "bg-green-soft text-green-2 border-green",
  moderate: "bg-bg-2 text-ink-2 border-rule-strong",
  high: "bg-terra-soft text-terra-2 border-terra",
};

const RISK_LABEL: Record<RiskLevel, string> = {
  low: "Sustainable",
  moderate: "Watch your pace",
  high: "High burnout risk",
};

interface ScaleFieldProps {
  label: string;
  hint: string;
  value: number;
  onChange: (v: number) => void;
}

function ScaleField({ label, hint, value, onChange }: ScaleFieldProps) {
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between">
        <span className="text-[12.5px] font-medium text-ink">{label}</span>
        <span className="text-[11px] text-ink-3">{hint}</span>
      </div>
      <div className="flex gap-1.5">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            onClick={() => onChange(n)}
            className={cn(
              "h-9 flex-1 rounded-[7px] border text-[13px] font-medium tabular-nums transition-colors duration-150",
              value === n
                ? "border-green bg-green text-bg"
                : "border-rule bg-bg text-ink-2 hover:border-rule-strong",
            )}
          >
            {n}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function WellnessPage() {
  const queryClient = useQueryClient();
  const [energy, setEnergy] = useState(3);
  const [stress, setStress] = useState(3);
  const [motivation, setMotivation] = useState(3);
  const [hours, setHours] = useState("40");
  const [sleep, setSleep] = useState("7");
  const [notes, setNotes] = useState("");

  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: QUERY_KEYS.wellnessStatus,
    queryFn: wellnessApi.status,
    staleTime: 30 * 1000,
  });

  const { data: checkins, isLoading: listLoading } = useQuery({
    queryKey: QUERY_KEYS.wellnessCheckins,
    queryFn: wellnessApi.list,
    staleTime: 30 * 1000,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: QUERY_KEYS.wellnessStatus });
    queryClient.invalidateQueries({ queryKey: QUERY_KEYS.wellnessCheckins });
  };

  const createMutation = useMutation({
    mutationFn: wellnessApi.create,
    onSuccess: () => {
      invalidate();
      toast.success("Check-in logged");
      setNotes("");
    },
    onError: () => toast.error("Couldn't save that check-in."),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => wellnessApi.remove(id),
    onSuccess: () => {
      invalidate();
      toast.success("Removed");
    },
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    createMutation.mutate({
      energy,
      stress,
      motivation,
      hoursWorked: hours ? Number(hours) : 40,
      sleepHours: sleep ? Number(sleep) : 7,
      notes: notes.trim(),
    });
  };

  return (
    <div className="mx-auto max-w-[820px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Sustainability"
        title="Wellness Monitor"
        description="Track your pace so ambition doesn't cost you burnout. Log how you're doing and we'll flag rising risk early — and suggest a recovery week before momentum stalls."
      />

      {statusLoading ? (
        <LoadingSpinner label="Reading your pace…" />
      ) : status && status.sampleSize > 0 ? (
        <div className={cn("mb-6 rounded-[12px] border p-5", RISK_TONE[status.riskLevel])}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="text-[14px] font-semibold">{RISK_LABEL[status.riskLevel]}</span>
            <span className="text-[12.5px] tabular-nums opacity-80">
              risk {status.riskScore}/100 · {status.trend}
            </span>
          </div>
          <p className="mt-2 text-[13px] leading-relaxed text-ink-2">{status.recommendation}</p>
          {status.drivers.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {status.drivers.map((d) => (
                <span
                  key={d}
                  className="rounded-[5px] bg-paper/70 px-2 py-0.5 text-[11px] font-medium text-ink-2"
                >
                  {d}
                </span>
              ))}
            </div>
          )}
          {status.recoverySuggested && (
            <p className="mt-3 rounded-[8px] bg-paper px-3.5 py-2.5 text-[12.5px] font-medium text-terra-2">
              💡 Consider scheduling a recovery week — lighten goals and protect rest.
            </p>
          )}
        </div>
      ) : (
        <div className="mb-6 rounded-[12px] border border-rule bg-bg-2 px-4 py-3 text-[12.5px] text-ink-2">
          Log a couple of check-ins to unlock your burnout-risk read.
        </div>
      )}

      <form
        onSubmit={onSubmit}
        className="mb-8 space-y-4 rounded-[12px] border border-rule bg-paper p-5"
      >
        <p className="text-[12px] font-semibold uppercase tracking-[0.06em] text-ink-3">
          How are you doing this week?
        </p>
        <div className="grid gap-4 sm:grid-cols-3">
          <ScaleField label="Energy" hint="low → high" value={energy} onChange={setEnergy} />
          <ScaleField label="Stress" hint="low → high" value={stress} onChange={setStress} />
          <ScaleField label="Motivation" hint="low → high" value={motivation} onChange={setMotivation} />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1.5 block text-[12.5px] font-medium text-ink">Hours worked / week</span>
            <input value={hours} onChange={(e) => setHours(e.target.value)} type="number" min="0" max="168" className={FIELD_CLASS} />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-[12.5px] font-medium text-ink">Sleep / night</span>
            <input value={sleep} onChange={(e) => setSleep(e.target.value)} type="number" min="0" max="24" step="0.5" className={FIELD_CLASS} />
          </label>
        </div>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Anything notable this week? (optional)"
          rows={2}
          className={`${FIELD_CLASS} resize-y placeholder:text-ink-3`}
        />
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={createMutation.isPending}
            className="rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors hover:bg-green-2 disabled:opacity-50"
          >
            {createMutation.isPending ? "Saving…" : "Log check-in"}
          </button>
        </div>
      </form>

      <p className="mb-3 text-[12px] font-semibold uppercase tracking-[0.06em] text-ink-3">
        History
      </p>
      {listLoading ? (
        <LoadingSpinner label="Loading history…" />
      ) : !checkins || checkins.length === 0 ? (
        <EmptyState
          title="No check-ins yet"
          description="Your first log starts the trend line. A minute a week is enough to keep your pace honest."
        />
      ) : (
        <div className="space-y-2">
          {checkins.map((c: WellnessCheckin) => (
            <div
              key={c.id}
              className="flex items-center justify-between gap-3 rounded-[10px] border border-rule bg-paper px-4 py-3"
            >
              <div className="min-w-0">
                <p className="text-[12.5px] text-ink-2">
                  <span className="tabular-nums">E{c.energy}</span> · S{c.stress} · M
                  {c.motivation} · {c.hoursWorked}h · {c.sleepHours}h sleep
                </p>
                {c.notes && <p className="mt-0.5 truncate text-[12px] text-ink-3">{c.notes}</p>}
              </div>
              <div className="flex shrink-0 items-center gap-3">
                {c.createdAt && (
                  <span className="text-[11.5px] text-ink-3">{formatDate(c.createdAt)}</span>
                )}
                <button
                  type="button"
                  onClick={() => deleteMutation.mutate(c.id)}
                  className="text-[11.5px] font-medium text-ink-3 transition-colors hover:text-destructive"
                >
                  Remove
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
