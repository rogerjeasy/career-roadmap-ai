import { apiClient } from "./client";

export interface Habit {
  id: string;
  label: string;
  cadence: string;
  streak: number;
  doneToday: boolean;
  createdAt: string;
  /** Recent completion history (ISO `YYYY-MM-DD`), newest last. */
  completedDates: string[];
  /** Completion flags for the current week, Monday … Sunday. */
  weekCompletions: boolean[];
}

export type BlockCategory = "build" | "read" | "network" | "review";

export interface ScheduleBlock {
  id: string;
  day: number; // 0 = Mon … 6 = Sun
  label: string;
  category: BlockCategory;
  createdAt: string;
}

export type BudgetTone = "green" | "ink" | "terra" | "gold";

export interface BudgetCategory {
  id: BlockCategory;
  label: string;
  hoursLogged: number;
  hoursTarget: number;
  tone: BudgetTone;
}

export interface Budget {
  weekStart: string; // ISO `YYYY-MM-DD`, Monday of the current week
  categories: BudgetCategory[];
}

export interface BudgetTargetsInput {
  build: number;
  read: number;
  network: number;
  review: number;
}

export interface TimeLog {
  id: string;
  category: BlockCategory;
  hours: number;
  loggedOn: string; // ISO `YYYY-MM-DD`
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

  async getBudget(): Promise<Budget> {
    const { data } = await apiClient.get<Budget>("/api/v1/schedule/budget");
    return data;
  },

  async setBudgetTargets(input: BudgetTargetsInput): Promise<Budget> {
    const { data } = await apiClient.put<Budget>("/api/v1/schedule/budget/targets", input);
    return data;
  },

  async listTimeLogs(): Promise<TimeLog[]> {
    const { data } = await apiClient.get<TimeLog[]>("/api/v1/schedule/time-logs");
    return data;
  },

  async logTime(input: { category: BlockCategory; hours: number; loggedOn?: string }): Promise<TimeLog> {
    const { data } = await apiClient.post<TimeLog>("/api/v1/schedule/time-logs", input);
    return data;
  },

  async deleteTimeLog(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/schedule/time-logs/${id}`);
  },
};
