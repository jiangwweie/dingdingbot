import { apiClient } from "../../api/client";
import { ApiError, apiErrorFromResponse } from "../../api/errors";
import type { components } from "../../api/schema";

export type InstrumentEnvelope = components["schemas"]["ApiEnvelope_InstrumentCenterPage_"];
export type UniversePreviewBody = components["schemas"]["UniversePreviewBody"];
export type UniverseApplyBody = components["schemas"]["UniverseApplyBody"];
export type UniverseChangePreview = components["schemas"]["UniverseChangePreview"];
export type UniverseInstallResult = components["schemas"]["UniverseInstallResult"];
export type InstrumentRefreshResponse = components["schemas"]["InstrumentRefreshResponse"];

export interface InstrumentFilters {
  product_family?: "crypto_perpetual" | "tradfi_equity_perpetual";
  session_state?: "pre_market" | "regular" | "after_market" | "overnight" | "no_trading" | "unavailable";
  limit?: number;
}

export const instrumentsQueryKey = (filters: InstrumentFilters) => ["owner", "instruments", filters] as const;

export async function getInstruments(filters: InstrumentFilters): Promise<InstrumentEnvelope> {
  const { data, error, response } = await apiClient.GET("/api/owner/v1/instruments", {
    params: { query: filters },
  });
  if (!response.ok) throw apiErrorFromResponse(response, error);
  if (!data) throw new ApiError(502, "invalid_response", "Instrument Center response is missing");
  return data;
}

export async function previewUniverse(body: UniversePreviewBody): Promise<UniverseChangePreview> {
  const { data, error, response } = await apiClient.POST(
    "/api/owner/v1/instruments/universes/preview",
    { body },
  );
  if (!response.ok) throw apiErrorFromResponse(response, error);
  if (!data) throw new ApiError(502, "invalid_response", "Universe preview response is missing");
  return data;
}

export async function applyUniverse(body: UniverseApplyBody): Promise<UniverseInstallResult> {
  const { data, error, response } = await apiClient.POST(
    "/api/owner/v1/instruments/universes/apply",
    { body },
  );
  if (!response.ok) throw apiErrorFromResponse(response, error);
  if (!data) throw new ApiError(502, "invalid_response", "Universe apply response is missing");
  return data;
}

export async function refreshInstruments(): Promise<InstrumentRefreshResponse> {
  const { data, error, response } = await apiClient.POST(
    "/api/owner/v1/instruments/refresh",
    { headers: { "Content-Type": "application/json" } },
  );
  if (!response.ok) throw apiErrorFromResponse(response, error);
  if (!data) throw new ApiError(502, "invalid_response", "Instrument refresh response is missing");
  return data;
}
