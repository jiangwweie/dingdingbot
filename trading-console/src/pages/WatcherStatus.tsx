import {
  BellRing,
  CircleCheck,
  Clock3,
  FileCheck2,
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
import { displayValue, formatTimestampMs, useReadModel } from '@/lib/tradingConsoleApi';

function toneForStatus(status?: string): ConsoleTone {
  const value = String(status || '');
  if (value.includes('ready') || value === 'watching_no_signal') return 'normal';
  if (value.includes('attention') || value.includes('review') || value.includes('stale')) return 'attention';
  if (value.includes('blocked') || value.includes('unsafe') || value.includes('missing')) return 'blocked';
  return 'unavailable';
}

function statusLabel(status?: string): string {
  const labels: Record<string, string> = {
    ready: '部署就绪',
    post_signal_resume_ready: '可恢复推进',
    owner_attention_pending: '需要关注',
    watching_no_signal: '监测中',
    operator_packet_needs_review: '需要审阅',
    evidence_missing: '证据缺失',
    evidence_stale: '证据过期',
    notification_not_configured: '通知未配置',
    unsafe_watcher_effect_detected: '安全异常',
  };
  return labels[String(status || '')] || displayValue(status, '状态未知');
}

function boolLabel(value: unknown): string {
  return value ? '是' : '否';
}

export default function WatcherStatus() {
  const { envelope, loading, error } = useReadModel<any>('/api/trading-console/runtime-signal-watcher-status');

  if (loading) return <div className="p-4 text-sm text-slate-500">正在读取当前内容...</div>;

  const data = envelope?.data || {};
  const deployment = data.deployment_readiness || {};
  const watcher = data.watcher || {};
  const notification = data.notification || {};
  const resume = data.post_signal_resume || {};
  const safety = data.safety_invariants || {};
  const fileStatus = deployment.file_status || {};
  const readinessTone = toneForStatus(deployment.status);
  const resumeTone = resume.can_continue_steps_5_8 ? 'normal' : toneForStatus(watcher.wakeup_status);

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-100">Signal Watcher</h1>
          <p className="mt-1 text-sm text-slate-500">Tokyo runtime signal watcher readiness and post-signal resume gate.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusChip tone={readinessTone}>
            <RadioTower className="h-3.5 w-3.5" />
            {statusLabel(deployment.status)}
          </StatusChip>
          <StatusChip tone={resumeTone}>
            <ShieldCheck className="h-3.5 w-3.5" />
            {resume.can_continue_steps_5_8 ? '5-8 可继续' : '等待 fresh signal'}
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
            label="Watcher"
            value={statusLabel(watcher.wakeup_status)}
            tone={toneForStatus(watcher.wakeup_status)}
            icon={<RadioTower className="h-4 w-4" />}
          />
          <MetricRailItem
            label="Notification"
            value={notification.sent ? 'Sent' : notification.duplicate_suppressed ? 'Suppressed' : notification.required ? 'Pending' : 'Idle'}
            tone={notification.sent || notification.duplicate_suppressed ? 'normal' : notification.required ? 'attention' : 'unavailable'}
            icon={<BellRing className="h-4 w-4" />}
          />
          <MetricRailItem
            label="Evidence Age"
            value={deployment.latest_evidence_age_seconds ?? 'NA'}
            sub={deployment.latest_evidence_age_seconds === null || deployment.latest_evidence_age_seconds === undefined ? undefined : 'sec'}
            tone={toneForStatus(deployment.status)}
            icon={<Clock3 className="h-4 w-4" />}
          />
          <MetricRailItem
            label="Safety"
            value={(safety.forbidden_effect_flags || []).length === 0 ? 'Clean' : 'Blocked'}
            tone={(safety.forbidden_effect_flags || []).length === 0 ? 'normal' : 'blocked'}
            icon={<CircleCheck className="h-4 w-4" />}
          />
        </div>
      </ConsolePanel>

      <ConsolePanel title="Resume Gate" caption="Fresh signal must precede candidate, authorization, FinalGate, and official Operation Layer action.">
        <div className="divide-y divide-slate-800/90">
          <EntityRow
            title={resume.can_continue_steps_5_8 ? 'Post-signal chain ready' : 'Fresh signal not ready'}
            subtitle={displayValue(resume.current_gate, 'waiting_for_fresh_strategy_signal')}
            tone={resume.can_continue_steps_5_8 ? 'normal' : 'attention'}
            cells={[
              { label: 'wakeup', value: displayValue(watcher.wakeup_status) },
              { label: 'operator', value: displayValue(watcher.operator_status) },
              { label: 'notification', value: notification.duplicate_suppressed ? 'duplicate suppressed' : boolLabel(notification.sent) },
              { label: 'resume pack', value: displayValue(resume.resume_pack_path) },
            ]}
          />
        </div>
      </ConsolePanel>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.25fr_0.75fr]">
        <ConsolePanel title="Evidence Files" caption={displayValue(deployment.report_dir)}>
          <div className="divide-y divide-slate-800/90">
            {Object.entries(fileStatus).map(([name, status]: [string, any]) => (
              <div key={name}>
                <EntityRow
                  title={name}
                  subtitle={displayValue(status.path)}
                  tone={status.present ? 'normal' : 'blocked'}
                  cells={[
                    { label: 'present', value: boolLabel(status.present) },
                    { label: 'mtime', value: formatTimestampMs(status.mtime_ms) },
                    { label: 'source', value: envelope?.source || 'read_model' },
                    { label: 'freshness', value: envelope?.freshness_status || 'unknown' },
                  ]}
                  action={<FileCheck2 className="h-4 w-4 text-slate-500" />}
                />
              </div>
            ))}
          </div>
        </ConsolePanel>

        <InspectorPanel
          title="Safety Boundary"
          items={[
            {
              title: 'Read-only watcher',
              body: 'Watcher status reads evidence packets only and does not create orders, execution intents, budget mutations, withdrawals, or transfers.',
              tone: 'normal',
            },
            {
              title: 'Official resume path',
              body: 'A ready signal only resumes fresh candidate, runtime grant, authorization evidence, action-time FinalGate, official Operation Layer action, and post-submit settlement.',
              tone: resume.can_continue_steps_5_8 ? 'normal' : 'attention',
            },
            {
              title: 'Duplicate suppression',
              body: notification.duplicate_suppressed ? 'The latest duplicate event was suppressed.' : 'Notification state is available for duplicate suppression.',
              tone: notification.duplicate_suppressed || deployment.duplicate_suppression === 'active' ? 'normal' : 'unavailable',
            },
          ]}
        />
      </div>

      <TechnicalDetails title="Watcher read-model payload">
        <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words">
          {JSON.stringify(envelope?.data || {}, null, 2)}
        </pre>
      </TechnicalDetails>
    </div>
  );
}
