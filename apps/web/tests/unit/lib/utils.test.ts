import { describe, expect, it } from "vitest";

import { cn, fixMojibake, MOJIBAKE_MAP } from "@/lib/utils";

describe("cn", () => {
  it("joins truthy class names", () => {
    expect(cn("a", "b")).toBe("a b");
  });

  it("drops falsy values", () => {
    expect(cn("a", false, null, undefined, "b")).toBe("a b");
  });

  it("merges conflicting tailwind classes, last wins", () => {
    expect(cn("px-2", "px-4")).toBe("px-4");
    expect(cn("text-red-500", "text-blue-500")).toBe("text-blue-500");
  });

  it("supports conditional object syntax", () => {
    expect(cn("base", { active: true, hidden: false })).toBe("base active");
  });
});

describe("fixMojibake", () => {
  // Drive off the source-of-truth map so the test never re-types fragile
  // mojibake byte sequences (which would be re-encoded on save and drift).
  it.each(MOJIBAKE_MAP)("repairs %s → %s", (bad, good) => {
    expect(fixMojibake(bad)).toBe(good);
  });

  it("repairs an occurrence embedded in surrounding text", () => {
    const [bad, good] = MOJIBAKE_MAP[2]; // brain
    expect(fixMojibake(`${bad} Brain`)).toBe(`${good} Brain`);
  });

  it("repairs multiple occurrences in one string", () => {
    const [bad, good] = MOJIBAKE_MAP[4]; // waving hand
    expect(fixMojibake(`${bad} ${bad}`)).toBe(`${good} ${good}`);
  });

  it("leaves clean text untouched", () => {
    expect(fixMojibake("Hello, world")).toBe("Hello, world");
    expect(fixMojibake("🧠 already correct")).toBe("🧠 already correct");
  });
});
