"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  opportunitiesApi,
  type AlertsResponse,
  type JobMatch,
} from "@/lib/api/opportunities";
import { subscribeToAgentStream, type SSESubscription } from "@/lib/sse";
import type { AgentEvent } from "@/types/agent.types";
import { QUERY_KEYS } from "@/lib/constants";

export interface UseOpportunitiesResult {
  alerts: AlertsResponse | null;
  isLoadingAlerts: boolean;
  jobs: JobMatch[];
  isSearching: boolean;
  searchError: string | null;
  /** True once a search has completed (so we can distinguish "no results"). */
  hasSearched: boolean;
  runSearch: (params: { role?: string; location?: string }) => void;
}

/** Normalise a snake_case streamed JobMatchScore into the camelCase UI shape. */
function normaliseJob(raw: Record<string, unknown>, index: number): JobMatch {
  const listing = (raw.listing as Record<string, unknown>) ?? {};
  const num = (v: unknown): number | null => (typeof v === "number" ? v : null);
  const str = (v: unknown): string => (typeof v === "string" ? v : "");
  const arr = (v: unknown): string[] => (Array.isArray(v) ? (v as string[]) : []);
  return {
    id: str(listing.id) || `job-${index}`,
    title: str(listing.title),
    company: str(listing.company),
    location: str(listing.location),
    url: str(listing.url),
    remote: Boolean(listing.remote),
    seniorityLevel: str(listing.seniority_level) || null,
    salaryMin: num(listing.salary_min),
    salaryMax: num(listing.salary_max),
    matchScore: typeof raw.match_score === "number" ? raw.match_score : 0,
    skillOverlap: arr(raw.skill_overlap),
    missingSkills: arr(raw.missing_skills),
    matchReasons: arr(raw.match_reasons),
  };
}

export function useOpportunities(): UseOpportunitiesResult {
  const alertsQuery = useQuery({
    queryKey: QUERY_KEYS.opportunityAlerts,
    queryFn: opportunitiesApi.getAlerts,
    staleTime: 5 * 60 * 1000,
  });

  const [jobs, setJobs] = useState<JobMatch[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const subRef = useRef<SSESubscription | null>(null);

  useEffect(() => () => subRef.current?.close(), []);

  const handleEvent = useCallback((event: AgentEvent) => {
    if (event.event_type === "orchestration_completed") {
      const results = event.payload.agent_results as Record<string, unknown> | undefined;
      const opp = results?.opportunity as Record<string, unknown> | undefined;
      const high = (opp?.high_match_jobs ?? opp?.scored_jobs) as unknown[] | undefined;
      if (Array.isArray(high)) {
        setJobs(high.map((j, i) => normaliseJob(j as Record<string, unknown>, i)));
      }
      setIsSearching(false);
      setHasSearched(true);
    } else if (event.event_type === "orchestration_failed") {
      setSearchError("The search couldn't complete. Please try again.");
      setIsSearching(false);
      setHasSearched(true);
    }
  }, []);

  const runSearch = useCallback(
    (params: { role?: string; location?: string }) => {
      if (isSearching) return;
      setSearchError(null);
      setIsSearching(true);
      setJobs([]);

      opportunitiesApi
        .search(params)
        .then(({ sessionId }) => {
          subRef.current?.close();
          subRef.current = subscribeToAgentStream(
            sessionId,
            handleEvent,
            () => {
              setSearchError("Connection error. Please try again.");
              setIsSearching(false);
            },
            () => setIsSearching(false),
          );
        })
        .catch(() => {
          setSearchError("Couldn't start the search. Please try again.");
          setIsSearching(false);
        });
    },
    [isSearching, handleEvent],
  );

  return {
    alerts: alertsQuery.data ?? null,
    isLoadingAlerts: alertsQuery.isLoading,
    jobs,
    isSearching,
    searchError,
    hasSearched,
    runSearch,
  };
}
