"use client";

import { useEffect, useRef, useState } from "react";
import type {
  CvAnalysisResult,
  OnboardingDirection,
  OnboardingConstraints,
} from "@/types/onboarding.types";
import type { ClarificationQuestion } from "@/types/agent.types";
import { useAgentStream } from "@/hooks/use-agent-stream";
import { useAgentStore, type AgentStatus, type AgentEvent } from "@/store/agent.store";
import { useClarification } from "@/hooks/use-clarification";

// ── Pipeline metadata ────────────────────────────────────────────────────────

const PIPELINE_STEPS = [
  {
    key: "parse_intent",
    label: "Understanding your goal",
    detail: "Extracting intent and target role from your message",
  },
  {
    key: "score_completeness",
    label: "Checking profile completeness",
    detail: "Scoring how much context is available for your roadmap",
  },
  {
    key: "build_dag",
    label: "Planning the analysis",
    detail: "Constructing the specialist-agent execution plan",
  },
  {
    key: "initialize_roadmap",
    label: "Initialising your roadmap",
    detail: "Creating your roadmap workspace",
  },
  {
    key: "assemble_rag_context",
    label: "Gathering career intelligence",
    detail: "Retrieving relevant knowledge, examples, and market data",
  },
  {
    key: "dispatch_and_collect",
    label: "Running specialist agents",
    detail: "Parallel analysis across CV, market, opportunities, and more",
  },
  {
    key: "synthesize",
    label: "Synthesising your roadmap",
    detail: "Merging all agent outputs into a cohesive week-by-week plan",
  },
  {
    key: "validate",
    label: "Quality checking",
    detail: "Realism · grounding · confidence scoring",
  },
] as const;

const AGENT_LABELS: Record<string, string> = {
  intake: "Profile intake",
  cv_analysis: "CV analysis",
  gap_analysis: "Gap analysis",
  market_intelligence: "Market intelligence",
  roadmap_generation: "Roadmap generation",
  validator: "Output validation",
  learning_resources: "Learning resources",
  networking: "Networking strategy",
  opportunity: "Opportunity matching",
  progress: "Progress planning",
  coach: "Career coaching",
};

const EVENT_LABELS: Record<string, string> = {
  orchestration_started: "Started",
  step_progress: "Step",
  agent_started: "↳ Starting",
  agent_completed: "✓ Done",
  agent_failed: "✗ Failed",
  orchestration_completed: "✓ Complete",
  orchestration_failed: "✗ Failed",
  clarification_required: "? Clarification",
};

const EVENT_COLORS: Record<string, string> = {
  agent_completed: "text-green",
  orchestration_completed: "text-green",
  agent_failed: "text-red-400",
  orchestration_failed: "text-red-400",
  clarification_required: "text-gold",
};

// ── Types ────────────────────────────────────────────────────────────────────

type StepStatus = "todo" | "doing" | "done";

