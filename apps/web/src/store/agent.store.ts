import { create } from "zustand";
import type {
  AgentEvent,
  ClarificationPayload,
  OrchestratorCompletedPayload,
} from "@/types/agent.types";
import type { RoadmapData } from "@/types/roadmap.types";

export type { AgentEvent };

export type GenerationStatus =
  | "idle"
  | "connecting"
  | "generating"
  | "clarification"
  | "completed"
  | "failed";

export interface AgentStatus {
  name: string;
  status: "running" | "completed" | "failed";
  duration_ms?: number;
}

interface AgentState {
  status: GenerationStatus;
  currentPct: number;
  currentStepIndex: number;
  currentStepName: string;
  totalSteps: number;
  agents: Record<string, AgentStatus>;
  clarification: ClarificationPayload | null;
  error: string | null;
  roadmap: RoadmapData | null;
  confidence: number;
  validationPassed: boolean;
  durationMs: number;
  eventLog: AgentEvent[];

  setStatus: (status: GenerationStatus) => void;
  setError: (message: string) => void;
  handleEvent: (event: AgentEvent) => void;
  reset: () => void;
}

const INITIAL: Omit<AgentState, "setStatus" | "setError" | "handleEvent" | "reset"> = {
  status: "idle",
  currentPct: 0,
  currentStepIndex: -1,
  currentStepName: "",
  totalSteps: 7,
  agents: {},
  clarification: null,
  error: null,
  roadmap: null,
  confidence: 0,
  validationPassed: false,
  durationMs: 0,
  eventLog: [],
};

export const useAgentStore = create<AgentState>()((set) => ({
  ...INITIAL,

  setStatus: (status) => set({ status }),

  setError: (message) => set({ status: "failed", error: message }),

  handleEvent: (event) => {
    // Prepend to event log, newest first, capped at 20 entries
    set((s) => ({ eventLog: [event, ...s.eventLog].slice(0, 20) }));

    const { event_type, payload } = event;

    switch (event_type) {
      case "orchestration_started":
        set({ status: "generating", currentPct: 0, error: null, clarification: null });
        break;

      case "step_progress": {
        // Orchestrator-level events carry {step_name, step_index, total_steps, pct}.
        // Individual agent _emit_progress() calls carry {agent, step, description} —
        // those only go to the event log and must not overwrite pipeline progress state.
        const p = payload as Record<string, unknown>;
        if (typeof p.step_name === "string" && typeof p.pct === "number") {
          set({
            currentPct: p.pct,
            currentStepIndex: typeof p.step_index === "number" ? p.step_index : -1,
            currentStepName: p.step_name,
            totalSteps: typeof p.total_steps === "number" ? p.total_steps : 8,
          });
        }
        break;
      }

      case "agent_started": {
        const p = payload as { agent: string };
        set((s) => ({
          agents: { ...s.agents, [p.agent]: { name: p.agent, status: "running" } },
        }));
        break;
      }

      case "agent_completed":
      case "agent_failed": {
        const p = payload as { agent: string; duration_ms: number };
        set((s) => ({
          agents: {
            ...s.agents,
            [p.agent]: {
              name: p.agent,
              status: event_type === "agent_completed" ? "completed" : "failed",
              duration_ms: p.duration_ms,
            },
          },
        }));
        break;
      }

      case "clarification_required": {
        const p = payload as unknown as ClarificationPayload;
        set({ status: "clarification", clarification: p });
        break;
      }

      case "orchestration_completed": {
        const p = payload as unknown as OrchestratorCompletedPayload;
        set({
          status: "completed",
          roadmap: p.roadmap,
          confidence: p.confidence,
          validationPassed: p.validation_passed,
          durationMs: p.duration_ms,
          currentPct: 100,
          error: null,
        });
        break;
      }

      case "orchestration_failed": {
        const p = payload as { error: string };
        set({ status: "failed", error: p.error ?? "Roadmap generation failed" });
        break;
      }

      default:
        break;
    }
  },

  reset: () => set(INITIAL),
}));
