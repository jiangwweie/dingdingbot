import { apiClient } from "../../api/client";
import { ApiError, apiErrorFromResponse } from "../../api/errors";
import type { components } from "../../api/schema";

export type ControlsResponse = components["schemas"]["ControlsResponse"];
export type ControlWriteBody = components["schemas"]["ControlWriteBody"];
export type FlattenBody = components["schemas"]["FlattenBody"];
export type FlattenPreview = components["schemas"]["FlattenPreview"];
export type OwnerControlOperation = components["schemas"]["OwnerControlOperation"];
export type SelectionPreview = components["schemas"]["GenericSelectionPreviewView"];
export type SelectionIntent = components["schemas"]["GenericSelectionActivationBody"];

export async function getSelectionPreview(strategyGroupId: string): Promise<SelectionPreview> {
  const result = await apiClient.GET("/api/owner/v1/controls/strategies/{strategy_group_id}/selection", {
    params: { path: { strategy_group_id: strategyGroupId } },
  });
  if (!result.response.ok) throw apiErrorFromResponse(result.response, result.error);
  if (!result.data) throw new ApiError(502, "invalid_response", "Selection preview is missing");
  return result.data;
}

export async function submitSelectionIntent(strategyGroupId: string, mode: "dynamic" | "static", body: SelectionIntent & {
  rollback_baseline_id?: string; selection_epoch_id?: string;
}): Promise<void> {
  const result = mode === "dynamic"
    ? await apiClient.POST("/api/owner/v1/controls/strategies/{strategy_group_id}/selection/dynamic/activate", {
      params: { path: { strategy_group_id: strategyGroupId } }, body,
    })
    : await apiClient.POST("/api/owner/v1/controls/strategies/{strategy_group_id}/selection/static/activate", {
      params: { path: { strategy_group_id: strategyGroupId } },
      body: { ...body, rollback_baseline_id: body.rollback_baseline_id!, selection_epoch_id: body.selection_epoch_id! },
    });
  if (!result.response.ok) throw apiErrorFromResponse(result.response, result.error);
}

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
