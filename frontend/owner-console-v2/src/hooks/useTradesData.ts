import { useActiveTrades } from './useActiveTrades';
import { tradesPaginationOptions } from '../api/tradesPagination';
import { useMemo, useCallback } from 'react';
import { useInfiniteQuery } from '@tanstack/react-query';
import { type TicketsQueryParams } from '../api/ticketsApi';
import { mapTradeListItemToEpisode, computeTradesSummaryMetrics } from '../mapping/tradeEpisodeMapping';
import type { TradeEpisode, TradesSummaryMetrics, TradeListItem } from '../types/trades';
import type { TradesFilterParams } from '../utils/urlParams.ts';

const TRADES_LIMIT = 100;

export function useTradesData(filters?: Partial<TradesFilterParams>) {
  const queryParams = useMemo<TicketsQueryParams>(() => {
    return {
      limit: TRADES_LIMIT,
      from_ms: filters?.from_ms,
      to_ms: filters?.to_ms,
      strategy_group_id: filters?.strategy_group_id,
      exchange_instrument_id: filters?.exchange_instrument_id,
      position_side: filters?.position_side,
      aggregate_status: filters?.aggregate_status,
    };
  }, [
    filters?.from_ms,
    filters?.to_ms,
    filters?.strategy_group_id,
    filters?.exchange_instrument_id,
    filters?.position_side,
    filters?.aggregate_status,
  ]);

  const live = useActiveTrades();

  const query = useInfiniteQuery(tradesPaginationOptions(queryParams));

  const rawItems = useMemo<TradeListItem[]>(() => {
    const unique = new Map<string, TradeListItem>();
    for (const page of query.data?.pages ?? []) {
      for (const item of page.data.items) if (!unique.has(item.ticket_id)) unique.set(item.ticket_id, item);
    }
    return [...unique.values()];
  }, [query.data]);

  const hasNextPage = Boolean(query.hasNextPage);
  const isFetchingNextPage = query.isFetchingNextPage;

  const allTrades = useMemo<TradeEpisode[]>(() => {
    const now = Date.now();
    return rawItems.map((item) => mapTradeListItemToEpisode(item, now));
  }, [rawItems]);

  const completedTrades = useMemo(
    () => allTrades.filter((t) => !t.isActive),
    [allTrades]
  );

  const metrics = useMemo<TradesSummaryMetrics>(() => {
    return computeTradesSummaryMetrics(allTrades, { hasMore: hasNextPage });
  }, [allTrades, hasNextPage]);

  const refetch = useCallback(async () => {
    await Promise.all([live.refetch(), query.refetch()]);
  }, [query, live]);

  const fetchNextPage = useCallback(async () => {
    if (hasNextPage && !isFetchingNextPage) {
      await query.fetchNextPage();
    }
  }, [hasNextPage, isFetchingNextPage, query]);

  const firstPage = query.data?.pages[0];

  return {
    coverage: live.coverage,
    liveActiveTicketCount: live.liveActiveTicketCount,
    liveError: live.error,
    isLiveLoading: live.isLoading,
    isLoading: query.isLoading,
    isFetching: query.isFetching || live.isFetching,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage,
    isError: query.isError && !query.data,
    paginationError: query.isFetchNextPageError ? query.error : null,
    refreshError: query.isError && query.data && !query.isFetchNextPageError ? query.error : null,
    error: query.error,
    freshness: query.isError ? 'stale' : firstPage?.freshness ?? 'unavailable',
    generatedAt: firstPage?.generated_at ?? null,
    sourceWatermark: firstPage?.source_watermark ?? null,
    allTrades,
    activeTrades: live.activeTrades,
    completedTrades,
    metrics,
    refetch,
  };
}
