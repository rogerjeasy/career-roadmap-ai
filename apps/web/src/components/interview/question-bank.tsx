"use client";

import { useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  interviewApi,
  type InterviewQuestion,
  type InterviewType,
} from "@/lib/api/interview";
import { LoadingSpinner } from "@/components/shared/loading-spinner";

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

const TYPES: { value: InterviewType; label: string }[] = [
  { value: "mixed", label: "Mixed" },
  { value: "behavioral", label: "Behavioral" },
  { value: "technical", label: "Technical" },
  { value: "system_design", label: "System design" },
  { value: "role_specific", label: "Role-specific" },
];

export interface QuestionBankProps {
  className?: string;
}

export function QuestionBank(_props: QuestionBankProps): React.ReactElement {
  const [role, setRole] = useState("");
  const [company, setCompany] = useState("");
  const [interviewType, setInterviewType] = useState<InterviewType>("mixed");
  const [questions, setQuestions] = useState<InterviewQuestion[] | null>(null);

  const mutation = useMutation({
    mutationFn: interviewApi.generateQuestions,
    onSuccess: (data) => {
      setQuestions(data.questions);
      toast.success(`${data.questions.length} questions ready`);
    },
    onError: () => toast.error("Couldn't generate questions. Add a role and try again."),
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!role.trim()) return;
    mutation.mutate({ role: role.trim(), company: company.trim(), interviewType, count: 6 });
  };

  return (
    <div className="space-y-5">
      <form onSubmit={onSubmit} className="space-y-3 rounded-[12px] border border-rule bg-paper p-5">
        <div className="grid gap-3 sm:grid-cols-2">
          <input value={role} onChange={(e) => setRole(e.target.value)} placeholder="Role (e.g. Senior PM)" className={FIELD_CLASS} />
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
            disabled={!role.trim() || mutation.isPending}
            className="rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors hover:bg-green-2 disabled:opacity-50"
          >
            {mutation.isPending ? "Generating…" : "Generate questions"}
          </button>
        </div>
      </form>

      {mutation.isPending && <LoadingSpinner label="Preparing your question bank…" />}

      {questions && questions.length > 0 && (
        <div className="space-y-3">
          {questions.map((q, i) => (
            <article key={i} className="rounded-[12px] border border-rule bg-paper p-5">
              <div className="flex items-start gap-3">
                <span className="mt-0.5 shrink-0 font-serif text-[15px] font-medium text-ink-3">
                  Q{i + 1}
                </span>
                <div className="min-w-0">
                  <p className="text-[14px] font-medium leading-snug text-ink">{q.question}</p>
                  {q.category && (
                    <p className="mt-1 text-[11.5px] uppercase tracking-[0.04em] text-ink-3">
                      {q.category.replace("_", " ")}
                      {q.assesses ? ` · ${q.assesses}` : ""}
                    </p>
                  )}
                  {q.answerTips.length > 0 && (
                    <ul className="mt-2 list-disc space-y-1 pl-5 text-[12.5px] text-ink-2">
                      {q.answerTips.map((tip, j) => (
                        <li key={j}>{tip}</li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
