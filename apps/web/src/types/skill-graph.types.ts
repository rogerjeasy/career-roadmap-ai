/**
 * Skill Graph view model.
 *
 * Derived entirely from real data — the user's profile skills (held) and their
 * roadmap's per-phase `skillsToGain` (target), reconciled against roadmap
 * progress. No skill data is invented; a skill only appears because it is either
 * something the user listed or something a roadmap phase targets.
 */

export type SkillStatus = "have" | "acquired" | "learning" | "planned";

export type PhaseStatus = "done" | "current" | "future";

export interface SkillNode {
  name: string;
  status: SkillStatus;
  /** 1-based phase number a target skill belongs to; null for foundation skills. */
  phaseNumber: number | null;
}

export interface PhaseSkillTrack {
  id: string;
  number: number;
  title: string;
  status: PhaseStatus;
  skills: SkillNode[];
  /** Skills in this phase already held or acquired. */
  acquiredCount: number;
}

export interface SkillGraphStats {
  /** Distinct target skills across all phases. */
  targetTotal: number;
  /** Target skills already held or acquired through a completed phase. */
  acquired: number;
  /** Target skills being built in the current phase. */
  learning: number;
  /** Target skills not yet started. */
  gaps: number;
  /** acquired / targetTotal, as a 0–100 integer. */
  readinessPercent: number;
  /** Held skills that sit outside the roadmap's target set. */
  foundationCount: number;
}

export interface SkillGraphView {
  isLoading: boolean;
  hasRoadmap: boolean;
  targetRole: string | null;
  /** Held skills not targeted by any phase — the user's existing base. */
  foundationSkills: SkillNode[];
  phases: PhaseSkillTrack[];
  stats: SkillGraphStats;
}
