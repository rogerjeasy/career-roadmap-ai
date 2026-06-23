/**
 * Global Vitest setup — runs once before every test file.
 *
 * - Registers jest-dom matchers (`toBeInTheDocument`, `toHaveClass`, …).
 * - Unmounts React trees and clears mocks after each test so suites stay isolated.
 * - Stubs browser APIs jsdom does not implement (matchMedia) that UI code touches.
 */
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// jsdom lacks matchMedia — provide a no-op implementation for components/hooks
// that read responsive media queries.
if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = (query: string): MediaQueryList =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }) as unknown as MediaQueryList;
}
