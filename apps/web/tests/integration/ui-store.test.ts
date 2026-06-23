import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { useUIStore } from "@/store/ui.store";

/**
 * Exercises the Zustand UI store the way components consume it (via the hook),
 * including the persist middleware wiring.
 */
describe("useUIStore", () => {
  beforeEach(() => {
    // Reset transient + persisted state between tests.
    act(() => {
      useUIStore.setState({
        sidebarCollapsed: false,
        commandOpen: false,
        mobileNavOpen: false,
      });
    });
    localStorage.clear();
  });

  it("toggles the sidebar", () => {
    const { result } = renderHook(() => useUIStore());
    expect(result.current.sidebarCollapsed).toBe(false);
    act(() => result.current.toggleSidebar());
    expect(result.current.sidebarCollapsed).toBe(true);
    act(() => result.current.toggleSidebar());
    expect(result.current.sidebarCollapsed).toBe(false);
  });

  it("sets sidebar collapsed explicitly", () => {
    const { result } = renderHook(() => useUIStore());
    act(() => result.current.setSidebarCollapsed(true));
    expect(result.current.sidebarCollapsed).toBe(true);
  });

  it("opens and toggles the command palette", () => {
    const { result } = renderHook(() => useUIStore());
    act(() => result.current.setCommandOpen(true));
    expect(result.current.commandOpen).toBe(true);
    act(() => result.current.toggleCommand());
    expect(result.current.commandOpen).toBe(false);
  });

  it("controls the mobile nav drawer", () => {
    const { result } = renderHook(() => useUIStore());
    act(() => result.current.setMobileNavOpen(true));
    expect(result.current.mobileNavOpen).toBe(true);
  });

  it("persists only the sidebar preference (partialize)", () => {
    const { result } = renderHook(() => useUIStore());
    act(() => {
      result.current.setSidebarCollapsed(true);
      result.current.setCommandOpen(true);
    });
    const persisted = JSON.parse(localStorage.getItem("ui-store") ?? "{}");
    expect(persisted.state).toEqual({ sidebarCollapsed: true });
    expect(persisted.state.commandOpen).toBeUndefined();
  });
});
