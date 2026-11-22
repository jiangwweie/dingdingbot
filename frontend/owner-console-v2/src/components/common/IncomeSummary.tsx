import type { PerformanceSummary, ExitScope } from '../../api/performanceApi';
import { formatReviewMoneyMetric } from '../../mapping/reviewMapping';
import { formatShanghaiRangeDisplay } from '../../utils/timeRange';

const scopes: [ExitScope, string][] = [
  ['all', '全部实际交易'],
  ['strategy', '策略自身退出'],
  ['owner', 'Owner 平仓'],
  ['safety', '安全恢复退出'],
  ['unknown', '退出原因未知'],
];

export function IncomeScopeBar({
  view = 'all',
  scope = 'all',
  onChange,
}: {
  view?: 'all' | 'current';
  scope?: ExitScope;
  onChange: (patch: { view?: 'all' | 'current'; exit_scope?: ExitScope }) => void;
}) {
  const hasScopeParams =
    typeof window !== 'undefined' &&
    ['strategy_group_id', 'strategy_version_id', 'exchange_instrument_id', 'position_side'].some((key) =>
      new URLSearchParams(window.location.search).has(key)
    );

  return (
    <div className="flex flex-wrap items-center gap-3 text-xs" data-testid="income-scope-bar">
      <label className="inline-flex items-center gap-1.5 text-text-secondary">
        <span>收益范围</span>
        <select
          aria-label="收益范围"
          value={scope}
          onChange={(e) => onChange({ exit_scope: e.target.value as ExitScope })}
          className="h-7 rounded border border-border bg-surface-subtle px-2 text-xs text-text-primary focus:border-brand focus:outline-none"
        >
          {scopes.map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
      </label>

      <label className="inline-flex items-center gap-1.5 text-text-secondary">
        <span>版本范围</span>
        <select
          aria-label="版本范围"
          value={view}
          onChange={(e) => onChange({ view: e.target.value as 'all' | 'current' })}
          className="h-7 rounded border border-border bg-surface-subtle px-2 text-xs text-text-primary focus:border-brand focus:outline-none"
        >
          <option value="all">全部版本</option>
          <option value="current">仅当前版本</option>
        </select>
      </label>

      {hasScopeParams && (
        <span className="text-text-muted">
          对账限定：
          {['strategy_group_id', 'strategy_version_id', 'exchange_instrument_id', 'position_side']
            .map((key) => new URLSearchParams(window.location.search).get(key))
            .filter(Boolean)
            .join(' · ')}{' '}
          <a
            className="underline text-brand"
            href={(() => {
              const q = new URLSearchParams(window.location.search);
              for (const key of [
                'strategy_group_id',
                'strategy_version_id',
                'exchange_instrument_id',
                'position_side',
                'drawer_tab',
              ]) {
                q.delete(key);
              }
              return `?${q}`;
            })()}
          >
            清除对账限定
          </a>
        </span>
      )}

      <span className="text-[11px] text-text-muted">
        上海时间 · 按交易终态归属 · 不含未成交终止与未结浮盈
      </span>
    </div>
  );
}

export function IncomeSummary({
  summary,
  error,
  onRefresh,
  onSelectTicket,
}: {
  summary: PerformanceSummary | null;
  error?: unknown;
  onRefresh: () => void;
  onSelectTicket?: (id: string) => void;
}) {
  if (error) {
    return (
      <div role="alert" className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 text-xs">
        全窗口收益统计读取失败，不能以已加载明细代替总额。
        {error instanceof Error ? ` ${error.message}` : ''}
        <button type="button" onClick={onRefresh} className="ml-2 underline font-semibold text-brand cursor-pointer">
          刷新整组数据
        </button>
      </div>
    );
  }
  if (!summary) {
    return (
      <div role="status" className="rounded-lg border border-border bg-surface p-3 text-xs text-text-muted">
        正在统计完整筛选范围...
      </div>
    );
  }

  const netPnl = formatReviewMoneyMetric(summary.verified_totals.net_pnl, { sign: true, fractionDigits: 2 });
  const netR = formatReviewMoneyMetric(summary.verified_totals.net_r, { sign: true, fractionDigits: 4 });
  const pnlCov = summary.metric_coverage.net_pnl;
  const rCov = summary.metric_coverage.net_r;
  const pnlPartial = pnlCov && pnlCov.available_count < pnlCov.total_count;
  const rPartial = rCov && rCov.available_count < rCov.total_count;
  const unconfirmedCount = Math.max(0, summary.sample_count - summary.confirmed_count);

  const detailLabels = [
    ['fees', '手续费'],
    ['funding', '资金费'],
  ] as const;

  const allMissingIds = Array.from(
    new Set(Object.values(summary.metric_coverage).flatMap((c) => c?.missing_ticket_ids ?? []))
  );

  return (
    <section
      data-testid="income-summary"
      className="rounded-lg border border-border bg-surface px-4 py-3 shadow-xs space-y-2"
    >
      {/* Compact Single-Line Primary Summary */}
      <details className="group">
        <summary className="cursor-pointer select-none list-none flex flex-wrap items-center justify-between gap-3 text-xs focus-visible:outline-2 focus-visible:outline-brand rounded">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
            <span className="rounded bg-surface-subtle border border-border px-2 py-0.5 text-[11px] font-medium text-text-secondary">
              {scopes.find(([key]) => key === summary.exit_scope)?.[1] ?? '全部实际交易'}
            </span>
            <div className="flex items-baseline gap-1.5">
              <span className="text-text-muted">全窗口终态交易</span>
              <strong className="font-mono text-base text-text-primary">{summary.sample_count}</strong>
              <span className="text-[11px] text-text-muted">笔</span>
              {unconfirmedCount > 0 && (
                <span className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:text-amber-300 border border-amber-500/30">
                  未核实 {unconfirmedCount}
                </span>
              )}
            </div>

            <div data-testid="income-net_pnl" className="flex items-baseline gap-1.5">
              <span className="text-text-muted">已核实净收益</span>
              <strong
                className={`font-mono text-base ${
                  netPnl.isPositive === true
                    ? 'text-emerald-600 dark:text-emerald-400'
                    : netPnl.isPositive === false
                    ? 'text-rose-600 dark:text-rose-400'
                    : 'text-text-secondary'
                }`}
              >
                {netPnl.formatted}
              </strong>
              {pnlCov && (
                <span
                  className={`text-[10px] px-1.5 py-0.5 rounded border ${
                    pnlPartial
                      ? 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/30 font-semibold'
                      : 'bg-surface-subtle text-text-muted border-border'
                  }`}
                >
                  {pnlPartial ? `部分合计 ${pnlCov.available_count}/${pnlCov.total_count}` : `核实 ${pnlCov.available_count}/${pnlCov.total_count}`}
                </span>
              )}
            </div>

            <div data-testid="income-net_r" className="flex items-baseline gap-1.5">
              <span className="text-text-muted">单笔净 R 合计</span>
              <strong
                className={`font-mono text-base ${
                  netR.isPositive === true
                    ? 'text-emerald-600 dark:text-emerald-400'
                    : netR.isPositive === false
                    ? 'text-rose-600 dark:text-rose-400'
                    : 'text-text-secondary'
                }`}
              >
                {netR.formatted}
              </strong>
              {rCov && (
                <span
                  className={`text-[10px] px-1.5 py-0.5 rounded border ${
                    rPartial
                      ? 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/30 font-semibold'
                      : 'bg-surface-subtle text-text-muted border-border'
                  }`}
                >
                  {rPartial ? `部分合计 ${rCov.available_count}/${rCov.total_count}` : `核实 ${rCov.available_count}/${rCov.total_count}`}
                </span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {allMissingIds.length > 0 && (
              <span className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:text-amber-300 border border-amber-500/30">
                缺项 {allMissingIds.length} 笔
              </span>
            )}
            <span className="text-[11px] font-semibold text-brand group-open:hidden">
              收益详情 ›
            </span>
            <span className="text-[11px] font-semibold text-text-muted hidden group-open:inline">
              收起详情 ‹
            </span>
          </div>
        </summary>

        {/* Tier 2 & 3: Fees, Funding, Missing Tickets, Breakdown, Scope Note & Snapshot */}
        <div className="mt-3 pt-3 border-t border-border/80 space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5 text-xs">
            <div className="rounded border border-border bg-surface-subtle/60 p-2.5">
              <div className="text-text-muted">全窗口核算完整度</div>
              <div className="mt-1 font-mono font-semibold text-text-primary">
                完整 {summary.confirmed_count} · 未核实 {unconfirmedCount}
              </div>
            </div>

            {detailLabels.map(([key, label]) => {
              const metric = summary.verified_totals[key];
              const coverage = summary.metric_coverage[key];
              const money = formatReviewMoneyMetric(metric, { sign: false, fractionDigits: 2 });
              return (
                <div key={key} data-testid={`income-${key}`} className="rounded border border-border bg-surface-subtle/60 p-2.5">
                  <div className="text-text-muted">{label}</div>
                  <div
                    className={`mt-1 font-mono font-bold ${
                      money.isPositive === true
                        ? 'text-emerald-600 dark:text-emerald-400'
                        : money.isPositive === false
                        ? 'text-rose-600 dark:text-rose-400'
                        : 'text-text-secondary'
                    }`}
                  >
                    {money.formatted}
                  </div>
                  <div className="mt-0.5 text-[10px] text-text-muted">
                    {coverage.available_count < coverage.total_count ? '已核实部分合计' : '已核实合计'} · 覆盖{' '}
                    {coverage.available_count}/{coverage.total_count} 笔
                  </div>
                </div>
              );
            })}

            {allMissingIds.length > 0 && (
              <div className="rounded border border-amber-500/30 bg-amber-500/5 p-2.5">
                <div className="font-semibold text-amber-700 dark:text-amber-300">缺项交易直达</div>
                <div className="mt-1 space-y-1 max-h-24 overflow-y-auto">
                  {allMissingIds.map((id) => (
                    <button
                      key={id}
                      type="button"
                      onClick={() => onSelectTicket?.(id)}
                      className="block w-full text-left font-mono text-[11px] text-brand underline hover:text-brand-hover break-all cursor-pointer"
                    >
                      {id}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
            {scopes.slice(1).map(([kind, label]) => {
              const part = summary.breakdown[kind];
              return (
                <div key={kind} className="rounded border border-border bg-surface-subtle/50 p-2 text-xs">
                  <strong className="text-text-primary">{label}</strong>
                  <div className="mt-0.5 text-text-secondary">
                    {part.sample_count} 笔 · 已核实净额{' '}
                    <span className="font-mono font-semibold">
                      {formatReviewMoneyMetric(part.verified_totals.net_pnl, { sign: true }).formatted}
                    </span>
                  </div>
                  <div className="text-[10px] text-text-muted">
                    核算覆盖 {part.confirmed_count}/{part.sample_count}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-text-muted">
            <p data-testid="income-scope-note">
              全窗口统计，与明细分页无关。{scopes.find(([key]) => key === summary.exit_scope)?.[1]} ·{' '}
              {summary.view === 'all' ? '全部版本' : '仅当前版本'} ·{' '}
              {formatShanghaiRangeDisplay(summary.from_ms, summary.to_ms)}。缺失费用不按 0 计算；累计单笔净 R 不是账户收益率。
            </p>
            <span className="font-mono text-[10px] break-all">统计快照: {summary.snapshot_id}</span>
          </div>
        </div>
      </details>
    </section>
  );
}
