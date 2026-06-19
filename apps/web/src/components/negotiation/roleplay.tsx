"use client";

import { useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  negotiationApi,
  type OfferInput,
  type RoleplayMessage,
} from "@/lib/api/negotiation";
import { cn } from "@/lib/utils";

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

interface Turn {
  role: "user" | "recruiter";
  content: string;
  coaching?: string;
  tip?: string;
}

export interface NegotiationRoleplayProps {
  className?: string;
}

export function NegotiationRoleplay(_props: NegotiationRoleplayProps): React.ReactElement {
  const [started, setStarted] = useState(false);
  const [role, setRole] = useState("");
  const [baseSalary, setBaseSalary] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");

  const offer = (): OfferInput => ({
    role: role.trim(),
    baseSalary: baseSalary ? Number(baseSalary) : 0,
    currency: currency.trim() || "USD",
  });

  const sendMutation = useMutation({
    mutationFn: (message: string) =>
      negotiationApi.roleplay({
        offer: offer(),
        history: turns.map<RoleplayMessage>((t) => ({ role: t.role, content: t.content })),
        message,
      }),
    onSuccess: (reply, message) => {
      setTurns((prev) => [
        ...prev,
        { role: "user", content: message },
        { role: "recruiter", content: reply.reply, coaching: reply.coaching, tip: reply.tip },
      ]);
      setInput("");
    },
    onError: () => toast.error("The recruiter didn't respond. Try again."),
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
          Set the scene, then negotiate. After each of your messages the AI
          recruiter replies in character and you get private coaching.
        </p>
        <input value={role} onChange={(e) => setRole(e.target.value)} placeholder="Role you're negotiating" className={FIELD_CLASS} />
        <div className="grid gap-3 sm:grid-cols-2">
          <input value={baseSalary} onChange={(e) => setBaseSalary(e.target.value)} type="number" min="0" placeholder="Their offered base" className={FIELD_CLASS} />
          <input value={currency} onChange={(e) => setCurrency(e.target.value)} placeholder="Currency" className={FIELD_CLASS} />
        </div>
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={!role.trim()}
            className="rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors hover:bg-green-2 disabled:opacity-50"
          >
            Start roleplay
          </button>
        </div>
      </form>
    );
  }

  return (
    <div className="space-y-4">
      <div className="space-y-4">
        {turns.length === 0 && (
          <p className="rounded-[10px] border border-dashed border-rule-strong bg-paper px-4 py-6 text-center text-[13px] text-ink-3">
            Open with your first move — e.g. express enthusiasm, then raise the base.
          </p>
        )}
        {turns.map((t, i) => (
          <div key={i} className={cn("flex", t.role === "user" ? "justify-end" : "justify-start")}>
            <div className="max-w-[85%] space-y-2">
              <div
                className={cn(
                  "rounded-[12px] px-4 py-2.5 text-[13.5px] leading-relaxed",
                  t.role === "user"
                    ? "bg-ink text-bg"
                    : "border border-rule bg-paper text-ink-2",
                )}
              >
                {t.content}
              </div>
              {t.coaching && (
                <div className="rounded-[10px] border border-green/40 bg-green-soft px-3.5 py-2.5">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-green-2">
                    Coaching
                  </p>
                  <p className="mt-1 text-[12.5px] leading-relaxed text-ink-2">{t.coaching}</p>
                  {t.tip && (
                    <p className="mt-1.5 text-[12.5px] leading-relaxed text-ink-2">
                      <span className="font-medium">Try next: </span>
                      {t.tip}
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      <form
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          if (!input.trim() || sendMutation.isPending) return;
          sendMutation.mutate(input.trim());
        }}
        className="flex items-end gap-2"
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Your message to the recruiter…"
          rows={2}
          className={`${FIELD_CLASS} resize-y`}
        />
        <button
          type="submit"
          disabled={!input.trim() || sendMutation.isPending}
          className="shrink-0 rounded-[7px] bg-ink px-4 py-2.5 text-[13px] font-medium text-bg transition-colors hover:bg-green-2 disabled:opacity-50"
        >
          {sendMutation.isPending ? "…" : "Send"}
        </button>
      </form>
    </div>
  );
}
