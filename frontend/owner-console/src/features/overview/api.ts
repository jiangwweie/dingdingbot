import { apiClient } from "../../api/client";
import { ApiError, apiErrorFromResponse } from "../../api/errors";
import type { components } from "../../api/schema";

export type OverviewEnvelope = components["schemas"]["ApiEnvelope_OwnerOverview_"];

export const overviewQueryKey = ["owner", "overview"] as const;

export async function getOverview(): Promise<OverviewEnvelope> {
  const { data, error, response } = await apiClient.GET("/api/owner/v1/overview");

  if (!response.ok) {
    throw apiErrorFromResponse(response, error);
  }
  if (!data) {
    throw new ApiError(502, "invalid_response", "Overview response is missing");
  }

  return data;
}
