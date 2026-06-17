"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { ROUTES, QUERY_KEYS } from "@/lib/constants";
import { progressApi } from "@/lib/api/progress";
import { PageHeader } from "@/components/shared/page-header";

interface SignalGuide {
  label: string;
  measures: string;
  improve: string;
  /** A real page the user can act on to move this signal. */
  link: { href: string; label: string };
}

// The canonical five signals (matches the dashboard card + agent-written snapshot).
const SIGNAL_GUIDE: SignalGuide[] = [
  {
    label: "Roadmap progress",
    measures:
      "How many milestones you've completed across your active roadmap, weighted toward your current phase.",
    improve: "Check off milestones as you finish them and keep your roadmap current.",
    link: { href: ROUTES.roadmap, label: "Open your roadmap →" },
  },
  {
    label: "Skill readiness",
    measures:
      "How much of your target-role skill set you've acquired versus what's still planned.",
    improve: "Build the skills your phases target, and list skills you already hold in your profile.",
    link: { href: ROUTES.skillGraph, label: "View your skill graph →" },
  },
  {
    label: "Portfolio strength",
    measures:
      "The depth of shipped, evidenced work — projects in your portfolio and items in your evidence vault.",
    improve: "Add projects and concrete evidence: metrics you moved, certifications, recommendations.",
    link: { href: ROUTES.portfolio, label: "Add to your portfolio →" },
  },
  {
    label: "Market alignment",
    measures:
      "How well your target role and skills track current market demand and compensation.",
    improve: "Prioritise fast-rising, in-demand skills — and revisit your target if the market shifts.",
    link: { href: ROUTES.market, label: "Check the market pulse →" },
  },
  {
    label: "Network activity",
    measures:
      "The momentum of your professional outreach — contacts, events, and conversations logged.",
    improve: "Log conversations, attend events, and keep outreach warm rather than cold.",
    link: { href: ROUTES.networking, label: "Open your network →" },
  },
];

const SCORE_BANDS = [
  { range: "75–100", label: "Strong", tone: "bg-green-soft text-green-2" },
  { range: "50–74", label: "On track", tone: "bg-bg-2 text-ink-2" },
  { range: "0–49", label: "Needs attention", tone: "bg-terra-soft text-terra-2" },
];

export default function HealthMethodologyPage() {
  // The user's live snapshot, so each explanation sits next to their real number.
  const { data: health } = useQuery({
    queryKey: QUERY_KEYS.health,
    queryFn: progressApi.getHealth,
    staleTime: 60 * 1000,
  });

  const scoreByLabel = new Map(
    (health?.signals ?? []).map((s) => [s.label.toLowerCase(), s.score]),
  );

  return (
    <div className="mx-auto max-w-[820px] px-7 pb-24 pt-7">
      <Link
        href={ROUTES.dashboard}
        className="mb-4 inline-flex items-center gap-1 text-[12.5px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
      >
        ← Back to dashboard
      </Link>

      <PageHeader
        eyebrow="Career Health"
        title="How your score works"
        description="One number, five honest signals. The score is transparent and built only from what you actually do — it can't be gamed by self-reporting."
      />

      {/* Overview */}
      <section className="mb-8 space-y-3 text-[14px] leading-relaxed text-ink-2">
        <p>
          Your <strong className="text-ink">Career Health</strong> is an overall
          score from <strong className="text-ink">0 to 100</strong>, made up of five
          component signals — each also scored 0–100. The arrow next to the score is
          the <strong className="text-ink">delta</strong>: how it has moved since the
          last update.
        </p>
        <p>
          The score recomputes as your real activity changes — completing milestones,
          logging deep-work hours, updating your CV, adding evidence, and reaching out
          to your network. Nothing here is self-rated; every signal is derived from
          data already in your account.
        </p>
      </section>

      {/* Score bands */}
      <section className="mb-9">
        <h2 className="mb-3 text-[12px] font-semibold uppercase tracking-[0.14em] text-ink-3">
          Reading the score
        </h2>
        <div className="grid gap-2.5 sm:grid-cols-3">
          {SCORE_BANDS.map((b) => (
            <div key={b.label} className="rounded-[10px] border border-rule bg-paper p-4">
              <span
                className={cn(
                  "inline-block rounded-[5px] px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.04em]",
                  b.tone,
                )}
              >
                {b.label}
              </span>
              <p className="mt-2 font-mono text-[15px] text-ink [font-variant-numeric:tabular-nums]">
                {b.range}
              </p>
            </div>
          ))}
        </div>
        <p className="mt-3 text-[13px] leading-relaxed text-ink-3">
          Any individual signal below <strong className="text-ink-2">50</strong> is
          flagged for attention (shown in terracotta on your dashboard) — a prompt to
          focus there next.
        </p>
      </section>

      {/* The five signals */}
      <section>
        <h2 className="mb-4 text-[12px] font-semibold uppercase tracking-[0.14em] text-ink-3">
          The five signals
        </h2>
        <div className="space-y-3">
          {SIGNAL_GUIDE.map((sig) => {
            const current = scoreByLabel.get(sig.label.toLowerCase());
            const hasScore = current !== undefined;
            const isWarn = hasScore && current < 50;
            return (
              <article
                key={sig.label}
                className="rounded-[12px] border border-rule bg-paper p-5"
              >
                <div className="mb-2 flex items-center justify-between gap-3">
                  <h3 className="font-serif text-[16px] font-medium tracking-[-0.01em] text-ink">
                    {sig.label}
                  </h3>
                  {hasScore && (
                    <span
                      className={cn(
                        "shrink-0 font-mono text-[13px] [font-variant-numeric:tabular-nums]",
                        isWarn ? "text-terra-2" : "text-green-2",
                      )}
                    >
                      {current}
                      <span className="text-ink-3">/100</span>
                    </span>
                  )}
                </div>

                {hasScore && (
                  <div className="mb-3 h-1 overflow-hidden rounded-sm bg-bg-2">
                    <div
                      className={cn(
                        "h-full w-[--score] rounded-sm",
                        isWarn ? "bg-terra" : "bg-green",
                      )}
                      style={{ "--score": `${current}%` } as React.CSSProperties}
                    />
                  </div>
                )}

                <p className="text-[13.5px] leading-relaxed text-ink-2">
                  <span className="font-medium text-ink">What it measures · </span>
                  {sig.measures}
                </p>
                <p className="mt-1.5 text-[13.5px] leading-relaxed text-ink-2">
                  <span className="font-medium text-ink">How to improve it · </span>
                  {sig.improve}
                </p>
                <Link
                  href={sig.link.href}
                  className="mt-3 inline-block text-[12.5px] font-medium text-terra transition-colors duration-150 hover:text-terra-2"
                >
                  {sig.link.label}
                </Link>
              </article>
            );
          })}
        </div>
      </section>
    </div>
  );
}
