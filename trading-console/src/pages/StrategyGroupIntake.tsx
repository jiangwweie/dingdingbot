import {
  Boxes,
  FileCheck2,
  ListChecks,
  RadioTower,
  ShieldCheck,
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
  if (value.includes('ready')) return 'normal';
  if (value.includes('blocked') || value.includes('missing')) return 'blocked';
  if (value.includes('observe_only') || value.includes('conditional')) return 'attention';
  return 'unavailable';
}

function modeLabel(value?: string): string {
  const labels: Record<string, string> = {
    armed_observation: '武装观察',
    observe_only: '只观察',
    armed_observation_if_derivatives_facts_pass: '衍生品 facts 通过后武装观察',
    armed_observation_near_session_window: 'session 窗口武装观察',
  };
  return labels[String(value || '')] || displayValue(value, '待定');
}

function intakeLabel(value?: string): string {
  const labels: Record<string, string> = {
    ready_for_main_control_intake: '可接手',
    blocked_handoff_intake: '接手阻断',
    armed_observation_intake_ready: '可进入武装观察接入',
    observe_only_intake_ready: '只观察接入',
    conditional_armed_observation_intake_ready: '条件武装观察接入',
    blocked_handoff_incomplete: 'handoff 不完整',
  };
  return labels[String(value || '')] || displayValue(value, '状态未知');
}

