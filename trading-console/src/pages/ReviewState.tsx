import { Link } from 'react-router-dom';
import type { ReactNode } from 'react';
import { BarChart3, FileSearch, ListChecks, WalletCards } from 'lucide-react';
import {
  ActionNudge,
  ConsolePanel,
  EntityRow,
  InspectorPanel,
  MetricRailItem,
  StatusChip,
  type ConsoleTone,
} from '@/components/console/ConsolePrimitives';
import { EnvelopeStatus, TechnicalDetails } from '@/components/ui';
import { asArray, displayValue, formatTimestampMs, isNotAvailable, useReadModel } from '@/lib/tradingConsoleApi';
import { blockingReasonLabel, sideLabel } from '@/lib/ownerViewModel';

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

function analysisTone(value?: string): ConsoleTone {
  if (value === 'reviewed') return 'normal';
  if (value?.startsWith('explained_by_')) return 'normal';
  if (value === 'right_tail_win' || value === 'small_bounded_loss') return 'normal';
  if (value === 'ordinary_win' || value === 'flat_or_cost' || value === 'empty') return 'unavailable';
  if (value === 'loss_boundary_breach' || value === 'unresolved_equity_delta' || value === 'invalid_capital_base') return 'intervention';
  if (value === 'review_inputs_required' || value === 'not_reviewed_missing_inputs') return 'attention';
  return 'attention';
}

function metricValue(value: unknown, fallback = '暂无'): string {
  if (isNotAvailable(value)) return fallback;
  if (typeof value === 'boolean') return value ? '是' : '否';
  return String(value);
}

function percentValue(value: unknown): string {
  if (isNotAvailable(value)) return '暂无';
  const text = String(value);
  return text.endsWith('%') ? text : `${text}%`;
}

function boolSignal(value: unknown, trueLabel = '成立', falseLabel = '未成立', fallback = '待评估'): string {
  if (value === true) return trueLabel;
  if (value === false) return falseLabel;
  return fallback;
}

function firstPresent(...values: unknown[]): unknown {
  return values.find((value) => !isNotAvailable(value));
}

