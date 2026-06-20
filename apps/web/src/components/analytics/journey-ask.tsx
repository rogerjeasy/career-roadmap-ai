"use client";

import { useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { journeyApi, type AskMessage } from "@/lib/api/journey";

const SUGGESTED = [
  "How is my job search going?",
  "What should I focus on this week?",
  "Where am I losing momentum?",
];

interface Turn {
  question: string;
  answer: string;
  sources: string[];
  suggestions: string[];
}

export interface JourneyAskProps {
  className?: string;
}

export function JourneyAsk(_props: JourneyAskProps): React.ReactElement {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);

  const askMutation = useMutation({
    mutationFn: (q: string) => {
      const history: AskMessage[] = turns.flatMap<AskMessage>((t) => [
        { role: "user", content: t.question },
        { role: "assistant", content: t.answer },
      ]);
      return journeyApi.ask(q, history);
    },
    onSuccess: (reply, q) => {
      setTurns((prev) => [
        ...prev,
        { question: q, answer: reply.answer, sources: reply.sources, suggestions: reply.suggestions },
      ]);
      setQuestion("");
    },
    onError: () => toast.error("Couldn't answer that. Please try again."),
  });

  const ask = (q: string) => {
    if (!q.trim() || askMutation.isPending) return;
    askMutation.mutate(q.trim());
  };

  return (
    <section className="mb-8 rounded-[12px] border border-rule bg-paper p-5">
      <h2 className="font-serif text-[16px] font-medium tracking-[-0.01em] text-ink">
        Ask about your journey
      </h2>
      <p className="text-[12.5px] text-ink-3">
        Grounded answers from your own data — applications, learning, evidence, and more.
      </p>

      {turns.length === 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {SUGGESTED.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => ask(s)}
              className="rounded-[7px] border border-rule bg-bg px-3 py-1.5 text-[12px] font-medium text-ink-2 transition-colors hover:border-rule-strong"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {turns.length > 0 && (
        <div className="mt-4 space-y-4">
          {turns.map((t, i) => (
            <div key={i}>
              <p className="text-[13px] font-medium text-ink">{t.question}</p>
              <p className="mt-1.5 text-[13px] leading-relaxed text-ink-2">{t.answer}</p>
              {t.sources.length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {t.sources.map((s) => (
                    <span
                      key={s}
                      className="rounded-[4px] bg-bg-2 px-1.5 py-0.5 text-[10.5px] font-medium text-ink-3"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              )}
              {t.suggestions.length > 0 && (
                <ul className="mt-1.5 list-disc space-y-0.5 pl-5 text-[12.5px] text-ink-2">
                  {t.suggestions.map((sg, j) => (
                    <li key={j}>{sg}</li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}

      <form
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          ask(question);
        }}
        className="mt-4 flex items-center gap-2"
      >
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask anything about your progress…"
          className="w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none"
        />
        <button
          type="submit"
          disabled={!question.trim() || askMutation.isPending}
          className="shrink-0 rounded-[7px] bg-ink px-4 py-2.5 text-[13px] font-medium text-bg transition-colors hover:bg-green-2 disabled:opacity-50"
        >
          {askMutation.isPending ? "…" : "Ask"}
        </button>
      </form>
    </section>
  );
}
