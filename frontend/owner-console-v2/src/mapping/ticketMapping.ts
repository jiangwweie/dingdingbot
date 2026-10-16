/**
 * Ticket Mapping and Active Ticket Accounting Truth
 * 
 * Ensures that active tickets and unloaded tickets are strictly derived from
 * real authoritative facts without fabricating synthetic tickets.
 */

export interface TicketBadgeItem {
  type: 'ticket' | 'count_only' | 'empty';
  id?: string;
  count?: number;
  label?: string;
  symbol?: string;
  side?: 'long' | 'short';
  pnl_r?: string;
}

/**
 * Computes the number of authoritative active tickets that have not yet been loaded
 * in the paginated response.
 *
 * @param authoritativeCount Active count reported by authoritative state (e.g. Overview or AccountCapacity)
 * @param loadedCount Number of ticket objects loaded in the current page
 */
export function computeUnloadedActiveCount(
  authoritativeCount: number | null | undefined,
  loadedCount: number
): number {
  if (typeof authoritativeCount === 'number' && authoritativeCount > loadedCount) {
    return authoritativeCount - loadedCount;
  }
  return 0;
}

/**
 * Derives badges for strategy matrix positions without fabricating fake ticket IDs.
 */
export function formatTicketOccupationBadge(
  activeTickets: Array<{ ticket_id?: string; id?: string; symbol?: string; side?: 'long' | 'short'; pnl_r?: string }> | undefined,
  activeTicketCount: number | undefined
): TicketBadgeItem[] {
  if (activeTickets && activeTickets.length > 0) {
    return activeTickets.map((t) => ({
      type: 'ticket' as const,
      id: t.ticket_id ?? t.id,
      symbol: t.symbol,
      side: t.side,
      pnl_r: t.pnl_r,
    }));
  }
  if (typeof activeTicketCount === 'number' && activeTicketCount > 0) {
    return [
      {
        type: 'count_only' as const,
        count: activeTicketCount,
        label: `${activeTicketCount} 个占用`,
      },
    ];
  }
  return [{ type: 'empty' as const, count: 0, label: '0 个占用' }];
}
