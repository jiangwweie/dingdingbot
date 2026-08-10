import { apiClient } from "../../api/client";
import { ApiError, apiErrorFromResponse } from "../../api/errors";
import type { components } from "../../api/schema";
import type { StrategySearchParams } from "./searchParams";

export type StrategySummaryEnvelope = components["schemas"]["ApiEnvelope_StrategySummaryPage_"];
export type StrategyTicketEnvelope = components["schemas"]["ApiEnvelope_StrategyTicketListPage_"];

export const strategiesQueryKey = (filters: Pick<StrategySearchParams, "from_ms" | "to_ms" | "view">) => ["owner", "strategies", filters] as const;
export const strategyTicketsQueryKey = (filters: Pick<StrategySearchParams, "strategy_version_id" | "from_ms" | "to_ms" | "scope" | "exit_path" | "cursor">) => ["owner", "strategies", "tickets", filters] as const;

export async function getStrategies(filters: Pick<StrategySearchParams, "from_ms" | "to_ms" | "view">): Promise<StrategySummaryEnvelope> {
  const query: { from_ms?: number | null; to_ms?: number | null; view?: "current" | "all" } = {};
  if (filters.from_ms !== undefined) query.from_ms = filters.from_ms;
  if (filters.to_ms !== undefined) query.to_ms = filters.to_ms;
  if (filters.view !== undefined) query.view = filters.view;
  const { data, error, response } = await apiClient.GET("/api/owner/v1/strategies", {
    params: { query },
  });
  if (!response.ok) throw apiErrorFromResponse(response, error);
  if (!data) throw new ApiError(502, "invalid_response", "Strategy summary response is missing");
  return data;
}

export async function getStrategyTickets(filters: { strategy_version_id: string; from_ms?: number | undefined; to_ms?: number | undefined; scope?: "natural" | "all" | undefined; exit_path?: "tp1_reached" | "tp1_not_reached" | "controlled_exit" | undefined; cursor?: string | undefined }): Promise<StrategyTicketEnvelope> {
  const query: { from_ms?: number | null; to_ms?: number | null; scope?: "natural" | "all"; exit_path?: "tp1_reached" | "tp1_not_reached" | "controlled_exit" | null; cursor?: string | null } = {};
  if (filters.from_ms !== undefined) query.from_ms = filters.from_ms;
  if (filters.to_ms !== undefined) query.to_ms = filters.to_ms;
  if (filters.scope !== undefined) query.scope = filters.scope;
  if (filters.exit_path !== undefined) query.exit_path = filters.exit_path;
  if (filters.cursor !== undefined) query.cursor = filters.cursor;
  const { data, error, response } = await apiClient.GET("/api/owner/v1/strategies/{strategy_version_id}/tickets", {
    params: {
      path: { strategy_version_id: filters.strategy_version_id },
      query,
    },
  });
  if (!response.ok) throw apiErrorFromResponse(response, error);
  if (!data) throw new ApiError(502, "invalid_response", "Strategy Ticket response is missing");
  return data;
}
