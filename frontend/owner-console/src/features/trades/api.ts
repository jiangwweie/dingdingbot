import { apiClient } from "../../api/client";
import { ApiError, apiErrorFromResponse } from "../../api/errors";
import type { components } from "../../api/schema";
import type { TradeSearchParams } from "./searchParams";

export type TradeListEnvelope = components["schemas"]["ApiEnvelope_TradeListPage_"];

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