export default function StrategyGroupIntake() {
  const { envelope, loading, error } = useReadModel<any>('/api/trading-console/strategy-group-handoff-intake');
  const {
    envelope: liveEnvelope,
    loading: liveLoading,
    error: liveError,
  } = useReadModel<any>('/api/trading-console/strategy-group-live-facts-readiness');

  if (loading) return <div className="p-4 text-sm text-slate-500">正在读取当前内容...</div>;

  const data = envelope?.data || {};
  const counts = data.counts || {};
  const groups = asArray<any>(data.strategy_picker);
  const watcherScope = asArray<any>(data.watcher_scope);
  const factRows = asArray<any>(data.required_facts_matrix);
  const source = data.source_anchor || {};
  const liveData = liveEnvelope?.data || {};
  const liveCounts = liveData.counts || {};
  const visibleFactRows = factRows.slice(0, 12);

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-100">Strategy Group Intake</h1>
          <p className="mt-1 text-sm text-slate-500">Strategy research handoff intake for picker, RequiredFacts, watcher scope, and armed observation.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusChip tone={toneForStatus(data.status)}>
            <Boxes className="h-3.5 w-3.5" />
            {intakeLabel(data.status)}
          </StatusChip>
          <StatusChip tone="unavailable">
            <FileCheck2 className="h-3.5 w-3.5" />
            {displayValue(source.commit, 'commit 未确认')}
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
            label="Groups"
            value={counts.strategy_groups ?? 0}
            tone={groups.length > 0 ? 'normal' : 'blocked'}
            icon={<Boxes className="h-4 w-4" />}
          />
          <MetricRailItem
            label="Armed Intake"
            value={counts.armed_observation_intake_ready ?? 0}
            tone={(counts.armed_observation_intake_ready ?? 0) > 0 ? 'attention' : 'unavailable'}
            icon={<ShieldCheck className="h-4 w-4" />}
          />
          <MetricRailItem
            label="Observe Only"
            value={counts.observe_only_intake_ready ?? 0}
            tone={(counts.observe_only_intake_ready ?? 0) > 0 ? 'attention' : 'unavailable'}
            icon={<RadioTower className="h-4 w-4" />}
          />
          <MetricRailItem
            label="Fact Rows"
            value={counts.required_fact_rows ?? 0}
            tone={(counts.required_fact_rows ?? 0) > 0 ? 'normal' : 'blocked'}
            icon={<ListChecks className="h-4 w-4" />}
          />
        </div>
      </ConsolePanel>

      <ConsolePanel title="Live Facts Readiness" caption={liveLoading ? '正在读取 live facts readiness' : displayValue(liveData.live_facts_source?.path, 'live facts source 未配置')}>
        <div className="grid grid-cols-1 divide-y divide-slate-800 md:grid-cols-4 md:divide-x md:divide-y-0">
          <MetricRailItem
            label="Observe Ready"
            value={liveCounts.observe_ready ?? 0}
            tone={(liveCounts.observe_ready ?? 0) > 0 ? 'normal' : liveError ? 'blocked' : 'unavailable'}
            icon={<RadioTower className="h-4 w-4" />}
          />
          <MetricRailItem
            label="Armed Ready"
            value={liveCounts.armed_candidate_prepare_ready ?? 0}
            tone={(liveCounts.armed_candidate_prepare_ready ?? 0) > 0 ? 'normal' : 'attention'}
            icon={<ShieldCheck className="h-4 w-4" />}
          />
          <MetricRailItem
            label="Candidate Blocked"
            value={liveCounts.blocked_for_candidate_prepare ?? 0}
            tone={(liveCounts.blocked_for_candidate_prepare ?? 0) > 0 ? 'attention' : 'normal'}
            icon={<ListChecks className="h-4 w-4" />}
          />
          <MetricRailItem
            label="Gate"
            value={displayValue(liveData.operator_path?.can_prepare_fresh_candidate ? 'candidate' : liveData.operator_path?.can_continue_observation ? 'observe' : 'blocked')}
            tone={liveData.operator_path?.can_prepare_fresh_candidate ? 'normal' : liveData.operator_path?.can_continue_observation ? 'attention' : 'blocked'}
            icon={<FileCheck2 className="h-4 w-4" />}
          />
        </div>
        {liveError && <div className="border-t border-slate-800 px-4 py-3 text-sm text-rose-300">live facts readiness 暂不可用</div>}
      </ConsolePanel>

      <ConsolePanel title="Strategy Picker Intake" caption={`${displayValue(source.branch)} · ${displayValue(source.handoff_dir)}`}>
        <div className="divide-y divide-slate-800/90">
          {groups.map((group) => (
            <div key={group.strategy_group_id}>
              <EntityRow
                title={group.strategy_group_id}
                subtitle={group.name}
                tone={toneForStatus(group.intake_status)}
                cells={[
                  { label: 'mode', value: modeLabel(group.picker?.default_mode) },
                  { label: 'symbols', value: group.supported_symbol_count ?? 0 },
                  { label: 'facts', value: group.required_fact_count ?? 0 },
                  { label: 'status', value: intakeLabel(group.intake_status) },
                ]}
              />
            </div>
          ))}
        </div>
      </ConsolePanel>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.25fr_0.75fr]">
        <ConsolePanel title="Watcher Scope" caption="Observation cadence recommendations from the anchored handoff.">
          <div className="divide-y divide-slate-800/90">
            {watcherScope.map((item) => (
              <div key={item.strategy_group_id}>
                <EntityRow
                  title={item.strategy_group_id}
                  subtitle={modeLabel(item.default_mode)}
                  tone={toneForStatus(item.intake_status)}
                  cells={[
                    { label: 'poll', value: displayValue(item.watcher_poll_cadence) },
                    { label: 'validity', value: displayValue(item.business_signal_validity) },
                    { label: 'fresh', value: `${item.candidate_packet_freshness_seconds ?? 120}s` },
                    { label: 'status', value: intakeLabel(item.intake_status) },
                  ]}
                />
              </div>
            ))}
          </div>
        </ConsolePanel>

        <InspectorPanel
          title="Execution Boundary"
          items={[
            {
              title: 'Handoff intake only',
              body: 'This page reads strategy research handoff metadata and does not register runtime instances, create candidates, or grant execution.',
              tone: 'normal',
            },
            {
              title: 'Facts before candidate',
              body: 'RequiredFacts, exchange rules, same-symbol account state, and protection hints must pass before candidate preparation.',
              tone: 'attention',
            },
            {
              title: 'Official submit path',
              body: 'A real action still requires fresh candidate, runtime grant, authorization evidence, action-time FinalGate, and Operation Layer.',
              tone: 'attention',
            },
          ]}
        />
      </div>

      <ConsolePanel title="RequiredFacts Preview" caption="First rows from the main-control readiness matrix.">
        <div className="divide-y divide-slate-800/90">
          {visibleFactRows.map((item, index) => (
            <div key={`${item.strategy_group_id}-${item.category}-${item.fact_key}-${index}`}>
              <EntityRow
                title={item.fact_key}
                subtitle={`${item.strategy_group_id} · ${item.category}`}
                tone={item.missing_behavior === 'block_candidate_prepare' ? 'blocked' : 'attention'}
                cells={[
                  { label: 'source', value: displayValue(item.readiness_source) },
                  { label: 'status', value: displayValue(item.current_status) },
                  { label: 'missing', value: displayValue(item.missing_behavior) },
                  { label: 'scope', value: 'readiness only' },
                ]}
              />
            </div>
          ))}
        </div>
      </ConsolePanel>

      <TechnicalDetails title="Strategy group intake payload">
        <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words">
          {JSON.stringify(envelope?.data || {}, null, 2)}
        </pre>
      </TechnicalDetails>
    </div>
  );
}
