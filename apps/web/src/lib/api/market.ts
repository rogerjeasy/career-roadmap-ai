import { apiClient } from "./client";
import type { MarketSignal, SalaryBenchmark, TrendingSkill } from "@/types/market.types";

export interface MarketOverview {
  summary: string;
  signals: MarketSignal[];
  salaryBenchmark: SalaryBenchmark | null;
  trendingSkills: TrendingSkill[];
  hasData: boolean;
}

export const marketApi = {
  async getOverview(): Promise<MarketOverview> {
    const { data } = await apiClient.get<MarketOverview>("/api/v1/market/overview");
    return data;
  },
};