export default function ReviewState() {
  const { envelope, loading, error } = useReadModel<any>('/api/trading-console/review-state?include_exchange=false');

  if (loading) {
    return (
      <div className="flex min-h-[480px] items-center justify-center rounded-md border border-slate-800 bg-slate-900/50 text-sm text-slate-400">
        正在读取分析数据...
      </div>
    );
  }

  const pageData = envelope?.data || {};
  const reviews = asArray(pageData.reviews);
  const liveLifecycleReviews = asArray(pageData.live_lifecycle_reviews);
  const filledOrderFacts = asArray(pageData.filled_order_facts);
  const positions = asArray(pageData.positions);
  const ownerCapitalReview = pageData.owner_capital_base_review || {};
  const capitalReviewResult = ownerCapitalReview.review_result || {};
  const ownerCapitalRecords = asArray(ownerCapitalReview.records);
  const requiredInputs = asArray<string>(ownerCapitalReview.required_inputs);
  const rightTailReview = pageData.right_tail_review || {};
  const rightTailTrades = asArray(rightTailReview.trade_reviews);
  const rightTailRequiredInputs = asArray<string>(rightTailReview.required_inputs);
  const skippedSources = asArray(rightTailReview.skipped_sources);
  const semanticPackets = asArray(rightTailReview.closed_trade_review_packets);
  const packetSummary = rightTailReview.closed_trade_review_packet_summary || {};
  const unavailableFields = pageData.unavailable_fields || {};

  const pageTone: ConsoleTone = error
    ? 'intervention'
    : requiredInputs.length > 0 || rightTailRequiredInputs.length > 0
      ? 'attention'
      : analysisTone(rightTailReview.status);
  const capitalTone = analysisTone(ownerCapitalReview.status === 'reviewed' ? ownerCapitalReview.classification : ownerCapitalReview.status);
  const rightTailTone = analysisTone(rightTailReview.status);
  const selectedTrade = rightTailTrades[0] || null;

  const inspectorItems: Array<{ title: string; body: string; tone: ConsoleTone }> = [
    {
      title: '分析是检查面，不是强制复盘任务',
      body: '这里用于理解策略、订单、runtime 和资金基准的历史事实；缺失事实会显式展示，不要求每笔交易都有即时结论。',
      tone: pageTone,
    },
    {
      title: '右尾目标优先看收益结构',
      body: '指标围绕 MFE / MAE、R multiple、右尾赢家、小亏样本和单次右尾是否覆盖多次小亏，不把胜率或短期 PnL 当作唯一答案。',
      tone: rightTailTone,
    },
    {
      title: 'Owner 资金动作不等于策略亏损',
      body: '手动提现、盈利提取、资金注入和资本基准重置只进入复盘语义，不会发起提现、转账、订单或 runtime 预算变更。',
      tone: capitalTone,
    },
    {
      title: selectedTrade ? '已选交易路径来自显式元数据' : '暂无可选交易路径',
      body: selectedTrade
        ? '右尾路径只从 live lifecycle review metadata 的 right_tail_trade_path 读取，不从账户权益或提现记录倒推策略表现。'
        : '当前没有显式 right-tail trade-path 事实；系统保持观察，不猜测 alpha 或策略表现。',
      tone: selectedTrade ? 'normal' : 'unavailable',
    },
  ];

  return (
    <div className="mx-auto max-w-[1500px] space-y-4">
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusChip tone={pageTone}>{analysisStatusLabel(error, rightTailReview.status, requiredInputs.length + rightTailRequiredInputs.length)}</StatusChip>
            {envelope?.freshness_status && (
              <StatusChip tone={envelope.freshness_status === 'fresh' ? 'normal' : 'attention'}>
                {envelope.freshness_status === 'fresh' ? '已同步' : '部分同步'}
              </StatusChip>
            )}
          </div>
          <h1 className="mt-4 text-3xl font-semibold text-slate-100">分析</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
            检查右尾机会、小亏预算、交易路径和资金基准。分析页只读，不创建 ExecutionIntent、订单、提现、转账或 runtime 预算动作。
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <AnalysisSoftButton to="/trades">
            <ListChecks className="h-4 w-4" />
            交易与仓位
          </AnalysisSoftButton>
          <AnalysisSoftButton to="/evidence">
            <FileSearch className="h-4 w-4" />
            证据
          </AnalysisSoftButton>
        </div>
      </header>

      <EnvelopeStatus envelope={envelope} error={error} />

      {(requiredInputs.length > 0 || rightTailRequiredInputs.length > 0) && (
        <ActionNudge
          tone="attention"
          text={`分析仍缺少事实：${missingFactsSummary(requiredInputs, rightTailRequiredInputs)}`}
          action={<AnalysisSoftButton to="/evidence">查看证据</AnalysisSoftButton>}
        />
      )}

      <ConsolePanel>
        <div className="grid grid-cols-1 md:grid-cols-5">
          <MetricRailItem label="右尾胜笔" value={metricValue(rightTailReview.right_tail_win_count, '0')} tone={Number(rightTailReview.right_tail_win_count || 0) > 0 ? 'normal' : 'unavailable'} sub={`${metricValue(rightTailReview.trade_count, '0')} 条路径`} />
          <MetricRailItem label="小亏样本" value={metricValue(rightTailReview.small_loss_count, '0')} tone={Number(rightTailReview.small_loss_count || 0) > 0 ? 'attention' : 'unavailable'} sub="预算内可接受" />
          <MetricRailItem label="最大 R" value={metricValue(rightTailReview.max_r_multiple)} tone={isNotAvailable(rightTailReview.max_r_multiple) ? 'unavailable' : 'normal'} sub="收益偏度线索" />
          <MetricRailItem label="最大 MFE" value={percentValue(rightTailReview.max_mfe_pct)} tone={isNotAvailable(rightTailReview.max_mfe_pct) ? 'unavailable' : 'normal'} sub={`MAE ${percentValue(rightTailReview.max_mae_pct)}`} />
          <MetricRailItem label="资金事件" value={ownerCapitalRecords.length} tone={ownerCapitalRecords.length > 0 ? 'attention' : 'unavailable'} sub={capitalClassificationLabel(ownerCapitalReview.classification)} />
        </div>
      </ConsolePanel>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-4">
          <RightTailAnalysisPanel
            rightTailReview={rightTailReview}
            rightTailTrades={rightTailTrades}
            requiredInputs={rightTailRequiredInputs}
            skippedSources={skippedSources}
            semanticPackets={semanticPackets}
            packetSummary={packetSummary}
          />
          <CapitalBasePanel
            ownerCapitalReview={ownerCapitalReview}
            capitalReviewResult={capitalReviewResult}
            records={ownerCapitalRecords}
            requiredInputs={requiredInputs}
          />
          <TradeEvidencePanel
            reviews={reviews}
            liveLifecycleReviews={liveLifecycleReviews}
            filledOrderFacts={filledOrderFacts}
            positions={positions}
            unavailableFields={unavailableFields}
          />
        </div>

        <InspectorPanel
          title="分析说明"
          items={inspectorItems}
          footer={
            <div className="space-y-2 text-xs leading-5 text-slate-500">
              <div>数据来源：Trading Console GET readmodel。</div>
              <div>动作边界：无下单、无提现、无转账、无 exchange 写调用。</div>
            </div>
          }
        />
      </div>
    </div>
  );
}

