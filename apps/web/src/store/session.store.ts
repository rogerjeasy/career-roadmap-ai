import { create } from "zustand";
import { getSession, clearSession as apiClearSession } from "@/lib/api/session";
import type { ClarificationQuestion, SessionState } from "@/types/session.types";

interface SessionStore {
  session: SessionState | null;
  isLoading: boolean;
  error: string | null;

  /** Fetch (or create) the session from Redis via the API. */
  fetchSession: () => Promise<void>;

  /** Delete the session on the server and clear local state. */
  clearSession: () => Promise<void>;

  /** Optimistically update local session state after a mutation. */
  setSession: (session: SessionState) => void;

  /** Convenience accessor — derived from session.followUpQueue. */
  setPendingClarifications: (questions: ClarificationQuestion[]) => void;
}

export const useSessionStore = create<SessionStore>((set, get) => ({
  session: null,
  isLoading: false,
  error: null,

  fetchSession: async () => {
    set({ isLoading: true, error: null });
    try {
      const session = await getSession();
      set({ session, isLoading: false });
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : "Failed to load session",
        isLoading: false,
      });
    }
  },

  clearSession: async () => {
    set({ isLoading: true, error: null });
    try {
      await apiClearSession();
      set({ session: null, isLoading: false });
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : "Failed to clear session",
        isLoading: false,
      });
    }
  },

  setSession: (session) => set({ session }),

  setPendingClarifications: (questions) => {
    const current = get().session;
    if (!current) return;
    set({ session: { ...current, followUpQueue: questions } });
  },
}));
