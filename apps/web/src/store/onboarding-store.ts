import { create } from "zustand";
import { persist } from "zustand/middleware";
import { fixMojibake } from "@/lib/utils";
import type {
  CvAnalysisResult,
  LocationPreference,
  OnboardingChatMessage,
  OnboardingConstraints,
  OnboardingDirection,
  OnboardingStep,
} from "@/types/onboarding.types";

const DEFAULT_CONSTRAINTS: OnboardingConstraints = {
  weeklyHours: 12,
  location: "",
  locationPreference: "remote",
  compensationTarget: 120,
  workStyles: [],
  lifeContext: "",
  lifeContextPrivate: true,
};

interface OnboardingState {
  step: OnboardingStep;
  cvResult: CvAnalysisResult | null;
  direction: OnboardingDirection;
  constraints: OnboardingConstraints;
  chatMessages: OnboardingChatMessage[];
  generationRequestId: string | null;
  generationSessionId: string | null;

  setStep: (step: OnboardingStep) => void;
  setCvResult: (result: CvAnalysisResult | null) => void;
  setDirection: (patch: Partial<OnboardingDirection>) => void;
  setWeeklyHours: (hours: number) => void;
  setLocation: (location: string) => void;
  setLocationPreference: (pref: LocationPreference) => void;
  setCompensationTarget: (amount: number) => void;
  toggleWorkStyle: (style: string) => void;
  setLifeContext: (text: string) => void;
  setLifeContextPrivate: (value: boolean) => void;
  addChatMessage: (msg: OnboardingChatMessage) => void;
  selectChip: (messageId: string, chip: string) => void;
  setGenerationIds: (requestId: string, sessionId: string) => void;
  /** Clears all state accumulated AFTER the CV step (direction, constraints,
   *  chat, generation IDs) without touching `step` or `cvResult`. Call this
   *  whenever a new CV is uploaded so steps 3–5 start from a clean slate. */
  resetDownstreamSteps: () => void;
  reset: () => void;
}

export const useOnboardingStore = create<OnboardingState>()(
  persist(
    (set) => ({
      step: 1,
      cvResult: null,
      direction: { goal: "", timelineMonths: null },
      constraints: DEFAULT_CONSTRAINTS,
      chatMessages: [],
      generationRequestId: null,
      generationSessionId: null,

      setStep: (step) => set({ step }),
      setCvResult: (cvResult) => set({ cvResult }),
      setDirection: (patch) =>
        set((s) => ({ direction: { ...s.direction, ...patch } })),
      setWeeklyHours: (weeklyHours) =>
        set((s) => ({ constraints: { ...s.constraints, weeklyHours } })),
      setLocation: (location) =>
        set((s) => ({ constraints: { ...s.constraints, location } })),
      setLocationPreference: (locationPreference) =>
        set((s) => ({ constraints: { ...s.constraints, locationPreference } })),
      setCompensationTarget: (compensationTarget) =>
        set((s) => ({ constraints: { ...s.constraints, compensationTarget } })),
      toggleWorkStyle: (style) =>
        set((s) => ({
          constraints: {
            ...s.constraints,
            workStyles: s.constraints.workStyles.includes(style)
              ? s.constraints.workStyles.filter((w) => w !== style)
              : [...s.constraints.workStyles, style],
          },
        })),
      setLifeContext: (lifeContext) =>
        set((s) => ({ constraints: { ...s.constraints, lifeContext } })),
      setLifeContextPrivate: (lifeContextPrivate) =>
        set((s) => ({ constraints: { ...s.constraints, lifeContextPrivate } })),
      addChatMessage: (msg) =>
        set((s) => ({ chatMessages: [...s.chatMessages, msg] })),
      selectChip: (messageId, chip) =>
        set((s) => ({
          chatMessages: s.chatMessages.map((m) =>
            m.id === messageId ? { ...m, selectedChip: chip } : m,
          ),
        })),
      setGenerationIds: (generationRequestId, generationSessionId) =>
        set({ generationRequestId, generationSessionId }),
      resetDownstreamSteps: () =>
        set({
          direction: { goal: "", timelineMonths: null },
          constraints: DEFAULT_CONSTRAINTS,
          chatMessages: [],
          generationRequestId: null,
          generationSessionId: null,
        }),
      reset: () =>
        set({
          step: 1,
          cvResult: null,
          direction: { goal: "", timelineMonths: null },
          constraints: DEFAULT_CONSTRAINTS,
          chatMessages: [],
          generationRequestId: null,
          generationSessionId: null,
        }),
    }),
    {
      name: "crai-onboarding",
      version: 2,
      migrate(persisted, fromVersion) {
        const s = persisted as Partial<OnboardingState>;

        // v1 → v2: clear chat messages that may have been duplicated by a
        // React Strict Mode / persist-hydration race in the previous version.
        // StepDirection re-seeds the chat on next mount via the useRef guard.
        if (fromVersion < 2) {
          s.chatMessages = [];
        }

        if (s.direction?.goal) {
          s.direction = { ...s.direction, goal: fixMojibake(s.direction.goal) };
        }
        if (s.chatMessages?.length) {
          s.chatMessages = s.chatMessages.map((m) => ({
            ...m,
            content: fixMojibake(m.content),
            chips: m.chips?.map(fixMojibake),
            selectedChip: m.selectedChip ? fixMojibake(m.selectedChip) : m.selectedChip,
          }));
        }
        return s;
      },
      partialize: (s) => ({
        step: s.step,
        cvResult: s.cvResult,
        direction: s.direction,
        constraints: s.constraints,
        chatMessages: s.chatMessages,
        generationRequestId: s.generationRequestId,
        generationSessionId: s.generationSessionId,
      }),
    },
  ),
);