function RightTailAnalysisPanel({
  rightTailReview,
  rightTailTrades,
  requiredInputs,
  skippedSources,
  semanticPackets,
  packetSummary,
}: {
  rightTailReview: any;
  rightTailTrades: any[];
  requiredInputs: string[];
  skippedSources: any[];
  semanticPackets: any[];
  packetSummary: Record<string, any>;
}) {
  return (
    <ConsolePanel
      title="右尾结构"
      caption="用明确 trade-path facts 检查 payoff asymmetry，不从账户权益倒推策略表现"
      action={<StatusChip tone={analysisTone(rightTailReview.status)}>{rightTailStatusLabel(rightTailReview.status)}</StatusChip>}
    >
      <div className="grid grid-cols-1 gap-0 border-b border-slate-800/90 md:grid-cols-4">
        <ValueTile label="Largest tail win" value={metricValue(firstPresent(rightTailReview.largest_tail_win, rightTailReview.max_realized_pnl))} />
        <ValueTile label="Payoff asymmetry" value={boolSignal(rightTailReview.payoff_asymmetry_present)} />
        <ValueTile label="Tail covers losses" value={boolSignal(rightTailReview.single_tail_win_covers_small_losses, '覆盖', '未覆盖')} />
        <ValueTile label="Review packets" value={metricValue(packetSummary.packet_count || semanticPackets.length, '0')} />
      </div>

      {requiredInputs.length > 0 && (
        <div className="border-b border-slate-800/90 px-4 py-3 text-sm text-amber-200">
          待补路径事实：{requiredInputs.join(' / ')}
        </div>
      )}

      {rightTailTrades.length === 0 ? (
        <EmptyState title="暂无右尾路径事实" body="没有显式 right_tail_trade_path metadata 时，分析保持观察，不推断赢家或小亏结构。" />
      ) : (
        <div>
          {rightTailTrades.slice(0, 6).map((trade: any) => (
            <div key={displayValue(trade.trade_id, trade.source_review_id)}>
              <EntityRow
              title={`${displayValue(trade.symbol, '未知标的')} · ${sideLabel(trade.side)}`}
              subtitle={displayValue(trade.strategy_family_id, '未绑定策略')}
              tone={analysisTone(trade.classification)}
              cells={[
                { label: '分类', value: rightTailClassificationLabel(trade.classification) },
                { label: 'MFE / MAE', value: `${percentValue(trade.mfe_pct)} / ${percentValue(trade.mae_pct)}`, className: 'font-mono' },
                { label: 'R', value: metricValue(trade.r_multiple), className: 'font-mono' },
                { label: 'Runner', value: boolSignal(trade.runner_capped_too_early, '过早截断', '未截断') },
              ]}
              action={<StatusChip tone={analysisTone(trade.classification)}>只读</StatusChip>}
              />
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 border-t border-slate-800/90 md:grid-cols-3">
        <ValueTile label="Skipped sources" value={skippedSources.length} />
        <ValueTile label="Source" value={displayValue(rightTailReview.source, 'explicit metadata only')} />
        <ValueTile label="Policy" value={displayValue(rightTailReview.required_metadata_shape?.source_policy, 'no inference')} />
      </div>
    </ConsolePanel>
  );
}

function CapitalBasePanel({
  ownerCapitalReview,
  capitalReviewResult,
  records,
  requiredInputs,
}: {
  ownerCapitalReview: any;
  capitalReviewResult: any;
  records: any[];
  requiredInputs: string[];
}) {
  return (
    <ConsolePanel
      title="资金基准"
      caption="区分 trading PnL、Owner 手动提现/注入和资本基准调整"
      action={
        <StatusChip tone={analysisTone(ownerCapitalReview.status === 'reviewed' ? ownerCapitalReview.classification : ownerCapitalReview.status)}>
          {capitalClassificationLabel(ownerCapitalReview.classification)}
        </StatusChip>
      }
    >
      <div className="grid grid-cols-1 border-b border-slate-800/90 md:grid-cols-4">
        <ValueTile label="Owner flow" value={metricValue(capitalReviewResult.owner_equity_flow_delta)} />
        <ValueTile label="Trading PnL" value={metricValue(firstPresent(capitalReviewResult.realized_trading_pnl, ownerCapitalReview.input_facts?.realized_trading_pnl, '0'))} />
        <ValueTile label="Capital base" value={metricValue(ownerCapitalReview.ending_capital_base)} />
        <ValueTile label="Unexplained" value={metricValue(ownerCapitalReview.unexplained_account_equity_delta)} />
      </div>

      {requiredInputs.length > 0 && (
        <div className="border-b border-slate-800/90 px-4 py-3 text-sm text-amber-200">
          待补资金事实：{requiredInputs.join(' / ')}
        </div>
      )}

      {records.length === 0 ? (
        <EmptyState title="暂无 Owner 资金记录" body="Owner 手动提现或注入发生后，可记录为复盘事实；系统不会自动发起提现或转账。" />
      ) : (
        <div>
          {records.slice(0, 5).map((record: any) => (
            <div key={displayValue(record.adjustment_id, `${record.adjustment_type}-${record.recorded_at_ms}`)}>
              <EntityRow
              title={adjustmentTypeLabel(record.adjustment_type)}
              subtitle={displayValue(record.reason, '暂无说明')}
              tone="attention"
              cells={[
                { label: '金额', value: metricValue(firstPresent(record.amount, record.target_capital_base)), className: 'font-mono' },
                { label: '币种', value: displayValue(record.currency, 'USDT') },
                { label: '记录人', value: displayValue(record.recorded_by, 'owner') },
                { label: '时间', value: formatTimestampMs(record.recorded_at_ms) },
              ]}
              action={<StatusChip tone="unavailable">资金事实</StatusChip>}
              />
            </div>
          ))}
        </div>
      )}

      <TechnicalDetails title="非执行保证">
        <pre className="overflow-auto whitespace-pre-wrap break-words font-mono">
          {JSON.stringify(ownerCapitalReview.no_action_guarantee || {}, null, 2)}
        </pre>
      </TechnicalDetails>
    </ConsolePanel>
  );
}

function TradeEvidencePanel({
  reviews,
  liveLifecycleReviews,
  filledOrderFacts,
  positions,
  unavailableFields,
}: {
  reviews: any[];
  liveLifecycleReviews: any[];
  filledOrderFacts: any[];
  positions: any[];
  unavailableFields: Record<string, any>;
}) {
  const unavailableEntries = Object.entries(unavailableFields);
  return (
    <ConsolePanel
      title="交易路径证据"
      caption="连接已成交订单、仓位、lifecycle review 和不可用成本字段"
      action={<StatusChip tone={filledOrderFacts.length > 0 || liveLifecycleReviews.length > 0 ? 'normal' : 'unavailable'}>只读证据</StatusChip>}
    >
      <div className="grid grid-cols-1 border-b border-slate-800/90 md:grid-cols-4">
        <ValueTile label="Review records" value={reviews.length} />
        <ValueTile label="Lifecycle reviews" value={liveLifecycleReviews.length} />
        <ValueTile label="Filled orders" value={filledOrderFacts.length} />
        <ValueTile label="Positions" value={positions.length} />
      </div>

      {filledOrderFacts.length === 0 && liveLifecycleReviews.length === 0 ? (
        <EmptyState title="暂无可分析交易路径" body="没有成交或 lifecycle review 时，分析页只展示准备状态和缺失事实，不要求 Owner 完成复盘任务。" />
      ) : (
        <div>
          {[...liveLifecycleReviews.slice(0, 3), ...filledOrderFacts.slice(0, 3)].slice(0, 6).map((item: any, index) => (
            <div key={displayValue(item.review_id || item.order_id || item.exchange_order_id, `evidence-${index}`)}>
              <EntityRow
              title={displayValue(item.symbol, '未知标的')}
              subtitle={displayValue(item.review_id || item.order_id || item.exchange_order_id, '暂无链路 ID')}
              tone="unavailable"
              cells={[
                { label: '方向', value: sideLabel(item.side || item.direction) },
                { label: '状态', value: displayValue(item.status || item.result, '待确认') },
                { label: '价格', value: metricValue(firstPresent(item.average_exec_price, item.price, item.entry_price)) },
                { label: '时间', value: formatTimestampMs(item.updated_at || item.created_at || item.closed_at_ms) },
              ]}
              action={<StatusChip tone="unavailable">证据</StatusChip>}
              />
            </div>
          ))}
        </div>
      )}

      <div className="border-t border-slate-800/90 px-4 py-4">
        <div className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-100">
          <BarChart3 className="h-4 w-4 text-slate-400" />
          成本与滑点可用性
        </div>
        <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
          {unavailableEntries.length === 0 ? (
            <div className="text-sm text-slate-500">暂无不可用字段报告</div>
          ) : (
            unavailableEntries.map(([key, value]) => (
              <div key={key} className="rounded-md border border-slate-800 bg-slate-900/40 px-3 py-2 text-sm">
                <div className="text-xs text-slate-500">{key}</div>
                <div className="mt-1 text-slate-300">{unavailableFieldLabel(value)}</div>
              </div>
            ))
          )}
        </div>
      </div>
    </ConsolePanel>
  );
}

function ValueTile({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="min-h-20 border-b border-r border-slate-800/90 px-4 py-4 last:border-r-0 md:border-b-0">
      <div className="text-[11px] font-medium uppercase text-slate-500">{label}</div>
      <div className="mt-2 min-w-0 truncate font-mono text-lg font-semibold text-slate-100">{metricValue(value)}</div>
    </div>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="px-4 py-7 text-center">
      <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full border border-slate-800 bg-slate-900/50">
        <WalletCards className="h-4 w-4 text-slate-500" />
      </div>
      <div className="mt-3 text-sm font-medium text-slate-200">{title}</div>
      <p className="mx-auto mt-1 max-w-md text-xs leading-5 text-slate-500">{body}</p>
    </div>
  );
}

function AnalysisSoftButton({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link
      to={to}
      className="inline-flex min-h-9 items-center gap-2 rounded-md border border-slate-700 bg-slate-900/70 px-3 py-2 text-sm text-slate-300 transition hover:bg-slate-800 hover:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
    >
      {children}
    </Link>
  );
}

function analysisStatusLabel(error: string | null, rightTailStatus: string | undefined, missingCount: number): string {
  if (error) return '分析暂不可用';
  if (missingCount > 0) return '缺少事实';
  if (rightTailStatus === 'reviewed') return '可分析';
  if (rightTailStatus === 'empty') return '观察中';
  return '待补事实';
}

function missingFactsSummary(capitalInputs: string[], rightTailInputs: string[]): string {
  const labels = new Set<string>();
  if (capitalInputs.some((item) => item.includes('account_equity'))) labels.add('账户权益');
  if (capitalInputs.some((item) => item.includes('capital_base'))) labels.add('资本基准');
  if (rightTailInputs.length > 0) labels.add('右尾交易路径');
  capitalInputs
    .filter((item) => !item.includes('account_equity') && !item.includes('capital_base'))
    .forEach((item) => labels.add(item));
  return Array.from(labels).join(' / ') || '待补事实';
}

function unavailableFieldLabel(value: unknown): string {
  if (value === 'not_available' || value === 'unknown' || value === null || value === undefined) return '暂无数据';
  return blockingReasonLabel(String(value));
}
