"use client";

import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  interviewApi,
  type InterviewType,
  type TurnMessage,
} from "@/lib/api/interview";
import { QUERY_KEYS } from "@/lib/constants";
import { cn } from "@/lib/utils";

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

const TYPES: { value: InterviewType; label: string }[] = [
  { value: "mixed", label: "Mixed" },
  { value: "behavioral", label: "Behavioral" },
  { value: "technical", label: "Technical" },
  { value: "system_design", label: "System design" },
  { value: "role_specific", label: "Role-specific" },
];

interface Exchange {
  question: string;
  answer: string;
  feedback: string;
  score: number;
  strengths: string[];
  improvements: string[];
}

export interface MockInterviewProps {
  className?: string;
}

export function MockInterview(_props: MockInterviewProps): React.ReactElement {
  const queryClient = useQueryClient();
  const [started, setStarted] = useState(false);
  const [role, setRole] = useState("");
  const [company, setCompany] = useState("");
  const [interviewType, setInterviewType] = useState<InterviewType>("mixed");
  const [currentQuestion, setCurrentQuestion] = useState("Tell me about yourself and why this role.");
  const [answer, setAnswer] = useState("");
  const [exchanges, setExchanges] = useState<Exchange[]>([]);

  const history = (): TurnMessage[] =>
    exchanges.flatMap<TurnMessage>((x) => [
      { role: "interviewer", content: x.question },
      { role: "candidate", content: x.answer },
    ]);

  const turnMutation = useMutation({
    mutationFn: (a: string) =>
      interviewApi.turn({
        role: role.trim(),
        company: company.trim(),
        interviewType,
        currentQuestion,
        history: history(),
        answer: a,
      }),
    onSuccess: (reply, a) => {
      setExchanges((prev) => [
        ...prev,
        {
          question: currentQuestion,
          answer: a,
          feedback: reply.feedback,
          score: reply.score,
          strengths: reply.strengths,
          improvements: reply.improvements,
        },
      ]);
      setCurrentQuestion(reply.nextQuestion || "Thanks — that's all for now.");
      setAnswer("");
    },
    onError: () => toast.error("The interviewer didn't respond. Try again."),
  });

  const saveMutation = useMutation({
    mutationFn: () => {
      const avg =
        exchanges.length > 0
          ? Math.round(exchanges.reduce((s, x) => s + x.score, 0) / exchanges.length)
          : 0;
      return interviewApi.saveSession({
        role: role.trim(),
        company: company.trim(),
        interviewType,
        overallScore: avg,
        transcript: history(),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.interviewSessions });
      toast.success("Practice saved");
    },
    onError: () => toast.error("Couldn't save this practice."),
  });

  if (!started) {
    return (
      <form
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          if (!role.trim()) return;
          setStarted(true);
        }}
        className="space-y-3 rounded-[12px] border border-rule bg-paper p-5"
      >
        <p className="text-[13px] leading-relaxed text-ink-2">
          Set the role, then answer each question. The AI interviewer scores your
          answer and asks a follow-up.
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <input value={role} onChange={(e) => setRole(e.target.value)} placeholder="Role" className={FIELD_CLASS} />
          <input value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Company (optional)" className={FIELD_CLASS} />
        </div>
        <select value={interviewType} onChange={(e) => setInterviewType(e.target.value as InterviewType)} className={FIELD_CLASS}>
          {TYPES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={!role.trim()}
            className="rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors hover:bg-green-2 disabled:opacity-50"
          >
            Start interview
          </button>
        </div>
      </form>
    );
  }

  return (
    <div className="space-y-4">
      {exchanges.map((x, i) => (
        <div key={i} className="space-y-2">
          <div className="rounded-[12px] border border-rule bg-paper px-4 py-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-3">
              Interviewer
            </p>
            <p className="mt-1 text-[13.5px] leading-relaxed text-ink">{x.question}</p>
          </div>
          <div className="ml-auto max-w-[88%] rounded-[12px] bg-ink px-4 py-2.5 text-[13.5px] leading-relaxed text-bg">
            {x.answer}
          </div>
          <div className="rounded-[12px] border border-green/40 bg-green-soft px-4 py-3">
            <div className="flex items-center justify-between">
              <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-green-2">
                Feedback
              </p>
              <span className="rounded-[5px] bg-paper px-2 py-0.5 text-[12px] font-semibold tabular-nums text-ink">
                {x.score}/100
              </span>
            </div>
            <p className="mt-1.5 text-[12.5px] leading-relaxed text-ink-2">{x.feedback}</p>
            {x.improvements.length > 0 && (
              <ul className="mt-1.5 list-disc space-y-0.5 pl-5 text-[12px] text-ink-2">
                {x.improvements.map((imp, j) => (
                  <li key={j}>{imp}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ))}

      <div className="rounded-[12px] border border-rule bg-paper px-4 py-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-3">
          Question {exchanges.length + 1}
        </p>
        <p className="mt-1 text-[14px] font-medium leading-snug text-ink">{currentQuestion}</p>
      </div>

      <form
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          if (!answer.trim() || turnMutation.isPending) return;
          turnMutation.mutate(answer.trim());
        }}
        className="space-y-2"
      >
        <textarea
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          placeholder="Your answer…"
          rows={4}
          className={cn(FIELD_CLASS, "resize-y")}
        />
        <div className="flex flex-wrap items-center justify-between gap-2">
          <button
            type="button"
            onClick={() => saveMutation.mutate()}
            disabled={exchanges.length === 0 || saveMutation.isPending}
            className="rounded-[7px] border border-rule px-3.5 py-2 text-[12.5px] font-medium text-ink-2 transition-colors hover:border-rule-strong disabled:opacity-50"
          >
            Save practice
          </button>
          <button
            type="submit"
            disabled={!answer.trim() || turnMutation.isPending}
            className="rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors hover:bg-green-2 disabled:opacity-50"
          >
            {turnMutation.isPending ? "Scoring…" : "Submit answer"}
          </button>
        </div>
      </form>
    </div>
  );
}
