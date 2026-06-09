import { Link } from 'react-router-dom';
import type { ReactNode } from 'react';
import { AlertTriangle, FileSearch, ListChecks, ShieldCheck, Workflow } from 'lucide-react';
import {
  ActionNudge,
  ConsolePanel,
  EntityRow,
  InspectorPanel,
  MetricRailItem,
  StatusChip,
  type ConsoleTone,
} from '@/components/console/ConsolePrimitives';
import { DeferredActionSlot, EnvelopeStatus, TechnicalDetails } from '@/components/ui';
import { asArray, displayValue, formatTimestampMs, isNotAvailable, useReadModel } from '@/lib/tradingConsoleApi';
import {
  blockingReasonLabel,
  consistencyStatusLabel,
  orderClassLabel,
  orderRoleLabel,
  orderStatusLabel,
  protectionStatusLabel,
  sideLabel,
} from '@/lib/ownerViewModel';

function incidentTone(params: {
  error: string | null;
  manualActionRequired: boolean;
  recoveryRequired: boolean;
  recoveryTaskCount: number;
  mismatchCount: number;
  protectionStatus?: string;
  activePositionCount: number | null;
  cockpitBlockerCount: number;
  degraded: boolean;
}): ConsoleTone {
  if (params.error || params.manualActionRequired || params.recoveryRequired || params.recoveryTaskCount > 0 || params.mismatchCount > 0) {
    return 'intervention';
  }
  if (params.activePositionCount && params.activePositionCount > 0 && params.protectionStatus !== 'protected') return 'intervention';
  if (params.protectionStatus === 'orphaned' || params.protectionStatus === 'unprotected') return 'intervention';
  if (params.degraded || params.cockpitBlockerCount > 0 || params.protectionStatus === 'unknown') return 'attention';
  return 'normal';
}

function protectionTone(status?: string): ConsoleTone {
  if (status === 'protected') return 'normal';
  if (status === 'partially_protected' || status === 'unknown') return 'attention';
  if (status === 'unprotected' || status === 'orphaned') return 'intervention';
  return 'unavailable';
}

function mismatchTone(item: any): ConsoleTone {
  const classification = String(item.classification || 'unknown');
  if (classification === 'mismatch' || classification === 'orphan_protection') return 'intervention';
  if (classification === 'pg_only' || classification === 'exchange_only' || classification === 'pg_unchecked') return 'attention';
  return 'unavailable';
}

function taskTone(task: any): ConsoleTone {
  const status = String(task.status || '').toLowerCase();
  if (status.includes('failed') || status.includes('pending') || status.includes('retry')) return 'intervention';
  if (status.includes('resolved') || status.includes('closed')) return 'normal';
  return 'attention';
}

function shortProtectionLabel(status?: string): string {
  if (status === 'protected') return '完整';
  if (status === 'partially_protected') return '部分';
  if (status === 'unprotected') return '未保护';
  if (status === 'orphaned') return '孤儿单';
  if (status === 'unknown') return '无法确认';
  return '暂无';
}

function incidentStatusLabel(tone: ConsoleTone, degraded: boolean): string {
  if (tone === 'intervention' || tone === 'blocked') return '需要介入';
  if (tone === 'attention') return degraded ? '部分事实不可核验' : '有待关注项';
  return '暂无活动异常';
}

function actionLabel(action: string): string {
  const map: Record<string, string> = {
    retry_protection: '重试保护单',
    cancel_order: '取消订单',
    cancel_protection: '取消保护单',
    flatten_position: '平仓',
    resolve_recovery_task: '关闭恢复任务',
    manual_reconciliation: '人工对账',
  };
  return map[action] || action.replaceAll('_', ' ');
}

function factLabel(item: any): string {
  const code = displayValue(item?.error || item?.code, '无法确认');
  return blockingReasonLabel(code) === '需要人工确认' ? code : blockingReasonLabel(code);
}

function timeLabel(value: unknown): string {
  if (typeof value === 'number') return formatTimestampMs(value);
  if (typeof value === 'string' && value.trim()) return value;
  return '暂无';
}

function numericOrNull(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '' && !Number.isNaN(Number(value))) return Number(value);
  return null;
}

function dedupeUnavailableSources(items: any[]): any[] {
  const seen = new Set<string>();
  const result: any[] = [];
  for (const item of items) {
    const key = `${item?.source || 'source'}:${item?.code || item?.error || 'unknown'}`;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(item);
  }
  return result;
}

function recoveryTaskTitle(task: any, index: number): string {
  return displayValue(task.recovery_type || task.type || task.task_type || task.status, `恢复任务 ${index + 1}`);
}

function recoveryTaskSubtitle(task: any): string {
  const symbol = displayValue(task.symbol, '未知标的');
  const intent = displayValue(task.intent_id || task.execution_intent_id || task.order_id, '暂无关联意图');
  return `${symbol} · ${intent}`;
}

