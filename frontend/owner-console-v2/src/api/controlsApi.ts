import { apiClient } from './client';
import { ApiError, apiErrorFromResponse } from './errors';
import type { components } from './schema';

export type ControlsResponse = components['schemas']['ControlsResponse'];
export type GenericSelectionPreview = components['schemas']['GenericSelectionPreviewView'];
export type OrbSelectionPreview = components['schemas']['OrbSelectionPreviewView'];
export type StrategyEntryControl = components['schemas']['StrategyEntryControl'];
export type ControlWriteBody = components['schemas']['ControlWriteBody'];
export type FlattenPreview = components['schemas']['FlattenPreview'];
export type FlattenBody = components['schemas']['FlattenBody'];
export type OwnerControlOperation = components['schemas']['OwnerControlOperation'];
export type EmptyControlBody = components['schemas']['EmptyControlBody'];

export const controlsQueryKey = ['owner', 'controls'] as const;
export const selectionQueryKey = (strategyGroupId: string) => ['owner', 'selection', strategyGroupId] as const;
export const flattenOperationQueryKey = (authId: string) => ['owner', 'control-operation', authId] as const;

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

export async function pauseStrategy(
  strategyGroupId: string,
  body: ControlWriteBody,
): Promise<StrategyEntryControl> {
  const { data, error, response } = await apiClient.POST(
    '/api/owner/v1/controls/strategies/{strategy_group_id}/pause',
    {
      params: { path: { strategy_group_id: strategyGroupId } },
      body,
    },
  );
  if (!response.ok) throw apiErrorFromResponse(response, error);
  if (!data) throw new ApiError(502, 'invalid_response', 'Pause response is missing');
  return data;
}

export async function resumeStrategy(
  strategyGroupId: string,
  body: ControlWriteBody,
): Promise<StrategyEntryControl> {
  const { data, error, response } = await apiClient.POST(
    '/api/owner/v1/controls/strategies/{strategy_group_id}/resume',
    {
      params: { path: { strategy_group_id: strategyGroupId } },
      body,
    },
  );
  if (!response.ok) throw apiErrorFromResponse(response, error);
  if (!data) throw new ApiError(502, 'invalid_response', 'Resume response is missing');
  return data;
}

export async function fetchFlattenPreview(body?: EmptyControlBody): Promise<FlattenPreview> {
  const { data, error, response } = await apiClient.POST(
    '/api/owner/v1/controls/exposure/flatten-all/preview',
    {
      body: body ?? {},
    }
  );
  if (!response.ok) throw apiErrorFromResponse(response, error);
  if (!data) throw new ApiError(502, 'invalid_response', 'Flatten preview is missing');
  return data;
}

export async function submitFlatten(body: FlattenBody): Promise<OwnerControlOperation> {
  const { data, error, response } = await apiClient.POST(
    '/api/owner/v1/controls/exposure/flatten-all',
    {
      body,
    }
  );
  if (!response.ok) throw apiErrorFromResponse(response, error);
  if (!data) throw new ApiError(502, 'invalid_response', 'Flatten response is missing');
  return data;
}

export async function fetchControlOperation(
  authorizationId: string
): Promise<OwnerControlOperation | null> {
  const { data, error, response } = await apiClient.GET(
    '/api/owner/v1/control-operations/{authorization_id}',
    {
      params: { path: { authorization_id: authorizationId } },
    }
  );
  if (!response.ok) throw apiErrorFromResponse(response, error);
  if (!data) throw new ApiError(502, 'invalid_response', 'Control operation is missing');
  if ('status' in data && data.status === 'not_found') {
    return null;
  }
  return data as OwnerControlOperation;
}
