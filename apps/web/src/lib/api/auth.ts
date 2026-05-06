import {
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
  updateProfile,
} from "firebase/auth";
import { firebaseAuth, googleProvider } from "@/lib/firebase";
import type { UserProfile } from "@/types/api.types";
import { apiClient } from "./client";

export const authApi = {
  /**
   * Register with email and password.
   * Firebase SDK creates the user → backend auto-provisions the DB record.
   */
  async registerWithEmail(
    email: string,
    password: string,
    displayName?: string,
  ): Promise<UserProfile> {
    const { user } = await createUserWithEmailAndPassword(firebaseAuth, email, password);
    if (displayName) {
      await updateProfile(user, { displayName });
    }
    const { data } = await apiClient.get<UserProfile>("/api/v1/users/me");
    return data;
  },

  /**
   * Sign in with email and password.
   * Firebase SDK authenticates → backend returns the full DB profile.
   */
  async loginWithEmail(email: string, password: string): Promise<UserProfile> {
    await signInWithEmailAndPassword(firebaseAuth, email, password);
    const { data } = await apiClient.get<UserProfile>("/api/v1/users/me");
    return data;
  },

  /**
   * Sign in with Google via popup.
   * Firebase SDK handles OAuth → backend syncs the user with provider info.
   */
  async loginWithGoogle(): Promise<UserProfile> {
    await signInWithPopup(firebaseAuth, googleProvider);
    const { data } = await apiClient.post<UserProfile>("/api/v1/auth/google");
    return data;
  },

  /**
   * Sign out — revokes the Firebase token server-side, then clears client state.
   */
  async logout(): Promise<void> {
    try {
      // Best-effort: revoke refresh tokens on the server
      await apiClient.post("/api/v1/auth/logout");
    } finally {
      // Always clear local Firebase state regardless of server response
      await signOut(firebaseAuth);
    }
  },
};
