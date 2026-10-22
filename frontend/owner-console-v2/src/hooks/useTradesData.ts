import { ApiError } from '../api/errors';
import { usePerformance } from './usePerformance';
import { formatReviewMoneyMetric } from '../mapping/reviewMapping';
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
      limit: TRADES_LIMIT, time_basis: 'terminal',
      view: filters?.view,exit_scope: filters?.exit_scope,strategy_version_id: filters?.strategy_version_id,
      from_ms: filters?.from_ms,
      to_ms: filters?.to_ms,
      strategy_group_id: filters?.strategy_group_id,
      exchange_instrument_id: filters?.exchange_instrument_id,
      position_side: filters?.position_side,
      aggregate_status: filters?.aggregate_status,
    };
  }, [
    filters?.view,filters?.exit_scope,filters?.strategy_version_id,
    filters?.from_ms,
    filters?.to_ms,
    filters?.strategy_group_id,
    filters?.exchange_instrument_id,
    filters?.position_side,
    filters?.aggregate_status,
  ]);

  const live = useActiveTrades();

  const {limit: _limit,time_basis: _basis,...incomeParams}=queryParams;
  const performance=usePerformance(incomeParams);
  const query=useInfiniteQuery({...tradesPaginationOptions({...queryParams,snapshot:performance.data?.data.snapshot_id}),enabled:!!performance.data&&!performance.isError});

  const rawItems = useMemo<TradeListItem[]>(() => {
    const unique = new Map<string, TradeListItem>();
    for (const page of query.data?.pages ?? []) {
      for (const item of page.data.items) if (!unique.has(item.ticket_id)) unique.set(item.ticket_id, item);
    }
    return [...unique.values()];
  }, [query.data]);

  const snapshotChanged=query.error instanceof ApiError && query.error.code==='statistics_snapshot_changed';
  const hasNextPage = Boolean(query.hasNextPage)&&!snapshotChanged;
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
    const loaded=computeTradesSummaryMetrics(allTrades, { hasMore: hasNextPage });
    const full=performance.data?.data;
    if(!full) return {...loaded,totalNetPnlFormatted:'统计不可用',totalNetRFormatted:'统计不可用'};
    const pnl=formatReviewMoneyMetric(full.verified_totals.net_pnl,{sign:true});
    const r=formatReviewMoneyMetric(full.verified_totals.net_r,{sign:true,fractionDigits:4});
    const coverage=full.metric_coverage!;
    return {...loaded,completedCount:full.sample_count,winCount:full.win_count,lossCount:full.loss_count,winRatePercent:full.win_count+full.loss_count?Math.round(full.win_count*100/(full.win_count+full.loss_count)):null,
      totalNetPnlFormatted:pnl.formatted,totalNetRFormatted:r.formatted,
      hasPnlGaps:coverage.net_pnl.available_count<full.sample_count,hasRGaps:coverage.net_r.available_count<full.sample_count,
      pnlCoverageText:`全窗口 · 已核实 ${coverage.net_pnl.available_count}/${full.sample_count} 笔`,rCoverageText:`累计单笔净 R · 已核实 ${coverage.net_r.available_count}/${full.sample_count} 笔`,
      winRateDenominatorText:`全窗口已核实：${full.win_count} 胜 / ${full.loss_count} 负；${full.breakeven_count} 笔持平`,
    };
  }, [allTrades, hasNextPage,performance.data]);

  const refetch = useCallback(async () => {
    const next=await performance.refetch();
    await live.refetch();
    if(next.data?.data.snapshot_id===performance.data?.data.snapshot_id) await query.refetch();
  }, [query, live,performance]);

  const fetchNextPage = useCallback(async () => {
    if (hasNextPage && !isFetchingNextPage) {
      await query.fetchNextPage();
    }
  }, [hasNextPage, isFetchingNextPage, query]);

  const firstPage = query.data?.pages[0];

  return {
    performance:performance.data?.data ?? null,
    performanceError:performance.error ?? (snapshotChanged ? query.error : null),
    coverage: live.coverage,
    liveActiveTicketCount: live.liveActiveTicketCount,
    liveError: live.error,
    isLiveLoading: live.isLoading,
    isLoading: !performance.isError && (query.isLoading || performance.isPending),
    isFetching: query.isFetching || live.isFetching,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage,
    isError: (query.isError && !query.data)||performance.isError,
    paginationError: query.isFetchNextPageError ? query.error : null,
    refreshError: query.isError && query.data && !query.isFetchNextPageError ? query.error : null,
    error: query.error??performance.error,
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
