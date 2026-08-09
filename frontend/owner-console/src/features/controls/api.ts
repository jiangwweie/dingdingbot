import { apiClient } from "../../api/client";
import { ApiError, apiErrorFromResponse } from "../../api/errors";
import type { components } from "../../api/schema";

export type ControlsResponse = components["schemas"]["ControlsResponse"];
export type ControlWriteBody = components["schemas"]["ControlWriteBody"];
export type FlattenBody = components["schemas"]["FlattenBody"];
export type FlattenPreview = components["schemas"]["FlattenPreview"];
export type OwnerControlOperation = components["schemas"]["OwnerControlOperation"];

export const controlsQueryKey = ["owner", "controls"] as const;

export async function getControls(): Promise<ControlsResponse> {
  const { data, error, response } = await apiClient.GET("/api/owner/v1/controls");
  if (!response.ok) throw apiErrorFromResponse(response, error);
  if (!data) throw new ApiError(502, "invalid_response", "Control response is missing");
  return data;
}

export async function setStrategyControl(
  strategyGroupId: string,
  action: "pause" | "resume",
  body: ControlWriteBody,
): Promise<void> {
  const path = action === "pause"
    ? "/api/owner/v1/controls/strategies/{strategy_group_id}/pause"
    : "/api/owner/v1/controls/strategies/{strategy_group_id}/resume";
  const result = action === "pause"
    ? await apiClient.POST(path, { params: { path: { strategy_group_id: strategyGroupId } }, body })
    : await apiClient.POST(path, { params: { path: { strategy_group_id: strategyGroupId } }, body });
  if (!result.response.ok) throw apiErrorFromResponse(result.response, result.error);
}

export async function setGlobalEntry(
  action: "pause" | "resume",
  body: ControlWriteBody,
): Promise<void> {
  const result = action === "pause"
    ? await apiClient.POST("/api/owner/v1/controls/entry/pause", { body })
    : await apiClient.POST("/api/owner/v1/controls/entry/resume", { body });
  if (!result.response.ok) throw apiErrorFromResponse(result.response, result.error);
}

export async function getFlattenPreview(): Promise<FlattenPreview> {
  const { data, error, response } = await apiClient.POST(
    "/api/owner/v1/controls/exposure/flatten-all/preview",
    { body: {} },
  );
  if (!response.ok) throw apiErrorFromResponse(response, error);
  if (!data) throw new ApiError(502, "invalid_response", "Flatten preview is missing");
  return data;
}

export async function submitFlatten(body: FlattenBody): Promise<OwnerControlOperation> {
  const { data, error, response } = await apiClient.POST(
    "/api/owner/v1/controls/exposure/flatten-all",
    { body },
  );
  if (!response.ok) throw apiErrorFromResponse(response, error);
  if (!data) throw new ApiError(502, "invalid_response", "Flatten operation is missing");
  return data;
}
