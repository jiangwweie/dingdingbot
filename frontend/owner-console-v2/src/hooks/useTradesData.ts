import { useMemo, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchTickets, ticketsQueryKey, type TicketsQueryParams } from '../api/ticketsApi';
import { mapTradeListItemToEpisode, computeTradesSummaryMetrics } from '../mapping/tradeEpisodeMapping';
import type { TradeEpisode, TradesSummaryMetrics } from '../types/trades';

const TRADES_LIMIT = 100;

export function useTradesData(params?: TicketsQueryParams) {
  const queryParams = useMemo<TicketsQueryParams>(
    () => ({
      limit: TRADES_LIMIT,
      ...params,
    }),
    [params]
  );

  const query = useQuery({
    queryKey: ticketsQueryKey(queryParams),
    queryFn: () => fetchTickets(queryParams),
    staleTime: 15_000,
    retry: false,
  });

  const rawItems = query.data?.data?.items ?? [];

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
    return computeTradesSummaryMetrics(allTrades);
  }, [allTrades]);

  const refetch = useCallback(async () => {
    await query.refetch();
  }, [query]);

  return {
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
    freshness: query.data?.freshness ?? 'unavailable',
    generatedAt: query.data?.generated_at ?? null,
    sourceWatermark: query.data?.source_watermark ?? null,
    allTrades,
    activeTrades,
    completedTrades,
    metrics,
    refetch,
  };
}
