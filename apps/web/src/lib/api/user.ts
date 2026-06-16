import type { UserProfile, UserUpdateInput } from "@/types/api.types";
import { apiClient } from "./client";

export const userApi = {
  /** Fetch the current user's full DB profile. */
  async getMe(): Promise<UserProfile> {
    const { data } = await apiClient.get<UserProfile>("/api/v1/users/me");
    return data;
  },

  /** Apply a partial update to the current user's profile. */
  async updateMe(input: UserUpdateInput): Promise<UserProfile> {
    const { data } = await apiClient.patch<UserProfile>("/api/v1/users/me", input);
    return data;
  },

  /** Permanently delete the current user's account. Irreversible. */
  async deleteAccount(): Promise<void> {
    await apiClient.delete("/api/v1/users/me");
  },
};
