import type { SkillLevel } from "@/lib/api/assessments";

export const LEVEL_LABEL: Record<SkillLevel, string> = {
  beginner: "Beginner",
  intermediate: "Intermediate",
  advanced: "Advanced",
  expert: "Expert",
};

export const LEVEL_TONE: Record<SkillLevel, string> = {
  beginner: "bg-bg-2 text-ink-2",
  intermediate: "bg-gold-soft text-ink-2",
  advanced: "bg-green-soft text-green-2",
  expert: "bg-green text-bg",
};

export function scoreTone(score: number): string {
  if (score >= 70) return "bg-green-soft text-green-2";
  if (score >= 45) return "bg-gold-soft text-ink-2";
  return "bg-terra-soft text-terra-2";
}
