export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws";

export const ROUTES = {
  home: "/",
  login: "/login",
  register: "/register",
  forgotPassword: "/forgot-password",
  onboarding: "/onboarding",
  dashboard: "/dashboard",
  roadmap: "/roadmap",
  roadmapGenerate: "/roadmap/generate",
  cvAnalysis: "/cv-analysis",
  coach: "/coach",
  market: "/market",
  progress: "/progress",
  schedule: "/schedule",
  networking: "/networking",
  opportunities: "/opportunities",
  monthlyPlan: "/monthly-plan",
  books: "/books",
  settings: "/settings",
  settingsProfile: "/settings/profile",
  settingsIntegrations: "/settings/integrations",
} as const;

export const QUERY_KEYS = {
  me: ["user", "me"] as const,
  roadmap: (id?: string) => ["roadmap", id] as const,
  roadmapList: ["roadmap", "list"] as const,
  roadmapListInfinite: ["roadmap", "list", "infinite"] as const,
  notifications: ["notifications"] as const,
  market: ["market"] as const,
  session: ["session"] as const,
  opportunityAlerts: ["opportunity", "alerts"] as const,
} as const;
