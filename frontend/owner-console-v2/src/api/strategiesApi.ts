import { apiClient } from './client.ts';
import { ApiError, apiErrorFromResponse } from './errors.ts';
import type { components } from './schema.d.ts';

export type StrategySummaryEnvelope = components['schemas']['ApiEnvelope_StrategySummaryPage_'];
export type StrategySummaryPage = components['schemas']['StrategySummaryPage'];
export type StrategyVersionSummary = components['schemas']['StrategyVersionSummary'];

export interface StrategiesQueryParams {
  from_ms?: number;
  to_ms?: number;
  view?: 'current' | 'all';
}

export const strategiesQueryKey = (params?: StrategiesQueryParams) =>
  ['owner', 'strategies', params ?? { view: 'current' as const }] as const;

export async function fetchStrategies(params?: StrategiesQueryParams): Promise<StrategySummaryEnvelope> {
  const queryParams = params ?? { view: 'current' as const };
  const { data, error, response } = await apiClient.GET('/api/owner/v1/strategies', {
    params: {
      query: queryParams,
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
