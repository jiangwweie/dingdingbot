import type { components } from '../api/schema';

type Freshness = components['schemas']['Freshness'];

export const overviewLiveOptions = {
  refetchInterval: 15_000,
  refetchIntervalInBackground: false,
  refetchOnWindowFocus: true,
  refetchOnReconnect: true,
} as const;

export function effectiveOverviewFreshness(
  source: Freshness,
  generatedAt: string | null | undefined,
  nowMs: number,
  receivedAtMs?: number,
): Freshness {
  if (source === 'contradictory' || source === 'unavailable') return source;
  const timestamp = generatedAt ? Date.parse(generatedAt) : NaN;
  if (!Number.isFinite(timestamp)) return 'unavailable';
  // Browser and server clocks may differ. Locally age a validated response
  // from its arrival; retain the server's own stale/unavailable classification.
  const age = nowMs - (receivedAtMs ?? timestamp);
  if (age < 0) return 'contradictory';
  if (age > 60_000) return 'unavailable';
  if (age > 20_000) return 'stale';
  return source;
}
