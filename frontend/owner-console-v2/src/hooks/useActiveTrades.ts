import { useCallback } from 'react';
import { useQueries, useQuery } from '@tanstack/react-query';
import { fetchOverview, overviewQueryKey } from '../api/overviewApi';
import { causalityQueryKey, fetchTicketCausality } from '../api/ticketsApi';
import { activeCoverage } from '../mapping/tradeTruth';
import { mapTradeListItemToEpisode } from '../mapping/tradeEpisodeMapping';

// Current identities come only from Overview. Historical date/business filters never enter these keys.
export function useActiveTrades() {
  const overview = useQuery({ queryKey: overviewQueryKey, queryFn: fetchOverview, staleTime: 15_000, retry: false });
  const ids = [...new Set(overview.data?.data.active_ticket_ids ?? [])];
  const details = useQueries({ queries: ids.map(id => ({
    queryKey: causalityQueryKey(id),
    queryFn: () => fetchTicketCausality(id),
    staleTime: 10_000,
    retry: false,
  })) });
  const trades = details.flatMap((query, index) => {
    const trade = query.data?.data.trade;
    // Reject mismatched identities and a Ticket that ended after the Overview snapshot.
    return trade?.ticket_id === ids[index] && trade.terminal_at_ms === null ? [trade] : [];
  });
  const activeTrades = trades.map(t => mapTradeListItemToEpisode(t));
  const error = overview.error ?? details.find(q => q.isError)?.error ?? null;
  const isLoading = overview.isPending || details.some(q => q.isPending);
  const coverage = activeCoverage(activeTrades.map(t => t.ticket_id), overview.data?.data,
    !error && !isLoading && overview.data?.freshness === 'fresh');
  const refetch = useCallback(async () => {
    await overview.refetch();
    await Promise.all(details.map(q => q.refetch()));
  }, [overview, details]);
  return { activeTrades, coverage, error, isLoading, isFetching: overview.isFetching || details.some(q => q.isFetching),
    liveActiveTicketCount: overview.data?.data.active_ticket_count ?? null, refetch };
}
