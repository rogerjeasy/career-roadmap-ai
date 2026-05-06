import type { UserProfile } from "@/types/api.types";
import { apiClient } from "./client";

export const userApi = {
  /** Fetch the current user's full DB profile. */
  async getMe(): Promise<UserProfile> {
    const { data } = await apiClient.get<UserProfile>("/api/v1/users/me");
    return data;
  },
};
