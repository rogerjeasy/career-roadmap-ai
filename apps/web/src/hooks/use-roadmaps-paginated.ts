import { useInfiniteQuery } from "@tanstack/react-query";
import { roadmapApi, type RoadmapSummary } from "@/lib/api/roadmap";
import { QUERY_KEYS } from "@/lib/constants";

export interface UseRoadmapsPaginatedResult {
  roadmaps: RoadmapSummary[];
  fetchNextPage: () => void;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
}

/**
 * TanStack Query infinite-scroll hook for roadmap history.
 *
 * Each page is fetched from GET /api/v1/roadmaps/paginated using cursor-based
 * keyset pagination (ISO-8601 created_at timestamp as cursor). Roadmaps are
 * ordered newest-first; the next page starts immediately after the last item
 * of the current page.
 */
export function useRoadmapsPaginated(limit = 10): UseRoadmapsPaginatedResult {
  const query = useInfiniteQuery({
    queryKey: QUERY_KEYS.roadmapListInfinite,
    queryFn: ({ pageParam }) =>
      roadmapApi.listPaginated({
        limit,
        cursor: pageParam as string | undefined,
      }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.nextCursor ?? undefined,
  });

  const roadmaps: RoadmapSummary[] = query.data
    ? query.data.pages.flatMap((page) => page.items)
    : [];

  return {
    roadmaps,
    fetchNextPage: query.fetchNextPage,
    hasNextPage: query.hasNextPage,
    isFetchingNextPage: query.isFetchingNextPage,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
  };
}