function conditionTone(pass: boolean, unavailable = false): ConsoleTone {
  if (pass) return 'normal';
  return unavailable ? 'attention' : 'intervention';
}

export default function RecoveryState() {
  const recoveryState = useReadModel<any>('/api/trading-console/recovery-exception-state?include_exchange=true');
  const protectionState = useReadModel<any>('/api/trading-console/protection-health?include_exchange=true');
  const ledgerState = useReadModel<any>('/api/trading-console/order-ledger?include_exchange=true&limit=100');
  const cockpitState = useReadModel<any>('/api/trading-console/operations-cockpit?include_exchange=true');

  const loading = recoveryState.loading && protectionState.loading && ledgerState.loading && cockpitState.loading;
  if (loading) {
    return (
      <div className="flex min-h-[480px] items-center justify-center rounded-md border border-slate-800 bg-slate-900/50 text-sm text-slate-400">
        正在读取异常介入状态...
      </div>
    );
  }

  const recoveryData = recoveryState.envelope?.data || {};
  const protectionData = protectionState.envelope?.data || {};
  const ledgerData = ledgerState.envelope?.data || {};
  const cockpitData = cockpitState.envelope?.data || {};
  const cockpitRecovery = cockpitData.recovery || {};

  const recoveryTasks = asArray(recoveryData.recovery_tasks);
  const mismatches = asArray(recoveryData.mismatches);
  const deferredActions = Array.from(new Set([
    ...asArray<string>(recoveryData.deferred_actions),
    ...asArray<string>(protectionData.deferred_actions),
  ]));
  const protectionFindings = asArray(protectionData.findings);
  const orphanProtectionOrders = asArray(protectionData.orphan_protection_orders);
  const currentScopeProtection = asArray(protectionData.current_scope_protection);
  const orders = asArray(ledgerData.orders);
  const blockers = asArray(cockpitData.blockers);
  const warnings = asArray(cockpitData.warnings);
  const unavailableSources = dedupeUnavailableSources([
    ...asArray(recoveryState.envelope?.unavailable),
    ...asArray(protectionState.envelope?.unavailable),
    ...asArray(ledgerState.envelope?.unavailable),
    ...asArray(cockpitState.envelope?.unavailable),
  ]);
  const errors = [recoveryState.error, protectionState.error, ledgerState.error, cockpitState.error].filter(Boolean) as string[];
  const activePositionCount = numericOrNull(protectionData.active_position_count);
  const degraded = [recoveryState.envelope, protectionState.envelope, ledgerState.envelope, cockpitState.envelope]
    .some((envelope) => envelope?.freshness_status !== 'fresh');
  const tone = incidentTone({
    error: errors[0] || null,
    manualActionRequired: recoveryData.manual_action_required === true || cockpitRecovery.manual_action_required === true,
    recoveryRequired: cockpitRecovery.required === true,
    recoveryTaskCount: recoveryTasks.length,
    mismatchCount: mismatches.length,
    protectionStatus: protectionData.status,
    activePositionCount,
    cockpitBlockerCount: blockers.length,
    degraded,
  });

  const exposedRecoveryActions = asArray(protectionData.actions_exposed);
  const noExecutableRecoveryActions = exposedRecoveryActions.length === 0;
  const consistencyStatus = cockpitRecovery.consistency_status || cockpitData.active_position?.consistency_status;
  const recoveryRequired = tone === 'intervention' || cockpitRecovery.required === true;
  const selectedMismatch = mismatches[0] || null;
  const recentOrders = orders.slice(0, 6);

  const inspectorItems: Array<{ title: string; body: string; tone: ConsoleTone; action?: ReactNode }> = [
    {
      title: recoveryRequired ? '介入优先级高于继续尝试' : '当前没有活动恢复任务',
      body: recoveryRequired
        ? '只要存在恢复任务、本地/交易所不一致或保护风险，新的策略尝试必须等官方恢复条件清除后再考虑。'
        : '当前恢复任务和不一致订单都为空；但只要 readmodel 降级，页面不会宣称系统完全干净。',
      tone,
    },
    {
      title: '恢复动作没有在前端开放',
      body: '此页不会调用取消订单、重试保护、平仓、resolve recovery task 或 exchange 写接口；deferred slot 只说明未来动作位。',
      tone: noExecutableRecoveryActions ? 'normal' : 'intervention',
    },
    {
      title: protectionData.status === 'protected' ? '保护事实已覆盖当前范围' : '保护事实需要核验',
      body: protectionData.status === 'protected'
        ? '当前 scope 的保护状态为完整。仍需在交易与仓位页核对订单归属。'
        : '保护状态不是完整可确认时，应先核验仓位、保护单和孤儿保护事实。',
      tone: protectionTone(protectionData.status),
    },
    {
      title: '恢复正常看条件，不看按钮',
      body: '恢复正常需要账户、订单、仓位、保护和对账事实重新可读并一致；不是点击单个按钮就能解除。',
      tone: unavailableSources.length > 0 ? 'attention' : 'normal',
    },
  ];

  return (
    <div className="mx-auto max-w-[1500px] space-y-4">
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusChip tone={tone}>{incidentStatusLabel(tone, degraded)}</StatusChip>
            {recoveryState.envelope?.freshness_status && (
              <StatusChip tone={recoveryState.envelope.freshness_status === 'fresh' ? 'normal' : 'attention'}>
                {recoveryState.envelope.freshness_status === 'fresh' ? '已同步' : '部分同步'}
              </StatusChip>
            )}
          </div>
          <h1 className="mt-4 text-3xl font-semibold text-slate-100">异常介入</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
            判断发生了什么、当前风险在哪里、系统已经停掉什么、Owner 可以核验什么，以及恢复正常需要满足哪些事实条件。
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <IncidentSoftButton to="/trades">
            <ListChecks className="h-4 w-4" />
            交易与仓位
          </IncidentSoftButton>
          <IncidentSoftButton to="/runtime">
            <ShieldCheck className="h-4 w-4" />
            运行治理
          </IncidentSoftButton>
          <IncidentSoftButton to="/evidence">
            <FileSearch className="h-4 w-4" />
            证据
          </IncidentSoftButton>
        </div>
      </header>

      <EnvelopeStatus envelope={recoveryState.envelope} error={errors[0] || null} />

      {(recoveryRequired || degraded) && (
        <ActionNudge
          tone={recoveryRequired ? 'intervention' : 'attention'}
          text={incidentNudgeText(recoveryRequired, recoveryTasks.length, mismatches.length, unavailableSources.length)}
          action={<IncidentSoftButton to="/trades">核验订单与保护</IncidentSoftButton>}
        />
      )}

      <ConsolePanel>
        <div className="grid grid-cols-1 md:grid-cols-5">
          <MetricRailItem label="恢复任务" value={recoveryTasks.length} tone={recoveryTasks.length > 0 ? 'intervention' : 'normal'} sub={taskCountSummary(recoveryData.recovery_task_counts)} />
          <MetricRailItem label="不一致订单" value={mismatches.length} tone={mismatches.length > 0 ? 'intervention' : 'normal'} sub="PG / Exchange" />
          <MetricRailItem label="保护状态" value={shortProtectionLabel(protectionData.status)} tone={protectionTone(protectionData.status)} sub={`${displayValue(protectionData.tp_count, '0')} TP / ${displayValue(protectionData.sl_count, '0')} SL`} />
          <MetricRailItem label="阻断项" value={blockers.length} tone={blockers.length > 0 ? 'attention' : 'normal'} sub={`${warnings.length} 条 warning`} />
          <MetricRailItem label="不可核验" value={unavailableSources.length} tone={unavailableSources.length > 0 ? 'attention' : 'normal'} sub="readmodel sources" />
        </div>
      </ConsolePanel>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-4">
          <IncidentBriefPanel
            tone={tone}
            recoveryRequired={recoveryRequired}
            summary={cockpitRecovery.summary}
            recoveryTasks={recoveryTasks}
            mismatches={mismatches}
            degraded={degraded}
            unavailableSources={unavailableSources}
            operationalDrift={recoveryData.operational_drift}
          />
          <CurrentRiskPanel
            activePositionCount={activePositionCount}
            protection={protectionData}
            protectionFindings={protectionFindings}
            orphanProtectionOrders={orphanProtectionOrders}
            selectedMismatch={selectedMismatch}
            consistencyStatus={consistencyStatus}
          />
          <SystemStoppedPanel
            deferredActions={deferredActions}
            exposedRecoveryActions={exposedRecoveryActions}
            blockers={blockers}
          />
          <OwnerInterventionPanel unavailableSources={unavailableSources} blockers={blockers} />
          <RecoveryConditionsPanel
            recoveryTasks={recoveryTasks}
            mismatches={mismatches}
            unavailableSources={unavailableSources}
            protectionStatus={protectionData.status}
            activePositionCount={activePositionCount}
            consistencyStatus={consistencyStatus}
            exposedRecoveryActions={exposedRecoveryActions}
          />
          <RecoveryTaskPanel recoveryTasks={recoveryTasks} />
          <MismatchPanel mismatches={mismatches} recentOrders={recentOrders} />
          <ProtectionFactPanel currentScopeProtection={currentScopeProtection} findings={protectionFindings} />
          <UnavailableFactsPanel unavailableSources={unavailableSources} />
          <TechnicalDetails title="Deferred recovery action slots">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {deferredActions.map((action) => (
                <DeferredActionSlot key={action} actionName={actionLabel(action)} reason="当前没有开放动作 API" />
              ))}
              {deferredActions.length === 0 && (
                <div className="text-sm text-slate-500">当前没有 deferred recovery action slot。</div>
              )}
            </div>
          </TechnicalDetails>
        </div>

        <InspectorPanel
          title="介入说明"
          items={inspectorItems}
          footer={
            <div className="space-y-2 text-xs leading-5 text-slate-500">
              <div>数据源：recovery-exception-state / protection-health / order-ledger / operations-cockpit。</div>
              <div>动作边界：无下单、无撤单、无重试保护、无平仓、无 exchange 写调用。</div>
            </div>
          }
        />
      </div>
    </div>
  );
}

