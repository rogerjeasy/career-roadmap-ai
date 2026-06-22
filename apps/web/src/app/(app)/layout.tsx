import type { ReactNode } from "react";
import { AppSidebar, AppMobileNav } from "@/components/layout/app-sidebar";
import { AppTopbar } from "@/components/layout/app-topbar";
import { CommandPalette } from "@/components/shared/command-palette";

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen bg-bg">
      <AppSidebar />
      <AppMobileNav />
      <div className="flex min-w-0 flex-1 flex-col">
        <AppTopbar />
        <main className="flex-1 overflow-x-hidden">
          {children}
        </main>
      </div>
      <CommandPalette />
    </div>
  );
}
