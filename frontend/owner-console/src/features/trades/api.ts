import { apiClient } from "../../api/client";
import { ApiError, apiErrorFromResponse } from "../../api/errors";
import type { components } from "../../api/schema";
import type { TradeSearchParams } from "./searchParams";

export type TradeListEnvelope = components["schemas"]["ApiEnvelope_TradeListPage_"];
export type TradeCausalityEnvelope = components["schemas"]["ApiEnvelope_TradeCausalityDetail_"];
export type CandleEnvelope = components["schemas"]["ApiEnvelope_CandleSeries_"];
export type CandleTimeframe = "15m" | "1h";

export const tradesQueryKey = (filters: TradeSearchParams) => ["owner", "trades", filters] as const;

export async function getTrades(filters: TradeSearchParams): Promise<TradeListEnvelope> {
  const query: {
    from_ms?: number | null;
    to_ms?: number | null;
    cursor?: string | null;
    aggregate_status?: string | null;
    strategy_group_id?: string | null;
    exchange_instrument_id?: string | null;
    position_side?: "long" | "short" | null;
  } = {};
  if (filters.from_ms !== undefined) query.from_ms = filters.from_ms;
  if (filters.to_ms !== undefined) query.to_ms = filters.to_ms;
  if (filters.cursor !== undefined) query.cursor = filters.cursor;
  if (filters.aggregate_status !== undefined) query.aggregate_status = filters.aggregate_status;
  if (filters.strategy_group_id !== undefined) query.strategy_group_id = filters.strategy_group_id;
  if (filters.exchange_instrument_id !== undefined) query.exchange_instrument_id = filters.exchange_instrument_id;
  if (filters.position_side !== undefined) query.position_side = filters.position_side;

  const { data, error, response } = await apiClient.GET("/api/owner/v1/tickets", {
    params: { query },
  });

  if (!response.ok) throw apiErrorFromResponse(response, error);
  if (!data) throw new ApiError(502, "invalid_response", "Trade list response is missing");
  return data;
}

export const tradeCausalityQueryKey = (ticketId: string) => ["owner", "trades", "causality", ticketId] as const;
export const candlesQueryKey = (ticketId: string, timeframe: CandleTimeframe, closedAtMs: number, limit: number) => ["owner", "trades", "candles", ticketId, timeframe, closedAtMs, limit] as const;

export async function getTradeCausality(ticketId: string): Promise<TradeCausalityEnvelope> {
  const { data, error, response } = await apiClient.GET("/api/owner/v1/tickets/{ticket_id}/causality", {
    params: { path: { ticket_id: ticketId } },
  });
  if (!response.ok) throw apiErrorFromResponse(response, error);
  if (!data) throw new ApiError(502, "invalid_response", "Trade causality response is missing");
  return data;
}

export async function getCandles(input: { exchangeInstrumentId: string; timeframe: CandleTimeframe; closedAtMs: number; limit: number }): Promise<CandleEnvelope> {
  const { data, error, response } = await apiClient.GET("/api/owner/v1/market/candles", {
    params: {
      query: {
        exchange_instrument_id: input.exchangeInstrumentId,
        timeframe: input.timeframe,
        closed_at_ms: input.closedAtMs,
        limit: input.limit,
      },
    },
  });
  if (!response.ok) throw apiErrorFromResponse(response, error);
  if (!data) throw new ApiError(502, "invalid_response", "Candle response is missing");
  return data;
}
