import { apiClient } from "../../api/client";
import { ApiError, apiErrorFromResponse } from "../../api/errors";
import type { components } from "../../api/schema";

export type ExitCurrent = components["schemas"]["ExitParameterCurrentView"];
export type ExitBody = components["schemas"]["ExitParameterBody"];
export type ExitPreview = components["schemas"]["ExitParameterPreview"];
export type ExitChange = components["schemas"]["ExitParameterChange"];

export async function getExitParameters(): Promise<ExitCurrent> {
  const result = await apiClient.GET("/api/owner/v1/controls/exit-parameters");
  if (!result.response.ok) throw apiErrorFromResponse(result.response, result.error);
  if (!result.data) throw new ApiError(502, "invalid_response", "退出配置不可用");
  return result.data;
}
export async function previewExitParameters(body: ExitBody): Promise<ExitPreview> {
  const result = await apiClient.POST("/api/owner/v1/controls/exit-parameters/preview", { body });
  if (!result.response.ok) throw apiErrorFromResponse(result.response, result.error);
  if (!result.data) throw new ApiError(502, "invalid_response", "退出预览不可用");
  return result.data;
}
export async function publishExitParameters(body: ExitBody) {
  const result = await apiClient.POST("/api/owner/v1/controls/exit-parameters/publish", { body });
  if (!result.response.ok) throw apiErrorFromResponse(result.response, result.error);
  if (!result.data) throw new ApiError(502, "invalid_response", "发布结果不可用，请使用同一请求重试核实");
  return result.data;
}
