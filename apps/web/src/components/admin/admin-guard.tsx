"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/auth.store";
import { ROUTES } from "@/lib/constants";
import { LoadingSpinner } from "@/components/shared/loading-spinner";

export interface AdminGuardProps {
  children: React.ReactNode;
}

/**
 * Client-side gate for the admin area. Authorization is always enforced again
 * on the server (every admin endpoint depends on `require_admin`); this just
 * keeps non-admins from seeing the shell and redirects them sensibly.
 */
export function AdminGuard({ children }: AdminGuardProps) {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const isLoading = useAuthStore((s) => s.isLoading);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const isAdmin = user?.role === "admin" || user?.role === "superadmin";

  useEffect(() => {
    if (isLoading) return;
    if (!isAuthenticated) {
      router.replace(ROUTES.login);
    } else if (!isAdmin) {
      router.replace(ROUTES.dashboard);
    }
  }, [isLoading, isAuthenticated, isAdmin, router]);

  if (isLoading || !isAuthenticated || !isAdmin) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg">
        <LoadingSpinner size="lg" label="Checking access…" />
      </div>
    );
  }

  return <>{children}</>;
}