export interface GenerateProgressProps {
  cvResult: CvAnalysisResult | null;
  direction: OnboardingDirection;
  constraints: OnboardingConstraints;
  sessionId: string | null;
  onComplete?: () => void;
  onRetry?: () => void;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtElapsed(ms: number): string {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  return m > 0 ? `${m}m ${s % 60}s` : `${s}s`;
}

function fmtMs(ms: number): string {
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

function eventDetail(evt: AgentEvent): string {
  const p = evt.payload;
  switch (evt.event_type) {
    case "agent_started":
      return AGENT_LABELS[p.agent as string] ?? (p.agent as string) ?? "";
    case "agent_completed":
    case "agent_failed": {
      const name = AGENT_LABELS[p.agent as string] ?? (p.agent as string) ?? "";
      const dur = p.duration_ms ? ` · ${fmtMs(p.duration_ms as number)}` : "";
      return name + dur;
    }
    case "step_progress": {
      // Orchestrator-level: {step_name, step_index, total_steps, pct}
      if (typeof p.step_name === "string") {
        const label = PIPELINE_STEPS.find((s) => s.key === p.step_name)?.label ?? (p.step_name as string);
        return `${label} · ${p.pct as number}%`;
      }
      // Agent-level: {agent, step, description} — show agent name + internal step
      if (typeof p.step === "string") {
        const agentLabel = AGENT_LABELS[p.agent as string] ?? (p.agent as string) ?? "";
        return agentLabel ? `${agentLabel}: ${p.step as string}` : (p.step as string);
      }
      return "";
    }
    case "orchestration_started":
      return "Pipeline initialised";
    default:
      return "";
  }
}

// ── Main component ────────────────────────────────────────────────────────────

export function GenerateProgress({
  direction,
  sessionId,
  onComplete,
  onRetry,
}: GenerateProgressProps) {
  const status = useAgentStore((s) => s.status);
  const currentPct = useAgentStore((s) => s.currentPct);
  const stepIndex = useAgentStore((s) => s.currentStepIndex);
  const stepName = useAgentStore((s) => s.currentStepName);
  const agents = useAgentStore((s) => s.agents);
  const error = useAgentStore((s) => s.error);
  const eventLog = useAgentStore((s) => s.eventLog);

  const { clarification, isClarifying, isSubmitting, submitError, submitAnswers } =
    useClarification();

  useAgentStream(sessionId);

  // ── Elapsed timer ──────────────────────────────────────────────────────────
  const [elapsed, setElapsed] = useState(0);
  const startedAtRef = useRef<number | null>(null);

  useEffect(() => {
    if (status !== "connecting" && status !== "generating") return;
    if (startedAtRef.current === null) startedAtRef.current = Date.now();
    const id = window.setInterval(() => {
      setElapsed(Date.now() - startedAtRef.current!);
    }, 1000);
    return () => window.clearInterval(id);
  }, [status]);

  // ── Auto-navigate on completion ────────────────────────────────────────────
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  useEffect(() => {
    if (status !== "completed") return;
    const t = window.setTimeout(() => onCompleteRef.current?.(), 2500);
    return () => window.clearTimeout(t);
  }, [status]);

  // ── Clarification ──────────────────────────────────────────────────────────
  if (isClarifying && clarification) {
    return (
      <ClarificationForm
        questions={clarification.questions}
        round={clarification.round}
        isSubmitting={isSubmitting}
        submitError={submitError}
        onSubmit={submitAnswers}
      />
    );
  }

  // ── Error ──────────────────────────────────────────────────────────────────
  if (status === "failed") {
    return (
      <div className="mx-auto max-w-[620px] py-10 text-center">
        <div className="mb-6 flex justify-center">
          <span className="flex h-[60px] w-[60px] items-center justify-center rounded-full bg-red-50">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              className="h-8 w-8 text-red-500"
              aria-hidden="true"
            >
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" />
              <path
                d="M12 8v4m0 4h.01"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          </span>
        </div>
        <h2 className="mb-2 font-serif text-2xl font-[350] text-ink">Generation failed</h2>
        <p className="mx-auto mb-6 max-w-[420px] text-[14px] text-ink-2">
          {error ?? "Something went wrong. Please try again."}
        </p>
        <div className="flex justify-center gap-3">
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="rounded-lg bg-green px-6 py-2.5 text-[14px] font-medium text-white transition-opacity hover:opacity-90"
            >
              Try again
            </button>
          )}
          <button
            type="button"
            onClick={() => onComplete?.()}
            className="rounded-lg border border-rule px-6 py-2.5 text-[14px] font-medium text-ink transition-colors hover:bg-bg-2"
          >
            Back to dashboard
          </button>
        </div>
      </div>
    );
  }

