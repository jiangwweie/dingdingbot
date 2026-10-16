import { apiClient } from './client';
import { ApiError, apiErrorFromResponse } from './errors';
import type { components } from './schema';

export type TicketListEnvelope = components['schemas']['ApiEnvelope_TradeListPage_'];
export type TradeListPage = components['schemas']['TradeListPage'];
export type TradeListItem = components['schemas']['TradeListItem'];
export type CausalityEnvelope = components['schemas']['ApiEnvelope_TradeCausalityDetail_'];
export type TradeCausalityDetail = components['schemas']['TradeCausalityDetail'];
export type LifecycleStageView = components['schemas']['LifecycleStageView'];

export interface TicketsQueryParams {
  from_ms?: number;
  to_ms?: number;
  limit?: number;
  aggregate_status?: string;
  strategy_group_id?: string;
  exchange_instrument_id?: string;
  position_side?: 'long' | 'short';
}

export const ticketsQueryKey = (params?: TicketsQueryParams) =>
  ['owner', 'tickets', params ?? { limit: 100 }] as const;

export const causalityQueryKey = (ticketId: string) =>
  ['owner', 'causality', ticketId] as const;

export async function fetchTickets(params?: TicketsQueryParams): Promise<TicketListEnvelope> {
  const queryParams = params ?? { limit: 100 };
  const { data, error, response } = await apiClient.GET('/api/owner/v1/tickets', {
    params: {
      query: queryParams,
    },
  });
  if (!response.ok) {
    throw apiErrorFromResponse(response, error);
  }
  if (!data?.data?.items) {
    throw new ApiError(502, 'invalid_response', 'Tickets response data is missing');
  }
  return data;
}

export async function fetchTicketCausality(ticketId: string): Promise<CausalityEnvelope> {
  const { data, error, response } = await apiClient.GET('/api/owner/v1/tickets/{ticket_id}/causality', {
    params: {
      path: { ticket_id: ticketId },
    },
  });
  if (!response.ok) {
    throw apiErrorFromResponse(response, error);
  }
  if (!data?.data) {
    throw new ApiError(502, 'invalid_response', 'Ticket causality response data is missing');
  }
  return data;
}
