"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getSession } from "@/lib/api/session";
import { QUERY_KEYS } from "@/lib/constants";
import { fixMojibake } from "@/lib/utils";
import { useRoadmap } from "@/hooks/use-roadmap";
import { useRoadmapProgress } from "@/hooks/use-roadmap-progress";
import type {
  PhaseSkillTrack,
  PhaseStatus,
  SkillGraphStats,
  SkillGraphView,
  SkillNode,
  SkillStatus,
} from "@/types/skill-graph.types";

const norm = (s: string): string => s.trim().toLowerCase();

const EMPTY_STATS: SkillGraphStats = {
  targetTotal: 0,
  acquired: 0,
  learning: 0,
  gaps: 0,
  readinessPercent: 0,
  foundationCount: 0,
};

/**
 * Builds the Skill Graph from the user's roadmap and profile.
 *
 * Target skills come from each phase's `skillsToGain`; held skills from the
 * session profile. A target skill's status is resolved against roadmap progress:
 * already held → "have"; in a fully-complete phase → "acquired"; in the active
 * phase → "learning"; otherwise → "planned". A skill is attributed to the
 * earliest phase that targets it, so it appears once.
 */
export function useSkillGraph(): SkillGraphView {
  const sessionQuery = useQuery({
    queryKey: QUERY_KEYS.session,
    queryFn: getSession,
    staleTime: 60 * 1000,
  });

  const { roadmap, isLoading: roadmapLoading } = useRoadmap();
  const roadmapId = roadmap?.id ?? null;
  const { completedKeys } = useRoadmapProgress(roadmapId);

  const session = sessionQuery.data ?? null;
  const targetRole = session?.userProfileContext?.targetRole
    ? fixMojibake(session.userProfileContext.targetRole)
    : null;

  const heldList = useMemo(
    () =>
      (session?.userProfileContext?.skills ?? [])
        .map((s) => fixMojibake(s).trim())
        .filter(Boolean),
    [session],
  );

  const { phases, foundationSkills, stats } = useMemo(() => {
    if (!roadmap) {
      return {
        phases: [] as PhaseSkillTrack[],
        foundationSkills: [] as SkillNode[],
        stats: EMPTY_STATS,
      };
    }

    const heldSet = new Set(heldList.map(norm));
    const sorted = [...roadmap.phases].sort((a, b) => a.order - b.order);

    const isPhaseDone = (phaseId: string, milestoneCount: number): boolean => {
      if (milestoneCount === 0) return false;
      for (let m = 0; m < milestoneCount; m += 1) {
        if (!completedKeys.has(`${phaseId}:${m}`)) return false;
      }
      return true;
    };

    // Phase status mirrors the dashboard: any fully-complete phase is "done";
    // the first not-yet-complete phase is "current"; the rest are "future".
    const firstIncompleteIdx = sorted.findIndex(
      (p) => !isPhaseDone(p.id, p.milestones.length),
    );
    const phaseStatuses: PhaseStatus[] = sorted.map((p, idx) => {
      if (isPhaseDone(p.id, p.milestones.length)) return "done";
      return idx === firstIncompleteIdx ? "current" : "future";
    });

    const seen = new Set<string>(); // dedupe target skills; earliest phase wins
    const tracks: PhaseSkillTrack[] = sorted.map((p, i) => {
      const number = p.order || i + 1;
      const phaseStatus = phaseStatuses[i];
      const skills: SkillNode[] = [];

      for (const raw of p.skillsToGain) {
        const name = fixMojibake(raw).trim();
        if (!name) continue;
        const key = norm(name);
        if (seen.has(key)) continue;
        seen.add(key);

        let status: SkillStatus;
        if (heldSet.has(key)) status = "have";
        else if (phaseStatus === "done") status = "acquired";
        else if (phaseStatus === "current") status = "learning";
        else status = "planned";

        skills.push({ name, status, phaseNumber: number });
      }

      const acquiredCount = skills.filter(
        (s) => s.status === "have" || s.status === "acquired",
      ).length;

      return {
        id: p.id,
        number,
        title: fixMojibake(p.title),
        status: phaseStatus,
        skills,
        acquiredCount,
      };
    });

    // Foundation = held skills the roadmap never targets (deduped, original case).
    const foundationSeen = new Set<string>();
    const foundation: SkillNode[] = [];
    for (const s of heldList) {
      const key = norm(s);
      if (seen.has(key) || foundationSeen.has(key)) continue;
      foundationSeen.add(key);
      foundation.push({ name: s, status: "have", phaseNumber: null });
    }

    const allTarget = tracks.flatMap((t) => t.skills);
    const targetTotal = allTarget.length;
    const acquired = allTarget.filter(
      (s) => s.status === "have" || s.status === "acquired",
    ).length;
    const learning = allTarget.filter((s) => s.status === "learning").length;
    const gaps = allTarget.filter((s) => s.status === "planned").length;

    return {
      phases: tracks,
      foundationSkills: foundation,
      stats: {
        targetTotal,
        acquired,
        learning,
        gaps,
        readinessPercent:
          targetTotal > 0 ? Math.round((acquired / targetTotal) * 100) : 0,
        foundationCount: foundation.length,
      },
    };
  }, [roadmap, heldList, completedKeys]);

  return {
    isLoading: sessionQuery.isLoading || roadmapLoading,
    hasRoadmap: Boolean(roadmap),
    targetRole,
    foundationSkills,
    phases,
    stats,
  };
}