  // ── Completed ──────────────────────────────────────────────────────────────
  if (status === "completed") {
    return (
      <div className="mx-auto max-w-[620px] py-10 text-center">
        <div className="mx-auto mb-9 flex h-[80px] w-[80px] items-center justify-center rounded-full bg-green shadow-[0_16px_32px_-8px_rgba(19,78,58,0.5)]">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            className="h-10 w-10 text-white"
            aria-hidden="true"
          >
            <path
              d="M5 13l4 4L19 7"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
        <p className="mb-3 font-mono text-[11px] uppercase tracking-[0.14em] text-green">
          Step five of five &middot; Complete
        </p>
        <h2 className="mb-3 font-serif text-[40px] font-[350] leading-[1.05] tracking-[-0.025em] text-ink sm:text-[48px]">
          Your roadmap is <em className="italic text-green">ready.</em>
        </h2>
        <p className="mx-auto mb-8 max-w-[460px] text-[14px] leading-relaxed text-ink-2">
          Taking you to your personalised career roadmap&hellip;
        </p>
        {Object.keys(agents).length > 0 && (
          <div className="mx-auto max-w-[500px] rounded-xl border border-rule bg-paper px-5 py-4 text-left">
            <p className="mb-3 font-mono text-[10px] uppercase tracking-[0.12em] text-ink-3">
              Completed agents
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              {Object.entries(agents).map(([key, agent]) => (
                <div key={key} className="flex items-center gap-2.5 text-[12.5px]">
                  <span className="h-[6px] w-[6px] shrink-0 rounded-full bg-green" />
                  <span className="min-w-0 flex-1 truncate text-ink">
                    {AGENT_LABELS[key] ?? key}
                  </span>
                  {agent.duration_ms !== undefined && agent.duration_ms > 0 && (
                    <span className="shrink-0 font-mono text-[10px] text-ink-3">
                      {fmtMs(agent.duration_ms)}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  // ── Active: connecting / generating ───────────────────────────────────────

  const pct = status === "connecting" ? 0 : currentPct;
  const activeStep = PIPELINE_STEPS[stepIndex] ?? null;
  const hasAgents = Object.keys(agents).length > 0;
  const targetGoal = direction.goal ?? null;

  return (
    <div className="mx-auto max-w-[700px] py-8">

      {/* ── Status bar ────────────────────────────────────────────────────── */}
      <div className="mb-5 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span
            className="h-2 w-2 shrink-0 rounded-full bg-terra"
            style={{ animation: "pulse-dot 1.4s ease-in-out infinite" }}
          />
          <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-terra">
            Step five of five &middot;{" "}
            {status === "connecting" ? "Connecting" : "Generating"}
          </span>
        </div>
        {elapsed > 0 && (
          <span className="font-mono text-[11px] tabular-nums text-ink-3">
            {fmtElapsed(elapsed)} elapsed
          </span>
        )}
      </div>

      {/* ── Headline + percentage ─────────────────────────────────────────── */}
      <div className="mb-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 className="font-serif text-[28px] font-[350] leading-tight tracking-[-0.02em] text-ink sm:text-[36px]">
              {status === "connecting" ? (
                "Connecting to the pipeline…"
              ) : (
                <>
                  Designing your{" "}
                  <em className="italic text-green">career roadmap.</em>
                </>
              )}
            </h2>
            {activeStep && (
              <p className="mt-2 text-[13.5px] leading-snug text-ink-2">
                <span className="font-medium">{activeStep.label}</span>
                {" — "}
                <span className="text-ink-3">{activeStep.detail}</span>
              </p>
            )}
            {targetGoal && status !== "connecting" && (
              <p className="mt-1 truncate text-[12px] text-ink-3">
                Goal:{" "}
                <span className="text-ink-2">
                  {targetGoal.length > 60 ? targetGoal.slice(0, 60) + "…" : targetGoal}
                </span>
              </p>
            )}
          </div>
          <span className="shrink-0 font-mono text-[28px] font-semibold tabular-nums text-green sm:text-[36px]">
            {pct}%
          </span>
        </div>
      </div>

      {/* ── Progress bar ─────────────────────────────────────────────────── */}
      <div className="mb-8 h-[3px] w-full overflow-hidden rounded-full bg-rule">
        <div
          className="h-full rounded-full bg-green transition-all duration-700 ease-out [width:var(--progress-pct)]"
          style={{ "--progress-pct": `${pct}%` } as React.CSSProperties}
        />
      </div>

      {/* ── Pipeline tracker ─────────────────────────────────────────────── */}
      <div className="mb-5 overflow-hidden rounded-xl border border-rule bg-paper">
        <div className="flex items-center justify-between border-b border-rule px-4 py-2.5">
          <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-3">
            Pipeline
          </span>
          <span className="font-mono text-[10px] tabular-nums text-ink-3">
            {stepIndex >= 0 ? `${Math.min(stepIndex + 1, PIPELINE_STEPS.length)} / ${PIPELINE_STEPS.length}` : "—"}
          </span>
        </div>

        <div className="divide-y divide-rule">
          {PIPELINE_STEPS.map((step, idx) => {
            const ss: StepStatus =
              idx < stepIndex ? "done" : idx === stepIndex ? "doing" : "todo";

            return (
              <div key={step.key}>
                <div
                  className={`flex items-center gap-3 px-4 py-3 ${
                    ss === "doing" ? "bg-green-faint" : ""
                  }`}
                >
                  <StepDot status={ss} index={idx} />
                  <div className="min-w-0 flex-1">
                    <p
                      className={`text-[13.5px] leading-snug ${
                        ss === "todo"
                          ? "text-ink-3"
                          : ss === "doing"
                          ? "font-medium text-ink"
                          : "text-ink"
                      }`}
                    >
                      {step.label}
                    </p>
                    {ss === "doing" && (
                      <p className="mt-0.5 text-[11.5px] text-ink-3">{step.detail}</p>
                    )}
                  </div>
                  {ss === "done" && (
                    <span className="shrink-0 font-mono text-[10.5px] font-semibold text-green">
                      ✓
                    </span>
                  )}
                  {ss === "doing" && (
                    <span
                      className="h-[14px] w-[14px] shrink-0 rounded-full border-2 border-terra border-t-transparent"
                      style={{ animation: "spin 0.75s linear infinite" }}
                    />
                  )}
                </div>

                {/* Specialist agents — visible during dispatch_and_collect */}
                {step.key === "dispatch_and_collect" && hasAgents && (
                  <div className="border-t border-rule/50 bg-bg px-4 pb-4 pt-3">
                    <p className="mb-2.5 font-mono text-[9.5px] uppercase tracking-[0.1em] text-ink-3">
                      Specialist agents
                    </p>
                    <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                      {Object.entries(agents).map(([key, agent]) => (
                        <AgentCard key={key} agentKey={key} agent={agent} />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Live event log ────────────────────────────────────────────────── */}
      {eventLog.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-rule bg-paper">
          <div className="flex items-center gap-2 border-b border-rule px-4 py-2.5">
            <span
              className="h-1.5 w-1.5 rounded-full bg-terra"
              style={{ animation: "pulse-dot 1.2s ease-in-out infinite" }}
            />
            <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-3">
              Live events
            </span>
          </div>
          <div className="divide-y divide-rule/50">
            {eventLog.slice(0, 8).map((evt) => {
              const label = EVENT_LABELS[evt.event_type] ?? evt.event_type;
              const color = EVENT_COLORS[evt.event_type] ?? "text-ink-3";
              const detail = eventDetail(evt);
              const time = new Date(evt.timestamp).toLocaleTimeString([], {
                hour12: false,
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
              });
              return (
                <div
                  key={evt.event_id}
                  className="flex items-center gap-3 px-4 py-[9px]"
                >
                  <span
                    className={`w-[80px] shrink-0 font-mono text-[10.5px] ${color}`}
                  >
                    {label}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-[11.5px] text-ink-2">
                    {detail}
                  </span>
                  <span className="shrink-0 font-mono text-[9.5px] text-ink-3">
                    {time}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
        @keyframes pulse-dot {
          0%, 100% { opacity: 1;    transform: scale(1); }
          50%       { opacity: 0.3; transform: scale(0.65); }
        }
      `}</style>
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StepDot({ status, index }: { status: StepStatus; index: number }) {
  if (status === "done") {
    return (
      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-green">
        <svg viewBox="0 0 10 10" fill="none" className="h-[8px] w-[8px]" aria-hidden="true">
          <path
            d="M1.5 5.5l2.5 2.5 4.5-6"
            stroke="#fff"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
    );
  }
  if (status === "doing") {
    return (
      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 border-terra">
        <span className="h-[7px] w-[7px] rounded-full bg-terra" />
      </span>
    );
  }
  return (
    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-rule bg-bg-2">
      <span className="font-mono text-[9px] text-ink-3">{index + 1}</span>
    </span>
  );
}

function AgentCard({ agentKey, agent }: { agentKey: string; agent: AgentStatus }) {
  const label = AGENT_LABELS[agentKey] ?? agentKey;
  return (
    <div className="flex items-center gap-2.5 rounded-lg border border-rule bg-paper px-3 py-2">
      {agent.status === "running" ? (
        <span
          className="h-2.5 w-2.5 shrink-0 rounded-full border-[1.5px] border-terra border-t-transparent"
          style={{ animation: "spin 0.7s linear infinite" }}
        />
      ) : agent.status === "completed" ? (
        <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-green" />
      ) : (
        <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-red-400" />
      )}
      <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink">{label}</span>
      {agent.status !== "running" && agent.duration_ms !== undefined && agent.duration_ms > 0 ? (
        <span className="shrink-0 font-mono text-[10px] text-ink-3">
          {fmtMs(agent.duration_ms)}
        </span>
      ) : agent.status === "running" ? (
        <span className="shrink-0 font-mono text-[10px] text-ink-3">…</span>
      ) : null}
    </div>
  );
}

// ── ClarificationForm ────────────────────────────────────────────────────────

interface ClarificationFormProps {
  questions: ClarificationQuestion[];
  round: number;
  isSubmitting: boolean;
  submitError: string | null;
  onSubmit: (answers: Record<string, string>) => void;
}

function ClarificationForm({
  questions,
  round,
  isSubmitting,
  submitError,
  onSubmit,
}: ClarificationFormProps) {
  const [answers, setAnswers] = useState<Record<string, string>>({});

  const setAnswer = (key: string, value: string) =>
    setAnswers((prev) => ({ ...prev, [key]: value }));

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(answers);
  };

  const hasAnswers = Object.values(answers).some(Boolean);

  return (
    <div className="mx-auto max-w-[620px] py-10">
      <p className="mb-3 text-center font-mono text-[11px] uppercase tracking-[0.14em] text-terra">
        Clarification &middot; Round {round}
      </p>
      <h2 className="mb-2 text-center font-serif text-[34px] font-[350] leading-[1.1] tracking-[-0.02em] text-ink">
        A few more details
      </h2>
      <p className="mx-auto mb-8 max-w-[440px] text-center text-[14px] leading-relaxed text-ink-2">
        To build the most accurate roadmap, please answer these quick questions.
      </p>

      <form onSubmit={handleSubmit} className="space-y-5">
        {questions.map((q, i) => {
          const key = q.id ?? String(i);
          return (
            <div key={key} className="rounded-xl border border-rule bg-paper p-5">
              <p className="mb-3 text-[14px] font-medium text-ink">{q.question}</p>

              {q.type === "choice" && q.options ? (
                <div className="flex flex-wrap gap-2">
                  {q.options.map((opt) => (
                    <button
                      key={opt}
                      type="button"
                      onClick={() => setAnswer(key, opt)}
                      className={`rounded-full border px-4 py-1.5 text-[13px] transition-colors ${
                        answers[key] === opt
                          ? "border-green bg-green text-white"
                          : "border-rule text-ink-2 hover:border-green hover:text-ink"
                      }`}
                    >
                      {opt}
                    </button>
                  ))}
                </div>
              ) : (
                <textarea
                  className="w-full resize-none rounded-lg border border-rule bg-bg px-3 py-2 text-[14px] text-ink placeholder:text-ink-3 focus:border-green focus:outline-none"
                  rows={3}
                  placeholder="Your answer…"
                  value={answers[key] ?? ""}
                  onChange={(e) => setAnswer(key, e.target.value)}
                />
              )}
            </div>
          );
        })}

        {submitError && (
          <p className="text-center text-[13px] text-red-500">{submitError}</p>
        )}

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={isSubmitting || !hasAnswers}
            className="rounded-lg bg-green px-6 py-2.5 text-[14px] font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            {isSubmitting ? "Submitting…" : "Continue"}
          </button>
        </div>
      </form>
    </div>
  );
}
