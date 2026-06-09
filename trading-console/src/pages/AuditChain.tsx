import { Link } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useMemo, useState } from 'react';
import { BarChart3, FileSearch, ListChecks, RotateCcw, Search, ShieldAlert } from 'lucide-react';
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
import {
  blockingReasonLabel,
  orderRoleLabel,
  orderStatusLabel,
  sideLabel,
} from '@/lib/ownerViewModel';

type EvidenceFilters = {
  authorization_id: string;
  runtime_instance_id: string;
  trial_binding_id: string;
  strategy_family_id: string;
  strategy_family_version_id: string;
  signal_evaluation_id: string;
  order_candidate_id: string;
  intent_id: string;
  order_id: string;
  exchange_order_id: string;
  symbol: string;
  limit: string;
};

const EMPTY_FILTERS: EvidenceFilters = {
  authorization_id: '',
  runtime_instance_id: '',
  trial_binding_id: '',
  strategy_family_id: '',
  strategy_family_version_id: '',
  signal_evaluation_id: '',
  order_candidate_id: '',
  intent_id: '',
  order_id: '',
  exchange_order_id: '',
  symbol: '',
  limit: '100',
};

const TRACE_FIELDS = [
  ['runtime_instance_id', 'Runtime'] as const,
  ['trial_binding_id', 'TrialBinding'] as const,
  ['strategy_family_version_id', 'StrategyVersion'] as const,
  ['signal_evaluation_id', 'SignalEvaluation'] as const,
  ['order_candidate_id', 'OrderCandidate'] as const,
];

function buildAuditPath(filters: EvidenceFilters): string {
  const params = new URLSearchParams();
  for (const [key, rawValue] of Object.entries(filters)) {
    const value = rawValue.trim();
    if (!value) continue;
    params.set(key, value);
  }
  const suffix = params.toString();
  return `/api/trading-console/audit-chain${suffix ? `?${suffix}` : ''}`;
}

function pageTone(params: {
  error: string | null;
  unavailableCount: number;
  recordCount: number;
  auditEvents: number;
  semanticCompleteness: number;
}): ConsoleTone {
  if (params.error) return 'intervention';
  if (params.unavailableCount > 0) return 'attention';
  if (params.recordCount === 0) return 'unavailable';
  if (params.auditEvents === 0 || params.semanticCompleteness < 0.5) return 'attention';
  return 'normal';
}

function objectTone(item: any): ConsoleTone {
  const status = String(item.status || item.lifecycle_status || '').toLowerCase();
  if (status.includes('reject') || status.includes('fail') || status.includes('blocked')) return 'intervention';
  if (status.includes('pending') || status.includes('open') || status.includes('created') || status.includes('partial')) return 'attention';
  if (status.includes('complete') || status.includes('filled') || status.includes('closed')) return 'normal';
  return 'unavailable';
}

function traceCompleteness(items: any[]): number {
  if (items.length === 0) return 0;
  const possible = items.length * TRACE_FIELDS.length;
  const present = items.reduce((count, item) => (
    count + TRACE_FIELDS.filter(([field]) => !isNotAvailable(item[field])).length
  ), 0);
  return possible === 0 ? 0 : present / possible;
}

function percentage(value: number): string {
  if (!Number.isFinite(value)) return '0%';
  return `${Math.round(value * 100)}%`;
}

function safeLimit(value: string): string {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return '100';
  return String(Math.min(500, Math.max(1, Math.round(parsed))));
}

function queryScopeLabel(query: Record<string, unknown>): string {
  const entries = Object.entries(query || {}).filter(([, value]) => !isNotAvailable(value));
  if (entries.length === 0) return '全局最近证据';
  return entries.map(([key, value]) => `${key}=${value}`).join(' / ');
}

function unavailableLabel(item: any): string {
  const code = displayValue(item?.error || item?.code, '无法确认');
  const label = blockingReasonLabel(code);
  return label === '需要人工确认' ? code : label;
}

function copyJson(value: unknown) {
  navigator.clipboard?.writeText(JSON.stringify(value, null, 2));
}

function firstNonEmpty(...values: unknown[]): string {
  for (const value of values) {
    if (!isNotAvailable(value)) return String(value);
  }
  return '暂无';
}

