import { Badge, Card, EnvelopeStatus, PageHeader, PageSummary } from '@/components/ui';
import { asArray, displayValue, useReadModel } from '@/lib/tradingConsoleApi';
import { blockingReasonLabel, pageSummaryFromEnvelope } from '@/lib/ownerViewModel';

function capitalClassificationLabel(value?: string): string {
  const map: Record<string, string> = {
    explained_by_trading_only: '交易 PnL 已解释',
    explained_by_owner_capital_events: 'Owner 资金事件已解释',
    explained_by_trading_and_owner_capital_events: '交易与资金事件已解释',
    unresolved_equity_delta: '权益差额未解释',
    invalid_capital_base: '资本基准异常',
    not_reviewed_missing_inputs: '待补复盘事实',
  };
  return map[value || ''] || displayValue(value, '待补复盘事实');
}

function adjustmentTypeLabel(value?: string): string {
  const map: Record<string, string> = {
    owner_manual_withdrawal: '手动提现',
    manual_profit_extraction: '盈利提取',
    owner_capital_injection: '资金注入',
    capital_base_reset: '基准重置',
  };
  return map[value || ''] || displayValue(value, '资金事件');
}

function rightTailStatusLabel(value?: string): string {
  const map: Record<string, string> = {
    reviewed: '已复盘',
    review_inputs_required: '待补路径事实',
    empty: '暂无路径事实',
  };
  return map[value || ''] || displayValue(value, '待补路径事实');
}

function rightTailClassificationLabel(value?: string): string {
  const map: Record<string, string> = {
    right_tail_win: '右尾胜笔',
    ordinary_win: '普通盈利',
    small_bounded_loss: '预算内小亏',
    loss_boundary_breach: '亏损越界',
    flat_or_cost: '持平/成本',
    review_inputs_required: '待补事实',
  };
  return map[value || ''] || displayValue(value, '待补事实');
}

function statusVariant(value?: string): 'normal' | 'warning' | 'danger' | 'caution' | 'muted' {
  if (value === 'reviewed') return 'normal';
  if (value?.startsWith('explained_by_')) return 'normal';
  if (value === 'right_tail_win' || value === 'small_bounded_loss') return 'normal';
  if (value === 'ordinary_win' || value === 'flat_or_cost' || value === 'empty') return 'muted';
  if (value === 'loss_boundary_breach') return 'danger';
  if (value === 'unresolved_equity_delta' || value === 'invalid_capital_base') return 'danger';
  if (value === 'review_inputs_required' || value === 'not_reviewed_missing_inputs') return 'warning';
  return 'caution';
}

