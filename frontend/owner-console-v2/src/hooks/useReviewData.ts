import { ApiError } from '../api/errors';
import { usePerformance } from './usePerformance';
import { useMemo, useCallback } from 'react';
import { useInfiniteQuery } from '@tanstack/react-query';
import { reviewPaginationOptions } from '../api/reviewPagination.ts';
import type { ReviewFilterParams, ReviewCenterItem, ReviewCenterSummary } from '../types/review.ts';
import type { ReviewQueryParams } from '../api/reviewApi.ts';
import { computeReviewSummary } from '../mapping/reviewSummary.ts';

const REVIEW_PAGE_LIMIT = 50;

export function useReviewData(filters?: Partial<ReviewFilterParams>) {
  const queryParams = useMemo<ReviewQueryParams>(() => {
    return {
      limit: REVIEW_PAGE_LIMIT,
      exchange_instrument_id:filters?.exchange_instrument_id,position_side:filters?.position_side,
      view: filters?.view,exit_scope: filters?.exit_scope,strategy_version_id: filters?.strategy_version_id,
      from_ms: filters?.from_ms,
      to_ms: filters?.to_ms,
      review_status: filters?.review_status,
      strategy_group_id: filters?.strategy_group_id,
    };
  }, [
    filters?.exchange_instrument_id,filters?.position_side,
    filters?.view,filters?.exit_scope,filters?.strategy_version_id,
    filters?.from_ms,
    filters?.to_ms,
    filters?.review_status,
    filters?.strategy_group_id,
  ]);

  const performance=usePerformance(queryParams);
  const query = useInfiniteQuery({...reviewPaginationOptions({...queryParams,snapshot:performance.data?.data.snapshot_id}),enabled:!!performance.data&&!performance.isError});

  const items = useMemo<ReviewCenterItem[]>(() => {
    const unique = new Map<string, ReviewCenterItem>();
    for (const page of query.data?.pages ?? []) {
      for (const item of page.data.items) {
        if (!unique.has(item.ticket_id)) {
          unique.set(item.ticket_id, item);
        }
      }
    }
    return [...unique.values()];
  }, [query.data]);

  const snapshotChanged=query.error instanceof ApiError && query.error.code==='statistics_snapshot_changed';
  const hasNextPage = Boolean(query.hasNextPage)&&!snapshotChanged;
  const isFetchingNextPage = query.isFetchingNextPage;

  const firstPage = query.data?.pages[0];
  const lastPage = query.data?.pages ? query.data.pages[query.data.pages.length - 1] : undefined;
  const currentNextCursor = lastPage?.data?.next_cursor ?? null;

  const summary = useMemo<ReviewCenterSummary | null>(() => {
    const baseSummary = firstPage?.data;
    if (!baseSummary) return null;
    return computeReviewSummary(items, baseSummary, currentNextCursor);
  }, [items, firstPage?.data, currentNextCursor]);

  const totalAttentionCount = useMemo(() => {
    return items.reduce((sum, item) => sum + (item.review.attention_items?.length || 0), 0);
  }, [items]);

  const refetch = useCallback(async () => {
    const next=await performance.refetch();
    if(next.data?.data.snapshot_id===performance.data?.data.snapshot_id) await query.refetch();
  }, [query,performance]);

  const fetchNextPage = useCallback(async () => {
    if (hasNextPage && !isFetchingNextPage) {
      await query.fetchNextPage();
    }
  }, [hasNextPage, isFetchingNextPage, query]);

  return {
    performance:performance.data?.data ?? null,
    performanceError:performance.error ?? (snapshotChanged ? query.error : null),
    isLoading: !performance.isError && (query.isLoading || performance.isPending),
    isFetching: query.isFetching,
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
    items,
    summary,
    totalAttentionCount,
    refetch,
  };
}
