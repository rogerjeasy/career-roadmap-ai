export type MarketSentiment = "positive" | "neutral" | "negative";

export interface MarketSignal {
  id: string;
  title: string;
  summary: string;
  source: string;
  sentiment: MarketSentiment;
  tag: string;
  timeLabel: string;
}

export interface SalaryBenchmark {
  role: string;
  location: string;
  currency: string;
  p25: number;
  p50: number;
  p75: number;
}

export interface TrendingSkill {
  name: string;
  /** 0–100 relative demand index. */
  demandIndex: number;
  /** Percentage change vs. the previous period. */
  deltaPct: number;
}
