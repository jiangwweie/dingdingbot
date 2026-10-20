import { apiClient } from './client.ts';
import { ApiError, apiErrorFromResponse } from './errors.ts';
import type { components } from './schema.d.ts';

export type CandleEnvelope = components['schemas']['ApiEnvelope_CandleSeries_'];
export type CandleSeries = components['schemas']['CandleSeries'];
export type CandleView = components['schemas']['CandleView'];
export type CandleTimeframe = '15m' | '1h';

export interface MarketCandlesQueryParams {
  exchange_instrument_id: string;
  timeframe: CandleTimeframe;
  closed_at_ms: number;
  limit?: number;
}

export const marketCandlesQueryKey = (params: MarketCandlesQueryParams) =>
  ['owner', 'market', 'candles', params.exchange_instrument_id, params.timeframe, params.closed_at_ms, params.limit ?? 300] as const;

export async function fetchMarketCandles(
  params: MarketCandlesQueryParams,
  signal?: AbortSignal
): Promise<CandleEnvelope> {
  const { data, error, response } = await apiClient.GET('/api/owner/v1/market/candles', {
    params: {
      query: {
        exchange_instrument_id: params.exchange_instrument_id,
        timeframe: params.timeframe,
        closed_at_ms: params.closed_at_ms,
        limit: params.limit ?? 300,
      },
    },
    signal,
  });

  if (!response.ok) {
    throw apiErrorFromResponse(response, error);
  }
  if (!data?.data?.candles) {
    throw new ApiError(502, 'invalid_response', 'Market candles response data is missing');
  }
  return data;
}
