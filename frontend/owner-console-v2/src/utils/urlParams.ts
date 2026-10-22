import type { ExitScope } from '../api/performanceApi';
/**
 * Pure URL Search Params parsing, validation, and serialization for Owner Console V2.
 * Adheres strictly to Trades and Strategies contracts.
 */

import {
  type TimeRangePreset,
  calculatePresetWindow,
  validateTimeWindow,
} from './timeRange.ts';
import type {
  StrategyViewMode,
  StrategyTicketExitPath,
  StrategyObservationFirstPath,
  StrategyDetailTabId,
} from '../types/strategies.ts';
import type { TradeFilterMode } from '../types/trades.ts';
import type { ReviewStatusQuery } from '../api/reviewApi.ts';

export interface ReviewFilterParams {
  view?: 'current' | 'all';
  exit_scope?: ExitScope;
  strategy_version_id?: string;
  range: TimeRangePreset;
  from_ms: number;
  to_ms: number;
  exchange_instrument_id?: string;
  position_side?: 'long'|'short';
  review_status?: ReviewStatusQuery;
  strategy_group_id?: string;
}

export interface TradesFilterParams {
  view?: 'current' | 'all';
  exit_scope?: ExitScope;
  strategy_version_id?: string;
  range: TimeRangePreset;
  from_ms: number;
  to_ms: number;
  strategy_group_id?: string;
  exchange_instrument_id?: string;
  position_side?: 'long' | 'short';
  aggregate_status?: string;
  filter_mode: TradeFilterMode;
}

export interface StrategiesFilterParams {
  exchange_instrument_id?:string;position_side?:'long'|'short';
  view: StrategyViewMode;
  exit_scope?: ExitScope;
  strategy_group_id?: string;
  range: TimeRangePreset;
  from_ms: number;
  to_ms: number;
  strategy_version_id?: string;
  drawer_tab?: StrategyDetailTabId;
  scope: 'natural' | 'all';
  exit_path?: StrategyTicketExitPath;
  first_path?: StrategyObservationFirstPath;
}

const VALID_PRESETS = new Set<TimeRangePreset>(['today', '24h', '7d', '30d', 'custom']);
const VALID_SIDES = new Set(['long', 'short']);
const VALID_DRAWER_TABS = new Set<StrategyDetailTabId>([
  'performance',
  'runtime',
  'selection',
  'tickets',
  'observations',
]);
const VALID_EXIT_PATHS = new Set<StrategyTicketExitPath>(['tp1_reached', 'tp1_not_reached', 'controlled_exit']);
const VALID_FIRST_PATHS = new Set<StrategyObservationFirstPath>([
  'tp1_first',
  'initial_stop_first',
  'ambiguous_same_bar',
  'opening_range_failure',
  'time_stop',
  'session_exit',
  'horizon_complete',
]);

/**
 * Parse and validate Trades filter params from URLSearchParams.
 */
export function parseTradesSearchParams(
  searchParams: URLSearchParams,
  nowMs: number = Date.now()
): TradesFilterParams {
  const rawRange = searchParams.get('range') as TimeRangePreset;
  const range: TimeRangePreset = VALID_PRESETS.has(rawRange) ? rawRange : '30d';

  const rawFrom = searchParams.get('from_ms');
  const rawTo = searchParams.get('to_ms');
  const parsedFrom = rawFrom ? parseInt(rawFrom, 10) : null;
  const parsedTo = rawTo ? parseInt(rawTo, 10) : null;

  let from_ms: number;
  let to_ms: number;

  const validation = validateTimeWindow(parsedFrom, parsedTo);
  if (validation.valid && parsedFrom != null && parsedTo != null) {
    from_ms = parsedFrom;
    to_ms = parsedTo;
  } else {
    // Fall back to preset window
    const presetWin = calculatePresetWindow(range, nowMs);
    from_ms = presetWin.from_ms;
    to_ms = presetWin.to_ms;
  }

  const rawSide = searchParams.get('position_side');
  const position_side = VALID_SIDES.has(rawSide as string)
    ? (rawSide as 'long' | 'short')
    : undefined;

  const rawStrat = searchParams.get('strategy_group_id')?.trim();
  const strategy_group_id = rawStrat && rawStrat.length > 0 ? rawStrat : undefined;

  const rawInst = searchParams.get('exchange_instrument_id')?.trim();
  const exchange_instrument_id = rawInst && rawInst.length > 0 ? rawInst : undefined;

  const rawStatus = searchParams.get('aggregate_status')?.trim();
  const aggregate_status = rawStatus && rawStatus.length > 0 ? rawStatus : undefined;

  const rawMode = searchParams.get('filter_mode');
  const filter_mode: TradeFilterMode =
    rawMode === 'active' || rawMode === 'completed' ? rawMode : 'all';

  return {
    range,
    from_ms,
    to_ms,
    exit_scope: parseExitScope(searchParams.get('exit_scope')),
    view: searchParams.get('view') === 'current' ? 'current' : 'all',
    strategy_group_id,
    strategy_version_id: searchParams.get('strategy_version_id')?.trim() || undefined,
    exchange_instrument_id,
    position_side,
    aggregate_status,
    filter_mode,
  };
}

