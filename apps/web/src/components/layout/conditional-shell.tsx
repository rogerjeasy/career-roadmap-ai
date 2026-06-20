"use client";

import { usePathname } from "next/navigation";
import { Header } from "@/components/layout/header";
import { Footer } from "@/components/layout/footer";

const AUTH_ROUTES = ["/login", "/register", "/forgot-password", "/onboarding"];

// App routes use their own sidebar+topbar shell — skip the marketing chrome
const APP_ROUTE_PREFIXES = [
  "/dashboard",
  "/analytics",
  "/roadmap",
  "/roadmap-options",
  "/skill-graph",
  "/schedule",
  "/monthly-plan",
  "/progress",
  "/cv-analysis",
  "/applications",
  "/discovery",
  "/market",
  "/localisation",
  "/autopilot",
  "/career-twin",
  "/networking",
  "/books",
  "/evidence",
  "/credentials",
  "/learning",
  "/open-source",
  "/storytelling",
  "/cohorts",
  "/mentorship",
  "/outreach",
  "/wellness",
  "/portfolio",
  "/newsletter",
  "/opportunities",
  "/negotiation",
  "/interview",
  "/coach",
  "/settings",
  "/developer",
  "/help",
];

export function ConditionalShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isAuthPage = AUTH_ROUTES.includes(pathname);
  const isAppPage = APP_ROUTE_PREFIXES.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`),
  );

  if (isAuthPage || isAppPage) {
    return <>{children}</>;
  }

  return (
    <>
      <Header />
      {children}
      <Footer />
    </>
  );
}