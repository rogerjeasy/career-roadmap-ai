import { apiClient } from "./client";

export interface Habit {
  id: string;
  label: string;
  cadence: string;
  streak: number;
  doneToday: boolean;
  createdAt: string;
}

export type BlockCategory = "build" | "read" | "network" | "review";

export interface ScheduleBlock {
  id: string;
  day: number; // 0 = Mon … 6 = Sun
  label: string;
  category: BlockCategory;
  createdAt: string;
}

export const scheduleApi = {
  async listHabits(): Promise<Habit[]> {
    const { data } = await apiClient.get<Habit[]>("/api/v1/schedule/habits");
    return data;
  },

  async createHabit(input: { label: string; cadence?: string }): Promise<Habit> {
    const { data } = await apiClient.post<Habit>("/api/v1/schedule/habits", input);
    return data;
  },

  async updateHabit(id: string, input: { label?: string; cadence?: string }): Promise<Habit> {
    const { data } = await apiClient.patch<Habit>(`/api/v1/schedule/habits/${id}`, input);
    return data;
  },

  async toggleHabit(id: string): Promise<Habit> {
    const { data } = await apiClient.post<Habit>(`/api/v1/schedule/habits/${id}/toggle`);
    return data;
  },

  async deleteHabit(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/schedule/habits/${id}`);
  },

  async listBlocks(): Promise<ScheduleBlock[]> {
    const { data } = await apiClient.get<ScheduleBlock[]>("/api/v1/schedule/blocks");
    return data;
  },

  async createBlock(input: { day: number; label: string; category: BlockCategory }): Promise<ScheduleBlock> {
    const { data } = await apiClient.post<ScheduleBlock>("/api/v1/schedule/blocks", input);
    return data;
  },

  async deleteBlock(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/schedule/blocks/${id}`);
  },
};
