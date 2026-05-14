"use client";

import { useQuery } from "@tanstack/react-query";
import { userApi } from "@/lib/api/user";
import { opportunitiesApi } from "@/lib/api/opportunities";
import { getSession } from "@/lib/api/session";
import { QUERY_KEYS } from "@/lib/constants";

export function useDashboard() {
  const userQuery = useQuery({
    queryKey: QUERY_KEYS.me,
    queryFn: userApi.getMe,
    staleTime: 5 * 60 * 1000,
  });

  const sessionQuery = useQuery({
    queryKey: QUERY_KEYS.session,
    queryFn: getSession,
    staleTime: 60 * 1000,
  });

  const opportunityAlertsQuery = useQuery({
    queryKey: QUERY_KEYS.opportunityAlerts,
    queryFn: opportunitiesApi.getAlerts,
    staleTime: 5 * 60 * 1000,
  });

  const isLoading =
    userQuery.isLoading || sessionQuery.isLoading || opportunityAlertsQuery.isLoading;

  return {
    user: userQuery.data ?? null,
    session: sessionQuery.data ?? null,
    opportunityAlerts: opportunityAlertsQuery.data ?? null,
    isLoading,
    userError: userQuery.error,
    sessionError: sessionQuery.error,
  };
}
