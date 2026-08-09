import { apiClient } from "../../api/client";
import { ApiError, apiErrorFromResponse } from "../../api/errors";
import type { components } from "../../api/schema";
import type { SignalSearchParams } from "./searchParams";

export type SignalListEnvelope = components["schemas"]["ApiEnvelope_SignalListPage_"];
export type SignalDetailEnvelope = components["schemas"]["ApiEnvelope_SignalAdmissionDetail_"];

export const signalsQueryKey = (filters: SignalSearchParams) => ["owner", "signals", filters] as const;
export const signalDetailQueryKey = (signalEventId: string, refreshVersion: number) =>
  ["owner", "signals", "detail", signalEventId, refreshVersion] as const;

export async function getSignals(filters: SignalSearchParams): Promise<SignalListEnvelope> {
  const query: {
    from_ms?: number | null;
    to_ms?: number | null;
    cursor?: string | null;
    decision_status?: "admitted" | "rejected" | null;
    strategy_group_id?: string | null;
    exchange_instrument_id?: string | null;
    position_side?: "long" | "short" | null;
  } = {};
  if (filters.from_ms !== undefined) query.from_ms = filters.from_ms;
  if (filters.to_ms !== undefined) query.to_ms = filters.to_ms;
  if (filters.cursor !== undefined) query.cursor = filters.cursor;
  if (filters.decision_status !== undefined) query.decision_status = filters.decision_status;
  if (filters.strategy_group_id !== undefined) query.strategy_group_id = filters.strategy_group_id;
  if (filters.exchange_instrument_id !== undefined) query.exchange_instrument_id = filters.exchange_instrument_id;
  if (filters.position_side !== undefined) query.position_side = filters.position_side;
  const { data, error, response } = await apiClient.GET("/api/owner/v1/signals", {
    params: { query },
  });

  if (!response.ok) throw apiErrorFromResponse(response, error);
  if (!data) throw new ApiError(502, "invalid_response", "Signal list response is missing");
  return data;
}

export async function getSignalDetail(signalEventId: string): Promise<SignalDetailEnvelope> {
  const { data, error, response } = await apiClient.GET("/api/owner/v1/signals/{signal_event_id}", {
    params: { path: { signal_event_id: signalEventId } },
  });

  if (!response.ok) throw apiErrorFromResponse(response, error);
  if (!data) throw new ApiError(502, "invalid_response", "Signal detail response is missing");
  return data;
}
