import {
  Crosshair,
  FileCheck2,
  ListChecks,
  RadioTower,
  ShieldCheck,
  SlidersHorizontal,
} from 'lucide-react';
import {
  ConsolePanel,
  EntityRow,
  InspectorPanel,
  MetricRailItem,
  StatusChip,
  type ConsoleTone,
} from '@/components/console/ConsolePrimitives';
import { TechnicalDetails } from '@/components/ui';
import { asArray, displayValue, useReadModel } from '@/lib/tradingConsoleApi';

function toneForStatus(status?: string): ConsoleTone {
  const value = String(status || '');
  if (value === 'ready_for_non_executing_prepare') return 'normal';
  if (value === 'waiting_for_market') return 'attention';
  if (value === 'ready' || value === 'fresh' || value === 'ready_for_action_time_final_gate') return 'normal';
  if (value === 'waiting' || value === 'missing' || value === 'progressive_pending' || value === 'not_reached_waiting_for_signal') return 'attention';
  if (value === 'not_reached') return 'unavailable';
  if (value.includes('active_position') || value.includes('hard_safety')) return 'blocked';
  if (value.includes('blocked')) return 'intervention';
  return 'unavailable';
}

function statusLabel(status?: string): string {
  const labels: Record<string, string> = {
    waiting_for_market: '等待市场信号',
    ready_for_non_executing_prepare: '可准备候选',
    blocked_missing_fact: '事实缺失',
    blocked_active_position_resolution: '仓位待处理',
    blocked_deployment_issue: '部署证据异常',
    blocked_hard_safety_stop: '安全硬停',
    blocked_operator_review: '审阅待处理',
    blocked_no_strategy_group: '未选策略组',
  };
  return labels[String(status || '')] || displayValue(status, '状态未知');
}

function boolClean(value: unknown): string {
  return value ? 'Clean' : 'Blocked';
}

