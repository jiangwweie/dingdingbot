import { apiClient } from "../../api/client";
import { ApiError, apiErrorFromResponse } from "../../api/errors";
import type { components } from "../../api/schema";
import type { ReviewSearchParams } from "./searchParams";

export type ReviewCenterEnvelope = components["schemas"]["ApiEnvelope_ReviewCenterSummary_"];

export const reviewQueryKey = (filters: ReviewSearchParams) => ["owner", "review", filters] as const;

export async function getReviewCenter(filters: ReviewSearchParams): Promise<ReviewCenterEnvelope> {
  const query: {
    from_ms?: number | null;
    to_ms?: number | null;
    cursor?: string | null;
    review_status?: "in_progress" | "waiting_for_settlement" | "waiting_for_review" | "complete" | "incomplete_evidence" | null;
    strategy_group_id?: string | null;
  } = {};
  if (filters.from_ms !== undefined) query.from_ms = filters.from_ms;
  if (filters.to_ms !== undefined) query.to_ms = filters.to_ms;
  if (filters.cursor !== undefined) query.cursor = filters.cursor;
  if (filters.review_status !== undefined) query.review_status = filters.review_status;
  if (filters.strategy_group_id !== undefined) query.strategy_group_id = filters.strategy_group_id;

  const { data, error, response } = await apiClient.GET("/api/owner/v1/review", { params: { query } });
  if (!response.ok) throw apiErrorFromResponse(response, error);
  if (!data) throw new ApiError(502, "invalid_response", "Review Center response is missing");
  return data;
}
