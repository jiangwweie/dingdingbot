import { MoneyDecimal } from './tradeTruth.ts';
import type {
  ReviewCenterSummary,
  ReviewCenterItem,
  ReviewBreakdownItem,
  StrategyGroupSampleState,
  MoneyMetric,
  EvidenceRef,
} from '../types/review.ts';

/**
 * Deduplicate EvidenceRef list by (kind, identity, occurred_at_ms)
 * matching backend _deduplicate_evidence logic.
 */
export function deduplicateEvidence(evidence: Iterable<EvidenceRef>): EvidenceRef[] {
  const seen = new Set<string>();
  const exact: EvidenceRef[] = [];
  for (const item of evidence) {
    const key = `${item.kind}:${item.identity}:${item.occurred_at_ms}`;
    if (!seen.has(key)) {
      seen.add(key);
      exact.push(item);
    }
  }
  return exact;
}

/**
 * Recompute Review Center economics matching backend _center_economics logic:
 * - If 0 items: unavailable with 'no_review_evidence'
 * - If any item has null value in net_pnl, net_r, fees, or funding: unavailable with 'incomplete_review_economics'
 * - Otherwise: exact MoneyDecimal (80-digit precision) summation with string output
 */
export function computeReviewEconomics(
  items: readonly ReviewCenterItem[]
): {
  net_pnl: MoneyMetric;
  net_r: MoneyMetric;
  fees: MoneyMetric;
  funding: MoneyMetric;
} {
  if (items.length === 0) {
    const reason = 'no_review_evidence';
    return {
      net_pnl: { value: null, unit: 'USDT', unavailable_reason: reason },
      net_r: { value: null, unit: 'R', unavailable_reason: reason },
      fees: { value: null, unit: 'USDT', unavailable_reason: reason },
      funding: { value: null, unit: 'USDT', unavailable_reason: reason },
    };
  }

  let hasIncomplete = false;
  for (const item of items) {
    const econ = item.review?.economic_summary;
    if (
      econ?.net_pnl?.value === null ||
      econ?.net_pnl?.value === undefined ||
      econ?.net_r?.value === null ||
      econ?.net_r?.value === undefined ||
      econ?.fees?.value === null ||
      econ?.fees?.value === undefined ||
      econ?.funding?.value === null ||
      econ?.funding?.value === undefined
    ) {
      hasIncomplete = true;
      break;
    }
  }

  if (hasIncomplete) {
    const reason = 'incomplete_review_economics';
    return {
      net_pnl: { value: null, unit: 'USDT', unavailable_reason: reason },
      net_r: { value: null, unit: 'R', unavailable_reason: reason },
      fees: { value: null, unit: 'USDT', unavailable_reason: reason },
      funding: { value: null, unit: 'USDT', unavailable_reason: reason },
    };
  }

  let netPnlSum = new MoneyDecimal(0);
  let netRSum = new MoneyDecimal(0);
  let feesSum = new MoneyDecimal(0);
  let fundingSum = new MoneyDecimal(0);

  for (const item of items) {
    const econ = item.review.economic_summary;
    netPnlSum = netPnlSum.plus(new MoneyDecimal(econ.net_pnl.value!));
    netRSum = netRSum.plus(new MoneyDecimal(econ.net_r.value!));
    feesSum = feesSum.plus(new MoneyDecimal(econ.fees.value!));
    fundingSum = fundingSum.plus(new MoneyDecimal(econ.funding.value!));
  }

  return {
    net_pnl: { value: netPnlSum.toFixed(), unit: 'USDT', unavailable_reason: null },
    net_r: { value: netRSum.toFixed(), unit: 'R', unavailable_reason: null },
    fees: { value: feesSum.toFixed(), unit: 'USDT', unavailable_reason: null },
    funding: { value: fundingSum.toFixed(), unit: 'USDT', unavailable_reason: null },
  };
}

/**
 * Recompute full ReviewCenterSummary over all deduplicated loaded items,
 * ensuring card metrics, breakdowns, economics and table counts remain 100% consistent.
 */
