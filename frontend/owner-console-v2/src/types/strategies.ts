import type { components } from '../api/schema';
import type { StrategyAdmissionHealth } from './controls';

export type StrategySummaryPage = components['schemas']['StrategySummaryPage'];
export type StrategyVersionSummary = components['schemas']['StrategyVersionSummary'];
export type StrategyTicketListPage = components['schemas']['StrategyTicketListPage'];
export type StrategyTicketListItem = components['schemas']['StrategyTicketListItem'];
export type StrategyObservationListPage = components['schemas']['StrategyObservationListPage'];
export type StrategyObservationListItem = components['schemas']['StrategyObservationListItem'];
export type StrategyProductEventFacts = components['schemas']['StrategyProductEventFacts'];
export type StrategyControlView = components['schemas']['StrategyControlView'];
export type MoneyMetric = components['schemas']['MoneyMetric'];
export type Freshness = components['schemas']['Freshness'];

export type StrategyViewMode = 'current' | 'all';

export type StrategyTicketExitPath = 'tp1_reached' | 'tp1_not_reached' | 'controlled_exit';

export type StrategyObservationFirstPath =
  | 'tp1_first'
  | 'initial_stop_first'
  | 'ambiguous_same_bar'
  | 'opening_range_failure'
  | 'time_stop'
  | 'session_exit'
  | 'horizon_complete';

export interface EnrichedStrategyVersion {
  summary: StrategyVersionSummary;
  control?: StrategyControlView;
  admissionHealth?: StrategyAdmissionHealth;
  // Computed metrics & strings
  displayNameZh: string;
  timeframe: string;
  isCurrent: boolean;
  version: number;
  // Natural performance
  netPnlFormatted: string;
  netPnlIsPositive: boolean | null;
  netRFormatted: string;
  netRIsPositive: boolean | null;
  hasConfirmedReview: boolean;
  // Win rate
  winRatePercent: number | null;
  winRateLabel: string;
  // Sample counts
  totalTickets: number;
  naturalTerminals: number;
  controlledExits: number;
  confirmedReviews: number;
  pendingReviews: number;
  tp1Reached: number;
  tp1NotReached: number;
  // Runtime control
  runtimeStatus: 'enabled' | 'paused' | 'blocked' | 'unknown';
  runtimeStatusLabel: string;
  activeTicketCount: number;
  firstBlocker: string | null;
  // Observation
  observationCount: number;
  completedObservationCount: number;
  medianMfeR: string;
  medianMaeR: string;
}

export type StrategyDetailTabId = 'performance' | 'runtime' | 'selection' | 'tickets' | 'observations';
