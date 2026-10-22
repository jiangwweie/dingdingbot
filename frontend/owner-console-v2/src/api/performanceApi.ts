import { apiClient } from './client';
import { apiErrorFromResponse, ApiError } from './errors';
import type { components } from './schema';
export type PerformanceSummary = components['schemas']['PerformanceSummary'];
export type ExitScope = 'all' | 'strategy' | 'owner' | 'safety' | 'unknown';
export interface PerformanceParams {
  from_ms?: number; to_ms?: number;
  strategy_group_id?: string; strategy_version_id?: string;
  exchange_instrument_id?: string; position_side?: 'long' | 'short';
  view?: 'all' | 'current'; exit_scope?: ExitScope;
  aggregate_status?: string;
  review_status?: 'in_progress' | 'waiting_for_review' | 'complete' | 'incomplete_evidence';
}
export async function fetchPerformance(params: PerformanceParams) {
  const { data, error, response } = await apiClient.GET('/api/owner/v1/performance', { params: { query: params } });
  if (!response.ok) throw apiErrorFromResponse(response, error);
  if (!data?.data || data.data.summary_scope !== 'full_window') throw new ApiError(502, 'invalid_response', '全窗口统计不可用');
  return data;
}
