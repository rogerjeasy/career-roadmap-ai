import { describe, expect, it } from "vitest";

import { formatDate, formatDateTime, formatRelative } from "@/lib/date";

describe("formatDate", () => {
  it("formats an ISO string with the default pattern", () => {
    expect(formatDate("2026-06-01T00:00:00.000Z")).toBe("Jun 1, 2026");
  });

  it("accepts a Date instance", () => {
    expect(formatDate(new Date(2026, 5, 1))).toBe("Jun 1, 2026");
  });

  it("honours a custom date-fns pattern", () => {
    expect(formatDate("2026-06-01", "yyyy/MM/dd")).toBe("2026/06/01");
  });

  it("returns an empty string for unparseable input", () => {
    expect(formatDate("not-a-date")).toBe("");
  });
});

describe("formatDateTime", () => {
  it("includes time with the · separator", () => {
    const out = formatDateTime(new Date(2026, 5, 1, 14, 30));
    expect(out).toBe("Jun 1, 2026 · 14:30");
  });
});

describe("formatRelative", () => {
  it("produces a suffixed relative string for a past date", () => {
    const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000);
    expect(formatRelative(oneHourAgo)).toMatch(/ago$/);
  });

  it("returns an empty string for invalid input", () => {
    expect(formatRelative("garbage")).toBe("");
  });
});