export default function PilotControlBoard() {
  const { envelope, loading, error } = useReadModel<any>('/api/trading-console/strategygroup-runtime-pilot-status');

  if (loading) return <div className="p-4 text-sm text-slate-500">正在读取当前内容...</div>;

  const data = envelope?.data || {};
  const selection = data.pilot_selection || {};
  const ownerState = data.owner_state || {};
  const board = data.control_board || {};
  const strategyRow = board.strategy_group_row || {};
  const runtimeRow = board.runtime_row || {};
  const candidateRow = board.candidate_row || {};
  const reviewRow = board.review_row || {};
  const chain = asArray<any>(data.readiness_chain);
  const gateLedger = asArray<any>(data.gate_failure_ledger);
  const dualFreshness = data.dual_freshness || {};
  const strategyFreshness = dualFreshness.strategy_signal || {};
  const actionTimeFreshness = dualFreshness.action_time_facts || {};
  const watcher = data.watcher || {};
  const universe = asArray<string>(selection.selected_universe);
  const risk = selection.risk_profile || {};
  const statusTone = toneForStatus(data.status);

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-100">Pilot Control Board</h1>
          <p className="mt-1 text-sm text-slate-500">StrategyGroup runtime pilot · selected scope · current gate.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusChip tone={statusTone}>
            <Crosshair className="h-3.5 w-3.5" />
            {statusLabel(data.status)}
          </StatusChip>
          <StatusChip tone="unavailable">
            <SlidersHorizontal className="h-3.5 w-3.5" />
            {displayValue(risk.tier, 'tiny')} · {displayValue(risk.leverage, '1')}x
          </StatusChip>
        </div>
      </div>

      {error && (
        <ConsolePanel>
          <div className="px-4 py-4 text-sm text-rose-300">当前内容暂不可用</div>
        </ConsolePanel>
      )}

      <ConsolePanel>
        <div className="grid grid-cols-1 divide-y divide-slate-800 md:grid-cols-4 md:divide-x md:divide-y-0">
          <MetricRailItem
            label="StrategyGroup"
            value={displayValue(selection.strategy_group_id, 'NA')}
            tone={selection.strategy_group_id ? 'normal' : 'blocked'}
            icon={<Crosshair className="h-4 w-4" />}
          />
          <MetricRailItem
            label="Signal"
            value={statusLabel(data.status)}
            tone={statusTone}
            icon={<RadioTower className="h-4 w-4" />}
          />
          <MetricRailItem
            label="Universe"
            value={universe.length}
            sub="symbols"
            tone={universe.length > 0 ? 'normal' : 'blocked'}
            icon={<ListChecks className="h-4 w-4" />}
          />
          <MetricRailItem
            label="Safety"
            value={boolClean((data.safety_invariants || {}).places_order === false)}
            tone={(data.safety_invariants || {}).places_order === false ? 'normal' : 'blocked'}
            icon={<ShieldCheck className="h-4 w-4" />}
          />
        </div>
      </ConsolePanel>

      <ConsolePanel title="Owner State" caption={displayValue(ownerState.blocker_class)}>
        <div className="divide-y divide-slate-800/90">
          <EntityRow
            title={statusLabel(data.status)}
            subtitle={displayValue(ownerState.blocked_reason)}
            tone={statusTone}
            active
            cells={[
              { label: 'blocked_at', value: displayValue(ownerState.blocked_at) },
              { label: 'recover', value: displayValue(ownerState.next_recover_condition) },
              { label: 'auto action', value: displayValue(ownerState.automatic_recovery_action) },
              { label: 'downgrade', value: displayValue(ownerState.downgrade_mode) },
            ]}
          />
        </div>
      </ConsolePanel>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.35fr_0.65fr]">
        <ConsolePanel title="Control Rows" caption={`${displayValue(selection.selection_reason)} · ${universe.join(', ') || 'universe pending'}`}>
          <div className="divide-y divide-slate-800/90">
            <EntityRow
              title={displayValue(strategyRow.id, 'strategy group')}
              subtitle={displayValue(strategyRow.role)}
              tone={toneForStatus(strategyRow.status)}
              cells={[
                { label: 'signal', value: displayValue(strategyRow.signal_state) },
                { label: 'facts', value: displayValue(strategyRow.facts_state) },
                { label: 'risk', value: displayValue(strategyRow.risk_profile) },
                { label: 'next', value: displayValue(strategyRow.next_action) },
              ]}
            />
            <EntityRow
              title="Runtime"
              subtitle={displayValue(runtimeRow.next_gate)}
              tone={runtimeRow.active_position === 'no_active_position' && runtimeRow.open_order === 'no_open_orders' ? 'normal' : 'attention'}
              cells={[
                { label: 'budget', value: displayValue(runtimeRow.budget) },
                { label: 'attempts', value: displayValue(runtimeRow.attempts) },
                { label: 'position', value: displayValue(runtimeRow.active_position) },
                { label: 'orders', value: displayValue(runtimeRow.open_order) },
              ]}
            />
            <EntityRow
              title="Candidate"
              subtitle={displayValue(candidateRow.blocker)}
              tone={candidateRow.candidate_state === 'ready_for_non_executing_prepare' ? 'normal' : 'attention'}
              cells={[
                { label: 'symbol', value: displayValue(candidateRow.symbol) },
                { label: 'side', value: displayValue(candidateRow.side) },
                { label: 'FinalGate', value: displayValue(candidateRow.final_gate_status) },
                { label: 'Operation', value: displayValue(candidateRow.operation_layer_status) },
              ]}
            />
            <EntityRow
              title="Review"
              subtitle={displayValue(reviewRow.review_decision)}
              tone="unavailable"
              cells={[
                { label: 'outcome', value: displayValue(reviewRow.outcome) },
                { label: 'watcher', value: displayValue(watcher.wakeup_status) },
                { label: 'operator', value: displayValue(watcher.operator_status) },
                { label: 'resume', value: watcher.can_continue_steps_5_8 ? 'ready' : 'waiting' },
              ]}
            />
          </div>
        </ConsolePanel>

        <InspectorPanel
          title="Boundary"
          items={[
            {
              title: 'Tiny scope',
              body: `${displayValue(selection.strategy_group_id, 'NA')} · ${universe.join(', ') || 'no symbols'} · max active position ${displayValue(risk.max_active_position, '1')}.`,
              tone: 'normal',
            },
            {
              title: 'No shortcut',
              body: 'FinalGate and Operation Layer stay not reached until fresh candidate and authorization evidence exist.',
              tone: 'attention',
            },
            {
              title: 'Current checkpoint',
              body: displayValue(data.next_safe_checkpoint),
              tone: statusTone,
            },
          ]}
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <ConsolePanel title="Dual Freshness" caption="strategy signal · action-time facts">
          <div className="divide-y divide-slate-800/90">
            <EntityRow
              title="Strategy signal"
              subtitle={displayValue(strategyFreshness.current_gate)}
              tone={toneForStatus(strategyFreshness.status)}
              cells={[
                { label: 'status', value: displayValue(strategyFreshness.status) },
                { label: 'window', value: displayValue(strategyFreshness.freshness_window) },
                { label: 'candidate TTL', value: displayValue(strategyFreshness.candidate_packet_freshness_seconds) },
                { label: 'blockers', value: asArray(strategyFreshness.blockers).length },
              ]}
            />
            <EntityRow
              title="Action-time facts"
              subtitle={displayValue(actionTimeFreshness.reason)}
              tone={toneForStatus(actionTimeFreshness.status)}
              cells={[
                { label: 'status', value: displayValue(actionTimeFreshness.status) },
                { label: 'FinalGate', value: actionTimeFreshness.requires_final_gate ? 'required' : 'not required' },
                { label: 'Operation', value: actionTimeFreshness.requires_official_operation_layer ? 'required' : 'not required' },
                { label: 'fact blockers', value: asArray(actionTimeFreshness.candidate_fact_blockers).length },
              ]}
            />
          </div>
        </ConsolePanel>

        <ConsolePanel title="Gate Failure Ledger" caption="owner-readable first blocking layer">
          <div className="divide-y divide-slate-800/90">
            {gateLedger.map((item, index) => (
              <EntityRow
                key={`${item.gate}-${index}`}
                title={displayValue(item.gate)}
                subtitle={displayValue(item.blocked_reason)}
                tone={toneForStatus(item.status)}
                cells={[
                  { label: 'status', value: displayValue(item.status) },
                  { label: 'class', value: displayValue(item.blocker_class) },
                  { label: 'recover', value: displayValue(item.next_recover_condition) },
                  { label: 'downgrade', value: displayValue(item.downgrade_mode) },
                ]}
              />
            ))}
          </div>
        </ConsolePanel>
      </div>

      <ConsolePanel title="Readiness Chain">
        <div className="divide-y divide-slate-800/90">
          {chain.map((item, index) => (
            <div key={`${item.gate}-${index}`}>
              <EntityRow
                title={displayValue(item.gate)}
                subtitle={displayValue(item.class)}
                tone={toneForStatus(item.status)}
                cells={[
                  { label: 'status', value: displayValue(item.status) },
                  { label: 'class', value: displayValue(item.class) },
                  { label: 'blockers', value: asArray(item.blockers).length },
                  { label: 'scope', value: displayValue(selection.strategy_group_id) },
                ]}
                action={<FileCheck2 className="h-4 w-4 text-slate-500" />}
              />
            </div>
          ))}
        </div>
      </ConsolePanel>

      <TechnicalDetails title="Pilot status payload">
        <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words">
          {JSON.stringify(envelope?.data || {}, null, 2)}
        </pre>
      </TechnicalDetails>
    </div>
  );
}
