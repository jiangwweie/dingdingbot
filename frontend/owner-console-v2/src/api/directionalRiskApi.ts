import { apiClient } from './client';
import { ApiError, apiErrorFromResponse } from './errors';
import type { components } from './schema';

export type DirectionalRiskView = components['schemas']['DirectionalRiskView'];
export type DirectionalRiskBody = components['schemas']['DirectionalRiskBody'];
export async function fetchDirectionalRisk(): Promise<DirectionalRiskView> {
  const { data, error, response } = await apiClient.GET('/api/owner/v1/controls/directional-risk');
  if (!response.ok) throw apiErrorFromResponse(response, error);
  if (!data) throw new ApiError(502, 'invalid_response', '方向风险控制数据缺失');
  return data;
}
export async function changeDirectionalRisk(body: DirectionalRiskBody) {
  const { data, error, response } = await apiClient.POST('/api/owner/v1/controls/directional-risk', { body });
  if (!response.ok) throw apiErrorFromResponse(response, error);
  if (!data) throw new ApiError(502, 'invalid_response', '方向风险变更结果缺失');
  return data;
}
export async function fetchDirectionalReceipt(key: string) {
  const { data, error, response } = await apiClient.GET('/api/owner/v1/controls/directional-risk/requests/{idempotency_key}', { params: { path: { idempotency_key: key } } });
  if (!response.ok) throw apiErrorFromResponse(response, error);
  if (!data) throw new ApiError(502, 'invalid_response', '方向风险请求回执缺失');
  return data;
}