function IncidentBriefPanel({
  tone,
  recoveryRequired,
  summary,
  recoveryTasks,
  mismatches,
  degraded,
  unavailableSources,
  operationalDrift,
}: {
  tone: ConsoleTone;
  recoveryRequired: boolean;
  summary: unknown;
  recoveryTasks: any[];
  mismatches: any[];
  degraded: boolean;
  unavailableSources: any[];
  operationalDrift: any;
}) {
  const driftEntries = Object.entries(operationalDrift || {}).filter(([, value]) => !isNotAvailable(value));
  return (
    <ConsolePanel
      title="发生了什么"
      caption="异常介入先看事实状态，再看恢复路径"
      action={<StatusChip tone={tone}>{recoveryRequired ? '需处理' : degraded ? '待核验' : '无活动异常'}</StatusChip>}
    >
      <div className="grid grid-cols-1 gap-px bg-slate-800/80 md:grid-cols-4">
        <IncidentTile label="恢复任务" value={recoveryTasks.length > 0 ? `${recoveryTasks.length} 个活动任务` : '暂无活动任务'} tone={recoveryTasks.length > 0 ? 'intervention' : 'normal'} />
        <IncidentTile label="不一致" value={mismatches.length > 0 ? `${mismatches.length} 个订单事实` : '暂无不一致订单'} tone={mismatches.length > 0 ? 'intervention' : 'normal'} />
        <IncidentTile label="事实完整性" value={unavailableSources.length > 0 ? `${unavailableSources.length} 项不可核验` : '关键事实可读'} tone={unavailableSources.length > 0 ? 'attention' : 'normal'} />
        <IncidentTile label="运行漂移" value={driftEntries.length > 0 ? `${driftEntries.length} 项` : '未看到漂移'} tone={driftEntries.length > 0 ? 'attention' : 'normal'} />
      </div>
      <div className="border-t border-slate-800/90 px-4 py-4 text-sm leading-6 text-slate-400">
        {displayValue(summary, degraded ? '当前没有活动恢复任务，但部分读模型事实不可核验。' : '当前未看到需要 Owner 立即介入的恢复事项。')}
      </div>
    </ConsolePanel>
  );
}

