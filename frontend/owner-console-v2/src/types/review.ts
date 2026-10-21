import type {
  ReviewCenterSummary,
  ReviewCenterItem,
  ProgrammaticTradeReview,
  ReviewStatusQuery,
  ReviewItemReviewStatus,
  ExecutionClassification,
  ReviewSentence,
  ReviewBreakdownItem,
  StrategyGroupSampleState,
  MoneyMetric,
  EvidenceRef,
} from '../api/reviewApi.ts';
import type { TimeRangePreset } from '../utils/timeRange.ts';

export interface ReviewFilterParams {
  range: TimeRangePreset;
  from_ms: number;
  to_ms: number;
  review_status?: ReviewStatusQuery;
  strategy_group_id?: string;
}

export type {
  ReviewCenterSummary,
  ReviewCenterItem,
  ProgrammaticTradeReview,
  ReviewStatusQuery,
  ReviewItemReviewStatus,
  ExecutionClassification,
  ReviewSentence,
  ReviewBreakdownItem,
  StrategyGroupSampleState,
  MoneyMetric,
  EvidenceRef,
};
