import { apiClient } from './client';
import { ApiError, apiErrorFromResponse } from './errors';
import type { components } from './schema';
export type RiskBudgetView = components['schemas']['RiskBudgetView'];
export type RiskBudgetBody = components['schemas']['RiskBudgetBody'];
export async function fetchRiskBudget() {
  const {data,error,response}=await apiClient.GET('/api/owner/v1/controls/risk-budget');
  if (!response.ok) throw apiErrorFromResponse(response,error);
  if (!data) throw new ApiError(502,'invalid_response','风险预算数据缺失');
  return data;
}
export async function previewRiskBudget(baseline: string) {
  const {data,error,response}=await apiClient.POST('/api/owner/v1/controls/risk-budget/preview',{body:{baseline}});
  if (!response.ok) throw apiErrorFromResponse(response,error);
  if (!data) throw new ApiError(502,'invalid_response','风险预算预览缺失');
  return data;
}
export async function changeRiskBudget(body: RiskBudgetBody) {
  const {data,error,response}=await apiClient.POST('/api/owner/v1/controls/risk-budget',{body});
  if (!response.ok) throw apiErrorFromResponse(response,error);
  if (!data) throw new ApiError(502,'invalid_response','风险预算回执缺失');
  return data;
}
export async function fetchRiskBudgetReceipt(key: string) {
  const {data,error,response}=await apiClient.GET('/api/owner/v1/controls/risk-budget/requests/{idempotency_key}',{params:{path:{idempotency_key:key}}});
  if (!response.ok) throw apiErrorFromResponse(response,error);
  return data;
}
