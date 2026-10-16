import { apiClient } from './client';
import { ApiError, apiErrorFromResponse } from './errors';
import type { components } from './schema';

export type ControlsResponse = components['schemas']['ControlsResponse'];
export type GenericSelectionPreview = components['schemas']['GenericSelectionPreviewView'];
export type OrbSelectionPreview = components['schemas']['OrbSelectionPreviewView'];

export const controlsQueryKey = ['owner', 'controls'] as const;
export const selectionQueryKey = (strategyGroupId: string) => ['owner', 'selection', strategyGroupId] as const;

export async function fetchControls(): Promise<ControlsResponse> {
  const { data, error, response } = await apiClient.GET('/api/owner/v1/controls');
  if (!response.ok) throw apiErrorFromResponse(response, error);
  if (!data) throw new ApiError(502, 'invalid_response', 'Control response is missing');
  return data;
}

export async function fetchSelectionPreview(
  strategyGroupId: string
): Promise<GenericSelectionPreview | OrbSelectionPreview> {
  const result = await apiClient.GET(
    '/api/owner/v1/controls/strategies/{strategy_group_id}/selection',
    {
      params: { path: { strategy_group_id: strategyGroupId } },
    }
  );
  if (!result.response.ok) throw apiErrorFromResponse(result.response, result.error);
  if (!result.data) throw new ApiError(502, 'invalid_response', 'Selection preview is missing');
  return result.data;
}
