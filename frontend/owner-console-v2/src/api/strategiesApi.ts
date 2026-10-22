import { apiClient } from './client.ts';
import { ApiError, apiErrorFromResponse } from './errors.ts';
import type { components } from './schema.d.ts';
import type { StrategyTicketExitPath, StrategyObservationFirstPath } from '../types/strategies.ts';

export type StrategySummaryEnvelope = components['schemas']['ApiEnvelope_StrategySummaryPage_'];
export type StrategySummaryPage = components['schemas']['StrategySummaryPage'];
export type StrategyVersionSummary = components['schemas']['StrategyVersionSummary'];

export type StrategyTicketListEnvelope = components['schemas']['ApiEnvelope_StrategyTicketListPage_'];
export type StrategyTicketListPage = components['schemas']['StrategyTicketListPage'];
export type StrategyTicketListItem = components['schemas']['StrategyTicketListItem'];

export type StrategyObservationListEnvelope = components['schemas']['ApiEnvelope_StrategyObservationListPage_'];
export type StrategyObservationListPage = components['schemas']['StrategyObservationListPage'];
export type StrategyObservationListItem = components['schemas']['StrategyObservationListItem'];

export interface StrategiesQueryParams {
  exchange_instrument_id?:string;position_side?:'long'|'short';
  strategy_group_id?:string;strategy_version_id?:string;
  from_ms?: number;
  to_ms?: number;
  view?: 'current' | 'all';
  exit_scope?: import('./performanceApi').ExitScope;
}

export interface StrategyTicketsQueryParams {
  snapshot?:string;exit_scope?:import('./performanceApi').ExitScope;
  strategy_version_id: string;
  from_ms?: number;
  to_ms?: number;
  limit?: number;
  cursor?: string | null;
  scope?: 'natural' | 'all';
  exit_path?: StrategyTicketExitPath | null;
}

export interface StrategyObservationsQueryParams {
  strategy_version_id: string;
  from_ms?: number;
  to_ms?: number;
  limit?: number;
  cursor?: string | null;
  first_path?: StrategyObservationFirstPath | null;
}

export const strategiesQueryKey = (params?: StrategiesQueryParams) =>
  ['owner', 'strategies', params ?? { view: 'current' as const }] as const;

export const strategyTicketsQueryKey = (params: StrategyTicketsQueryParams) =>
  ['owner', 'strategies', 'tickets', params] as const;

export const strategyTicketsInfiniteQueryKey = (params: Omit<StrategyTicketsQueryParams, 'cursor'>) =>
  ['owner', 'strategies', 'tickets', 'infinite', params] as const;

export const strategyObservationsQueryKey = (params: StrategyObservationsQueryParams) =>
  ['owner', 'strategies', 'observations', params] as const;

export const strategyObservationsInfiniteQueryKey = (params: Omit<StrategyObservationsQueryParams, 'cursor'>) =>
  ['owner', 'strategies', 'observations', 'infinite', params] as const;

export async function fetchStrategies(params?: StrategiesQueryParams): Promise<StrategySummaryEnvelope> {
  const queryParams = params ?? { view: 'current' as const };
  const { data, error, response } = await apiClient.GET('/api/owner/v1/strategies', {
    params: {
      query: queryParams,
    },
  });
  if (!response.ok) {
    throw apiErrorFromResponse(response, error);
  }
  if (!data?.data?.items) {
    throw new ApiError(502, 'invalid_response', 'Strategies response data is missing');
  }
  return data;
}

export async function fetchStrategyTickets(
  params: StrategyTicketsQueryParams
): Promise<StrategyTicketListEnvelope> {
  const { strategy_version_id, ...query } = params;
  const { data, error, response } = await apiClient.GET(
    '/api/owner/v1/strategies/{strategy_version_id}/tickets',
    {
      params: {
        path: { strategy_version_id },
        query: {
          from_ms: query.from_ms,
          to_ms: query.to_ms,
          limit: query.limit ?? 50,
          cursor: query.cursor ?? undefined,
          scope: query.scope ?? 'all',snapshot:query.snapshot,exit_scope:query.exit_scope,
          exit_path: query.exit_path ?? undefined,
        },
      },
    }
  );
  if (!response.ok) {
    throw apiErrorFromResponse(response, error);
  }
  if (!data?.data?.items) {
    throw new ApiError(502, 'invalid_response', 'Strategy tickets response data is missing');
  }
  return data;
}

export async function fetchStrategyObservations(
  params: StrategyObservationsQueryParams
): Promise<StrategyObservationListEnvelope> {
  const { strategy_version_id, ...query } = params;
  const { data, error, response } = await apiClient.GET(
    '/api/owner/v1/strategies/{strategy_version_id}/observations',
    {
      params: {
        path: { strategy_version_id },
        query: {
          from_ms: query.from_ms,
          to_ms: query.to_ms,
          limit: query.limit ?? 50,
          cursor: query.cursor ?? undefined,
          first_path: query.first_path ?? undefined,
        },
      },
    }
  );
  if (!response.ok) {
    throw apiErrorFromResponse(response, error);
  }
  if (!data?.data?.items) {
    throw new ApiError(502, 'invalid_response', 'Strategy observations response data is missing');
  }
  return data;
}
