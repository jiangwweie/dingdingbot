import { ApiError } from '../api/errors';
import { usePerformance } from './usePerformance';
import { useState, useEffect, useMemo, useCallback } from 'react';
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

export interface UseStrategiesDataOptions {
  exchange_instrument_id?:string;position_side?:'long'|'short';
  strategy_group_id?:string;strategy_version_id?:string;
  view?: StrategyViewMode;
  exit_scope?: import('../api/performanceApi').ExitScope;
  from_ms?: number;
  to_ms?: number;
}

export function useStrategiesData(options?: UseStrategiesDataOptions) {
  const [internalView, setInternalView] = useState<StrategyViewMode>('all');

  const view = options?.view ?? internalView;
  const setView = useCallback((nextView: StrategyViewMode) => {
    setInternalView(nextView);
  }, []);

  const from_ms = options?.from_ms;
  const to_ms = options?.to_ms;

  const strategiesQuery = useQuery({
    queryKey: strategiesQueryKey({ view, from_ms, to_ms,exit_scope:options?.exit_scope,strategy_group_id:options?.strategy_group_id,strategy_version_id:options?.strategy_version_id,exchange_instrument_id:options?.exchange_instrument_id,position_side:options?.position_side }),
    queryFn: () => fetchStrategies({ view, from_ms, to_ms,exit_scope:options?.exit_scope,strategy_group_id:options?.strategy_group_id,strategy_version_id:options?.strategy_version_id,exchange_instrument_id:options?.exchange_instrument_id,position_side:options?.position_side }),
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
      const runtime = summary.is_current ? runtimeMap.get(summary.strategy_group_id) : undefined;
      const enriched = enrichStrategyVersion(summary, runtime?.control, {
        firstBlocker: runtime?.firstBlocker,
        activeTicketCount: runtime?.activeTicketCount,
        admissionHealth: runtime?.admissionHealth,
      });
      if (!summary.is_current) enriched.runtimeStatusLabel = '历史版本 · 不归属当前运行占用';
      return enriched;
    });
  }, [rawSummaries, runtimeMap]);

  const refetch = useCallback(async () => {
    await Promise.all([strategiesQuery.refetch(), controlsQuery.refetch()]);
  }, [strategiesQuery, controlsQuery]);

  return {
    performance:strategiesQuery.data?.data.performance ?? null,
    strategies: enrichedStrategies,
    liveActiveTicketCount: controlsQuery.data?.account_capacity?.active_ticket_count ?? null,
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

export interface UseStrategyTicketsOptions {
  exit_scope?:import('../api/performanceApi').ExitScope;
  from_ms?: number;
  to_ms?: number;
  scope?: 'natural' | 'all';
  exit_path?: StrategyTicketExitPath | null;
}

export function useStrategyTicketsData(
  strategyVersionId?: string | null,
  options?: UseStrategyTicketsOptions
) {
  const [internalScope, setInternalScope] = useState<'natural' | 'all'>('all');
  const [internalExitPath, setInternalExitPath] = useState<StrategyTicketExitPath | null>(null);
  const [internalWindowEnd, setInternalWindowEnd] = useState(() => Date.now());

  useEffect(() => {
    if (options && 'scope' in options) {
      setInternalScope(options.scope ?? 'all');
    }
  }, [options?.scope]);

  useEffect(() => {
    if (options && 'exit_path' in options) {
      setInternalExitPath(options.exit_path ?? null);
    }
  }, [options?.exit_path]);

  const scope =
    options && 'scope' in options
      ? (options.scope ?? 'all')
      : internalScope;
  const setScope = useCallback((newScope: 'natural' | 'all') => {
    setInternalScope(newScope);
  }, []);

  const exitPath =
    options && 'exit_path' in options
      ? (options.exit_path ?? null)
      : internalExitPath;
  const setExitPath = useCallback((newExitPath: StrategyTicketExitPath | null) => {
    setInternalExitPath(newExitPath);
  }, []);

  const windowEnd = options?.to_ms ?? internalWindowEnd;
  const windowStart = options?.from_ms ?? (windowEnd - 30 * 86_400_000);

  // Defensive guard: controlled_exit is illegal in natural scope
  const effectiveExitPath = useMemo(() => {
    if (scope === 'natural' && exitPath === 'controlled_exit') {
      return null;
    }
    return exitPath;
  }, [scope, exitPath]);

  const queryParams = useMemo(
    () => ({
      strategy_version_id: strategyVersionId ?? '',
      from_ms: windowStart,
      to_ms: windowEnd,
      scope,
      exit_path: effectiveExitPath,
      limit: 50,
    }),
    [strategyVersionId, windowStart, windowEnd, scope, effectiveExitPath]
  );

  const income=usePerformance({from_ms:windowStart,to_ms:windowEnd,strategy_version_id:strategyVersionId??undefined,exit_scope:options?.exit_scope});
  const query = useInfiniteQuery({
    queryKey: strategyTicketsInfiniteQueryKey({...queryParams,snapshot:income.data?.data.snapshot_id,exit_scope:options?.exit_scope}),
    queryFn: ({ pageParam }) =>
      fetchStrategyTickets({
        ...queryParams,snapshot:income.data?.data.snapshot_id,exit_scope:options?.exit_scope,
        cursor: pageParam ?? undefined,
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.data?.next_cursor ?? null,
    enabled: Boolean(strategyVersionId)&&!!income.data&&!income.isError,
    staleTime: 15_000,
    retry: false,
  });

  const rawItems = useMemo<StrategyTicketListItem[]>(() => {
    const all = query.data?.pages.flatMap((page) => page.data?.items ?? []) ?? [];
    const seen = new Set<string>();
    const deduped: StrategyTicketListItem[] = [];
    for (const item of all) {
      const key = item.ticket_id || `${item.exchange_instrument_id}-${item.issued_at_ms}`;
      if (!seen.has(key)) {
        seen.add(key);
        deduped.push(item);
      }
    }
    return deduped;
  }, [query.data]);

  // Natural scope strictly admits natural terminal paths (tp1_reached / tp1_not_reached)
  const items = useMemo<StrategyTicketListItem[]>(() => {
    if (scope === 'natural') {
      return rawItems.filter(
        (item) => item.evaluation_path === 'tp1_reached' || item.evaluation_path === 'tp1_not_reached'
      );
    }
    return rawItems;
  }, [rawItems, scope]);

  const excludedNonTerminalCount = useMemo(() => {
    if (scope === 'natural') {
      return rawItems.filter((item) => item.evaluation_path === 'not_terminal').length;
    }
    return 0;
  }, [rawItems, scope]);

  const snapshotChanged=query.error instanceof ApiError && query.error.code==='statistics_snapshot_changed';
  const fetchNextPage = useCallback(async () => {
    if (query.hasNextPage && !query.isFetchingNextPage && !snapshotChanged) {
      await query.fetchNextPage();
    }
  }, [query,snapshotChanged]);

  const refetch = useCallback(async () => {
    if (!options?.to_ms) {
      setInternalWindowEnd(Date.now());
    }
    const next=await income.refetch();
    if(next.data?.data.snapshot_id===income.data?.data.snapshot_id) await query.refetch();
  }, [query, options?.to_ms,income]);

  return {
    snapshotChanged,
    items,
    rawItems,
    excludedNonTerminalCount,
    scope,
    setScope,
    exitPath,
    setExitPath,
    isLoading: !income.isError&&(query.isLoading||income.isPending),
    isFetching: query.isFetching,
    isFetchingNextPage: query.isFetchingNextPage,
    hasNextPage: Boolean(query.hasNextPage)&&!snapshotChanged,
    isFetchNextPageError: query.isFetchNextPageError,
    isError: query.isError||income.isError,
    error: query.error??income.error,
    fetchNextPage,
    refetch,
    windowStart,
    windowEnd,
  };
}

export interface UseStrategyObservationsOptions {
  from_ms?: number;
  to_ms?: number;
  first_path?: StrategyObservationFirstPath | null;
}

export function useStrategyObservationsData(
  strategyVersionId?: string | null,
  options?: UseStrategyObservationsOptions
) {
  const [internalFirstPath, setInternalFirstPath] = useState<StrategyObservationFirstPath | null>(null);
  const [internalWindowEnd, setInternalWindowEnd] = useState(() => Date.now());

  useEffect(() => {
    if (options && 'first_path' in options) {
      setInternalFirstPath(options.first_path ?? null);
    }
  }, [options?.first_path]);

  const firstPath =
    options && 'first_path' in options
      ? (options.first_path ?? null)
      : internalFirstPath;
  const setFirstPath = useCallback((newFirstPath: StrategyObservationFirstPath | null) => {
    setInternalFirstPath(newFirstPath);
  }, []);

  const windowEnd = options?.to_ms ?? internalWindowEnd;
  const windowStart = options?.from_ms ?? (windowEnd - 30 * 86_400_000);

  const queryParams = useMemo(
    () => ({
      strategy_version_id: strategyVersionId ?? '',
      from_ms: windowStart,
      to_ms: windowEnd,
      first_path: firstPath,
      limit: 50,
    }),
    [strategyVersionId, windowStart, windowEnd, firstPath]
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
    const all = query.data?.pages.flatMap((page) => page.data?.items ?? []) ?? [];
    const seen = new Set<string>();
    const deduped: StrategyObservationListItem[] = [];
    for (const item of all) {
      const key = item.shadow_outcome_id || `${item.exchange_instrument_id}-${item.occurred_at_ms}`;
      if (!seen.has(key)) {
        seen.add(key);
        deduped.push(item);
      }
    }
    return deduped;
  }, [query.data]);

  const fetchNextPage = useCallback(async () => {
    if (query.hasNextPage && !query.isFetchingNextPage) {
      await query.fetchNextPage();
    }
  }, [query]);

  const refetch = useCallback(async () => {
    if (!options?.to_ms) {
      setInternalWindowEnd(Date.now());
    }
    await query.refetch();
  }, [query, options?.to_ms]);

  return {
    items: rawItems,
    firstPath,
    setFirstPath,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isFetchingNextPage: query.isFetchingNextPage,
    hasNextPage: Boolean(query.hasNextPage),
    isFetchNextPageError: query.isFetchNextPageError,
    isError: query.isError,
    error: query.error,
    fetchNextPage,
    refetch,
    windowStart,
    windowEnd,
  };
}
