"use client";

import { useState, type FormEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  negotiationApi,
  type OfferAnalysis,
  type Competitiveness,
} from "@/lib/api/negotiation";
import { QUERY_KEYS } from "@/lib/constants";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { cn } from "@/lib/utils";

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

const COMP_TONE: Record<Competitiveness, string> = {
  below: "bg-terra-soft text-terra-2",
  at: "bg-bg-2 text-ink-2",
  above: "bg-green-soft text-green-2",
  unknown: "bg-bg-2 text-ink-3",
};

const COMP_LABEL: Record<Competitiveness, string> = {
  below: "Below market",
  at: "At market",
  above: "Above market",
  unknown: "Insufficient data",
};

function money(value: number, currency: string): string {
  if (!value) return "—";
  return `${currency} ${value.toLocaleString()}`;
}

export interface OfferAnalyzerProps {
  className?: string;
}

export function OfferAnalyzer(_props: OfferAnalyzerProps): React.ReactElement {
  const queryClient = useQueryClient();
  const [role, setRole] = useState("");
  const [company, setCompany] = useState("");
  const [location, setLocation] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [baseSalary, setBaseSalary] = useState("");
  const [bonus, setBonus] = useState("");
  const [equity, setEquity] = useState("");
  const [years, setYears] = useState("");
  const [competing, setCompeting] = useState("");
  const [result, setResult] = useState<OfferAnalysis | null>(null);

  const { data: saved } = useQuery({
    queryKey: QUERY_KEYS.negotiationOffers,
    queryFn: negotiationApi.list,
    staleTime: 30 * 1000,
  });

  const analyzeMutation = useMutation({
    mutationFn: negotiationApi.analyze,
    onSuccess: (data) => {
      setResult(data);
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.negotiationOffers });
      toast.success("Offer analysed");
    },
    onError: () => toast.error("Couldn't analyse that offer. Please try again."),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => negotiationApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.negotiationOffers });
      toast.success("Removed");
    },
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!role.trim()) return;
    analyzeMutation.mutate({
      role: role.trim(),
      company: company.trim(),
      location: location.trim(),
      currency: currency.trim() || "USD",
      baseSalary: baseSalary ? Number(baseSalary) : 0,
      bonus: bonus ? Number(bonus) : 0,
      equity: equity.trim(),
      yearsExperience: years ? Number(years) : 0,
      competingOffer: competing.trim(),
    });
  };

  return (
    <div className="space-y-6">
      <form onSubmit={onSubmit} className="space-y-3 rounded-[12px] border border-rule bg-paper p-5">
        <div className="grid gap-3 sm:grid-cols-2">
          <input value={role} onChange={(e) => setRole(e.target.value)} placeholder="Role" className={FIELD_CLASS} />
          <input value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Company (optional)" className={FIELD_CLASS} />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Location" className={FIELD_CLASS} />
          <input value={currency} onChange={(e) => setCurrency(e.target.value)} placeholder="Currency (e.g. USD)" className={FIELD_CLASS} />
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <input value={baseSalary} onChange={(e) => setBaseSalary(e.target.value)} type="number" min="0" placeholder="Base salary" className={FIELD_CLASS} />
          <input value={bonus} onChange={(e) => setBonus(e.target.value)} type="number" min="0" placeholder="Bonus" className={FIELD_CLASS} />
          <input value={years} onChange={(e) => setYears(e.target.value)} type="number" min="0" placeholder="Years exp." className={FIELD_CLASS} />
        </div>
        <input value={equity} onChange={(e) => setEquity(e.target.value)} placeholder="Equity (optional)" className={FIELD_CLASS} />
        <input value={competing} onChange={(e) => setCompeting(e.target.value)} placeholder="Competing offer / leverage (optional)" className={FIELD_CLASS} />
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={!role.trim() || analyzeMutation.isPending}
            className="rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors hover:bg-green-2 disabled:opacity-50"
          >
            {analyzeMutation.isPending ? "Analysing…" : "Benchmark this offer"}
          </button>
        </div>
      </form>

      {analyzeMutation.isPending && <LoadingSpinner label="Coaching your offer…" />}

      {result && <AnalysisCard analysis={result} />}

      {saved && saved.length > 0 && (
        <div>
          <p className="mb-3 text-[12px] font-semibold uppercase tracking-[0.06em] text-ink-3">
            Saved analyses
          </p>
          <div className="space-y-2">
            {saved.map((a: OfferAnalysis) => (
              <div
                key={a.id}
                className="flex items-center justify-between gap-3 rounded-[9px] border border-rule bg-paper px-3.5 py-2.5 transition-colors hover:border-rule-strong"
              >
                <button
                  type="button"
                  onClick={() => setResult(a)}
                  className="min-w-0 flex-1 text-left"
                >
                  <span className="block truncate text-[13px] font-medium text-ink">
                    {a.offer.role}
                    {a.offer.company ? ` · ${a.offer.company}` : ""}
                  </span>
                  <span className="text-[11.5px] text-ink-3">
                    {COMP_LABEL[a.competitiveness]}
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => deleteMutation.mutate(a.id)}
                  className="shrink-0 text-[11.5px] font-medium text-ink-3 transition-colors hover:text-destructive"
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

interface AnalysisCardProps {
  analysis: OfferAnalysis;
}

function AnalysisCard({ analysis }: AnalysisCardProps): React.ReactElement {
  return (
    <div className="space-y-4 rounded-[12px] border border-green bg-paper p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span
          className={cn(
            "rounded-[6px] px-2.5 py-1 text-[12px] font-semibold",
            COMP_TONE[analysis.competitiveness],
          )}
        >
          {COMP_LABEL[analysis.competitiveness]}
        </span>
        <span className="text-[12px] text-ink-3">
          Confidence {Math.round(analysis.confidence * 100)}%
        </span>
      </div>

      <p className="text-[13.5px] leading-relaxed text-ink-2">{analysis.assessment}</p>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-[9px] bg-bg-2 px-4 py-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-3">
            Market range
          </p>
          <p className="mt-1 text-[15px] font-medium tabular-nums text-ink">
            {money(analysis.benchmarkLow, analysis.benchmarkCurrency)} –{" "}
            {money(analysis.benchmarkHigh, analysis.benchmarkCurrency)}
          </p>
        </div>
        <div className="rounded-[9px] bg-green-soft px-4 py-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-green-2">
            Suggested counter
          </p>
          <p className="mt-1 text-[15px] font-medium tabular-nums text-ink">
            {money(analysis.counterBase, analysis.benchmarkCurrency)}
          </p>
        </div>
      </div>

      {analysis.counterRationale && (
        <p className="text-[13px] leading-relaxed text-ink-2">
          <span className="font-medium text-ink">Why: </span>
          {analysis.counterRationale}
        </p>
      )}

      <CardList title="Talking points" items={analysis.talkingPoints} ordered />
      <CardList title="Risks" items={analysis.risks} />
      <CardList title="Assumptions" items={analysis.assumptions} muted />
    </div>
  );
}

interface CardListProps {
  title: string;
  items: string[];
  ordered?: boolean;
  muted?: boolean;
}

function CardList({ title, items, ordered, muted }: CardListProps): React.ReactElement | null {
  if (items.length === 0) return null;
  const ListTag = ordered ? "ol" : "ul";
  return (
    <div>
      <p className="text-[11.5px] font-semibold uppercase tracking-[0.06em] text-ink-3">
        {title}
      </p>
      <ListTag
        className={cn(
          "mt-1.5 space-y-1 pl-5 text-[13px]",
          ordered ? "list-decimal" : "list-disc",
          muted ? "text-ink-3" : "text-ink-2",
        )}
      >
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ListTag>
    </div>
  );
}
