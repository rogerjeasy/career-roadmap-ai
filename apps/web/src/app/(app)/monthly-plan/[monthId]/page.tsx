"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ROUTES } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";

interface WeekGoal {
  week: number;
  focus: string;
  goals: string[];
}

interface MonthDetail {
  id: string;
  month: string;
  theme: string;
  summary: string;
  weeks: WeekGoal[];
}

const DETAILS: Record<string, MonthDetail> = {
  "2026-06": {
    id: "2026-06",
    month: "June 2026",
    theme: "Evaluation & observability",
    summary:
      "Make your agentic project measurable. Add an evaluation harness, wire up tracing, and learn to read the signals that senior teams expect.",
    weeks: [
      { week: 1, focus: "Eval foundations", goals: ["Define 5 eval cases for your agent", "Add an offline eval script", "Read 2 papers on LLM evaluation"] },
      { week: 2, focus: "Observability", goals: ["Instrument traces with OpenTelemetry", "Add a metrics dashboard", "Close milestone M-07"] },
      { week: 3, focus: "Iterate on quality", goals: ["Run evals against 3 prompt variants", "Document findings", "Reach out to 2 ML engineers"] },
      { week: 4, focus: "Consolidate", goals: ["Write a project retro", "Publish a short write-up", "Plan July portfolio work"] },
    ],
  },
};

export default function MonthDetailPage() {
  const params = useParams<{ monthId: string }>();
  const detail =
    DETAILS[params.monthId] ?? {
      id: params.monthId,
      month: "This month",
      theme: "Planned focus",
      summary: "A detailed plan for this month will appear here once your roadmap generates monthly goals.",
      weeks: [],
    };

  return (
    <div className="mx-auto max-w-[820px] px-7 pb-24 pt-7">
      <Link
        href={ROUTES.monthlyPlan}
        className="mb-4 inline-flex items-center gap-1 text-[12.5px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
      >
        ← Monthly plan
      </Link>
      <PageHeader eyebrow={detail.theme} title={detail.month} description={detail.summary} />

      {detail.weeks.length === 0 ? (
        <p className="rounded-[10px] border border-dashed border-rule-strong bg-paper px-4 py-8 text-center text-[13px] text-ink-3">
          No weekly breakdown for this month yet.
        </p>
      ) : (
        <ol className="space-y-3">
          {detail.weeks.map((w) => (
            <li key={w.week} className="rounded-[12px] border border-rule bg-paper p-5">
              <div className="mb-2.5 flex items-center gap-2.5">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-green font-mono text-[12px] font-semibold text-white">
                  {w.week}
                </span>
                <p className="text-[14px] font-semibold text-ink">Week {w.week}</p>
                <span className="text-[12.5px] text-ink-3">· {w.focus}</span>
              </div>
              <ul className="space-y-1.5 pl-1">
                {w.goals.map((g, i) => (
                  <li key={i} className="flex gap-2 text-[13px] leading-snug text-ink-2">
                    <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-terra" aria-hidden="true" />
                    <span className="min-w-0">{g}</span>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
