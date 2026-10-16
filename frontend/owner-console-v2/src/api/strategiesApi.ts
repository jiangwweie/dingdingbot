import { apiClient } from './client';
import { ApiError, apiErrorFromResponse } from './errors';
import type { components } from './schema';

export type StrategySummaryEnvelope = components['schemas']['ApiEnvelope_StrategySummaryPage_'];
export type StrategySummaryPage = components['schemas']['StrategySummaryPage'];
export type StrategyVersionSummary = components['schemas']['StrategyVersionSummary'];

export const strategiesQueryKey = (params?: { from_ms?: number; to_ms?: number; view?: 'current' | 'all' }) =>
  ['owner', 'strategies', params] as const;

export async function fetchStrategies(params?: {
  from_ms?: number;
  to_ms?: number;
  view?: 'current' | 'all';
}): Promise<StrategySummaryEnvelope> {
  const { data, error, response } = await apiClient.GET('/api/owner/v1/strategies', {
    params: {
      query: params,
    },
  });
  if (!response.ok) {
    throw apiErrorFromResponse(response, error);
  }
  if (!data?.data?.items) {
    throw new ApiError(502, 'invalid_response', 'Strategies response data is missing');
  }
  return data;
}