function CurrentRiskPanel({
  activePositionCount,
  protection,
  protectionFindings,
  orphanProtectionOrders,
  selectedMismatch,
  consistencyStatus,
}: {
  activePositionCount: number | null;
  protection: any;
  protectionFindings: any[];
  orphanProtectionOrders: any[];
  selectedMismatch: any;
  consistencyStatus: unknown;
}) {
  const cells = [
    {
      label: '活跃仓位',
      value: activePositionCount === null ? '无法确认' : String(activePositionCount),
      tone: activePositionCount === null ? 'attention' as ConsoleTone : activePositionCount > 0 ? 'attention' as ConsoleTone : 'normal' as ConsoleTone,
    },
    {
      label: '保护状态',
      value: protectionStatusLabel(protection.status),
      tone: protectionTone(protection.status),
    },
    {
      label: '孤儿保护',
      value: `${orphanProtectionOrders.length} 个`,
      tone: orphanProtectionOrders.length > 0 ? 'intervention' as ConsoleTone : 'normal' as ConsoleTone,
    },
    {
      label: '一致性',
      value: consistencyStatusLabel(String(consistencyStatus || 'unknown')),
      tone: String(consistencyStatus || '') === 'clean' || String(consistencyStatus || '') === 'matched' ? 'normal' as ConsoleTone : 'attention' as ConsoleTone,
    },
  ];
  return (
    <ConsolePanel
      title="当前风险"
      caption="判断现在是否有失控风险，而不是阻止所有小亏"
      action={<StatusChip tone={protectionTone(protection.status)}>{shortProtectionLabel(protection.status)}</StatusChip>}
    >
      <div className="grid grid-cols-1 gap-px bg-slate-800/80 md:grid-cols-4">
        {cells.map((cell) => (
          <div key={cell.label}>
            <IncidentTile label={cell.label} value={cell.value} tone={cell.tone} />
          </div>
        ))}
      </div>
      <div className="border-t border-slate-800/90 px-4 py-4">
        {selectedMismatch ? (
          <EntityRow
            title={`${displayValue(selectedMismatch.symbol, '未知标的')} · ${orderClassLabel(selectedMismatch.classification)}`}
            subtitle={displayValue(selectedMismatch.order_id || selectedMismatch.exchange_order_id, '暂无订单 ID')}
            tone={mismatchTone(selectedMismatch)}
            cells={[
              { label: '状态', value: orderStatusLabel(selectedMismatch.status) },
              { label: '角色', value: orderRoleLabel(selectedMismatch.order_role) },
              { label: '方向', value: sideLabel(selectedMismatch.side || selectedMismatch.direction) },
              { label: '详情', value: displayValue(selectedMismatch.details || selectedMismatch.reason, '待核验') },
            ]}
            action={<StatusChip tone={mismatchTone(selectedMismatch)}>重点</StatusChip>}
          />
        ) : protectionFindings.length > 0 ? (
          <div className="space-y-2">
            {protectionFindings.slice(0, 3).map((item: any, index) => (
              <div key={`${displayValue(item.code, 'finding')}-${index}`} className="rounded-md border border-slate-800 bg-slate-900/40 px-3 py-2 text-sm">
                <div className="font-medium text-slate-200">{displayValue(item.code, '保护发现')}</div>
                <div className="mt-1 text-xs leading-5 text-slate-500">{displayValue(item.message || item.details, '等待进一步核验。')}</div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            icon={<ShieldCheck className="h-4 w-4 text-slate-500" />}
            title="当前未看到具体异常订单"
            body="如果交易所事实不可读，仍需保持部分同步状态，不把空列表当作完整安全证明。"
          />
        )}
      </div>
    </ConsolePanel>
  );
}

function SystemStoppedPanel({
  deferredActions,
  exposedRecoveryActions,
  blockers,
}: {
  deferredActions: string[];
  exposedRecoveryActions: any[];
  blockers: any[];
}) {
  const stoppedItems = [
    { title: '真实恢复动作未开放', body: exposedRecoveryActions.length === 0 ? '前端没有 retry/cancel/flatten/resolve recovery 的可执行入口。' : '检测到恢复动作入口，需要复核是否已接入官方后端门禁。', tone: exposedRecoveryActions.length === 0 ? 'normal' as ConsoleTone : 'intervention' as ConsoleTone },
    { title: '新尝试受阻断项约束', body: blockers.length > 0 ? `operations cockpit 当前有 ${blockers.length} 个阻断项。` : '当前 cockpit 没有返回阻断项。', tone: blockers.length > 0 ? 'attention' as ConsoleTone : 'normal' as ConsoleTone },
    { title: 'Deferred slot 只展示未来能力', body: deferredActions.length > 0 ? deferredActions.map(actionLabel).join(' / ') : '当前没有 deferred action slot。', tone: 'unavailable' as ConsoleTone },
    { title: '禁止无边界处理', body: '不允许在此页面直接下单、撤单、重试保护、平仓或写入 exchange。', tone: 'normal' as ConsoleTone },
  ];
  return (
    <ConsolePanel title="系统已经停掉什么" caption="停止未授权动作，保留可复盘事实">
      <div className="grid grid-cols-1 gap-px bg-slate-800/80 md:grid-cols-2">
        {stoppedItems.map((item) => (
          <div key={item.title} className="min-h-28 bg-slate-900 px-4 py-4">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-100">
              <span className={`h-2 w-2 rounded-sm ${item.tone === 'normal' ? 'bg-emerald-400' : item.tone === 'intervention' ? 'bg-rose-400' : item.tone === 'attention' ? 'bg-amber-400' : 'bg-slate-400'}`} />
              {item.title}
            </div>
            <p className="mt-2 text-xs leading-5 text-slate-500">{item.body}</p>
          </div>
        ))}
      </div>
    </ConsolePanel>
  );
}

function OwnerInterventionPanel({ unavailableSources, blockers }: { unavailableSources: any[]; blockers: any[] }) {
  return (
    <ConsolePanel
      title="Owner 可以做什么"
      caption="只提供核验入口，不提供交易动作"
      action={<StatusChip tone="attention">人工核验</StatusChip>}
    >
      <div className="grid grid-cols-1 gap-px bg-slate-800/80 md:grid-cols-3">
        <OwnerStep
          icon={<ListChecks className="h-4 w-4" />}
          title="核验订单与仓位"
          body="先确认是否有活跃仓位、未完成订单、孤儿保护单或未归属订单。"
          to="/trades"
        />
        <OwnerStep
          icon={<Workflow className="h-4 w-4" />}
          title="查看运行阻断"
          body={blockers.length > 0 ? '运行治理页可查看 FinalGate、预算和 runtime readiness。' : '当前没有 cockpit 阻断项，但仍可核对 runtime 状态。'}
          to="/runtime"
        />
        <OwnerStep
          icon={<FileSearch className="h-4 w-4" />}
          title="追溯证据"
          body={unavailableSources.length > 0 ? '优先确认不可用来源，避免把读取缺失误判为干净状态。' : '事实可读时，可查看审计链确认恢复前后的记录。'}
          to="/evidence"
        />
      </div>
    </ConsolePanel>
  );
}

function RecoveryConditionsPanel({
  recoveryTasks,
  mismatches,
  unavailableSources,
  protectionStatus,
  activePositionCount,
  consistencyStatus,
  exposedRecoveryActions,
}: {
  recoveryTasks: any[];
  mismatches: any[];
  unavailableSources: any[];
  protectionStatus?: string;
  activePositionCount: number | null;
  consistencyStatus: unknown;
  exposedRecoveryActions: any[];
}) {
  const protectionOk = protectionStatus === 'protected' || (activePositionCount !== null && activePositionCount === 0);
  const consistencyOk = String(consistencyStatus || '') === 'clean' || String(consistencyStatus || '') === 'matched';
  const conditions = [
    {
      title: '恢复任务清零',
      body: recoveryTasks.length === 0 ? '没有活动 recovery task。' : '仍有恢复任务需要官方处理或核验。',
      pass: recoveryTasks.length === 0,
      unavailable: false,
    },
    {
      title: '本地/交易所一致',
      body: mismatches.length === 0 ? '没有可见 mismatch / pg_only / exchange_only / orphan_protection。' : '存在订单或保护事实不一致。',
      pass: mismatches.length === 0,
      unavailable: false,
    },
    {
      title: '账户与订单事实可读',
      body: unavailableSources.length === 0 ? '关键 readmodel 未报告不可用来源。' : `${unavailableSources.length} 个来源不可核验。`,
      pass: unavailableSources.length === 0,
      unavailable: true,
    },
    {
      title: '保护覆盖当前敞口',
      body: protectionOk ? '无活跃仓位或保护状态可接受。' : '保护状态不能证明当前敞口已受控。',
      pass: protectionOk,
      unavailable: protectionStatus === 'unknown',
    },
    {
      title: '一致性读数通过',
      body: consistencyOk ? 'cockpit 一致性状态为 clean/matched。' : '一致性状态仍需核验。',
      pass: consistencyOk,
      unavailable: isNotAvailable(consistencyStatus),
    },
    {
      title: '恢复动作仍受门禁',
      body: exposedRecoveryActions.length === 0 ? '没有前端恢复动作暴露。' : '检测到恢复动作入口，需要确认官方门禁。',
      pass: exposedRecoveryActions.length === 0,
      unavailable: false,
    },
  ];
  return (
    <ConsolePanel title="恢复正常条件" caption="满足条件后才允许回到下一次 runtime / candidate 评估">
      <div className="divide-y divide-slate-800/90">
        {conditions.map((condition) => (
          <div key={condition.title} className="flex flex-col gap-2 px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="font-medium text-slate-100">{condition.title}</div>
              <div className="mt-1 text-xs leading-5 text-slate-500">{condition.body}</div>
            </div>
            <StatusChip tone={conditionTone(condition.pass, condition.unavailable)}>
              {condition.pass ? '通过' : condition.unavailable ? '待核验' : '未通过'}
            </StatusChip>
          </div>
        ))}
      </div>
    </ConsolePanel>
  );
}

function RecoveryTaskPanel({ recoveryTasks }: { recoveryTasks: any[] }) {
  return (
    <ConsolePanel
      title="恢复任务"
      caption="仅展示任务事实；不提供 resolve/retry 动作"
      action={<StatusChip tone={recoveryTasks.length > 0 ? 'intervention' : 'normal'}>{recoveryTasks.length} 个</StatusChip>}
    >
      {recoveryTasks.length === 0 ? (
        <EmptyState
          icon={<AlertTriangle className="h-4 w-4 text-slate-500" />}
          title="当前没有活动恢复任务"
          body="如果 recovery repository 不可用，页面会在不可用事实里展示，不会把缺失仓库当作无任务。"
        />
      ) : (
        <div>
          {recoveryTasks.map((task: any, index) => (
            <div key={displayValue(task.task_id || task.id || task.intent_id, `task-${index}`)}>
              <EntityRow
                title={recoveryTaskTitle(task, index)}
                subtitle={recoveryTaskSubtitle(task)}
                tone={taskTone(task)}
                cells={[
                  { label: '状态', value: displayValue(task.status, '无法确认') },
                  { label: '重试', value: displayValue(task.retry_count, '0'), className: 'font-mono' },
                  { label: '创建', value: timeLabel(task.created_at || task.created_at_ms) },
                  { label: '错误', value: displayValue(task.error_message || task.reason, '暂无') },
                ]}
                action={<StatusChip tone={taskTone(task)}>任务</StatusChip>}
              />
            </div>
          ))}
        </div>
      )}
    </ConsolePanel>
  );
}

function MismatchPanel({ mismatches, recentOrders }: { mismatches: any[]; recentOrders: any[] }) {
  return (
    <ConsolePanel
      title="不一致与异常订单"
      caption="优先展示 mismatch；没有 mismatch 时展示最近订单事实"
      action={<StatusChip tone={mismatches.length > 0 ? 'intervention' : 'normal'}>{mismatches.length} 个 mismatch</StatusChip>}
    >
      {mismatches.length > 0 ? (
        <div>
          {mismatches.slice(0, 10).map((item: any, index) => (
            <div key={displayValue(item.order_id || item.exchange_order_id, `mismatch-${index}`)}>
              <EntityRow
                title={`${displayValue(item.symbol, '未知标的')} · ${orderClassLabel(item.classification)}`}
                subtitle={displayValue(item.order_id || item.exchange_order_id, '暂无订单 ID')}
                tone={mismatchTone(item)}
                cells={[
                  { label: '来源', value: displayValue(item.source, '未知') },
                  { label: '状态', value: orderStatusLabel(item.status) },
                  { label: '角色', value: orderRoleLabel(item.order_role) },
                  { label: '更新时间', value: timeLabel(item.updated_at || item.created_at) },
                ]}
                action={<StatusChip tone={mismatchTone(item)}>{sideLabel(item.side || item.direction)}</StatusChip>}
              />
            </div>
          ))}
        </div>
      ) : recentOrders.length > 0 ? (
        <div>
          {recentOrders.map((item: any, index) => (
            <div key={displayValue(item.order_id || item.exchange_order_id, `order-${index}`)}>
              <EntityRow
                title={`${displayValue(item.symbol, '未知标的')} · ${orderRoleLabel(item.order_role)}`}
                subtitle={displayValue(item.order_id || item.exchange_order_id, '暂无订单 ID')}
                tone={mismatchTone(item)}
                cells={[
                  { label: '分类', value: orderClassLabel(item.classification) },
                  { label: '状态', value: orderStatusLabel(item.status) },
                  { label: '方向', value: sideLabel(item.side || item.direction) },
                  { label: '数量', value: displayValue(item.requested_qty || item.filled_qty, '暂无'), className: 'font-mono' },
                ]}
                action={<StatusChip tone={mismatchTone(item)}>订单</StatusChip>}
              />
            </div>
          ))}
        </div>
      ) : (
        <EmptyState
          icon={<ListChecks className="h-4 w-4 text-slate-500" />}
          title="当前没有可展示订单事实"
          body="订单读模型为空或不可读时，请查看不可用事实和证据页。"
        />
      )}
    </ConsolePanel>
  );
}

function ProtectionFactPanel({ currentScopeProtection, findings }: { currentScopeProtection: any[]; findings: any[] }) {
  return (
    <ConsolePanel
      title="保护事实"
      caption="保护是失控边界，不是收益承诺"
      action={<StatusChip tone={currentScopeProtection.length > 0 ? 'attention' : 'unavailable'}>{currentScopeProtection.length} 个当前保护</StatusChip>}
    >
      {currentScopeProtection.length > 0 ? (
        <div>
          {currentScopeProtection.slice(0, 8).map((item: any, index) => (
            <div key={displayValue(item.order_id || item.exchange_order_id, `protection-${index}`)}>
              <EntityRow
                title={`${displayValue(item.symbol, '未知标的')} · ${orderRoleLabel(item.order_role)}`}
                subtitle={displayValue(item.order_id || item.exchange_order_id, '暂无订单 ID')}
                tone={protectionTone(item.protection_status || item.status)}
                cells={[
                  { label: '状态', value: orderStatusLabel(item.status) },
                  { label: '价格', value: displayValue(item.trigger_price || item.price, '暂无'), className: 'font-mono' },
                  { label: '数量', value: displayValue(item.quantity || item.requested_qty, '暂无'), className: 'font-mono' },
                  { label: '来源', value: displayValue(item.source, '未知') },
                ]}
                action={<StatusChip tone={protectionTone(item.protection_status || item.status)}>保护</StatusChip>}
              />
            </div>
          ))}
        </div>
      ) : findings.length > 0 ? (
        <div className="grid grid-cols-1 gap-3 px-4 py-4 md:grid-cols-2">
          {findings.slice(0, 6).map((item: any, index) => (
            <div key={`${displayValue(item.code, 'finding')}-${index}`} className="rounded-md border border-slate-800 bg-slate-900/40 px-3 py-3 text-sm">
              <div className="font-medium text-slate-100">{displayValue(item.code, '保护发现')}</div>
              <div className="mt-1 text-xs leading-5 text-slate-500">{displayValue(item.message || item.details, '等待核验。')}</div>
            </div>
          ))}
        </div>
      ) : (
        <EmptyState
          icon={<ShieldCheck className="h-4 w-4 text-slate-500" />}
          title="当前没有活跃保护单"
          body="没有活跃仓位时这通常是正常状态；如果仓位事实不可读，则不能据此判断安全。"
        />
      )}
    </ConsolePanel>
  );
}

function UnavailableFactsPanel({ unavailableSources }: { unavailableSources: any[] }) {
  return (
    <ConsolePanel
      title="不可用事实"
      caption="缺失事实必须显式展示，不能被解释为安全"
      action={<StatusChip tone={unavailableSources.length > 0 ? 'attention' : 'normal'}>{unavailableSources.length} 项</StatusChip>}
    >
      {unavailableSources.length === 0 ? (
        <EmptyState
          icon={<FileSearch className="h-4 w-4 text-slate-500" />}
          title="当前没有不可用来源"
          body="本页读取到的 recovery、protection、order、cockpit 来源未报告不可用项。"
        />
      ) : (
        <div className="grid grid-cols-1 gap-3 px-4 py-4 md:grid-cols-2 xl:grid-cols-3">
          {unavailableSources.slice(0, 12).map((item: any, index) => (
            <div key={`${displayValue(item.source, 'source')}-${displayValue(item.code, 'code')}-${index}`} className="rounded-md border border-slate-800 bg-slate-900/40 px-3 py-3 text-sm">
              <div className="text-xs text-slate-500">{displayValue(item.source, '未知来源')}</div>
              <div className="mt-1 font-medium text-slate-200">{factLabel(item)}</div>
            </div>
          ))}
        </div>
      )}
    </ConsolePanel>
  );
}

function IncidentTile({ label, value, tone }: { label: string; value: string; tone: ConsoleTone }) {
  return (
    <div className="min-h-20 bg-slate-900 px-4 py-3">
      <div className="flex items-center gap-2 text-[11px] font-medium uppercase text-slate-500">
        <span className={`h-2 w-2 rounded-sm ${tone === 'normal' ? 'bg-emerald-400' : tone === 'intervention' ? 'bg-rose-400' : tone === 'attention' ? 'bg-amber-400' : 'bg-slate-400'}`} />
        {label}
      </div>
      <div className="mt-2 truncate text-sm font-medium text-slate-100">{value}</div>
    </div>
  );
}

function OwnerStep({ icon, title, body, to }: { icon: ReactNode; title: string; body: string; to: string }) {
  return (
    <Link
      to={to}
      className="min-h-32 bg-slate-900 px-4 py-4 text-left transition hover:bg-slate-800/80 focus:outline-none focus:ring-2 focus:ring-blue-500"
    >
      <div className="flex items-center gap-2 text-sm font-medium text-slate-100">
        <span className="text-slate-400">{icon}</span>
        {title}
      </div>
      <p className="mt-3 text-xs leading-5 text-slate-500">{body}</p>
    </Link>
  );
}

function EmptyState({ icon, title, body }: { icon: ReactNode; title: string; body: string }) {
  return (
    <div className="px-4 py-7 text-center">
      <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full border border-slate-800 bg-slate-900/50">
        {icon}
      </div>
      <div className="mt-3 text-sm font-medium text-slate-200">{title}</div>
      <p className="mx-auto mt-1 max-w-md text-xs leading-5 text-slate-500">{body}</p>
    </div>
  );
}

function IncidentSoftButton({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link
      to={to}
      className="inline-flex min-h-9 items-center gap-2 rounded-md border border-slate-700 bg-slate-900/70 px-3 py-2 text-sm text-slate-300 transition hover:bg-slate-800 hover:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
    >
      {children}
    </Link>
  );
}

function incidentNudgeText(recoveryRequired: boolean, taskCount: number, mismatchCount: number, unavailableCount: number): string {
  if (recoveryRequired) {
    if (taskCount > 0) return `存在 ${taskCount} 个恢复任务，新的 runtime 尝试应保持关闭。`;
    if (mismatchCount > 0) return `存在 ${mismatchCount} 个订单/保护不一致，先核验交易与仓位。`;
    return '存在恢复或保护介入要求，先确认官方恢复条件。';
  }
  if (unavailableCount > 0) return `当前 ${unavailableCount} 个事实来源不可核验，不能把空异常列表当作完整安全证明。`;
  return '当前没有活动异常。';
}

function taskCountSummary(counts: unknown): string {
  if (!counts || typeof counts !== 'object') return '无活动任务';
  const entries = Object.entries(counts as Record<string, unknown>);
  if (entries.length === 0) return '无活动任务';
  return entries.slice(0, 2).map(([key, value]) => `${key}:${displayValue(value, '0')}`).join(' / ');
}