export default function ReviewState() {
  const { envelope, loading, error } = useReadModel<any>('/api/trading-console/review-state');

  if (loading) return <div className="p-4 text-sm text-slate-500">正在读取当前内容...</div>;

  const pageData = envelope?.data || {};
  const reviews = asArray(pageData.reviews);
  const filledOrderFacts = asArray(pageData.filled_order_facts);
  const positions = asArray(pageData.positions);
  const ownerCapitalReview = pageData.owner_capital_base_review || {};
  const capitalReviewResult = ownerCapitalReview.review_result || {};
  const ownerCapitalRecords = asArray(ownerCapitalReview.records);
  const requiredInputs = asArray<string>(ownerCapitalReview.required_inputs);
  const rightTailReview = pageData.right_tail_review || {};
  const rightTailTrades = asArray(rightTailReview.trade_reviews);
  const rightTailRequiredInputs = asArray<string>(rightTailReview.required_inputs);
  const summary = pageSummaryFromEnvelope(envelope, reviews.length === 0 ? '当前没有复盘记录。' : '已有复盘记录可查看。');

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <PageHeader title="实盘复盘" subtitle="查看实盘行动结果、成交、保护和系统链路问题。" status={envelope?.freshness_status} />

      <PageSummary mood={summary.mood} title={summary.title} description={summary.description} />
      <EnvelopeStatus envelope={envelope} error={error} />

      <Card className="p-4">
        <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <h2 className="text-base font-medium">资金基准</h2>
            <p className="mt-1 text-sm text-slate-500">Owner 资金动作、交易 PnL 和未解释权益差额分开复盘。</p>
          </div>
          <Badge variant={statusVariant(ownerCapitalReview.status === 'reviewed' ? ownerCapitalReview.classification : ownerCapitalReview.status)}>
            {capitalClassificationLabel(ownerCapitalReview.classification)}
          </Badge>
        </div>

        <div className="grid grid-cols-1 gap-3 text-sm md:grid-cols-4">
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">
            <div className="text-xs text-slate-500">Owner flow</div>
            <div className="mt-1 font-mono text-base">{displayValue(capitalReviewResult.owner_equity_flow_delta, '暂无')}</div>
          </div>
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">
            <div className="text-xs text-slate-500">Trading PnL</div>
            <div className="mt-1 font-mono text-base">{displayValue(capitalReviewResult.realized_trading_pnl, ownerCapitalReview.input_facts?.realized_trading_pnl || '0')}</div>
          </div>
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">
            <div className="text-xs text-slate-500">Capital base</div>
            <div className="mt-1 font-mono text-base">{displayValue(ownerCapitalReview.ending_capital_base, '暂无')}</div>
          </div>
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">
            <div className="text-xs text-slate-500">Unexplained</div>
            <div className="mt-1 font-mono text-base">{displayValue(ownerCapitalReview.unexplained_account_equity_delta, '暂无')}</div>
          </div>
        </div>

        {requiredInputs.length > 0 && (
          <div className="mt-3 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200">
            待补事实：{requiredInputs.join(' / ')}
          </div>
        )}

        <div className="mt-4">
          <div className="mb-2 flex items-center justify-between text-sm">
            <span className="font-medium">Owner 资金记录</span>
            <span className="text-slate-500">{ownerCapitalRecords.length} 条</span>
          </div>
          {ownerCapitalRecords.length === 0 ? (
            <div className="rounded border border-dashed border-slate-200 py-6 text-center text-sm text-slate-500 dark:border-slate-800">当前没有 Owner 资金记录</div>
          ) : (
            <div className="space-y-2">
              {ownerCapitalRecords.slice(0, 5).map((record: any) => (
                <div key={record.adjustment_id} className="grid grid-cols-1 gap-2 rounded-md border border-slate-200 p-3 text-sm dark:border-slate-800 md:grid-cols-[1fr_0.7fr_0.7fr]">
                  <div>
                    <div className="font-medium">{adjustmentTypeLabel(record.adjustment_type)}</div>
                    <div className="mt-1 text-slate-600 dark:text-slate-400">{displayValue(record.reason, '暂无说明')}</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">金额</div>
                    <div className="mt-1 font-mono">{displayValue(record.amount || record.target_capital_base, '暂无')}</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">记录人</div>
                    <div className="mt-1">{displayValue(record.recorded_by, 'owner')}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </Card>

      <Card className="p-4">
        <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <h2 className="text-base font-medium">右尾复盘</h2>
            <p className="mt-1 text-sm text-slate-500">MFE / MAE、R multiple、小亏覆盖和 runner 结果。</p>
          </div>
          <Badge variant={statusVariant(rightTailReview.status)}>
            {rightTailStatusLabel(rightTailReview.status)}
          </Badge>
        </div>

        <div className="grid grid-cols-1 gap-3 text-sm md:grid-cols-5">
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">
            <div className="text-xs text-slate-500">Tail wins</div>
            <div className="mt-1 font-mono text-base">{displayValue(rightTailReview.right_tail_win_count, '0')}</div>
          </div>
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">
            <div className="text-xs text-slate-500">Small losses</div>
            <div className="mt-1 font-mono text-base">{displayValue(rightTailReview.small_loss_count, '0')}</div>
          </div>
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">
            <div className="text-xs text-slate-500">Max R</div>
            <div className="mt-1 font-mono text-base">{displayValue(rightTailReview.max_r_multiple, '暂无')}</div>
          </div>
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">
            <div className="text-xs text-slate-500">Max MFE</div>
            <div className="mt-1 font-mono text-base">{displayValue(rightTailReview.max_mfe_pct, '暂无')}</div>
          </div>
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">
            <div className="text-xs text-slate-500">Tail covers</div>
            <div className="mt-1 font-mono text-base">{displayValue(rightTailReview.single_tail_win_covers_small_losses, '暂无')}</div>
          </div>
        </div>

        {rightTailRequiredInputs.length > 0 && (
          <div className="mt-3 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200">
            待补路径事实：{rightTailRequiredInputs.join(' / ')}
          </div>
        )}

        <div className="mt-4">
          <div className="mb-2 flex items-center justify-between text-sm">
            <span className="font-medium">交易路径</span>
            <span className="text-slate-500">{rightTailTrades.length} 条</span>
          </div>
          {rightTailTrades.length === 0 ? (
            <div className="rounded border border-dashed border-slate-200 py-6 text-center text-sm text-slate-500 dark:border-slate-800">当前没有右尾路径事实</div>
          ) : (
            <div className="space-y-2">
              {rightTailTrades.slice(0, 5).map((trade: any) => (
                <div key={trade.trade_id} className="grid grid-cols-1 gap-2 rounded-md border border-slate-200 p-3 text-sm dark:border-slate-800 md:grid-cols-[1fr_0.6fr_0.6fr_0.6fr]">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{displayValue(trade.symbol, '未知标的')}</span>
                      <Badge variant={statusVariant(trade.classification)}>{rightTailClassificationLabel(trade.classification)}</Badge>
                    </div>
                    <div className="mt-1 text-slate-600 dark:text-slate-400">{displayValue(trade.strategy_family_id, '未绑定策略')}</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">MFE / MAE</div>
                    <div className="mt-1 font-mono">{displayValue(trade.mfe_pct, '暂无')} / {displayValue(trade.mae_pct, '暂无')}</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">R</div>
                    <div className="mt-1 font-mono">{displayValue(trade.r_multiple, '暂无')}</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">Runner</div>
                    <div className="mt-1">{trade.runner_capped_too_early === true ? '过早截断' : trade.runner_capped_too_early === false ? '未截断' : '待评估'}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </Card>

      <Card className="p-4">
        <h2 className="text-base font-medium mb-3">成本信息</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">手续费：暂无</div>
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">资金费率：暂无</div>
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">滑点：暂无</div>
        </div>
      </Card>

      <Card className="p-6">
        <h2 className="text-lg font-medium mb-4">复盘记录</h2>
        {reviews.length === 0 ? (
          <div className="text-center text-sm text-slate-500 py-8 border border-dashed border-slate-200 dark:border-slate-800 rounded">当前没有复盘记录</div>
        ) : (
          <div className="space-y-4">
            {reviews.map((review: any, i: number) => (
              <div key={i} className="border border-slate-200 dark:border-slate-800 p-4 rounded-md">
                <div className="text-sm font-semibold mb-2">结果：{displayValue(review.result || review.status, '未完成')}</div>
                <div className="text-sm text-slate-600 dark:text-slate-400">原因：{blockingReasonLabel(review.reason || review.blocker || review.summary || '暂无说明')}</div>
                <div className="text-sm text-slate-600 dark:text-slate-400 mt-1">影响：{displayValue(review.impact, '未确认完整执行结果')}</div>
                <div className="text-sm text-slate-600 dark:text-slate-400 mt-1">建议：查看技术审计</div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card className="p-4">
          <h2 className="text-base font-medium mb-4">已成交订单</h2>
          {filledOrderFacts.length === 0 ? (
            <div className="text-sm text-slate-500 text-center py-6 border border-dashed border-slate-200 dark:border-slate-800 rounded-lg">无相关成交</div>
          ) : (
            <div className="text-sm text-slate-500">已聚合成交订单：{filledOrderFacts.length}</div>
          )}
        </Card>

        <Card className="p-4">
          <h2 className="text-base font-medium mb-4">关联仓位</h2>
          {positions.length === 0 ? (
            <div className="text-sm text-slate-500 text-center py-6 border border-dashed border-slate-200 dark:border-slate-800 rounded-lg">无关联仓位</div>
          ) : (
            <div className="text-sm text-slate-500">已关联仓位：{positions.length}</div>
          )}
        </Card>
      </div>
    </div>
  );
}