/**
 * Serialize Trades filter params into clean URL search string.
 */
export function serializeTradesSearchParams(params: TradesFilterParams): string {
  const q = new URLSearchParams();
  if (params.exit_scope && params.exit_scope !== 'all') q.set('exit_scope', params.exit_scope);
  if (params.view === 'current') q.set('view', 'current');
  q.set('tab', 'trades');

  if (params.range !== '30d') {
    q.set('range', params.range);
  }
  q.set('from_ms', String(params.from_ms));
  q.set('to_ms', String(params.to_ms));

  if (params.strategy_group_id) q.set('strategy_group_id', params.strategy_group_id);
  if (params.strategy_version_id) q.set('strategy_version_id', params.strategy_version_id);
  if (params.exchange_instrument_id) {
    q.set('exchange_instrument_id', params.exchange_instrument_id);
  }
  if (params.position_side) {
    q.set('position_side', params.position_side);
  }
  if (params.aggregate_status) {
    q.set('aggregate_status', params.aggregate_status);
  }
  if (params.filter_mode && params.filter_mode !== 'all') {
    q.set('filter_mode', params.filter_mode);
  }

  return q.toString();
}

/**
 * Parse and validate Strategies filter params from URLSearchParams.
 */
export function parseStrategiesSearchParams(
  searchParams: URLSearchParams,
  nowMs: number = Date.now()
): StrategiesFilterParams {
  const rawView = searchParams.get('view');
  const view: StrategyViewMode = rawView === 'current' ? 'current' : 'all';

  const rawRange = searchParams.get('range') as TimeRangePreset;
  const range: TimeRangePreset = VALID_PRESETS.has(rawRange) ? rawRange : '30d';

  const rawFrom = searchParams.get('from_ms');
  const rawTo = searchParams.get('to_ms');
  const parsedFrom = rawFrom ? parseInt(rawFrom, 10) : null;
  const parsedTo = rawTo ? parseInt(rawTo, 10) : null;

  let from_ms: number;
  let to_ms: number;

  const validation = validateTimeWindow(parsedFrom, parsedTo);
  if (validation.valid && parsedFrom != null && parsedTo != null) {
    from_ms = parsedFrom;
    to_ms = parsedTo;
  } else {
    const presetWin = calculatePresetWindow(range, nowMs);
    from_ms = presetWin.from_ms;
    to_ms = presetWin.to_ms;
  }

  const rawVersionId = searchParams.get('strategy_version_id')?.trim();
  const strategy_version_id = rawVersionId && rawVersionId.length > 0 ? rawVersionId : undefined;

  const rawTab = searchParams.get('drawer_tab');
  const drawer_tab = VALID_DRAWER_TABS.has(rawTab as StrategyDetailTabId)
    ? (rawTab as StrategyDetailTabId)
    : undefined;

  const rawScope = searchParams.get('scope');
  const scope: 'natural' | 'all' = rawScope === 'natural' ? 'natural' : 'all';

  const rawExitPath = searchParams.get('exit_path') as StrategyTicketExitPath;
  let exit_path: StrategyTicketExitPath | undefined = VALID_EXIT_PATHS.has(rawExitPath)
    ? rawExitPath
    : undefined;

  // Defensive guard: controlled_exit is illegal in natural scope
  if (scope === 'natural' && exit_path === 'controlled_exit') {
    exit_path = undefined;
  }

  const rawFirstPath = searchParams.get('first_path') as StrategyObservationFirstPath;
  const first_path: StrategyObservationFirstPath | undefined = VALID_FIRST_PATHS.has(rawFirstPath)
    ? rawFirstPath
    : undefined;

  return {
    view,
    exchange_instrument_id:searchParams.get('exchange_instrument_id')?.trim()||undefined,
    position_side:VALID_SIDES.has(searchParams.get('position_side')??'')?searchParams.get('position_side') as 'long'|'short':undefined,
    exit_scope: parseExitScope(searchParams.get('exit_scope')),
    strategy_group_id: searchParams.get('strategy_group_id')?.trim() || undefined,
    range,
    from_ms,
    to_ms,
    strategy_version_id,
    drawer_tab,
    scope,
    exit_path,
    first_path,
  };
}

/**
 * Serialize Strategies filter params into clean URL search string.
 */
