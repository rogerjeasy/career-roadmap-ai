"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import { DirectionChat } from "@/components/onboarding/direction-chat";
import { CvContextCard } from "@/components/onboarding/cv-context-card";
import { useOnboardingStore } from "@/store/onboarding-store";
import type { CvAnalysisResult, OnboardingChatMessage } from "@/types/onboarding.types";

const TIME_CHIPS = ["3 months · soon", "6 months", "12–18 months · build it right", "Open / not sure"];

function escHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

const TIMELINE_MAP: Record<string, number | null> = {
  "3 months · soon": 3,
  "6 months": 6,
  "12–18 months · build it right": 15,
  "Open / not sure": null,
};

function deriveCareerPaths(cvResult: CvAnalysisResult): string[] {
  const skillNames = cvResult.skills.map((s) => s.name.toLowerCase());
  const hasSkill = (keywords: string[]) =>
    skillNames.some((name) => keywords.some((k) => name.includes(k)));

  const roleText = [
    cvResult.currentRole ?? "",
    ...cvResult.roles.map((r) => `${r.title} ${r.company ?? ""}`),
  ]
    .join(" ")
    .toLowerCase();

  const isAiMl =
    hasSkill([
      "machine learning", "deep learning", "neural", "nlp", "llm", "langchain",
      "pytorch", "tensorflow", "transformers", "scikit", "computer vision",
      "reinforcement", "generative ai",
    ]) ||
    /\bml\b|ai\b|machine learning/.test(roleText);

  const isInfra =
    hasSkill([
      "kubernetes", "k8s", "terraform", "devops", "sre", "aws", "gcp", "azure",
      "cloud", "docker", "ci/cd", "infrastructure", "platform engineering", "helm", "ansible",
    ]) ||
    /platform|devops|sre/.test(roleText);

  const isData =
    hasSkill([
      "spark", "kafka", "flink", "airflow", "dbt", "bigquery", "snowflake",
      "data pipeline", "etl", "data engineering", "databricks",
    ]) || roleText.includes("data engineer");

  const isBackend = hasSkill([
    "python", "java", "go", "golang", "rust", "fastapi", "django", "spring",
    "microservices", "distributed", "grpc", "graphql",
  ]);

  const isFrontend = hasSkill([
    "react", "vue", "angular", "next.js", "typescript", "javascript", "frontend",
  ]);

  const hasResearchBackground =
    cvResult.roles.some(
      (r) =>
        r.title.toLowerCase().includes("research") ||
        r.company?.toLowerCase().includes("university") ||
        r.company?.toLowerCase().includes("lab") ||
        r.company?.toLowerCase().includes("institute"),
    ) ||
    cvResult.projects.some(
      (p) =>
        p.description?.toLowerCase().includes("research") ||
        p.description?.toLowerCase().includes("fp7") ||
        p.description?.toLowerCase().includes("horizon"),
    );

  const isSenior = cvResult.yearsOfExperience >= 6;
  const isVeryExperienced = cvResult.yearsOfExperience >= 10;
  const hasLeadership = cvResult.leadershipSignals >= 2;

  const paths: string[] = [];

  if (isAiMl && hasResearchBackground) paths.push("🔬 AI Research Engineer");
  else if (isAiMl) paths.push("🧠 AI / ML Engineer");
  if (isInfra) paths.push("🛠️ Platform / Infra Engineer");
  if (isData && !isAiMl) paths.push("📊 Data Engineer");
  if ((isVeryExperienced || hasLeadership) && isBackend) paths.push("🏗️ Staff / Principal Engineer");
  else if (isSenior && isBackend && !isAiMl && !isInfra) paths.push("🏗️ Senior Backend Engineer");
  if (isFrontend && isBackend) paths.push("🎨 Fullstack Tech Lead");
  if (isSenior || hasLeadership) paths.push("🌱 Founding / Early-stage Eng.");

  const unique = [...new Set(paths)].slice(0, 4);

  if (unique.length < 2) {
    return [
      "🧠 AI / ML Engineer",
      "🏗️ Staff / Principal Engineer",
      "🌱 Founding / Early-stage Eng.",
      "🛠️ Platform / Infra Engineer",
    ];
  }

  return unique;
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
  const { cvResult, chatMessages, addChatMessage, selectChip, setDirection, direction } =
    useOnboardingStore();

  const firstProject = cvResult?.projects[0];

  // Guards against double-init from React Strict Mode's cleanup/re-run cycle and
  // from Zustand persist hydration transiently resetting chatMessages to [] after
  // the first effect run (which would otherwise make length drop back to 0 and
  // re-trigger the effect, producing duplicate greeting messages).
  const chatInitialized = useRef(false);

  useEffect(() => {
    if (chatInitialized.current || chatMessages.length > 0) return;
    chatInitialized.current = true;

    const greetingId = makeId();
    const pathId = makeId();

    const safeUserName = escHtml(userName ?? "there");
    const safeProjectName = firstProject?.name ? escHtml(firstProject.name) : null;

    const greeting: OnboardingChatMessage = {
      id: greetingId,
      from: "twin",
      content: `Hi <b>${safeUserName}</b> 👋 ${
        safeProjectName
          ? `I just finished reading your CV — really impressive work on <b>${safeProjectName}</b>.`
          : "I just finished reading your CV — great background."
      } Before we map out where you&apos;re going, I want to understand what you&apos;re <em>actually</em> looking for. A few quick questions:`,
      timestamp: now(),
    };

    const pathOptions = cvResult ? deriveCareerPaths(cvResult) : [];

    const pathMsg: OnboardingChatMessage = {
      id: pathId,
      from: "twin",
      content:
        pathOptions.length > 0
          ? "Looking at your trajectory, <b>these paths seem strongest</b>. Which one excites you most? (You can pick one — or type your own below.)"
          : "What career path are you aiming for? Describe it in your own words — there's no wrong answer.",
      chips: pathOptions.length > 0 ? pathOptions : undefined,
      selectedChip: null,
      timestamp: now(),
    };

    addChatMessage(greeting);
    addChatMessage(pathMsg);
  }, [chatMessages.length, addChatMessage, userName, cvResult, firstProject]);

  const timelineMessageId = useMemo(
    () => chatMessages.find((m) => m.chips?.some((c) => TIME_CHIPS.includes(c)))?.id,
    [chatMessages],
  );

  const handleSelectChip = useCallback(
    (messageId: string, chip: string) => {
      selectChip(messageId, chip);

      const isPathMessage = chatMessages
        .find((m) => m.id === messageId)
        ?.chips?.some((c) => !TIME_CHIPS.includes(c));

      const isTimelineMessage = TIME_CHIPS.includes(chip);

      if (isPathMessage) {
        setDirection({ goal: chip });

        // Add user reply
        const userMsg: OnboardingChatMessage = {
          id: makeId(),
          from: "user",
          content: chip,
          timestamp: now(),
        };
        addChatMessage(userMsg);

        // Add twin follow-up with timeline chips (after brief delay)
        if (!timelineMessageId) {
          const twinMsg: OnboardingChatMessage = {
            id: makeId(),
            from: "twin",
            content:
              "Got it — noted. And what&apos;s your <b>time horizon?</b> Are you in a &quot;land a role soon&quot; mode, or building the strongest possible profile over twelve to eighteen months?",
            chips: TIME_CHIPS,
            selectedChip: null,
            timestamp: now(),
          };
          addChatMessage(twinMsg);
        }
      } else if (isTimelineMessage) {
        setDirection({ timelineMonths: TIMELINE_MAP[chip] ?? null });

        const userMsg: OnboardingChatMessage = {
          id: makeId(),
          from: "user",
          content: chip,
          timestamp: now(),
        };
        addChatMessage(userMsg);

        const twinMsg: OnboardingChatMessage = {
          id: makeId(),
          from: "twin",
          content:
            "Perfect — I&apos;ve noted your goal and timeline. Click <b>Continue</b> below to set your practical constraints and I&apos;ll start building your roadmap.",
          timestamp: now(),
        };
        addChatMessage(twinMsg);
      }
    },
    [chatMessages, selectChip, addChatMessage, setDirection, timelineMessageId],
  );

  const handleSend = useCallback(
    (text: string) => {
      const userMsg: OnboardingChatMessage = {
        id: makeId(),
        from: "user",
        content: text,
        timestamp: now(),
      };
      addChatMessage(userMsg);

      if (!direction.goal) {
        setDirection({ goal: text });
        const twinMsg: OnboardingChatMessage = {
          id: makeId(),
          from: "twin",
          content: `Great — <b>${text.slice(0, 80)}</b> is noted as your goal. What&apos;s your time horizon?`,
          chips: TIME_CHIPS,
          selectedChip: null,
          timestamp: now(),
        };
        addChatMessage(twinMsg);
      } else {
        const twinMsg: OnboardingChatMessage = {
          id: makeId(),
          from: "twin",
          content: "Understood. Click <b>Continue</b> when you&apos;re ready to set your constraints.",
          timestamp: now(),
        };
        addChatMessage(twinMsg);
      }
    },
    [addChatMessage, direction.goal, setDirection],
  );

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
          {!direction.goal && (
            <button
              type="button"
              onClick={() => {
                setDirection({ goal: "AI Systems Engineer" });
                onNext();
              }}
              className="text-[14px] font-medium text-green transition-colors hover:text-green-2"
            >
              Skip — let AI suggest 3 paths
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

