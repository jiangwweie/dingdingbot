import { Link } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useMemo, useState } from 'react';
import { BarChart3, FileSearch, ShieldCheck } from 'lucide-react';
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
  formatMoney,
  orderClassLabel,
  orderRoleLabel,
  orderStatusLabel,
  protectionStatusLabel,
  sideLabel,
} from '@/lib/ownerViewModel';

const OPEN_STATUS = new Set(['CREATED', 'NEW', 'OPEN', 'PARTIALLY_FILLED', 'ACCEPTED']);
const PROTECTION_ROLES = new Set(['TP', 'TP1', 'TP2', 'TP3', 'SL']);

function isOpenOrder(order: any): boolean {
  return OPEN_STATUS.has(String(order.status || '').toUpperCase());
}

function isProtectionOrder(order: any): boolean {
  const role = String(order.order_role || '').toUpperCase();
  return PROTECTION_ROLES.has(role) || order.reduce_only === true;
}

function orderTone(order: any): ConsoleTone {
  const classification = String(order.classification || 'unknown');
  const status = String(order.status || '').toUpperCase();
  if (classification === 'mismatch' || classification === 'orphan_protection') return 'intervention';
  if (classification === 'pg_only' || classification === 'exchange_only' || classification === 'pg_unchecked') return 'attention';
  if (status === 'REJECTED') return 'intervention';
  if (isOpenOrder(order)) return 'attention';
  if (status === 'FILLED') return 'normal';
  return 'unavailable';
}

function protectionTone(status?: string): ConsoleTone {
  if (status === 'protected') return 'normal';
  if (status === 'partially_protected' || status === 'unknown') return 'attention';
  if (status === 'unprotected' || status === 'orphaned') return 'intervention';
  return 'unavailable';
}

function pageTone(params: {
  error: string | null;
  activePositions: number;
  protectionStatus?: string;
  degraded: boolean;
  mismatchCount: number;
}): ConsoleTone {
  if (params.error || params.mismatchCount > 0 || params.protectionStatus === 'orphaned') return 'intervention';
  if (params.activePositions > 0 && params.protectionStatus !== 'protected') return 'intervention';
  if (params.activePositions > 0 || params.degraded || params.protectionStatus === 'unknown') return 'attention';
  return 'normal';
}

function compactNumber(value: unknown, fallback = '0'): string {
  if (isNotAvailable(value)) return fallback;
  return String(value);
}

function valueOrDash(value: unknown): string {
  return isNotAvailable(value) ? '-' : String(value);
}

function sourceFactLabel(value: unknown): string {
  if (value === 'not_available' || value === 'unknown' || value === null || value === undefined) return '暂无数据';
  return blockingReasonLabel(String(value));
}

