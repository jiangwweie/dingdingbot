import { useMemo, useCallback } from 'react';
import { useInfiniteQuery } from '@tanstack/react-query';
import { fetchTickets, ticketsInfiniteQueryKey, type TicketsQueryParams } from '../api/ticketsApi';
import { mapTradeListItemToEpisode, computeTradesSummaryMetrics } from '../mapping/tradeEpisodeMapping';
import type { TradeEpisode, TradesSummaryMetrics, TradeListItem } from '../types/trades';

const TRADES_LIMIT = 100;

export function useTradesData(params?: Omit<TicketsQueryParams, 'cursor'>) {
  const queryParams = useMemo<TicketsQueryParams>(
    () => ({
      limit: TRADES_LIMIT,
      ...params,
    }),
    [params]
  );

  const query = useInfiniteQuery({
    queryKey: ticketsInfiniteQueryKey(queryParams),
    queryFn: ({ pageParam }) =>
      fetchTickets({
        ...queryParams,
        cursor: pageParam ?? undefined,
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.data?.next_cursor ?? null,
    staleTime: 15_000,
    retry: false,
  });

  const rawItems = useMemo<TradeListItem[]>(() => {
    return query.data?.pages.flatMap((page) => page.data?.items ?? []) ?? [];
  }, [query.data]);

  const hasNextPage = Boolean(query.hasNextPage);
  const isFetchingNextPage = query.isFetchingNextPage;

  const allTrades = useMemo<TradeEpisode[]>(() => {
    const now = Date.now();
    return rawItems.map((item) => mapTradeListItemToEpisode(item, now));
  }, [rawItems]);

  const activeTrades = useMemo(
    () => allTrades.filter((t) => t.isActive),
    [allTrades]
  );

  const completedTrades = useMemo(
    () => allTrades.filter((t) => !t.isActive),
    [allTrades]
  );

  const metrics = useMemo<TradesSummaryMetrics>(() => {
    return computeTradesSummaryMetrics(allTrades, { hasMore: hasNextPage });
  }, [allTrades, hasNextPage]);

  const refetch = useCallback(async () => {
    await query.refetch();
  }, [query]);

  const fetchNextPage = useCallback(async () => {
    if (hasNextPage && !isFetchingNextPage) {
      await query.fetchNextPage();
    }
  }, [hasNextPage, isFetchingNextPage, query]);

  const firstPage = query.data?.pages[0];

  return {
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage,
    isError: query.isError,
    error: query.error,
    freshness: firstPage?.freshness ?? 'unavailable',
    generatedAt: firstPage?.generated_at ?? null,
    sourceWatermark: firstPage?.source_watermark ?? null,
    allTrades,
    activeTrades,
    completedTrades,
    metrics,
    refetch,
  };
}
