import { fetchOverview, overviewQueryKey } from '../api/overviewApi';
import { activeCoverage } from '../mapping/tradeTruth';
import { tradesPaginationOptions } from '../api/tradesPagination';
import { useMemo, useCallback, useState } from 'react';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { type TicketsQueryParams } from '../api/ticketsApi';
import { mapTradeListItemToEpisode, computeTradesSummaryMetrics } from '../mapping/tradeEpisodeMapping';
import type { TradeEpisode, TradesSummaryMetrics, TradeListItem } from '../types/trades';

const TRADES_LIMIT = 100;

export function useTradesData(params?: Omit<TicketsQueryParams, 'cursor'>) {
  const [windowEnd, setWindowEnd] = useState(Date.now);
  const queryParams = useMemo<TicketsQueryParams>(
    () => ({
      limit: TRADES_LIMIT,
      from_ms: windowEnd - 30 * 86_400_000,
      to_ms: windowEnd,
      ...params,
    }),
    [params, windowEnd]
  );

  const overview = useQuery({queryKey:overviewQueryKey,queryFn:fetchOverview,staleTime:15000,retry:false});
  const query = useInfiniteQuery(tradesPaginationOptions(queryParams));

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
    await overview.refetch();
    if (params?.from_ms !== undefined || params?.to_ms !== undefined) await query.refetch();
    else setWindowEnd(Date.now());
  }, [query, overview]);

  const fetchNextPage = useCallback(async () => {
    if (hasNextPage && !isFetchingNextPage) {
      await query.fetchNextPage();
    }
  }, [hasNextPage, isFetchingNextPage, query]);

  const firstPage = query.data?.pages[0];

  const coverage = activeCoverage(activeTrades.map(t=>t.ticket_id),overview.data?.data, !overview.isError && overview.data?.freshness === 'fresh');
  return {
    coverage,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage,
    isError: query.isError && !query.data,
    paginationError: query.isFetchNextPageError ? query.error : null,
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