export function computeReviewSummary(
  items: readonly ReviewCenterItem[],
  baseSummary: ReviewCenterSummary,
  nextCursor?: string | null
): ReviewCenterSummary {
  const completeReviewCount = items.filter(
    (item) => item.review?.review_status === 'complete'
  ).length;
  const incompleteReviewCount = items.length - completeReviewCount;

  const economics = computeReviewEconomics(items);

  // 1. Strategy group samples breakdown
  const groupMap = new Map<string, EvidenceRef[]>();
  for (const item of items) {
    const sgId = item.strategy_group_id;
    if (!groupMap.has(sgId)) {
      groupMap.set(sgId, []);
    }
    if (item.review?.evidence) {
      groupMap.get(sgId)!.push(...item.review.evidence);
    }
  }

  // Preserve any explicit no_evidence strategy groups returned by backend baseSummary
  // (e.g. when querying a strategy group with 0 matching terminal records like SOR-US-EQ-PERP-001)
  const baseNoEvidenceGroups = (baseSummary.strategy_group_samples || []).filter(
    (s) => s.evidence_state === 'no_evidence' && s.sample_count === 0
  );

  let strategyGroupSamples: StrategyGroupSampleState[];

  if (groupMap.size === 0 && baseNoEvidenceGroups.length > 0) {
    strategyGroupSamples = baseNoEvidenceGroups.map((s) => ({
      strategy_group_id: s.strategy_group_id,
      sample_count: 0,
      evidence_state: 'no_evidence' as const,
      evidence: s.evidence || [],
    }));
  } else {
    const loadedSamples: StrategyGroupSampleState[] = [...groupMap.keys()]
      .sort()
      .map((strategy_group_id) => ({
        strategy_group_id,
        sample_count: items.filter((i) => i.strategy_group_id === strategy_group_id).length,
        evidence_state: 'observe_only' as const,
        evidence: deduplicateEvidence(groupMap.get(strategy_group_id) || []),
      }));

    const retainedNoEvidence = baseNoEvidenceGroups
      .filter((s) => !groupMap.has(s.strategy_group_id))
      .map((s) => ({
        strategy_group_id: s.strategy_group_id,
        sample_count: 0,
        evidence_state: 'no_evidence' as const,
        evidence: s.evidence || [],
      }));

    strategyGroupSamples = [...loadedSamples, ...retainedNoEvidence].sort((a, b) =>
      a.strategy_group_id.localeCompare(b.strategy_group_id)
    );
  }

  // 2. Execution quality breakdown
  const qualityMap = new Map<string, { count: number; evidence: EvidenceRef[] }>();
  for (const item of items) {
    const label = item.review?.execution_classification || 'unknown';
    if (!qualityMap.has(label)) {
      qualityMap.set(label, { count: 0, evidence: [] });
    }
    const entry = qualityMap.get(label)!;
    entry.count += 1;
    if (item.review?.evidence) {
      entry.evidence.push(...item.review.evidence);
    }
  }

  const executionQualityBreakdown: ReviewBreakdownItem[] = [...qualityMap.keys()]
    .sort()
    .map((label) => ({
      label,
      ticket_count: qualityMap.get(label)!.count,
      evidence: deduplicateEvidence(qualityMap.get(label)!.evidence),
    }));

  // 3. Exit reason breakdown
  const exitMap = new Map<string, { count: number; evidence: EvidenceRef[] }>();
  for (const item of items) {
    const label = item.review?.exit_reason || 'exit_reason_unavailable';
    if (!exitMap.has(label)) {
      exitMap.set(label, { count: 0, evidence: [] });
    }
    const entry = exitMap.get(label)!;
    entry.count += 1;
    if (item.review?.evidence) {
      entry.evidence.push(...item.review.evidence);
    }
  }

  const exitReasonBreakdown: ReviewBreakdownItem[] = [...exitMap.keys()]
    .sort()
    .map((label) => ({
      label,
      ticket_count: exitMap.get(label)!.count,
      evidence: deduplicateEvidence(exitMap.get(label)!.evidence),
    }));

  // 4. Overall deduplicated evidence
  const allEvidence = deduplicateEvidence(
    items.flatMap((item) => item.review?.evidence || [])
  );

  return {
    from_ms: baseSummary.from_ms,
    to_ms: baseSummary.to_ms,
    sample_count: items.length,
    next_cursor: nextCursor !== undefined ? nextCursor : baseSummary.next_cursor,
    items: [...items],
    net_pnl: economics.net_pnl,
    net_r: economics.net_r,
    fees: economics.fees,
    funding: economics.funding,
    complete_review_count: completeReviewCount,
    incomplete_review_count: incompleteReviewCount,
    strategy_group_samples: strategyGroupSamples,
    execution_quality_breakdown: executionQualityBreakdown,
    exit_reason_breakdown: exitReasonBreakdown,
    evidence: allEvidence,
  };
}
