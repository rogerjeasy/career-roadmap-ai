import { apiClient } from "./client";

export type PlanStatus = "done" | "current" | "future";

export interface WeekGoal {
  week: number;
  focus: string;
  goals: string[];
}

export interface MonthlyPlanSummary {
  id: string;
  monthId: string;
  month: string;
  theme: string;
  status: PlanStatus;
  goalsTotal: number;
  goalsDone: number;
}

export interface MonthlyPlan extends MonthlyPlanSummary {
  summary: string;
  weeks: WeekGoal[];
  createdAt: string;
}

export interface MonthlyPlanInput {
  monthId: string;
  month: string;
  theme?: string;
  summary?: string;
  status?: PlanStatus;
  weeks?: WeekGoal[];
  goalsTotal?: number;
  goalsDone?: number;
}

export const monthlyPlanApi = {
  async list(): Promise<MonthlyPlanSummary[]> {
    const { data } = await apiClient.get<MonthlyPlanSummary[]>("/api/v1/monthly-plans");
    return data;
  },

  async get(monthId: string): Promise<MonthlyPlan> {
    const { data } = await apiClient.get<MonthlyPlan>(`/api/v1/monthly-plans/${monthId}`);
    return data;
  },

  async upsert(input: MonthlyPlanInput): Promise<MonthlyPlan> {
    const { data } = await apiClient.put<MonthlyPlan>("/api/v1/monthly-plans", input);
    return data;
  },

  async remove(monthId: string): Promise<void> {
    await apiClient.delete(`/api/v1/monthly-plans/${monthId}`);
  },
};
