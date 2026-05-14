"use client";

import { useCallback } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { authApi } from "@/lib/api/auth";
import { roadmapApi } from "@/lib/api/roadmap";
import { useAuthStore } from "@/store/auth.store";
import { ApiError } from "@/types/api.types";
import { ROUTES } from "@/lib/constants";

// Checks Firestore for an existing roadmap and returns the correct post-login
// destination. Falls back to onboarding on any error so new or partial-setup
// users are never stuck on a blank dashboard.
async function postLoginRoute(): Promise<string> {
  try {
    const list = await roadmapApi.list(1);
    return list.length > 0 ? ROUTES.dashboard : ROUTES.onboarding;
  } catch {
    return ROUTES.onboarding;
  }
}

/**
 * Primary hook for authentication.
 *
 * Exposes the current user, auth state, and all auth actions.
 * Errors are surfaced via toast — callers don't need try/catch for UI feedback.
 */
export function useAuth() {
  const { user, isAuthenticated, isLoading, setUser, clear } = useAuthStore();
  const router = useRouter();

  const registerWithEmail = useCallback(
    async (email: string, password: string, displayName?: string) => {
      try {
        const profile = await authApi.registerWithEmail(email, password, displayName);
        setUser(profile);
        toast.success("Account created — welcome!");
        router.push(ROUTES.onboarding);
      } catch (err) {
        toast.error(err instanceof ApiError ? err.message : "Registration failed");
        throw err; // re-throw so form components can reset loading state
      }
    },
    [setUser, router],
  );

  const loginWithEmail = useCallback(
    async (email: string, password: string, rememberMe?: boolean) => {
      try {
        const profile = await authApi.loginWithEmail(email, password, rememberMe);
        setUser(profile);
        router.push(await postLoginRoute());
      } catch (err) {
        toast.error(err instanceof ApiError ? err.message : "Login failed");
        throw err;
      }
    },
    [setUser, router],
  );

  const loginWithGoogle = useCallback(async () => {
    try {
      const profile = await authApi.loginWithGoogle();
      setUser(profile);
      router.push(await postLoginRoute());
    } catch (err) {
      const isPopupClosed =
        err instanceof Error && err.message.includes("popup-closed-by-user");
      if (isPopupClosed) return;
      toast.error(err instanceof ApiError ? err.message : "Google sign-in failed");
      throw err;
    }
  }, [setUser, router]);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      clear();
      router.push(ROUTES.login);
    }
  }, [clear, router]);

  return {
    user,
    isAuthenticated,
    isLoading,
    registerWithEmail,
    loginWithEmail,
    loginWithGoogle,
    logout,
  };
}
