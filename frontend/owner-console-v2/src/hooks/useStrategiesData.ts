import { useState, useMemo, useCallback } from 'react';
import { useQuery, useInfiniteQuery } from '@tanstack/react-query';
import {
  fetchStrategies,
  strategiesQueryKey,
  fetchStrategyTickets,
  strategyTicketsInfiniteQueryKey,
  fetchStrategyObservations,
  strategyObservationsInfiniteQueryKey,
} from '../api/strategiesApi.ts';
import { fetchControls, controlsQueryKey } from '../api/controlsApi.ts';
import { enrichStrategyVersion } from '../mapping/strategyMapping.ts';
import { evaluateStrategyAdmissionHealth } from '../mapping/admissionHealthMapping.ts';
import type {
  StrategyViewMode,
  EnrichedStrategyVersion,
  StrategyTicketExitPath,
  StrategyObservationFirstPath,
  StrategyTicketListItem,
  StrategyObservationListItem,
  StrategyControlView,
} from '../types/strategies.ts';
import type { StrategyAdmissionHealth } from '../types/controls.ts';

export function useStrategiesData() {
  const [view, setView] = useState<StrategyViewMode>('current');

  const strategiesQuery = useQuery({
    queryKey: strategiesQueryKey({ view }),
    queryFn: () => fetchStrategies({ view }),
    staleTime: 30_000,
    retry: false,
  });

  const controlsQuery = useQuery({
    queryKey: controlsQueryKey,
    queryFn: fetchControls,
    staleTime: 15_000,
    retry: false,
  });

  const rawSummaries = useMemo(() => {
    return strategiesQuery.data?.data?.items ?? [];
  }, [strategiesQuery.data]);

  const runtimeMap = useMemo(() => {
    const map = new Map<
      string,
      {
        control: StrategyControlView;
        admissionHealth: StrategyAdmissionHealth;
        activeTicketCount: number;
        firstBlocker: string | null;
      }
    >();

    const controls = controlsQuery.data;
    if (!controls) return map;

    const capacityCounts = controls.account_capacity?.strategy_side_active_counts ?? {};

    controls.strategies?.forEach((ctrl) => {
      let activeTicketCount = 0;
      Object.entries(capacityCounts).forEach(([scope, count]) => {
        if (scope.startsWith(`${ctrl.strategy_group_id}:`)) {
          activeTicketCount += Number(count) || 0;
        }
      });

      const isRetired = ctrl.strategy_group_id === 'SOR-001';
      const admissionHealth = evaluateStrategyAdmissionHealth({
        strategy: ctrl,
        globalEntry: controls.global_entry,
        runtimeAuthority: controls.runtime_entry_authority,
        capacity: controls.account_capacity,
        isRetired,
      });

      const firstBlocker =
        admissionHealth.status === 'blocked'
          ? admissionHealth.summary
          : (controls.global_entry?.first_blocker ?? null);

      map.set(ctrl.strategy_group_id, {
        control: ctrl,
        admissionHealth,
        activeTicketCount,
        firstBlocker,
      });
    });

    return map;
  }, [controlsQuery.data]);

  const enrichedStrategies = useMemo<EnrichedStrategyVersion[]>(() => {
    return rawSummaries.map((summary) => {
      const runtime = runtimeMap.get(summary.strategy_group_id);
      return enrichStrategyVersion(summary, runtime?.control, {
        firstBlocker: runtime?.firstBlocker,
        activeTicketCount: runtime?.activeTicketCount,
        admissionHealth: runtime?.admissionHealth,
      });
    });
  }, [rawSummaries, runtimeMap]);

  const refetch = useCallback(async () => {
    await Promise.all([strategiesQuery.refetch(), controlsQuery.refetch()]);
  }, [strategiesQuery, controlsQuery]);

  return {
    strategies: enrichedStrategies,
    rawSummaries,
    view,
    setView,
    isLoading: strategiesQuery.isLoading || controlsQuery.isLoading,
    isFetching: strategiesQuery.isFetching || controlsQuery.isFetching,
    isError: strategiesQuery.isError || controlsQuery.isError,
    error: strategiesQuery.error || controlsQuery.error,
    freshness: strategiesQuery.data?.freshness ?? 'unavailable',
    sourceWatermark: strategiesQuery.data?.source_watermark ?? null,
    fromMs: strategiesQuery.data?.data?.from_ms ?? null,
    toMs: strategiesQuery.data?.data?.to_ms ?? null,
    refetch,
  };
}

export function useStrategyTicketsData(strategyVersionId?: string | null) {
  const [scope, setScope] = useState<'natural' | 'all'>('natural');
  const [exitPath, setExitPath] = useState<StrategyTicketExitPath | null>(null);

  const queryParams = useMemo(
    () => ({
      strategy_version_id: strategyVersionId ?? '',
      scope,
      exit_path: exitPath,
      limit: 50,
    }),
    [strategyVersionId, scope, exitPath]
  );

  const query = useInfiniteQuery({
    queryKey: strategyTicketsInfiniteQueryKey(queryParams),
    queryFn: ({ pageParam }) =>
      fetchStrategyTickets({
        ...queryParams,
        cursor: pageParam ?? undefined,
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.data?.next_cursor ?? null,
    enabled: Boolean(strategyVersionId),
    staleTime: 15_000,
    retry: false,
  });

  const rawItems = useMemo<StrategyTicketListItem[]>(() => {
    return query.data?.pages.flatMap((page) => page.data?.items ?? []) ?? [];
  }, [query.data]);

  const fetchNextPage = useCallback(async () => {
    if (query.hasNextPage && !query.isFetchingNextPage) {
      await query.fetchNextPage();
    }
  }, [query]);

  return {
    items: rawItems,
    scope,
    setScope,
    exitPath,
    setExitPath,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isFetchingNextPage: query.isFetchingNextPage,
    hasNextPage: Boolean(query.hasNextPage),
    isFetchNextPageError: query.isFetchNextPageError,
    error: query.error,
    fetchNextPage,
    refetch: query.refetch,
  };
}

export function useStrategyObservationsData(strategyVersionId?: string | null) {
  const [firstPath, setFirstPath] = useState<StrategyObservationFirstPath | null>(null);

  const queryParams = useMemo(
    () => ({
      strategy_version_id: strategyVersionId ?? '',
      first_path: firstPath,
      limit: 50,
    }),
    [strategyVersionId, firstPath]
  );

  const query = useInfiniteQuery({
    queryKey: strategyObservationsInfiniteQueryKey(queryParams),
    queryFn: ({ pageParam }) =>
      fetchStrategyObservations({
        ...queryParams,
        cursor: pageParam ?? undefined,
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.data?.next_cursor ?? null,
    enabled: Boolean(strategyVersionId),
    staleTime: 15_000,
    retry: false,
  });

  const rawItems = useMemo<StrategyObservationListItem[]>(() => {
    return query.data?.pages.flatMap((page) => page.data?.items ?? []) ?? [];
  }, [query.data]);

  const fetchNextPage = useCallback(async () => {
    if (query.hasNextPage && !query.isFetchingNextPage) {
      await query.fetchNextPage();
    }
  }, [query]);

  return {
    items: rawItems,
    firstPath,
    setFirstPath,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isFetchingNextPage: query.isFetchingNextPage,
    hasNextPage: Boolean(query.hasNextPage),
    isFetchNextPageError: query.isFetchNextPageError,
    error: query.error,
    fetchNextPage,
    refetch: query.refetch,
  };
}