function semanticTraceText(item: any): string {
  const present = TRACE_FIELDS.filter(([field]) => !isNotAvailable(item[field])).map(([, label]) => label);
  if (present.length === 0) return '缺少 runtime 语义 ID';
  return present.join(' / ');
}

function eventTitle(event: any, index: number): string {
  return firstNonEmpty(event.event_type, event.action, event.step, event.status, `审计事件 ${index + 1}`);
}

function timeText(value: unknown): string {
  if (typeof value === 'number') return formatTimestampMs(value);
  if (typeof value === 'string' && value.trim()) return value;
  return '暂无';
}

export default function AuditChain() {
  const [draftFilters, setDraftFilters] = useState<EvidenceFilters>(EMPTY_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<EvidenceFilters>(EMPTY_FILTERS);
  const path = useMemo(() => buildAuditPath(appliedFilters), [appliedFilters]);
  const { envelope, loading, error } = useReadModel<any>(path);

  if (loading) {
    return (
      <div className="flex min-h-[480px] items-center justify-center rounded-md border border-slate-800 bg-slate-900/50 text-sm text-slate-400">
        正在读取证据链...
      </div>
    );
  }

  const pageData = envelope?.data || {};
  const intents = asArray(pageData.intents);
  const orders = asArray(pageData.orders);
  const positions = asArray(pageData.positions);
  const reviews = asArray(pageData.reviews);
  const auditEvents = asArray(pageData.audit_events);
  const unavailable = asArray(envelope?.unavailable);
  const traceItems = [...intents, ...orders, ...reviews];
  const semanticCompleteness = traceCompleteness(traceItems);
  const recordCount = intents.length + orders.length + positions.length + reviews.length + auditEvents.length;
  const tone = pageTone({
    error,
    unavailableCount: unavailable.length,
    recordCount,
    auditEvents: auditEvents.length,
    semanticCompleteness,
  });
  const query = pageData.query || {};
  const activeQueryCount = Object.values(appliedFilters).filter((value) => String(value || '').trim()).length;
  const missingSemanticRows = traceItems.filter((item) => TRACE_FIELDS.every(([field]) => isNotAvailable(item[field])));
  const rawPayloadPolicy = pageData.raw_payload_policy;

  const inspectorItems: Array<{ title: string; body: string; tone: ConsoleTone; action?: ReactNode }> = [
    {
      title: '证据页只负责追踪与验证',
      body: '这里不会创建授权、ExecutionIntent、订单、恢复任务或 exchange 写请求；所有查询都走 Trading Console GET readmodel。',
      tone: 'normal',
    },
    {
      title: missingSemanticRows.length > 0 ? '存在历史语义缺口' : '语义 ID 可用于链路追踪',
      body: missingSemanticRows.length > 0
        ? '旧 one-shot 或历史订单可能没有 runtime / signal / candidate ID，页面会标出缺口，不会自动补写。'
        : '当前结果中的对象带有足够语义 ID，可继续追踪到 runtime / signal / candidate 层。',
      tone: missingSemanticRows.length > 0 ? 'attention' : 'normal',
    },
    {
      title: auditEvents.length > 0 ? '审计事件可读' : '审计事件为空',
      body: auditEvents.length > 0
        ? '当前查询命中审计事件，可用于核对链路变化。'
        : '当前查询没有返回审计事件；这不等于链路完整，只表示当前 readmodel 没有可展示事件。',
      tone: auditEvents.length > 0 ? 'normal' : 'attention',
    },
    {
      title: rawPayloadPolicy === 'masked_or_omitted' ? 'Raw payload 已脱敏或省略' : 'Raw payload 策略需确认',
      body: '原始响应保留在折叠层，只用于复核，不作为主操作面。',
      tone: rawPayloadPolicy === 'masked_or_omitted' ? 'normal' : 'attention',
    },
  ];

  return (
    <div className="mx-auto max-w-[1500px] space-y-4">
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusChip tone={tone}>{evidenceStatusLabel(tone)}</StatusChip>
            {envelope?.freshness_status && (
              <StatusChip tone={envelope.freshness_status === 'fresh' ? 'normal' : 'attention'}>
                {envelope.freshness_status === 'fresh' ? '已同步' : '部分同步'}
              </StatusChip>
            )}
          </div>
          <h1 className="mt-4 text-3xl font-semibold text-slate-100">证据</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
            用于追踪授权、runtime、signal、candidate、intent、订单和复盘之间的证据链。主屏显示人类可读摘要，技术 ID 与 raw JSON 留在详情层。
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <EvidenceSoftButton to="/trades">
            <ListChecks className="h-4 w-4" />
            交易与仓位
          </EvidenceSoftButton>
          <EvidenceSoftButton to="/analysis">
            <BarChart3 className="h-4 w-4" />
            分析
          </EvidenceSoftButton>
          <EvidenceSoftButton to="/incident">
            <ShieldAlert className="h-4 w-4" />
            异常介入
          </EvidenceSoftButton>
        </div>
      </header>

      <EnvelopeStatus envelope={envelope} error={error} />

      {(unavailable.length > 0 || missingSemanticRows.length > 0 || auditEvents.length === 0) && (
        <ActionNudge
          tone={unavailable.length > 0 ? 'attention' : 'unavailable'}
          text={evidenceNudgeText(unavailable.length, missingSemanticRows.length, auditEvents.length)}
          action={<EvidenceSoftButton to="/incident">查看异常介入</EvidenceSoftButton>}
        />
      )}

      <ConsolePanel>
        <div className="grid grid-cols-1 md:grid-cols-6">
          <MetricRailItem label="执行意图" value={intents.length} tone={intents.length > 0 ? 'attention' : 'unavailable'} sub="intent facts" />
          <MetricRailItem label="订单" value={orders.length} tone={orders.length > 0 ? 'attention' : 'unavailable'} sub="local PG" />
          <MetricRailItem label="仓位" value={positions.length} tone={positions.length > 0 ? 'attention' : 'normal'} sub="projection" />
          <MetricRailItem label="复盘" value={reviews.length} tone={reviews.length > 0 ? 'normal' : 'unavailable'} sub="review rows" />
          <MetricRailItem label="审计事件" value={auditEvents.length} tone={auditEvents.length > 0 ? 'normal' : 'attention'} sub="event rows" />
          <MetricRailItem label="语义覆盖" value={percentage(semanticCompleteness)} tone={semanticCompleteness >= 0.5 ? 'normal' : 'attention'} sub={`${missingSemanticRows.length} 行缺口`} />
        </div>
      </ConsolePanel>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-4">
          <EvidenceQueryPanel
            draftFilters={draftFilters}
            setDraftFilters={setDraftFilters}
            onApply={() => setAppliedFilters({ ...draftFilters, limit: safeLimit(draftFilters.limit) })}
            onReset={() => {
              setDraftFilters(EMPTY_FILTERS);
              setAppliedFilters(EMPTY_FILTERS);
            }}
            activeQueryCount={activeQueryCount}
          />
          <EvidenceScopePanel
            query={query}
            envelope={envelope}
            rawPayloadPolicy={rawPayloadPolicy}
            activeQueryCount={activeQueryCount}
          />
          <SemanticCoveragePanel items={traceItems} />
          <IntentPanel intents={intents} />
          <OrderEvidencePanel orders={orders} />
          <PositionReviewPanel positions={positions} reviews={reviews} />
          <AuditEventPanel auditEvents={auditEvents} />
          <UnavailableFactsPanel unavailable={unavailable} />
          <TechnicalDetails title="Raw / Debug：汇总响应">
            <button
              type="button"
              onClick={() => copyJson(envelope)}
              className="mb-2 rounded-md border border-slate-700 bg-slate-900/70 px-2 py-1 text-xs text-slate-300 transition hover:bg-slate-800 hover:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              复制响应
            </button>
            <pre className="max-h-[520px] overflow-auto whitespace-pre-wrap font-mono text-[11px] leading-5">
              {JSON.stringify(envelope, null, 2)}
            </pre>
          </TechnicalDetails>
        </div>

        <InspectorPanel
          title="证据说明"
          items={inspectorItems}
          footer={
            <div className="space-y-2 text-xs leading-5 text-slate-500">
              <div>数据源：GET /api/trading-console/audit-chain。</div>
              <div>动作边界：只读查询；不创建 ExecutionIntent、不下单、不撤单、不改 runtime。</div>
            </div>
          }
        />
      </div>
    </div>
  );
}

function EvidenceQueryPanel({
  draftFilters,
  setDraftFilters,
  onApply,
  onReset,
  activeQueryCount,
}: {
  draftFilters: EvidenceFilters;
  setDraftFilters: (filters: EvidenceFilters) => void;
  onApply: () => void;
  onReset: () => void;
  activeQueryCount: number;
}) {
  const update = (key: keyof EvidenceFilters, value: string) => setDraftFilters({ ...draftFilters, [key]: value });
  return (
    <ConsolePanel
      title="证据查询"
      caption="按任一 ID 缩小证据链范围；查询只走 GET readmodel"
      action={<StatusChip tone={activeQueryCount > 1 ? 'attention' : 'unavailable'}>{Math.max(0, activeQueryCount - 1)} 个过滤项</StatusChip>}
    >
      <form
        className="space-y-4 px-4 py-4"
        onSubmit={(event) => {
          event.preventDefault();
          onApply();
        }}
      >
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3 xl:grid-cols-4">
          <EvidenceInput label="Runtime" value={draftFilters.runtime_instance_id} onChange={(value) => update('runtime_instance_id', value)} placeholder="runtime_instance_id" />
          <EvidenceInput label="TrialBinding" value={draftFilters.trial_binding_id} onChange={(value) => update('trial_binding_id', value)} placeholder="trial_binding_id" />
          <EvidenceInput label="SignalEvaluation" value={draftFilters.signal_evaluation_id} onChange={(value) => update('signal_evaluation_id', value)} placeholder="signal_evaluation_id" />
          <EvidenceInput label="OrderCandidate" value={draftFilters.order_candidate_id} onChange={(value) => update('order_candidate_id', value)} placeholder="order_candidate_id" />
          <EvidenceInput label="Authorization" value={draftFilters.authorization_id} onChange={(value) => update('authorization_id', value)} placeholder="authorization_id" />
          <EvidenceInput label="Intent" value={draftFilters.intent_id} onChange={(value) => update('intent_id', value)} placeholder="intent_id" />
          <EvidenceInput label="Order" value={draftFilters.order_id} onChange={(value) => update('order_id', value)} placeholder="order_id" />
          <EvidenceInput label="Exchange Order" value={draftFilters.exchange_order_id} onChange={(value) => update('exchange_order_id', value)} placeholder="exchange_order_id" />
          <EvidenceInput label="Strategy Family" value={draftFilters.strategy_family_id} onChange={(value) => update('strategy_family_id', value)} placeholder="strategy_family_id" />
          <EvidenceInput label="Strategy Version" value={draftFilters.strategy_family_version_id} onChange={(value) => update('strategy_family_version_id', value)} placeholder="strategy_family_version_id" />
          <EvidenceInput label="Symbol" value={draftFilters.symbol} onChange={(value) => update('symbol', value)} placeholder="BNB/USDT:USDT" />
          <EvidenceInput label="Limit" value={draftFilters.limit} onChange={(value) => update('limit', value)} placeholder="100" type="number" />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="submit"
            className="inline-flex min-h-9 cursor-pointer items-center gap-2 rounded-md border border-blue-500/50 bg-blue-500/15 px-3 py-2 text-sm font-medium text-blue-200 transition hover:bg-blue-500/25 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <Search className="h-4 w-4" />
            查询证据
          </button>
          <button
            type="button"
            onClick={onReset}
            className="inline-flex min-h-9 cursor-pointer items-center gap-2 rounded-md border border-slate-700 bg-slate-900/70 px-3 py-2 text-sm text-slate-300 transition hover:bg-slate-800 hover:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <RotateCcw className="h-4 w-4" />
            清空
          </button>
          <span className="text-xs leading-5 text-slate-500">不会写入任何授权、订单或 runtime 状态。</span>
        </div>
      </form>
    </ConsolePanel>
  );
}

function EvidenceInput({
  label,
  value,
  onChange,
  placeholder,
  type = 'text',
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  type?: 'text' | 'number';
}) {
  return (
    <label className="block min-w-0">
      <span className="mb-1 block text-xs text-slate-500">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="w-full rounded-md border border-slate-700 bg-slate-900/70 px-2 py-2 text-sm text-slate-200 outline-none transition placeholder:text-slate-600 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/30"
      />
    </label>
  );
}

function EvidenceScopePanel({
  query,
  envelope,
  rawPayloadPolicy,
  activeQueryCount,
}: {
  query: Record<string, unknown>;
  envelope: any;
  rawPayloadPolicy: unknown;
  activeQueryCount: number;
}) {
  return (
    <ConsolePanel
      title="当前证据范围"
      caption="先看查询范围和数据状态，再进入对象明细"
      action={<StatusChip tone={activeQueryCount > 1 ? 'attention' : 'unavailable'}>{activeQueryCount > 1 ? '已过滤' : '全局'}</StatusChip>}
    >
      <div className="grid grid-cols-1 gap-px bg-slate-800/80 md:grid-cols-4">
        <EvidenceTile label="查询范围" value={queryScopeLabel(query)} tone={activeQueryCount > 1 ? 'attention' : 'unavailable'} />
        <EvidenceTile label="生成时间" value={envelope?.generated_at_ms ? formatTimestampMs(envelope.generated_at_ms) : '暂无'} tone="normal" />
        <EvidenceTile label="数据状态" value={displayValue(envelope?.freshness_status, '无法确认')} tone={envelope?.freshness_status === 'fresh' ? 'normal' : 'attention'} />
        <EvidenceTile label="Raw 策略" value={displayValue(rawPayloadPolicy, '无法确认')} tone={rawPayloadPolicy === 'masked_or_omitted' ? 'normal' : 'attention'} />
      </div>
    </ConsolePanel>
  );
}

function SemanticCoveragePanel({ items }: { items: any[] }) {
  const fieldCounts = TRACE_FIELDS.map(([field, label]) => ({
    field,
    label,
    count: items.filter((item) => !isNotAvailable(item[field])).length,
  }));
  return (
    <ConsolePanel
      title="语义 ID 覆盖"
      caption="缺失不会被自动补写；它决定证据可追溯程度"
      action={<StatusChip tone={items.length > 0 ? 'attention' : 'unavailable'}>{items.length} 行对象</StatusChip>}
    >
      <div className="grid grid-cols-1 gap-px bg-slate-800/80 sm:grid-cols-2 xl:grid-cols-5">
        {fieldCounts.map((item) => (
          <div key={item.field}>
            <EvidenceTile
              label={item.label}
              value={`${item.count} / ${items.length}`}
              tone={item.count > 0 ? 'normal' : 'attention'}
            />
          </div>
        ))}
      </div>
    </ConsolePanel>
  );
}

function IntentPanel({ intents }: { intents: any[] }) {
  return (
    <ConsolePanel
      title="ExecutionIntent 证据"
      caption="记录意图不等于可提交订单"
      action={<StatusChip tone={intents.length > 0 ? 'attention' : 'unavailable'}>{intents.length} 条</StatusChip>}
    >
      {intents.length === 0 ? (
        <EmptyState title="当前查询没有执行意图" body="没有 intent 不代表无历史交易；可按订单 ID、symbol 或 authorization 缩小证据范围。" />
      ) : (
        <div>
          {intents.slice(0, 12).map((intent: any, index) => (
            <div key={firstNonEmpty(intent.intent_id, intent.id, `intent-${index}`)}>
              <EntityRow
                title={`${firstNonEmpty(intent.symbol, '未知标的')} · ${displayValue(intent.status, '状态未知')}`}
                subtitle={firstNonEmpty(intent.intent_id, intent.id, '暂无 intent ID')}
                tone={objectTone(intent)}
                cells={[
                  { label: '授权', value: firstNonEmpty(intent.authorization_id, intent.owner_authorization_id) },
                  { label: 'Runtime', value: firstNonEmpty(intent.runtime_instance_id) },
                  { label: 'Candidate', value: firstNonEmpty(intent.order_candidate_id) },
                  { label: '语义覆盖', value: semanticTraceText(intent) },
                ]}
                action={<StatusChip tone={objectTone(intent)}>Intent</StatusChip>}
              />
            </div>
          ))}
        </div>
      )}
    </ConsolePanel>
  );
}

function OrderEvidencePanel({ orders }: { orders: any[] }) {
  return (
    <ConsolePanel
      title="订单证据"
      caption="订单事实用于追溯，不提供撤单、重试或平仓入口"
      action={<StatusChip tone={orders.length > 0 ? 'attention' : 'unavailable'}>{orders.length} 条</StatusChip>}
    >
      {orders.length === 0 ? (
        <EmptyState title="当前查询没有订单" body="可用 order_id、exchange_order_id 或 symbol 重新查询。" />
      ) : (
        <div>
          {orders.slice(0, 18).map((order: any, index) => (
            <div key={firstNonEmpty(order.order_id, order.exchange_order_id, `order-${index}`)}>
              <EntityRow
                title={`${firstNonEmpty(order.symbol, '未知标的')} · ${orderRoleLabel(order.order_role)}`}
                subtitle={`${firstNonEmpty(order.order_id, order.exchange_order_id, '暂无订单 ID')} · ${semanticTraceText(order)}`}
                tone={objectTone(order)}
                cells={[
                  { label: '状态', value: orderStatusLabel(order.status) },
                  { label: '方向', value: sideLabel(order.side || order.direction) },
                  { label: '数量', value: firstNonEmpty(order.requested_qty, order.filled_qty), className: 'font-mono' },
                  { label: 'Runtime', value: firstNonEmpty(order.runtime_instance_id) },
                ]}
                action={<StatusChip tone={objectTone(order)}>订单</StatusChip>}
              />
            </div>
          ))}
        </div>
      )}
    </ConsolePanel>
  );
}

function PositionReviewPanel({ positions, reviews }: { positions: any[]; reviews: any[] }) {
  return (
    <ConsolePanel
      title="仓位与复盘证据"
      caption="复盘证据用于解释结果，不发起提现、转账或资金划拨"
      action={<StatusChip tone={positions.length + reviews.length > 0 ? 'attention' : 'unavailable'}>{positions.length + reviews.length} 条</StatusChip>}
    >
      {positions.length === 0 && reviews.length === 0 ? (
        <EmptyState title="当前没有仓位或复盘记录" body="这可能是正常空状态，也可能表示相关 repository 不可用；请同时查看不可用事实。" />
      ) : (
        <div>
          {[...positions.map((item) => ({ ...item, __kind: 'position' })), ...reviews.map((item) => ({ ...item, __kind: 'review' }))].slice(0, 10).map((item: any, index) => (
            <div key={firstNonEmpty(item.position_id, item.review_id, item.order_id, `review-${index}`)}>
              <EntityRow
                title={`${item.__kind === 'position' ? '仓位' : '复盘'} · ${firstNonEmpty(item.symbol, item.result, '未知对象')}`}
                subtitle={firstNonEmpty(item.position_id, item.review_id, item.order_id, '暂无 ID')}
                tone={objectTone(item)}
                cells={[
                  { label: '状态', value: firstNonEmpty(item.status, item.lifecycle_status, item.outcome) },
                  { label: 'Runtime', value: firstNonEmpty(item.runtime_instance_id) },
                  { label: 'Candidate', value: firstNonEmpty(item.order_candidate_id) },
                  { label: '更新时间', value: timeText(item.updated_at || item.closed_at || item.created_at) },
                ]}
                action={<StatusChip tone={objectTone(item)}>{item.__kind === 'position' ? '仓位' : '复盘'}</StatusChip>}
              />
            </div>
          ))}
        </div>
      )}
    </ConsolePanel>
  );
}

function AuditEventPanel({ auditEvents }: { auditEvents: any[] }) {
  return (
    <ConsolePanel
      title="审计事件"
      caption="事件为空时不能宣称链路完整"
      action={<StatusChip tone={auditEvents.length > 0 ? 'normal' : 'attention'}>{auditEvents.length} 条</StatusChip>}
    >
      {auditEvents.length === 0 ? (
        <EmptyState title="当前没有审计事件" body="当前查询没有命中 audit_events；如需查具体链路，可粘贴订单、intent 或 signal ID 重新查询。" />
      ) : (
        <div>
          {auditEvents.slice(0, 16).map((event: any, index) => (
            <div key={firstNonEmpty(event.event_id, event.id, `audit-${index}`)}>
              <EntityRow
                title={eventTitle(event, index)}
                subtitle={firstNonEmpty(event.order_id, event.signal_id, event.intent_id, '暂无关联 ID')}
                tone={objectTone(event)}
                cells={[
                  { label: '来源', value: firstNonEmpty(event.source, event.actor, event.component) },
                  { label: '结果', value: firstNonEmpty(event.result, event.status, event.outcome) },
                  { label: '时间', value: timeText(event.created_at_ms || event.created_at || event.timestamp_ms) },
                  { label: '消息', value: firstNonEmpty(event.message, event.reason, event.error) },
                ]}
                action={<StatusChip tone={objectTone(event)}>事件</StatusChip>}
              />
            </div>
          ))}
        </div>
      )}
    </ConsolePanel>
  );
}

function UnavailableFactsPanel({ unavailable }: { unavailable: any[] }) {
  return (
    <ConsolePanel
      title="不可用事实"
      caption="缺失事实必须显式展示，不能被解释为链路完整"
      action={<StatusChip tone={unavailable.length > 0 ? 'attention' : 'normal'}>{unavailable.length} 项</StatusChip>}
    >
      {unavailable.length === 0 ? (
        <EmptyState title="当前没有不可用来源" body="audit-chain 读取没有报告不可用项。" />
      ) : (
        <div className="grid grid-cols-1 gap-3 px-4 py-4 md:grid-cols-2 xl:grid-cols-3">
          {unavailable.slice(0, 12).map((item: any, index) => (
            <div key={`${displayValue(item.source, 'source')}-${displayValue(item.code, 'code')}-${index}`} className="rounded-md border border-slate-800 bg-slate-900/40 px-3 py-3 text-sm">
              <div className="text-xs text-slate-500">{displayValue(item.source, '未知来源')}</div>
              <div className="mt-1 font-medium text-slate-200">{unavailableLabel(item)}</div>
            </div>
          ))}
        </div>
      )}
    </ConsolePanel>
  );
}

function EvidenceTile({ label, value, tone }: { label: string; value: string; tone: ConsoleTone }) {
  const dotClass = tone === 'normal' ? 'bg-emerald-400' : tone === 'intervention' ? 'bg-rose-400' : tone === 'attention' ? 'bg-amber-400' : 'bg-slate-400';
  return (
    <div className="min-h-20 bg-slate-900 px-4 py-3">
      <div className="flex items-center gap-2 text-[11px] font-medium uppercase text-slate-500">
        <span className={`h-2 w-2 rounded-sm ${dotClass}`} />
        {label}
      </div>
      <div className="mt-2 min-w-0 truncate text-sm font-medium text-slate-100">{value}</div>
    </div>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="px-4 py-7 text-center">
      <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full border border-slate-800 bg-slate-900/50">
        <FileSearch className="h-4 w-4 text-slate-500" />
      </div>
      <div className="mt-3 text-sm font-medium text-slate-200">{title}</div>
      <p className="mx-auto mt-1 max-w-md text-xs leading-5 text-slate-500">{body}</p>
    </div>
  );
}

function EvidenceSoftButton({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link
      to={to}
      className="inline-flex min-h-9 items-center gap-2 rounded-md border border-slate-700 bg-slate-900/70 px-3 py-2 text-sm text-slate-300 transition hover:bg-slate-800 hover:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
    >
      {children}
    </Link>
  );
}

function evidenceStatusLabel(tone: ConsoleTone): string {
  if (tone === 'intervention' || tone === 'blocked') return '证据读取异常';
  if (tone === 'attention') return '证据需核验';
  if (tone === 'unavailable') return '暂无证据';
  return '证据可读';
}

function evidenceNudgeText(unavailableCount: number, missingSemanticRows: number, auditEventCount: number): string {
  if (unavailableCount > 0) return `当前 ${unavailableCount} 个证据来源不可用，不能把链路视作完整。`;
  if (missingSemanticRows > 0) return `${missingSemanticRows} 行对象缺少 runtime 语义 ID，请按具体 ID 进一步核验。`;
  if (auditEventCount === 0) return '当前查询没有审计事件；如需复核某条链路，请输入 intent/order/signal ID。';
  return '证据可读。';
}
