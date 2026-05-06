import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { UserProfile } from "@/types/api.types";

interface AuthState {
  /** Full user profile from the application DB (not Firebase). */
  user: UserProfile | null;
  isAuthenticated: boolean;
  /** True while the auth provider is resolving the initial Firebase state. */
  isLoading: boolean;

  setUser: (user: UserProfile | null) => void;
  setLoading: (loading: boolean) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,
      isLoading: true,

      setUser: (user) => set({ user, isAuthenticated: !!user, isLoading: false }),
      setLoading: (isLoading) => set({ isLoading }),
      clear: () => set({ user: null, isAuthenticated: false, isLoading: false }),
    }),
    {
      name: "crai-auth",
      // Only persist the user profile — tokens are managed by Firebase SDK (IndexedDB)
      partialize: (state) => ({ user: state.user }),
    },
  ),
);
