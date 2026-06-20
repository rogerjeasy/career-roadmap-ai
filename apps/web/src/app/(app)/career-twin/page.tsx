"use client";

import { useState, type FormEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  careerTwinApi,
  type DailyCheckin,
  type TwinPersona,
  type TwinVoice,
} from "@/lib/api/career-twin";
import { QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { formatDate } from "@/lib/date";
import { cn } from "@/lib/utils";

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

const VOICES: TwinVoice[] = ["supportive", "direct", "playful", "stoic", "analytical"];

export default function CareerTwinPage() {
  const queryClient = useQueryClient();
  const [showPersona, setShowPersona] = useState(false);
  const [name, setName] = useState("");
  const [voice, setVoice] = useState<TwinVoice>("supportive");
  const [focus, setFocus] = useState("");
  const [hydratedFrom, setHydratedFrom] = useState<TwinPersona | null>(null);
  const [reply, setReply] = useState("");
  const [mood, setMood] = useState<number | undefined>();

  const { data: persona } = useQuery({
    queryKey: QUERY_KEYS.twinPersona,
    queryFn: careerTwinApi.getPersona,
    staleTime: 60 * 1000,
  });

  // Hydrate the persona form once it loads (render-phase pattern, no effect).
  if (persona && persona !== hydratedFrom) {
    setHydratedFrom(persona);
    setName(persona.name);
    setVoice(persona.voice);
    setFocus(persona.focus);
  }

  const { data: today, isLoading: todayLoading } = useQuery({
    queryKey: QUERY_KEYS.twinToday,
    queryFn: careerTwinApi.today,
    staleTime: 5 * 60 * 1000,
  });

  const { data: history } = useQuery({
    queryKey: QUERY_KEYS.twinHistory,
    queryFn: careerTwinApi.history,
    staleTime: 60 * 1000,
  });

  const savePersona = useMutation({
    mutationFn: careerTwinApi.upsertPersona,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.twinPersona });
      toast.success("Twin updated");
      setShowPersona(false);
    },
    onError: () => toast.error("Couldn't save your twin."),
  });

  const replyMutation = useMutation({
    mutationFn: () => careerTwinApi.reply(today!.id, reply.trim(), mood),
    onSuccess: (data) => {
      queryClient.setQueryData(QUERY_KEYS.twinToday, data);
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.twinHistory });
      setReply("");
      setMood(undefined);
    },
    onError: () => toast.error("Couldn't send your reply."),
  });

  const onSavePersona = (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    savePersona.mutate({ name: name.trim(), voice, focus: focus.trim() });
  };

  const answered = today?.status === "answered";
  const pastCheckins = (history ?? []).filter((c) => c.id !== today?.id && c.status === "answered");

  return (
    <div className="mx-auto max-w-[760px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Daily"
        title={persona?.name || "Career Twin"}
        description="Your persistent AI twin checks in daily, grounded in your roadmap and goals. Reply to keep a running journal of your journey."
        actions={
          <button
            type="button"
            onClick={() => setShowPersona((v) => !v)}
            className="inline-flex items-center rounded-[7px] border border-rule-strong bg-paper px-3.5 py-2 text-[12.5px] font-medium text-ink-2 transition-colors hover:bg-bg-2"
          >
            {showPersona ? "Close" : "Customise"}
          </button>
        }
      />

      {showPersona && (
        <form onSubmit={onSavePersona} className="mb-6 space-y-3 rounded-[12px] border border-rule bg-paper p-5">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Twin name" className={FIELD_CLASS} />
          <select value={voice} onChange={(e) => setVoice(e.target.value as TwinVoice)} className={FIELD_CLASS}>
            {VOICES.map((v) => (
              <option key={v} value={v}>
                {v.charAt(0).toUpperCase() + v.slice(1)} voice
              </option>
            ))}
          </select>
          <textarea
            value={focus}
            onChange={(e) => setFocus(e.target.value)}
            placeholder="What should your twin keep front of mind? (optional)"
            rows={2}
            className={`${FIELD_CLASS} resize-y`}
          />
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={!name.trim() || savePersona.isPending}
              className="rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors hover:bg-green-2 disabled:opacity-50"
            >
              {savePersona.isPending ? "Saving…" : "Save twin"}
            </button>
          </div>
        </form>
      )}

      {todayLoading ? (
        <LoadingSpinner fullPage label="Your twin is preparing today's check-in…" />
      ) : today ? (
        <div className="mb-8 space-y-4 rounded-[14px] border border-green bg-paper p-6">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-terra">
              {today.date}
            </p>
            <p className="mt-1.5 font-serif text-[18px] font-medium leading-snug tracking-[-0.01em] text-ink">
              {today.greeting}
            </p>
            <p className="mt-2 text-[14px] leading-relaxed text-ink-2">{today.prompt}</p>
            {today.focusSuggestion && (
              <p className="mt-3 rounded-[8px] bg-green-soft px-3.5 py-2.5 text-[12.5px] leading-relaxed text-green-2">
                💡 {today.focusSuggestion}
              </p>
            )}
          </div>

          {answered ? (
            <div className="space-y-3 border-t border-rule pt-4">
              <div className="rounded-[10px] bg-bg-2 px-4 py-3">
                <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-3">You</p>
                <p className="mt-1 text-[13.5px] leading-relaxed text-ink-2">{today.userReply}</p>
              </div>
              <div className="rounded-[10px] border border-green/40 bg-paper px-4 py-3">
                <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-green-2">
                  {persona?.name || "Your twin"}
                </p>
                <p className="mt-1 text-[13.5px] leading-relaxed text-ink-2">{today.twinResponse}</p>
              </div>
            </div>
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (!reply.trim()) return;
                replyMutation.mutate();
              }}
              className="space-y-3 border-t border-rule pt-4"
            >
              <textarea
                value={reply}
                onChange={(e) => setReply(e.target.value)}
                placeholder="Your reply…"
                rows={3}
                className={`${FIELD_CLASS} resize-y`}
              />
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-1.5">
                  <span className="text-[12px] text-ink-3">Mood</span>
                  {[1, 2, 3, 4, 5].map((n) => (
                    <button
                      key={n}
                      type="button"
                      onClick={() => setMood(n)}
                      className={cn(
                        "h-7 w-7 rounded-[6px] border text-[12px] font-medium tabular-nums transition-colors",
                        mood === n
                          ? "border-green bg-green text-bg"
                          : "border-rule bg-bg text-ink-2 hover:border-rule-strong",
                      )}
                    >
                      {n}
                    </button>
                  ))}
                </div>
                <button
                  type="submit"
                  disabled={!reply.trim() || replyMutation.isPending}
                  className="rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors hover:bg-green-2 disabled:opacity-50"
                >
                  {replyMutation.isPending ? "Sending…" : "Send to twin"}
                </button>
              </div>
            </form>
          )}
        </div>
      ) : null}

      {pastCheckins.length > 0 && (
        <div>
          <p className="mb-3 text-[12px] font-semibold uppercase tracking-[0.06em] text-ink-3">
            Journal
          </p>
          <div className="space-y-3">
            {pastCheckins.map((c: DailyCheckin) => (
              <article key={c.id} className="rounded-[12px] border border-rule bg-paper p-4">
                <div className="flex items-center justify-between">
                  <p className="text-[12px] font-medium text-ink-2">{c.prompt}</p>
                  {c.createdAt && (
                    <span className="shrink-0 text-[11px] text-ink-3">{formatDate(c.createdAt)}</span>
                  )}
                </div>
                <p className="mt-2 text-[13px] leading-relaxed text-ink-2">{c.userReply}</p>
                {c.twinResponse && (
                  <p className="mt-2 border-l-2 border-green pl-3 text-[12.5px] leading-relaxed text-ink-3">
                    {c.twinResponse}
                  </p>
                )}
              </article>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