export default function OrderLedger() {
  const ledgerState = useReadModel<any>('/api/trading-console/order-ledger?include_exchange=true&limit=100');
  const protectionState = useReadModel<any>('/api/trading-console/protection-health?include_exchange=true');
  const riskState = useReadModel<any>('/api/trading-console/account-risk?include_exchange=true');

  const ledgerData = ledgerState.envelope?.data || {};
  const protectionData = protectionState.envelope?.data || {};
  const accountRiskData = riskState.envelope?.data || {};
  const orders = asArray(ledgerData.orders);
  const groups = asArray(ledgerData.groups);
  const positions = asArray(accountRiskData.positions);
  const classificationCounts = ledgerData.classification_counts || {};
  const unavailableFields = ledgerData.unavailable_fields || {};
  const unavailableSources = dedupeUnavailableSources([
    ...asArray(ledgerState.envelope?.unavailable),
    ...asArray(protectionState.envelope?.unavailable),
    ...asArray(riskState.envelope?.unavailable),
  ]);
  const errors = [ledgerState.error, protectionState.error, riskState.error].filter(Boolean) as string[];
  const loading = ledgerState.loading && protectionState.loading && riskState.loading;

  const [sourceFilter, setSourceFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [roleFilter, setRoleFilter] = useState('all');
  const [riskFilter, setRiskFilter] = useState('all');
  const [symbolFilter, setSymbolFilter] = useState('all');
  const [timeFilter, setTimeFilter] = useState('all');
  const [customFrom, setCustomFrom] = useState('');
  const [customTo, setCustomTo] = useState('');
  const [pageSize, setPageSize] = useState(20);
  const [page, setPage] = useState(1);

  const symbols = useMemo(() => Array.from(new Set(orders.map((order: any) => String(order.symbol || 'unknown')))), [orders]);
  const openOrders = orders.filter(isOpenOrder);
  const protectionOrders = orders.filter(isProtectionOrder);
  const filledOrders = orders.filter((order: any) => String(order.status || '').toUpperCase() === 'FILLED');
  const rejectedOrders = orders.filter((order: any) => String(order.status || '').toUpperCase() === 'REJECTED');
  const mismatchCount = Number(classificationCounts.mismatch || 0) + Number(classificationCounts.orphan_protection || 0);
  const activePositionCount = Number(protectionData.active_position_count ?? positions.length ?? 0);
  const degraded = ledgerState.envelope?.freshness_status !== 'fresh' || protectionState.envelope?.freshness_status !== 'fresh' || riskState.envelope?.freshness_status !== 'fresh';
  const tone = pageTone({
    error: errors[0] || null,
    activePositions: activePositionCount,
    protectionStatus: protectionData.status,
    degraded,
    mismatchCount,
  });

  const filteredOrders = useMemo(() => {
    const now = Date.now();
    const customFromMs = customFrom ? new Date(customFrom).getTime() : null;
    const customToMs = customTo ? new Date(customTo).getTime() : null;
    return orders.filter((order: any) => {
      const source = String(order.source || 'unknown');
      const status = String(order.status || 'unknown').toLowerCase();
      const role = String(order.order_role || '').toLowerCase();
      const classification = String(order.classification || 'unknown');
      const symbol = String(order.symbol || 'unknown');
      const orderTime = Number(order.updated_at || order.created_at || 0);
      const sourceOk =
        sourceFilter === 'all' ||
        (sourceFilter === 'exchange' && source.includes('exchange')) ||
        (sourceFilter === 'local' && source === 'pg') ||
        (sourceFilter === 'exchange_only' && classification === 'exchange_only') ||
        (sourceFilter === 'pg_only' && classification === 'pg_only');
      const statusOk =
        statusFilter === 'all' ||
        (statusFilter === 'open' && isOpenOrder(order)) ||
        status === statusFilter;
      const roleOk =
        roleFilter === 'all' ||
        (roleFilter === 'entry' && role.includes('entry')) ||
        (roleFilter === 'exit' && (role.includes('exit') || role.includes('close'))) ||
        (roleFilter === 'protection' && isProtectionOrder(order)) ||
        (roleFilter === 'unknown' && !role);
      const riskOk =
        riskFilter === 'all' ||
        (riskFilter === 'normal' && classification === 'matched') ||
        (riskFilter === 'unchecked' && (classification === 'pg_unchecked' || classification === 'unknown')) ||
        (riskFilter === 'mismatch' && classification === 'mismatch') ||
        (riskFilter === 'orphan' && classification === 'orphan_protection') ||
        (riskFilter === 'rejected' && status === 'rejected');
      const symbolOk = symbolFilter === 'all' || symbol === symbolFilter;
      const timeOk =
        timeFilter === 'all' ||
        (timeFilter === '1h' && Number.isFinite(orderTime) && orderTime >= now - 60 * 60 * 1000) ||
        (timeFilter === '24h' && Number.isFinite(orderTime) && orderTime >= now - 24 * 60 * 60 * 1000) ||
        (timeFilter === '7d' && Number.isFinite(orderTime) && orderTime >= now - 7 * 24 * 60 * 60 * 1000) ||
        (timeFilter === 'custom' &&
          Number.isFinite(orderTime) &&
          (customFromMs === null || orderTime >= customFromMs) &&
          (customToMs === null || orderTime <= customToMs));
      return sourceOk && statusOk && roleOk && riskOk && symbolOk && timeOk;
    });
  }, [orders, sourceFilter, statusFilter, roleFilter, riskFilter, symbolFilter, timeFilter, customFrom, customTo]);

  const totalPages = Math.max(1, Math.ceil(filteredOrders.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const visibleOrders = filteredOrders.slice((safePage - 1) * pageSize, safePage * pageSize);

  if (loading) {
    return (
      <div className="flex min-h-[480px] items-center justify-center rounded-md border border-slate-800 bg-slate-900/50 text-sm text-slate-400">
        正在读取交易与仓位状态...
      </div>
    );
  }

  const inspectorItems: Array<{ title: string; body: string; tone: ConsoleTone }> = [
    {
      title: activePositionCount > 0 ? '当前存在仓位敞口' : '当前未看到活跃仓位',
      body: activePositionCount > 0
        ? '仓位必须能归属到策略/runtime，并被保护事实覆盖；保护不完整时不能把后续尝试视作安全。'
        : '本地/可读事实没有活跃仓位。若交易所事实不可读，页面会保持部分同步，不会声明完整安全。',
      tone,
    },
    {
      title: '保护状态优先于订单数量',
      body: '止盈/止损/保护单用于说明风险是否受边界控制；历史保护记录不会被当成当前保护。',
      tone: protectionTone(protectionData.status),
    },
    {
      title: '订单归属仍有历史缺口',
      body: '旧 one-shot 订单可能缺少 runtime_instance_id 或 order_candidate_id；页面会显示未绑定，而不是伪造 runtime 语义。',
      tone: orders.some((order: any) => order.runtime_instance_id || order.order_candidate_id) ? 'normal' : 'attention',
    },
    {
      title: '这里没有交易动作',
      body: '交易与仓位页只读展示订单、仓位、保护和成本可用性；不会提交订单、撤单、重试保护、关闭仓位或调用 exchange 写接口。',
      tone: 'unavailable' as ConsoleTone,
    },
  ];

  return (
    <div className="mx-auto max-w-[1500px] space-y-4">
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusChip tone={tone}>{tradesStatusLabel(tone, activePositionCount, protectionData.status)}</StatusChip>
            {ledgerState.envelope?.freshness_status && (
              <StatusChip tone={ledgerState.envelope.freshness_status === 'fresh' ? 'normal' : 'attention'}>
                {ledgerState.envelope.freshness_status === 'fresh' ? '已同步' : '部分同步'}
              </StatusChip>
            )}
          </div>
          <h1 className="mt-4 text-3xl font-semibold text-slate-100">交易与仓位</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
            查看仓位敞口、订单链路、保护覆盖和成本事实。页面只读，不提供买入、卖出、撤单、重试保护或平仓入口。
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <TradesSoftButton to="/runtime">
            <ShieldCheck className="h-4 w-4" />
            运行治理
          </TradesSoftButton>
          <TradesSoftButton to="/analysis">
            <BarChart3 className="h-4 w-4" />
            分析
          </TradesSoftButton>
          <TradesSoftButton to="/evidence">
            <FileSearch className="h-4 w-4" />
            证据
          </TradesSoftButton>
        </div>
      </header>

      <EnvelopeStatus envelope={ledgerState.envelope} error={errors[0] || null} />

      {degraded && (
        <ActionNudge
          tone="attention"
          text={exchangeAvailabilityMessage(unavailableSources)}
          action={<TradesSoftButton to="/incident">查看异常介入</TradesSoftButton>}
        />
      )}

      <ConsolePanel>
        <div className="grid grid-cols-1 md:grid-cols-5">
          <MetricRailItem label="活跃仓位" value={compactNumber(activePositionCount)} tone={activePositionCount > 0 ? 'attention' : 'normal'} sub={activePositionCount > 0 ? '需确认保护' : '本地无敞口'} />
          <MetricRailItem label="保护状态" value={shortProtectionStatusLabel(protectionData.status)} tone={protectionTone(protectionData.status)} sub={`${compactNumber(protectionData.tp_count)} TP / ${compactNumber(protectionData.sl_count)} SL`} />
          <MetricRailItem label="未完成订单" value={openOrders.length} tone={openOrders.length > 0 ? 'attention' : 'normal'} sub={`${protectionOrders.length} 个保护相关`} />
          <MetricRailItem label="已成交" value={filledOrders.length} tone={filledOrders.length > 0 ? 'normal' : 'unavailable'} sub={`${rejectedOrders.length} 个拒单`} />
          <MetricRailItem label="不可核验" value={compactNumber(classificationCounts.unknown || classificationCounts.pg_unchecked || 0)} tone={degraded ? 'attention' : 'unavailable'} sub="交易所事实受限" />
        </div>
      </ConsolePanel>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-4">
          <ExposurePanel
            accountRisk={accountRiskData}
            protection={protectionData}
            positions={positions}
          />
          <OrderGroupsPanel groups={groups} />
          <OrderFilterPanel
            sourceFilter={sourceFilter}
            setSourceFilter={setSourceFilter}
            statusFilter={statusFilter}
            setStatusFilter={setStatusFilter}
            roleFilter={roleFilter}
            setRoleFilter={setRoleFilter}
            riskFilter={riskFilter}
            setRiskFilter={setRiskFilter}
            symbolFilter={symbolFilter}
            setSymbolFilter={setSymbolFilter}
            symbols={symbols}
            timeFilter={timeFilter}
            setTimeFilter={setTimeFilter}
            pageSize={pageSize}
            setPageSize={setPageSize}
            setPage={setPage}
            customFrom={customFrom}
            setCustomFrom={setCustomFrom}
            customTo={customTo}
            setCustomTo={setCustomTo}
          />
          <OrdersPanel
            visibleOrders={visibleOrders}
            filteredCount={filteredOrders.length}
            safePage={safePage}
            totalPages={totalPages}
            setPage={setPage}
          />
          <UnavailableFactsPanel unavailableFields={unavailableFields} unavailableSources={unavailableSources} />
        </div>

        <InspectorPanel
          title="仓位说明"
          items={inspectorItems}
          footer={
            <div className="space-y-2 text-xs leading-5 text-slate-500">
              <div>数据源：order-ledger / protection-health / account-risk GET readmodel。</div>
              <div>动作边界：不下单、不撤单、不重试保护、不平仓、不写 exchange。</div>
            </div>
          }
        />
      </div>
    </div>
  );
}

function ExposurePanel({ accountRisk, protection, positions }: { accountRisk: any; protection: any; positions: any[] }) {
  const marginFacts = accountRisk.margin_facts || {};
  const account = accountRisk.account || {};
  return (
    <ConsolePanel
      title="当前敞口"
      caption="先看仓位与保护，再看历史订单"
      action={<StatusChip tone={protectionTone(protection.status)}>{protectionStatusLabel(protection.status)}</StatusChip>}
    >
      <div className="grid grid-cols-1 border-b border-slate-800/90 md:grid-cols-4">
        <ValueTile label="账户权益" value={formatMoney(account.total_balance)} />
        <ValueTile label="可用保证金" value={formatMoney(marginFacts.available_margin)} />
        <ValueTile label="未实现 PnL" value={formatMoney(marginFacts.unrealized_pnl)} />
        <ValueTile label="账户事实" value={displayValue(account.status, '暂无数据')} />
      </div>

      {positions.length === 0 ? (
        <EmptyState title="当前没有可展示仓位" body="本地仓位和可读交易所仓位都为空；若交易所读取受限，页面仍保持部分同步状态。" />
      ) : (
        <div>
          {positions.slice(0, 6).map((position: any, index) => (
            <div key={displayValue(position.position_id || position.symbol, `position-${index}`)}>
              <EntityRow
                title={`${displayValue(position.symbol, '未知标的')} · ${sideLabel(position.side || position.direction)}`}
                subtitle={position.system_owned ? '系统归属仓位' : '未确认系统归属'}
                tone={position.protection_status === 'protected' ? 'normal' : 'attention'}
                cells={[
                  { label: '数量', value: valueOrDash(position.quantity || position.contracts), className: 'font-mono' },
                  { label: '入场', value: valueOrDash(position.entry_price), className: 'font-mono' },
                  { label: '标记价', value: valueOrDash(position.mark_price), className: 'font-mono' },
                  { label: '保护', value: protectionStatusLabel(position.protection_status) },
                ]}
                action={<StatusChip tone={protectionTone(position.protection_status)}>仓位</StatusChip>}
              />
            </div>
          ))}
        </div>
      )}
    </ConsolePanel>
  );
}

function OrderGroupsPanel({ groups }: { groups: any[] }) {
  return (
    <ConsolePanel
      title="订单链路"
      caption="Entry 与保护/退出订单按 parent_order_id 归组"
      action={<StatusChip tone={groups.length > 0 ? 'attention' : 'unavailable'}>{groups.length} 组</StatusChip>}
    >
      {groups.length === 0 ? (
        <EmptyState title="暂无订单链路" body="当前 readmodel 没有可展示的 entry/protection 分组。" />
      ) : (
        <div>
          {groups.slice(0, 8).map((group: any, index) => {
            const entry = group.entry_order || {};
            const protections = asArray(group.protection_orders);
            const semantic = semanticLabel(entry);
            return (
              <div key={displayValue(group.parent_order_id, `group-${index}`)}>
                <EntityRow
                  title={`${displayValue(entry.symbol, '未知标的')} · ${orderRoleLabel(entry.order_role)}`}
                  subtitle={displayValue(entry.order_id, '暂无订单 ID')}
                  tone={orderTone(entry)}
                  cells={[
                    { label: '状态', value: orderStatusLabel(entry.status) },
                    { label: '保护', value: `${group.tp_count || 0} TP / ${group.sl_count || 0} SL` },
                    { label: '均价', value: valueOrDash(entry.average_exec_price || entry.price), className: 'font-mono' },
                    { label: '语义归属', value: semantic },
                  ]}
                  action={<StatusChip tone={protections.length > 0 ? 'attention' : 'unavailable'}>{protections.length} 子单</StatusChip>}
                />
              </div>
            );
          })}
        </div>
      )}
    </ConsolePanel>
  );
}

function OrderFilterPanel(props: {
  sourceFilter: string;
  setSourceFilter: (value: string) => void;
  statusFilter: string;
  setStatusFilter: (value: string) => void;
  roleFilter: string;
  setRoleFilter: (value: string) => void;
  riskFilter: string;
  setRiskFilter: (value: string) => void;
  symbolFilter: string;
  setSymbolFilter: (value: string) => void;
  symbols: string[];
  timeFilter: string;
  setTimeFilter: (value: string) => void;
  pageSize: number;
  setPageSize: (value: number) => void;
  setPage: (value: number) => void;
  customFrom: string;
  setCustomFrom: (value: string) => void;
  customTo: string;
  setCustomTo: (value: string) => void;
}) {
  const Select = ({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: Array<[string, string]> }) => (
    <label className="block">
      <span className="mb-1 block text-xs text-slate-500">{label}</span>
      <select
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
          props.setPage(1);
        }}
        className="w-full rounded-md border border-slate-700 bg-slate-900/70 px-2 py-2 text-sm text-slate-200 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-500/30"
      >
        {options.map(([optionValue, optionLabel]) => <option key={optionValue} value={optionValue}>{optionLabel}</option>)}
      </select>
    </label>
  );

  return (
    <ConsolePanel title="筛选" caption="用于定位订单事实，不改变任何订单状态">
      <div className="grid grid-cols-1 gap-3 px-4 py-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
        <Select label="来源" value={props.sourceFilter} onChange={props.setSourceFilter} options={[
          ['all', '全部'], ['exchange', '交易所'], ['local', '本地系统'], ['exchange_only', '仅交易所'], ['pg_only', '仅本地'],
        ]} />
        <Select label="状态" value={props.statusFilter} onChange={props.setStatusFilter} options={[
          ['all', '全部'], ['open', '未完成'], ['filled', '已成交'], ['canceled', '已取消'], ['rejected', '已拒绝'], ['unknown', '无法确认'],
        ]} />
        <Select label="角色" value={props.roleFilter} onChange={props.setRoleFilter} options={[
          ['all', '全部'], ['entry', '建仓'], ['exit', '退出/平仓'], ['protection', '保护'], ['unknown', '未知'],
        ]} />
        <Select label="风险" value={props.riskFilter} onChange={props.setRiskFilter} options={[
          ['all', '全部'], ['normal', '已匹配'], ['unchecked', '未核验/未知'], ['mismatch', '不一致'], ['orphan', '孤儿保护'], ['rejected', '拒单'],
        ]} />
        <Select label="标的" value={props.symbolFilter} onChange={props.setSymbolFilter} options={[
          ['all', '全部'], ...props.symbols.map((symbol) => [symbol, symbol] as [string, string]),
        ]} />
        <Select label="时间" value={props.timeFilter} onChange={props.setTimeFilter} options={[
          ['all', '全部'], ['1h', '最近 1 小时'], ['24h', '最近 24 小时'], ['7d', '最近 7 天'], ['custom', '自定义'],
        ]} />
        <Select label="每页" value={String(props.pageSize)} onChange={(value) => props.setPageSize(Number(value))} options={[
          ['20', '20'], ['50', '50'], ['100', '100'],
        ]} />
      </div>
      {props.timeFilter === 'custom' && (
        <div className="grid grid-cols-1 gap-3 border-t border-slate-800/90 px-4 py-4 sm:grid-cols-2">
          <TimeInput label="开始时间" value={props.customFrom} onChange={(value) => { props.setCustomFrom(value); props.setPage(1); }} />
          <TimeInput label="结束时间" value={props.customTo} onChange={(value) => { props.setCustomTo(value); props.setPage(1); }} />
        </div>
      )}
    </ConsolePanel>
  );
}

function OrdersPanel({
  visibleOrders,
  filteredCount,
  safePage,
  totalPages,
  setPage,
}: {
  visibleOrders: any[];
  filteredCount: number;
  safePage: number;
  totalPages: number;
  setPage: (value: number) => void;
}) {
  return (
    <ConsolePanel
      title="订单事实"
      caption="按最新筛选展示，技术 ID 默认压到行内次级信息"
      action={<StatusChip tone={filteredCount > 0 ? 'attention' : 'unavailable'}>{filteredCount} 条</StatusChip>}
    >
      {visibleOrders.length === 0 ? (
        <EmptyState title="当前没有可展示订单" body="调整筛选条件或查看证据页确认是否存在读模型缺失。" />
      ) : (
        <div>
          {visibleOrders.map((order: any, index) => (
            <div key={displayValue(order.order_id || order.exchange_order_id, `order-${index}`)}>
              <EntityRow
                title={`${displayValue(order.symbol, '未知标的')} · ${orderRoleLabel(order.order_role)}`}
                subtitle={`${displayValue(order.order_id || order.exchange_order_id, '暂无订单 ID')} · ${semanticLabel(order)}`}
                tone={orderTone(order)}
                cells={[
                  { label: '分类', value: orderClassLabel(order.classification) },
                  { label: '状态', value: orderStatusLabel(order.status) },
                  { label: '数量/成交', value: `${valueOrDash(order.requested_qty)} / ${valueOrDash(order.filled_qty)}`, className: 'font-mono' },
                  { label: '价格', value: valueOrDash(order.average_exec_price || order.price || order.trigger_price), className: 'font-mono' },
                ]}
                action={<StatusChip tone={orderTone(order)}>{sideLabel(order.side || order.direction)}</StatusChip>}
              />
            </div>
          ))}
        </div>
      )}
      <div className="flex items-center justify-between border-t border-slate-800/90 px-4 py-3 text-sm">
        <span className="text-slate-500">第 {safePage} / {totalPages} 页</span>
        <div className="flex gap-2">
          <PageButton disabled={safePage <= 1} onClick={() => setPage(Math.max(1, safePage - 1))}>上一页</PageButton>
          <PageButton disabled={safePage >= totalPages} onClick={() => setPage(Math.min(totalPages, safePage + 1))}>下一页</PageButton>
        </div>
      </div>
    </ConsolePanel>
  );
}

function UnavailableFactsPanel({ unavailableFields, unavailableSources }: { unavailableFields: Record<string, any>; unavailableSources: any[] }) {
  const fieldEntries = Object.entries(unavailableFields);
  return (
    <ConsolePanel
      title="不可用事实"
      caption="缺成本、资金费率、滑点或交易所读取时必须显式展示"
      action={<StatusChip tone={fieldEntries.length || unavailableSources.length ? 'attention' : 'normal'}>{fieldEntries.length + unavailableSources.length} 项</StatusChip>}
    >
      <div className="grid grid-cols-1 gap-2 px-4 py-4 md:grid-cols-3">
        {fieldEntries.length === 0 ? (
          <div className="text-sm text-slate-500">暂无不可用成本字段</div>
        ) : (
          fieldEntries.map(([key, value]) => (
            <div key={key} className="rounded-md border border-slate-800 bg-slate-900/40 px-3 py-2 text-sm">
              <div className="text-xs text-slate-500">{key}</div>
              <div className="mt-1 text-slate-300">{sourceFactLabel(value)}</div>
            </div>
          ))
        )}
      </div>
      {unavailableSources.length > 0 && (
        <TechnicalDetails title="读模型不可用来源">
          <div className="space-y-2">
            {unavailableSources.slice(0, 12).map((item: any, index) => (
              <div key={`${item.source || 'source'}-${item.code || 'code'}-${index}`} className="rounded border border-slate-800 p-2">
                <div className="font-medium text-slate-300">{displayValue(item.source, '未知来源')}</div>
                <div className="text-slate-500">{sourceFactLabel(item.error || item.code)}</div>
              </div>
            ))}
          </div>
        </TechnicalDetails>
      )}
    </ConsolePanel>
  );
}

function ValueTile({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="min-h-20 border-b border-r border-slate-800/90 px-4 py-4 last:border-r-0 md:border-b-0">
      <div className="text-[11px] font-medium uppercase text-slate-500">{label}</div>
      <div className="mt-2 min-w-0 truncate font-mono text-lg font-semibold text-slate-100">{displayValue(value, '暂无数据')}</div>
    </div>
  );
}

function TimeInput({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-slate-500">{label}</span>
      <input
        type="datetime-local"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-md border border-slate-700 bg-slate-900/70 px-2 py-2 text-sm text-slate-200 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-500/30"
      />
    </label>
  );
}

function PageButton({ disabled, onClick, children }: { disabled: boolean; onClick: () => void; children: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="cursor-pointer rounded-md border border-slate-700 px-3 py-1 text-slate-300 transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
    >
      {children}
    </button>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="px-4 py-7 text-center">
      <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full border border-slate-800 bg-slate-900/50">
        <ShieldCheck className="h-4 w-4 text-slate-500" />
      </div>
      <div className="mt-3 text-sm font-medium text-slate-200">{title}</div>
      <p className="mx-auto mt-1 max-w-md text-xs leading-5 text-slate-500">{body}</p>
    </div>
  );
}

function TradesSoftButton({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link
      to={to}
      className="inline-flex min-h-9 items-center gap-2 rounded-md border border-slate-700 bg-slate-900/70 px-3 py-2 text-sm text-slate-300 transition hover:bg-slate-800 hover:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
    >
      {children}
    </Link>
  );
}

function tradesStatusLabel(tone: ConsoleTone, activePositionCount: number, protectionStatus?: string): string {
  if (tone === 'intervention') return '需要介入';
  if (activePositionCount > 0) return protectionStatus === 'protected' ? '有敞口已保护' : '有敞口待确认';
  if (tone === 'attention') return '部分同步';
  return '无活跃敞口';
}

function shortProtectionStatusLabel(status?: string): string {
  const map: Record<string, string> = {
    protected: '完整',
    partially_protected: '部分',
    unprotected: '未保护',
    orphaned: '孤儿保护',
    unknown: '无法确认',
  };
  return map[String(status || 'unknown')] || '无法确认';
}

function exchangeAvailabilityMessage(unavailableSources: any[]): string {
  const exchangeIssue = unavailableSources.find((item: any) => item.source === 'exchange');
  if (exchangeIssue?.error) return '交易所只读事实当前不可用，页面仅能展示本地系统事实。';
  if (unavailableSources.length > 0) return `部分事实不可用：${unavailableSources.slice(0, 3).map((item: any) => displayValue(item.source, '未知来源')).join(' / ')}`;
  return '部分交易事实不可用。';
}

function semanticLabel(order: any): string {
  if (order.runtime_instance_id) return 'Runtime';
  if (order.order_candidate_id) return 'OrderCandidate';
  if (order.strategy_family_id) return 'StrategyFamily';
  if (order.signal_id) return '旧 signal';
  return '未绑定';
}

function dedupeUnavailableSources(items: any[]): any[] {
  const seen = new Set<string>();
  const result: any[] = [];
  for (const item of items) {
    const key = `${item?.source || ''}|${item?.code || ''}|${item?.error || ''}`;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(item);
  }
  return result;
}
