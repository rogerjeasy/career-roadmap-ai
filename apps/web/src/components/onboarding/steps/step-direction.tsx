"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { DirectionChat } from "@/components/onboarding/direction-chat";
import { CvContextCard } from "@/components/onboarding/cv-context-card";
import { useOnboardingStore } from "@/store/onboarding-store";
import { intakeApi } from "@/lib/api/intake";
import { subscribeToAgentStream } from "@/lib/sse";
import type { SSESubscription } from "@/lib/sse";
import type { AgentEvent } from "@/types/agent.types";
import type {
  IntakeClarificationPayload,
  IntakeResolvedPayload,
  OnboardingChatMessage,
} from "@/types/onboarding.types";

const TIME_CHIPS = ["3 months · soon", "6 months", "12–18 months · build it right", "Open / not sure"];

const TIMELINE_MAP: Record<string, number | null> = {
  "3 months · soon": 3,
  "6 months": 6,
  "12–18 months · build it right": 15,
  "Open / not sure": null,
};

function escHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function makeId() {
  return Math.random().toString(36).slice(2);
}

function now() {
  return new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

export interface StepDirectionProps {
  onBack: () => void;
  onNext: () => void;
  userName?: string | null;
}

export function StepDirection({ onBack, onNext, userName }: StepDirectionProps) {
  const {
    cvResult,
    chatMessages,
    addChatMessage,
    selectChip,
    setDirection,
    direction,
    setLocation,
    intakePendingQuestions,
    intakeComplete,
    setIntakeSessionId,
    setIntakePendingQuestions,
    setIntakeClarificationRound,
    setIntakeComplete,
  } = useOnboardingStore();

  const [isBotTyping, setIsBotTyping] = useState(false);

  const chatInitialized = useRef(false);
  const sseSubscription = useRef<SSESubscription | null>(null);
  // Stable ref to the latest handler so the one-time SSE subscription always
  // calls the current closure (avoids stale chatMessages.length capture).
  const handleSseEventRef = useRef<(event: AgentEvent) => void>(() => undefined);

  // ── SSE event handler ──────────────────────────────────────────────────────

  const handleSseEvent = useCallback(
    (event: AgentEvent) => {
      setIsBotTyping(false);

      if (event.event_type === "clarification_required") {
        const payload = event.payload as unknown as IntakeClarificationPayload;
        const questions = payload.questions ?? [];
        const round = payload.round ?? 1;
        const suggestions = payload.career_path_suggestions ?? [];

        setIntakeClarificationRound(round);
        setIntakePendingQuestions(
          questions.map((q) => ({
            id: q.id,
            question: q.question,
            field_name: q.field_name,
            priority: q.priority,
          }))
        );

        if (round === 1) {
          const safeUserName = escHtml(userName ?? "there");
          const firstProject = cvResult?.projects[0];
          const safeProjectName = firstProject?.name ? escHtml(firstProject.name) : null;

          const greeting: OnboardingChatMessage = {
            id: makeId(),
            from: "twin",
            content: `Hi <b>${safeUserName}</b> 👋 ${
              safeProjectName
                ? `I just finished reading your CV — really impressive work on <b>${safeProjectName}</b>.`
                : "I just finished reading your CV — great background."
            } Before we map out where you&apos;re going, I want to understand what you&apos;re <em>actually</em> looking for. A few quick questions:`,
            timestamp: now(),
          };
          addChatMessage(greeting);

          if (suggestions.length > 0) {
            const pathMsg: OnboardingChatMessage = {
              id: makeId(),
              from: "twin",
              content:
                "Looking at your trajectory, <b>these paths seem strongest</b>. Which one excites you most? (You can pick one — or type your own below.)",
              chips: suggestions.slice(0, 4),
              selectedChip: null,
              timestamp: now(),
            };
            addChatMessage(pathMsg);
          } else if (questions.length > 0 && questions[0].field_name === "target_role") {
            // No suggestions — show plain question for target_role
            const q = questions[0];
            const qMsg: OnboardingChatMessage = {
              id: makeId(),
              from: "twin",
              content: q.question,
              timestamp: now(),
            };
            addChatMessage(qMsg);
          }
        } else {
          // Rounds 2+ — show question(s) directly
          for (const q of questions) {
            const isTimeline = q.field_name === "timeline_months";
            const qMsg: OnboardingChatMessage = {
              id: makeId(),
              from: "twin",
              content: q.question,
              chips: isTimeline ? TIME_CHIPS : undefined,
              selectedChip: isTimeline ? null : undefined,
              timestamp: now(),
            };
            addChatMessage(qMsg);
          }
        }
      } else if (event.event_type === "clarification_resolved") {
        const payload = event.payload as unknown as IntakeResolvedPayload;
        const suggestions = payload.career_path_suggestions ?? [];

        setIntakeComplete(true);
        setIntakePendingQuestions([]);

        // If resolved on start (returning user / complete profile), still show path chips
        if (chatMessages.length === 0 && suggestions.length > 0) {
          const safeUserName = escHtml(userName ?? "there");
          const greeting: OnboardingChatMessage = {
            id: makeId(),
            from: "twin",
            content: `Welcome back, <b>${safeUserName}</b>! Your profile is up to date. Here are some directions we can explore:`,
            timestamp: now(),
          };
          const pathMsg: OnboardingChatMessage = {
            id: makeId(),
            from: "twin",
            content:
              "Which path are you focusing on? (You can also type your own goal below.)",
            chips: suggestions.slice(0, 4),
            selectedChip: null,
            timestamp: now(),
          };
          addChatMessage(greeting);
          addChatMessage(pathMsg);
        } else {
          const readyMsg: OnboardingChatMessage = {
            id: makeId(),
            from: "twin",
            content:
              "I&apos;ve got everything I need. Click <b>Continue</b> below and I&apos;ll start building your personalised roadmap.",
            timestamp: now(),
          };
          addChatMessage(readyMsg);
        }
      }
    },
    [
      userName,
      cvResult,
      chatMessages.length,
      addChatMessage,
      setIntakeClarificationRound,
      setIntakePendingQuestions,
      setIntakeComplete,
    ],
  );

  // Keep the ref in sync with the latest callback version.
  useEffect(() => {
    handleSseEventRef.current = handleSseEvent;
  }, [handleSseEvent]);

  // ── Mount: start intake ────────────────────────────────────────────────────

  useEffect(() => {
    if (chatInitialized.current || chatMessages.length > 0) return;
    chatInitialized.current = true;

    setIsBotTyping(true);

    // Call intake/start first to get the session_id, then subscribe to SSE.
    // The server writes events to an event_log replay list before publishing,
    // so late subscribers still receive them via the replay mechanism in the
    // stream controller.
    intakeApi
      .start()
      .then(({ sessionId }) => {
        setIntakeSessionId(sessionId);
        const sub = subscribeToAgentStream(
          sessionId,
          (event) => handleSseEventRef.current(event),
          (err) => {
            setIsBotTyping(false);
            addChatMessage({
              id: makeId(),
              from: "twin",
              content: `I had trouble connecting — please refresh and try again. (${escHtml(err.message)})`,
              timestamp: now(),
            });
          },
          () => {
            /* stream closed normally */
          },
        );
        sseSubscription.current = sub;
      })
      .catch((err: unknown) => {
        setIsBotTyping(false);
        const msg = err instanceof Error ? err.message : "Unknown error";
        addChatMessage({
          id: makeId(),
          from: "twin",
          content: `Something went wrong starting the intake. Please refresh. (${escHtml(msg)})`,
          timestamp: now(),
        });
      });

    return () => {
      sseSubscription.current?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Chip selection ─────────────────────────────────────────────────────────

  const handleSelectChip = useCallback(
    async (messageId: string, chip: string) => {
      selectChip(messageId, chip);

      const userMsg: OnboardingChatMessage = {
        id: makeId(),
        from: "user",
        content: chip,
        timestamp: now(),
      };
      addChatMessage(userMsg);

      const isTimeline = TIME_CHIPS.includes(chip);

      if (isTimeline) {
        setDirection({ timelineMonths: TIMELINE_MAP[chip] ?? null });
      } else {
        // Treat as career path / goal selection
        setDirection({ goal: chip });
      }

      if (!intakeComplete) {
        setIsBotTyping(true);
        try {
          await intakeApi.reply(chip);
        } catch {
          setIsBotTyping(false);
        }
      } else {
        // Intake resolved — add a continuation message for timeline chips
        if (isTimeline) {
          addChatMessage({
            id: makeId(),
            from: "twin",
            content:
              "Perfect — I&apos;ve noted your goal and timeline. Click <b>Continue</b> below to set your practical constraints.",
            timestamp: now(),
          });
        }
      }
    },
    [selectChip, addChatMessage, setDirection, intakeComplete],
  );

  // ── Text input ─────────────────────────────────────────────────────────────

  const handleSend = useCallback(
    async (text: string) => {
      const userMsg: OnboardingChatMessage = {
        id: makeId(),
        from: "user",
        content: text,
        timestamp: now(),
      };
      addChatMessage(userMsg);

      // Optimistically set local direction fields based on pending question context
      const pendingField = intakePendingQuestions[0]?.field_name;
      if (pendingField === "target_role" || !direction.goal) {
        setDirection({ goal: text });
      } else if (pendingField === "location") {
        setLocation(text);
      } else if (pendingField === "timeline_months") {
        const months = parseInt(text, 10);
        if (!isNaN(months)) setDirection({ timelineMonths: months });
      }

      if (!intakeComplete) {
        setIsBotTyping(true);
        try {
          await intakeApi.reply(text);
        } catch {
          setIsBotTyping(false);
          addChatMessage({
            id: makeId(),
            from: "twin",
            content: "I had trouble processing that — please try again.",
            timestamp: now(),
          });
        }
      } else {
        addChatMessage({
          id: makeId(),
          from: "twin",
          content: "Understood. Click <b>Continue</b> when you&apos;re ready.",
          timestamp: now(),
        });
      }
    },
    [addChatMessage, direction.goal, intakeComplete, intakePendingQuestions, setDirection, setLocation],
  );

  // ── Render ─────────────────────────────────────────────────────────────────

  const canContinue = !!(direction.goal || intakeComplete);

  return (
    <section>
      <div className="mb-9 max-w-[720px]">
        <p className="mb-[22px] inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-terra">
          <span className="font-serif text-[13px] italic font-medium normal-case tracking-normal text-ink-3">
            Step three of five
          </span>
          · Your direction
        </p>
        <h2 className="mb-4 font-serif font-[350] text-[clamp(32px,4.5vw,48px)] leading-[1.05] tracking-[-0.025em] text-ink">
          Where are you trying to <em className="italic text-green">go?</em>
        </h2>
        <p className="text-[16px] leading-[1.55] text-ink-2">
          No need for the perfect answer. Talk it through with the Career Twin like you would with a
          thoughtful friend who&apos;s done this before. We&apos;ll refine it together.
        </p>
      </div>

      <div className="grid grid-cols-1 items-start gap-[22px] xl:grid-cols-[1fr_320px]">
        <DirectionChat
          messages={chatMessages}
          userName={userName}
          onSend={handleSend}
          onSelectChip={handleSelectChip}
          isBotTyping={isBotTyping}
        />
        {cvResult && <CvContextCard cvResult={cvResult} userName={userName} />}
      </div>

      <div className="mt-11 flex items-center justify-between border-t border-rule pt-6">
        <button
          type="button"
          onClick={onBack}
          className="text-[14px] font-medium text-ink-3 transition-colors hover:text-ink"
        >
          ← Back
        </button>
        <div className="flex items-center gap-3">
          {!canContinue && (
            <button
              type="button"
              onClick={onNext}
              className="text-[14px] font-medium text-green transition-colors hover:text-green-2"
            >
              Skip — let AI decide
            </button>
          )}
          <button
            type="button"
            onClick={onNext}
            className="group inline-flex items-center gap-2 rounded-lg bg-ink px-5 py-3 text-[14px] font-medium text-bg transition-all hover:-translate-y-px hover:bg-green-2 hover:shadow-[0_8px_20px_-8px_rgba(14,58,43,0.4)]"
          >
            Continue
            <span className="transition-transform group-hover:translate-x-0.5" aria-hidden="true">
              →
            </span>
          </button>
        </div>
      </div>
    </section>
  );
}
