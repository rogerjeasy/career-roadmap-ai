"use client";

import { useEffect } from "react";
import { onAuthStateChanged } from "firebase/auth";
import { firebaseAuth } from "@/lib/firebase";
import { userApi } from "@/lib/api/user";
import { useAuthStore } from "@/store/auth.store";

/**
 * Listens to Firebase auth state changes and syncs the user profile
 * from our backend into the auth store.
 *
 * Mounted once at the root — no children rendering blocked.
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const setUser = useAuthStore((s) => s.setUser);
  const setLoading = useAuthStore((s) => s.setLoading);
  const clear = useAuthStore((s) => s.clear);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(firebaseAuth, async (firebaseUser) => {
      setLoading(true);
      if (firebaseUser) {
        try {
          // Fetch full profile from our DB — auto-provisions if first sign-in
          const profile = await userApi.getMe();
          setUser(profile);
        } catch {
          // Token invalid or backend unreachable — treat as unauthenticated
          clear();
        }
      } else {
        clear();
      }
    });

    return unsubscribe;
  }, [setUser, setLoading, clear]);

  return <>{children}</>;
}
