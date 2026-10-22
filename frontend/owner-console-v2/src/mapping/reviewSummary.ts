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

/** Strict totals and independently covered verified partials over loaded records. */
export function computeReviewEconomics(items: readonly ReviewCenterItem[]) {
  const names = ['gross_pnl', 'net_pnl', 'net_r', 'fees', 'funding'] as const;
  const verified = {} as Record<typeof names[number], MoneyMetric>;
  const totals = {} as Record<typeof names[number], MoneyMetric>;
  const coverage: ReviewCenterSummary['metric_coverage'] = {};
  for (const name of names) {
    let sum = new MoneyDecimal(0);
    const missing: string[] = [];
    for (const item of items) {
      const raw = item.review.economic_summary[name]?.value;
      if (raw == null || !new MoneyDecimal(raw).isFinite()) missing.push(item.ticket_id);
      else sum = sum.plus(new MoneyDecimal(raw));
    }
    const available = items.length - missing.length;
    verified[name] = { value: available ? sum.toFixed() : null, unit: name === 'net_r' ? 'R' : 'USDT', unavailable_reason: available ? null : items.length ? 'no_confirmed_metric' : 'no_review_evidence' };
    totals[name] = missing.length ? { value: null, unit: verified[name].unit, unavailable_reason: 'incomplete_review_economics' } : verified[name];
    coverage[name] = { available_count: available, total_count: items.length, missing_ticket_ids: missing };
  }
  return { ...totals, verified_totals: verified, metric_coverage: coverage };
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
    const raw = item.review?.exit_reason;
    const label = raw?.startsWith('owner_flatten_all:') ? 'owner_flatten_all' : raw?.startsWith('deployment_drain:') ? 'deployment_drain' : raw || 'exit_reason_unavailable';
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
    summary_scope: 'loaded_records',
    verified_totals: economics.verified_totals,
    metric_coverage: economics.metric_coverage,
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
