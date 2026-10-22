import { apiClient } from './client.ts';
import { ApiError, apiErrorFromResponse } from './errors.ts';
import type { components } from './schema.d.ts';

export type ReviewCenterEnvelope = components['schemas']['ApiEnvelope_ReviewCenterSummary_'];
export type ReviewCenterSummary = components['schemas']['ReviewCenterSummary'];
export type ReviewCenterItem = components['schemas']['ReviewCenterItem'];
export type ProgrammaticTradeReview = components['schemas']['ProgrammaticTradeReview'];
export type ReviewSentence = components['schemas']['ReviewSentence'];
export type ReviewEconomicSummary = components['schemas']['ReviewEconomicSummary'];
export type ReviewBreakdownItem = components['schemas']['ReviewBreakdownItem'];
export type StrategyGroupSampleState = components['schemas']['StrategyGroupSampleState'];
export type ExecutionClassification = components['schemas']['ProgrammaticTradeReview']['execution_classification'];
export type ReviewItemReviewStatus = components['schemas']['ProgrammaticTradeReview']['review_status'];
export type MoneyMetric = components['schemas']['MoneyMetric'];
export type EvidenceRef = components['schemas']['EvidenceRef'];

export type ReviewStatusQuery =
  | 'in_progress'
  | 'waiting_for_review'
  | 'complete'
  | 'incomplete_evidence';

export interface ReviewQueryParams {
  view?: 'all' | 'current';
  exit_scope?: import('./performanceApi').ExitScope;
  strategy_version_id?: string;
  exchange_instrument_id?: string;
  position_side?: 'long'|'short';
  snapshot?: string;
  from_ms?: number;
  to_ms?: number;
  limit?: number;
  cursor?: string | null;
  review_status?: ReviewStatusQuery;
  strategy_group_id?: string;
}

export const reviewQueryKey = (params?: ReviewQueryParams) =>
  ['owner', 'review', params ?? { limit: 50 }] as const;

export const reviewInfiniteQueryKey = (params?: Omit<ReviewQueryParams, 'cursor'>) =>
  ['owner', 'review', 'infinite', params ?? { limit: 50 }] as const;

export async function fetchReviewCenter(params?: ReviewQueryParams): Promise<ReviewCenterEnvelope> {
  const queryParams = params ?? { limit: 50 };
  const { data, error, response } = await apiClient.GET('/api/owner/v1/review', {
    params: {
      query: {
        exchange_instrument_id:queryParams.exchange_instrument_id,position_side:queryParams.position_side,
        view: queryParams.view, exit_scope: queryParams.exit_scope, strategy_version_id: queryParams.strategy_version_id, snapshot: queryParams.snapshot,
        from_ms: queryParams.from_ms,
        to_ms: queryParams.to_ms,
        limit: queryParams.limit,
        cursor: queryParams.cursor,
        review_status: queryParams.review_status,
        strategy_group_id: queryParams.strategy_group_id,
      },
    },
  });

  if (!response.ok) {
    throw apiErrorFromResponse(response, error);
  }
  if (!data?.data?.items) {
    throw new ApiError(502, 'invalid_response', 'Review Center response data is missing');
  }
  return data;
}
