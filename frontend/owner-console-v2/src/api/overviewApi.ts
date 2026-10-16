import { apiClient } from './client';
import { ApiError, apiErrorFromResponse } from './errors';
import type { components } from './schema';

export type OverviewEnvelope = components['schemas']['ApiEnvelope_OwnerOverview_'];
export type OwnerOverview = components['schemas']['OwnerOverview'];

export const overviewQueryKey = ['owner', 'overview'] as const;

export async function fetchOverview(): Promise<OverviewEnvelope> {
  const { data, error, response } = await apiClient.GET('/api/owner/v1/overview');
  if (!response.ok) {
    throw apiErrorFromResponse(response, error);
  }
  if (!data?.data) {
    throw new ApiError(502, 'invalid_response', 'Overview response data is missing');
  }
  return data;
}
