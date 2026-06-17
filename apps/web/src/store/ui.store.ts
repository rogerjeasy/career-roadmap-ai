import { create } from "zustand";
import { persist } from "zustand/middleware";

interface UIState {
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  /** Global command palette (⌘K) visibility — transient, never persisted. */
  commandOpen: boolean;
  setCommandOpen: (open: boolean) => void;
  toggleCommand: () => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
      commandOpen: false,
      setCommandOpen: (commandOpen) => set({ commandOpen }),
      toggleCommand: () => set((s) => ({ commandOpen: !s.commandOpen })),
    }),
    {
      name: "ui-store",
      // Only the sidebar preference persists; palette state stays in-memory.
      partialize: (s) => ({ sidebarCollapsed: s.sidebarCollapsed }),
    }
  )
);