export function serializeStrategiesSearchParams(params: StrategiesFilterParams): string {
  const q = new URLSearchParams();
  if (params.exit_scope && params.exit_scope !== 'all') q.set('exit_scope', params.exit_scope);
  if (params.view === 'current') q.set('view', 'current');
  q.set('tab', 'strategies');
  if(params.exchange_instrument_id)q.set('exchange_instrument_id',params.exchange_instrument_id);
  if(params.position_side)q.set('position_side',params.position_side);
  if(params.strategy_group_id)q.set('strategy_group_id',params.strategy_group_id);


  if (params.range !== '30d') {
    q.set('range', params.range);
  }
  q.set('from_ms', String(params.from_ms));
  q.set('to_ms', String(params.to_ms));

  if (params.strategy_version_id) {
    q.set('strategy_version_id', params.strategy_version_id);
  }
  if (params.drawer_tab) {
    q.set('drawer_tab', params.drawer_tab);
  }
  if (params.scope === 'natural') q.set('scope', 'natural');
  if (params.exit_path) {
    q.set('exit_path', params.exit_path);
  }
  if (params.first_path) {
    q.set('first_path', params.first_path);
  }

  return q.toString();
}

const VALID_REVIEW_STATUSES = new Set<ReviewStatusQuery>([
  'in_progress',
  'waiting_for_review',
  'complete',
  'incomplete_evidence',
]);

/**
 * Parse and validate Review filter params from URLSearchParams.
 */
export function parseReviewSearchParams(
  searchParams: URLSearchParams,
  nowMs: number = Date.now()
): ReviewFilterParams {
  const rawRange = searchParams.get('range') as TimeRangePreset;
  const range: TimeRangePreset = VALID_PRESETS.has(rawRange) ? rawRange : '30d';

  const rawFrom = searchParams.get('from_ms');
  const rawTo = searchParams.get('to_ms');
  const parsedFrom = rawFrom ? parseInt(rawFrom, 10) : null;
  const parsedTo = rawTo ? parseInt(rawTo, 10) : null;

  let from_ms: number;
  let to_ms: number;

  const validation = validateTimeWindow(parsedFrom, parsedTo);
  if (validation.valid && parsedFrom != null && parsedTo != null) {
    from_ms = parsedFrom;
    to_ms = parsedTo;
  } else {
    const presetWin = calculatePresetWindow(range, nowMs);
    from_ms = presetWin.from_ms;
    to_ms = presetWin.to_ms;
  }

  const rawStatus = searchParams.get('review_status') as ReviewStatusQuery;
  const review_status: ReviewStatusQuery | undefined = VALID_REVIEW_STATUSES.has(rawStatus)
    ? rawStatus
    : undefined;

  const rawStrat = searchParams.get('strategy_group_id')?.trim();
  const strategy_group_id = rawStrat && rawStrat.length > 0 ? rawStrat : undefined;

  return {
    range,from_ms,to_ms,
    exit_scope: parseExitScope(searchParams.get('exit_scope')),
    view: searchParams.get('view') === 'current' ? 'current' : 'all',
    strategy_version_id: searchParams.get('strategy_version_id')?.trim() || undefined,
    review_status,
    exchange_instrument_id:searchParams.get('exchange_instrument_id')?.trim()||undefined,
    position_side:VALID_SIDES.has(searchParams.get('position_side')??'')?searchParams.get('position_side') as 'long'|'short':undefined,
    strategy_group_id,
  };
}

/**
 * Serialize Review filter params into clean URL search string.
 */
export function serializeReviewSearchParams(params: ReviewFilterParams): string {
  const q = new URLSearchParams();
  if (params.exit_scope && params.exit_scope !== 'all') q.set('exit_scope', params.exit_scope);
  if (params.view === 'current') q.set('view', 'current');
  q.set('tab', 'review');

  if (params.range !== '30d') {
    q.set('range', params.range);
  }
  q.set('from_ms', String(params.from_ms));
  q.set('to_ms', String(params.to_ms));

  if(params.exchange_instrument_id)q.set('exchange_instrument_id',params.exchange_instrument_id);
  if(params.position_side)q.set('position_side',params.position_side);
  if (params.review_status) {
    q.set('review_status', params.review_status);
  }
  if (params.strategy_group_id) q.set('strategy_group_id', params.strategy_group_id);
  if (params.strategy_version_id) q.set('strategy_version_id', params.strategy_version_id);

  return q.toString();
}

export function parseExitScope(raw: string | null): ExitScope {
  return raw === 'strategy' || raw === 'owner' || raw === 'safety' || raw === 'unknown' ? raw : 'all';
}

export function incomeNavigationSearch(search: string, tab: string, nowMs = Date.now()): string {
  const old = new URLSearchParams(search);
  const parsed = parseReviewSearchParams(old, nowMs);
  const next = new URLSearchParams();
  next.set('tab', tab);
  next.set('range', parsed.range);
  next.set('from_ms', String(parsed.from_ms)); next.set('to_ms', String(parsed.to_ms));
  for (const key of ['view', 'exit_scope', 'strategy_group_id', 'strategy_version_id', 'exchange_instrument_id', 'position_side']) {
    const value = old.get(key); if (value) next.set(key, value);
  }
  return next.toString();
}
