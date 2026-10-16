// Independent verification oracle; does not import the UI's mapping logic.
export function exactDisplay(actual, expected) {
  const normalize = v => String(v ?? '').trim().replace(/\s+/g, ' ').replace(/(?<=\d),(?=\d{3}(?:\D|$))/g, '');
  return normalize(actual) === normalize(expected);
}
export function sameIdentities(actual, expected) {
  return actual.length === expected.length && new Set(actual).size === actual.length &&
    [...actual].sort().every((v,i) => v === [...expected].sort()[i]);
}
export function authorityEvidence(kind, preview, now) {
  const r = preview?.runtime;
  if (!r) return {complete:false,state:'unknown'};
  const a = kind === 'orb' ? r.current_authority?.authority : null;
  const id = kind === 'orb' ? a?.selection_authority_id : r.current_authority_id;
  const outcome = kind === 'orb' ? a?.authority_outcome : r.current_authority_outcome;
  const start = kind === 'orb' ? a?.effective_from_ms : null;
  const end = kind === 'orb' ? a?.expires_at_ms : r.membership_valid_until_ms;
  let state, label;
  if (!id) { state='missing'; label=kind==='orb'?'权威缺失 / 未生效':'权威未生效 / 缺失'; }
  else if (!outcome || !Number.isFinite(end) || (kind==='orb' && !Number.isFinite(start))) return {complete:false,state:'unknown',id,outcome,start,end};
  else if (now >= end) { state='expired'; label=`权威已过期 (${outcome})`; }
  else if (start !== null && now < start) { state='pending'; label=`权威未生效 (${outcome})`; }
  else if (kind==='generic' && r.first_blocker) { state='blocked'; label=`准入阻断 · ${r.first_blocker}`; }
  else { state='active'; label=kind==='orb' && outcome==='VALID_EMPTY'?'权威生效 · 空集合入围 (VALID_EMPTY)':`权威有效 · ${outcome}`; }
  return {complete:true,state,label,id:id??null,outcome:outcome??null,start:start??null,end:end??null,
    limitation:kind==='generic'?'API does not expose effective_from_ms':null};
}

export function tradesMetricsEvidence(rawTickets, pagination = { hasMore: false }) {
  if (!Array.isArray(rawTickets)) return { complete: false };
  const totalCount = rawTickets.length;
  const activeTickets = rawTickets.filter((t) => t.terminal_at_ms === null);
  const completedTickets = rawTickets.filter((t) => t.terminal_at_ms !== null);

  let winCount = 0;
  let lossCount = 0;
  let sumPnl = 0;
  let pnlEvaluatedCount = 0;
  let sumR = 0;
  let rEvaluatedCount = 0;

  for (const t of completedTickets) {
    const netRVal =
      t.net_r?.value !== null && t.net_r?.value !== undefined && t.net_r?.unavailable_reason !== 'ticket_active'
        ? Number(t.net_r.value)
        : null;
    if (netRVal !== null && !isNaN(netRVal)) {
      if (netRVal > 0) winCount++;
      else if (netRVal < 0) lossCount++;
      sumR += netRVal;
      rEvaluatedCount++;
    }

    const netPnlVal =
      t.net_pnl?.value !== null && t.net_pnl?.value !== undefined && t.net_pnl?.unavailable_reason !== 'ticket_active'
        ? Number(t.net_pnl.value)
        : null;
    if (netPnlVal !== null && !isNaN(netPnlVal)) {
      sumPnl += netPnlVal;
      pnlEvaluatedCount++;
    }
  }

  const evaluatedTradesCount = winCount + lossCount;
  const excludedFromWinRate = completedTickets.length - evaluatedTradesCount;
  const winRatePercent = evaluatedTradesCount > 0 ? Math.round((winCount / evaluatedTradesCount) * 100) : null;
  const hasMore = Boolean(pagination?.hasMore);

  const scopeLabel =
    totalCount === 0
      ? '暂无数据'
      : hasMore
      ? '已加载范围统计 (尚有未加载数据)'
      : `已加载全量账本 · 共 ${totalCount} 笔`;

  const winRateDenominatorText =
    completedTickets.length === 0
      ? '暂无历史平仓'
      : evaluatedTradesCount > 0
      ? excludedFromWinRate > 0
        ? `基准: ${winCount} 胜 / ${lossCount} 负 (排除 ${excludedFromWinRate} 笔平保/未评)`
        : `基准: ${winCount} 胜 / ${lossCount} 负 (全量评估)`
      : `未产生胜负评定 (${completedTickets.length} 笔平保或未评)`;

  const hasPnlGaps = completedTickets.length > 0 && pnlEvaluatedCount < completedTickets.length;
  const pnlCoverageText =
    completedTickets.length === 0
      ? '暂无历史记录'
      : hasPnlGaps
      ? `已记录合计 · 覆盖 ${pnlEvaluatedCount}/${completedTickets.length} 笔 (存在缺口)`
      : `全量结清 · 覆盖 ${completedTickets.length} 笔`;

  const hasRGaps = completedTickets.length > 0 && rEvaluatedCount < completedTickets.length;
  const rCoverageText =
    completedTickets.length === 0
      ? '暂无历史记录'
      : hasRGaps
      ? `已记录合计 · 覆盖 ${rEvaluatedCount}/${completedTickets.length} 笔 (存在缺口)`
      : `单位风险倍数 (R) · 覆盖 ${completedTickets.length} 笔`;

  const formattedPnl =
    pnlEvaluatedCount > 0
      ? `${sumPnl > 0 ? '+' : ''}${sumPnl.toLocaleString('en-US', {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })} USDT`
      : '—';

  const formattedR =
    rEvaluatedCount > 0
      ? `${sumR > 0 ? '+' : ''}${sumR.toLocaleString('en-US', {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })} R`
      : '—';

  return {
    complete: true,
    totalCount,
    activeCount: activeTickets.length,
    completedCount: completedTickets.length,
    winCount,
    lossCount,
    evaluatedTradesCount,
    excludedFromWinRate,
    winRatePercent,
    winRateDisplay: `${completedTickets.length} (${winRatePercent != null ? `${winRatePercent}%` : '—'})`,
    formattedPnl,
    formattedR,
    scopeLabel,
    winRateDenominatorText,
    pnlCoverageText,
    rCoverageText,
    hasPnlGaps,
    hasRGaps,
  };
}

