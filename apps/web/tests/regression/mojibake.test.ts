import { describe, expect, it } from "vitest";

import { fixMojibake, MOJIBAKE_MAP } from "@/lib/utils";

/**
 * REGRESSION: emoji authored/saved through Windows editors land in source and
 * content as Windows-1252 mojibake (e.g. "brain" emoji shows as garbled bytes).
 * fixMojibake is the runtime safety-net; every mapping it ships must keep working
 * so user-facing copy never shows garbled bytes again.
 *
 * The cases are driven off MOJIBAKE_MAP itself so this file never re-types the
 * fragile byte sequences (which would be re-encoded on save and silently drift).
 */
describe("mojibake regression", () => {
  it.each(MOJIBAKE_MAP)("repairs mapping %#", (bad, good) => {
    expect(fixMojibake(bad)).toBe(good);
  });

  it("repairs mojibake embedded mid-sentence", () => {
    const [bad, good] = MOJIBAKE_MAP[5]; // bar chart
    expect(fixMojibake(`Your roadmap ${bad} is ready`)).toBe(`Your roadmap ${good} is ready`);
  });

  it("is idempotent on already-clean strings", () => {
    const clean = "Build something great 🚀";
    expect(fixMojibake(clean)).toBe(clean);
  });

  it("every map value is a real emoji, not more mojibake", () => {
    for (const [, good] of MOJIBAKE_MAP) {
      // mojibake artefacts contain the tell-tale "Ã"/"ð" lead bytes
      expect(good).not.toMatch(/[ðÃ]/);
    }
  });
});
