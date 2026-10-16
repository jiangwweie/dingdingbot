import { infiniteQueryOptions } from '@tanstack/react-query';
import { fetchTickets, ticketsInfiniteQueryKey, type TicketsQueryParams } from './ticketsApi.ts';

export function tradesPaginationOptions(
  params: Omit<TicketsQueryParams, 'cursor'>,
  fetchPage: typeof fetchTickets = fetchTickets,
) {
  return infiniteQueryOptions({
    queryKey: ticketsInfiniteQueryKey(params),
    queryFn: ({ pageParam }) => fetchPage({ ...params, cursor: pageParam ?? undefined }),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.data.next_cursor ?? null,
    staleTime: 15_000,
    retry: false,
  });
}
