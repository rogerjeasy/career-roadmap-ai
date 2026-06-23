import { describe, expect, it } from "vitest";

import {
  OUTCOMES,
  OUTCOME_LABEL,
  STAGES,
  STATUS_LABEL,
  STATUS_TONE,
} from "@/lib/applications-meta";
import { LEVEL_LABEL, scoreTone } from "@/lib/assessments-meta";

describe("applications-meta", () => {
  it("orders pipeline stages saved → closed", () => {
    expect(STAGES).toEqual(["saved", "applied", "screening", "interview", "offer", "closed"]);
  });

  it("has a label and tone for every stage", () => {
    for (const stage of STAGES) {
      expect(STATUS_LABEL[stage]).toBeTruthy();
      expect(STATUS_TONE[stage]).toBeTruthy();
    }
  });

  it("has a label for every outcome", () => {
    for (const outcome of OUTCOMES) {
      expect(OUTCOME_LABEL[outcome]).toBeTruthy();
    }
  });
});

describe("assessments-meta scoreTone", () => {
  it.each([
    [70, "bg-green-soft text-green-2"],
    [85, "bg-green-soft text-green-2"],
    [45, "bg-gold-soft text-ink-2"],
    [69, "bg-gold-soft text-ink-2"],
    [44, "bg-terra-soft text-terra-2"],
    [0, "bg-terra-soft text-terra-2"],
  ])("maps score %i to its tone", (score, tone) => {
    expect(scoreTone(score)).toBe(tone);
  });

  it("labels each skill level", () => {
    expect(LEVEL_LABEL.beginner).toBe("Beginner");
    expect(LEVEL_LABEL.expert).toBe("Expert");
  });
});
