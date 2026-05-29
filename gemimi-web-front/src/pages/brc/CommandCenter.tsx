import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Activity, CircleDollarSign, GitBranch, ShieldCheck, X } from 'lucide-react';
import {
  brcApi,
} from '@/src/services/api';
import type {
  AccountFactsResponse,
  Mi001SolReadinessResponse,
  OperationCapability,
  OperationCapabilityStatus,
  OperationConfirmResponse,
  OperationPreflightResponse,
  ReadinessResponse,
} from '@/src/services/api';
import { Badge } from '@/src/components/ui/Badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import {
  ActionCardSummaryModal,
  CapabilityBadge,
  CapabilityStatus,
  capabilityForActionCard,
  ConsoleStatusBar,
  DeveloperDetails,
  ErrorState,
  JsonDetails,
  PrimaryActionPanel,
  QuickFact,
  StatusBadge,
} from './ConsolePrimitives';
import { actionCardDisabledReason, isActionCardEnabled } from './readiness';

export default function CommandCenter() {
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [accountFacts, setAccountFacts] = useState<AccountFactsResponse | null>(null);
  const [mi001, setMi001] = useState<Mi001SolReadinessResponse | null>(null);
  const [currentCampaign, setCurrentCampaign] = useState<Record<string, unknown> | null>(null);
  const [reviewPacket, setReviewPacket] = useState<Record<string, unknown> | null>(null);
  const [evidence, setEvidence] = useState<Record<string, unknown> | null>(null);
  const [capabilities, setCapabilities] = useState<OperationCapability[]>([]);
  const [selectedAction, setSelectedAction] = useState<ReadinessResponse['action_cards'][number] | null>(null);
  const [operationModal, setOperationModal] = useState<OperationPreflightState | null>(null);
  const [startupGuardActionResult, setStartupGuardActionResult] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    const [readinessPayload, capabilityPayload, accountFactsPayload, mi001Payload, currentCampaignPayload, reviewPacketPayload, evidencePayload] = await Promise.all([
      brcApi.readiness(),
      brcApi.operationCapabilities(),
      brcApi.accountFacts().catch(() => null),
      brcApi.mi001SolReadiness().catch(() => null),
      brcApi.currentCampaign().then((payload) => payload.campaign || null).catch(() => null),
      brcApi.reviewPacket().catch(() => null),
      brcApi.evidence().catch(() => null),
    ]);
    setReadiness(readinessPayload);
    setCapabilities(capabilityPayload.capabilities);
    setAccountFacts(accountFactsPayload);
    setMi001(mi001Payload);
    setCurrentCampaign(currentCampaignPayload);
    setReviewPacket(reviewPacketPayload);
    setEvidence(evidencePayload);
  }, []);

  useEffect(() => {
    load().catch(setError);
  }, [load]);

  const capabilityByType = useMemo(
    () => new Map(capabilities.map((capability) => [capability.operation_type, capability])),
    [capabilities],
  );

  if (error) return <ErrorState error={error} />;
  if (!readiness) return <div className="text-xs text-zinc-500">读取状态...</div>;

  const riskAccount = readiness.risk_account_summary || {};
  const accountState = recordAt(riskAccount, 'account_state');
  const exposure = recordAt(riskAccount, 'exposure_orders');
  const accountSummary = accountFacts?.account_summary || {};
  const reconciliationStatus = String(accountFacts?.reconciliation_status?.status || exposure.reconciliation_status || 'unknown');
  const flatness = recordAt(exposure, 'flatness_proof');
  const playbook = readiness.strategy_playbook_summary || readiness.playbook_summary || {};
  const environment = readiness.environment_boundary || {};
  const latestAudit = readiness.latest_audit;
  const testnetReady = isActionCardEnabled(readiness, 'testnet_rehearsal');
  const testnetReason = actionCardDisabledReason(readiness, 'testnet_rehearsal', '');
  const mainActions = readiness.action_cards.filter((action) => action.action_type !== 'read_status');
  const switchCapability = capabilityByType.get('switch_playbook');
  const operationLayerReadyCount = capabilities.filter((capability) => capability.executable_through_operation).length;

  const openSwitchPlaybookPreflight = async () => {
    setOperationModal({ loading: true, phrase: '', error: null, preflight: null, result: null });
    try {
      const preflight = await brcApi.preflightOperation({
        operation_type: 'switch_playbook',
        input_params: {
          target_playbook_id: 'PB-004-BRC-CONTROLLED-TESTNET',
          reason_category: 'owner_operation_layer',
          reason_text: 'Owner confirmed controlled BRC playbook switch from Command Center.',
          evidence_refs: ['docs/product/brc-owner-console-full-refactor.md'],
        },
      });
      setOperationModal({ loading: false, phrase: '', error: null, preflight, result: null });
    } catch (err) {
      setOperationModal({ loading: false, phrase: '', error: messageFromError(err), preflight: null, result: null });
    }
  };

  const runStartupGuardPreflight = async () => {
    setStartupGuardActionResult('Submitting startup guard preflight...');
    try {
      const result = await brcApi.armStartupGuardPreflight();
      setStartupGuardActionResult(`${result.status}: ${result.next_checklist_verdict}`);
      await load();
    } catch (err) {
      setStartupGuardActionResult(messageFromError(err));
    }
  };

  return (
    <div className="space-y-3">
      <ConsoleStatusBar
        items={[
          { label: '安全', value: riskText(readiness.risk_decision), tone: riskTone(readiness.risk_decision) },
          { label: 'Runtime', value: stateText(readiness.runtime_state), tone: stateTone(readiness.runtime_state) },
          { label: 'TRADING_ENV', value: envText(environment), tone: envText(environment) === 'live' ? 'warning' : 'info' },
          { label: 'Permission', value: permissionText(environment), tone: permissionText(environment) === 'intent_recording' ? 'warning' : 'outline' },
          { label: 'Orders', value: boolFrom(environment, 'order_allowed') ? 'allowed' : 'disabled', tone: boolFrom(environment, 'order_allowed') ? 'danger' : 'success' },
        ]}
      />

      <ExecutionPermissionPanel readiness={readiness} accountFacts={accountFacts} />

      {mi001 && (
        <Mi001SolReadinessPanel
          data={mi001}
          currentCampaign={currentCampaign}
          reviewPacket={reviewPacket}
          evidence={evidence}
        />
      )}

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-[1fr_1fr_1fr]">
        <CompactPanel
          icon={<ShieldCheck className="h-4 w-4 text-emerald-500" />}
          title="账户"
          rows={[
            ['Source', accountFacts?.source || stringAt(exposure, 'order_source', 'readiness_fallback')],
            ['Truth', accountFacts?.truth_level || 'summary'],
            ['Recon', <StatusBadge state={reconciliationStatus} />],
            ['真实影响', accountImpactText(stringAt(accountState, 'real_account_impact', 'none'))],
            ['审计', <StatusBadge state={valueAt(riskAccount, 'audit_writable', false) ? '可写' : '不可写'} />],
          ]}
        />
        <CompactPanel
          icon={<CircleDollarSign className="h-4 w-4 text-amber-500" />}
          title="仓位 / 订单"
          rows={[
            ['持仓', String(accountSummary.active_position_count ?? valueAt(exposure, 'active_position_count', 0))],
            ['挂单', String(accountSummary.open_order_count ?? valueAt(exposure, 'open_order_count', 0))],
            ['空仓', <StatusBadge state={(accountSummary.all_local_flat ?? valueAt(flatness, 'all_local_flat', false)) ? '是' : '否'} />],
          ]}
        />
        <CompactPanel
          icon={<GitBranch className="h-4 w-4 text-blue-500" />}
          title="Signal / Intent / Evidence"
          rows={[
            ['signal loop', signalLoopStatus(currentCampaign)],
            ['signal evaluated', evidence ? 'reported' : 'not reported yet'],
            ['trial trade intent', trialTradeIntentStatus(currentCampaign, evidence)],
          ]}
        />
      </div>

      <BoundaryPanel latestAudit={latestAudit} nextStep={readiness.next_step} testnetReason={testnetReason} operationLayerReadyCount={operationLayerReadyCount} />

      <DeveloperDetails data={{ readiness, account_facts: accountFacts, current_campaign: currentCampaign, review_packet: reviewPacket, evidence }} label="Details" />
      <ActionCardSummaryModal action={selectedAction} onClose={() => setSelectedAction(null)} />
      <OperationPreflightModal
        state={operationModal}
        onClose={() => setOperationModal(null)}
        onStateChange={setOperationModal}
        onRefresh={load}
      />
    </div>
  );
  async function openActionOperationPreflight(action: ReadinessResponse['action_cards'][number]) {
    const operationType = operationTypeForAction(action.action_type);
    const capability = capabilityByType.get(operationType);
    if (!capability || !canOpenOperationPreflight(capability)) {
      setSelectedAction(action);
      return;
    }
    setOperationModal({ loading: true, phrase: '', error: null, preflight: null, result: null });
    try {
      const preflight = await brcApi.preflightOperation({
        operation_type: operationType,
        input_params: operationInputForAction(action, readiness),
        source: { kind: 'command_center', ref: action.action_card_id },
      });
      setOperationModal({ loading: false, phrase: '', error: null, preflight, result: null });
    } catch (err) {
      setOperationModal({ loading: false, phrase: '', error: messageFromError(err), preflight: null, result: null });
    }
  }
}

function Mi001SolReadinessPanel({
  data,
  currentCampaign,
  reviewPacket,
  evidence,
}: {
  data: Mi001SolReadinessResponse;
  currentCampaign: Record<string, unknown> | null;
  reviewPacket: Record<string, unknown> | null;
  evidence: Record<string, unknown> | null;
}) {
  const blockingChecks = data.readiness.checks.filter((item) => item.blocking);
  return (
    <Card className="border-amber-500/30 bg-amber-500/[0.04]">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center justify-between gap-2">
          <span>MI-001 SOL Golden Path</span>
          <StatusBadge state={data.readiness.verdict} />
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
        <div className="rounded-sm border border-blue-500/30 bg-blue-500/[0.05] p-3 text-sm leading-6 text-blue-900 dark:text-blue-100">
          MI-001 SOL 已完成试验前准备和最终 review；当前 trial 未启动。唯一阻断项是 runtime-owned Startup Guard preflight。当前系统处于 Live 只读 / Intent Recording，不能下单。
          <div className="mt-2 flex flex-wrap gap-2 text-xs">
            <Badge variant="outline">technical: {data.readiness.verdict}</Badge>
            <Badge variant="outline">trial not started</Badge>
            <Badge variant="outline">no execution intent</Badge>
            <Badge variant="outline">no order</Badge>
          </div>
        </div>
        <div className="grid grid-cols-1 gap-2 lg:grid-cols-4">
          <QuickFact label="trial" value="not started" />
          <QuickFact label="execution intent" value="none" />
          <QuickFact label="order" value="none" />
          <QuickFact label="live trading" value="disabled" />
        </div>
        <p className="rounded-sm border border-rose-500/30 bg-rose-500/[0.04] p-2 text-rose-800 dark:text-rose-200">
          trial not started; no execution intent; no order; live trading disabled.
        </p>

        <div className="grid grid-cols-1 gap-2 lg:grid-cols-3">
          <div className="rounded-sm border border-zinc-200 bg-white/60 p-3 dark:border-zinc-800 dark:bg-zinc-950/50">
            <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-zinc-500">Candidate</p>
            <QuickFact label="Candidate id" value={data.candidate.candidate_id} />
            <QuickFact label="Strategy family" value={`${data.candidate.id} / ${data.candidate.strategy_family}`} />
            <QuickFact label="Symbol" value={data.candidate.symbol} />
            <QuickFact label="Side" value={data.candidate.side} />
            <QuickFact label="Terminal state" value={<StatusBadge state={data.terminal_state} />} />
          </div>
          <div className="rounded-sm border border-zinc-200 bg-white/60 p-3 dark:border-zinc-800 dark:bg-zinc-950/50">
            <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-zinc-500">Evidence</p>
            <QuickFact label="Signals" value={String(data.evidence.signal_count)} />
            <QuickFact label="72h mean" value={data.evidence.mean_72h} />
            <QuickFact label="72h positive" value={data.evidence.positive_rate_72h} />
            <QuickFact label="7d mean" value={data.evidence.mean_7d} />
            <QuickFact label="7d positive" value={data.evidence.positive_rate_7d} />
          </div>
          <div className="rounded-sm border border-zinc-200 bg-white/60 p-3 dark:border-zinc-800 dark:bg-zinc-950/50">
            <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-zinc-500">Risk policy</p>
            <QuickFact label="Capital source" value={data.risk_policy.capital_source} />
            <QuickFact label="Account equity" value={data.risk_policy.account_equity} />
            <QuickFact label="Available margin" value={data.risk_policy.available_margin} />
            <QuickFact label="Max leverage" value={`${data.risk_policy.max_leverage}x`} />
            <QuickFact label="Operation cap" value={data.risk_policy.operation_layer_notional_cap} />
          </div>
        </div>

        <div className="rounded-sm border border-zinc-200 bg-white/60 p-3 dark:border-zinc-800 dark:bg-zinc-950/50">
          <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-zinc-500">Terminal blocker</p>
          <div className="mb-2 rounded-sm border border-amber-500/30 bg-amber-500/[0.05] p-3 text-amber-900 dark:text-amber-100">
            <p className="font-semibold">Startup Guard 未在 runtime 中完成预检。</p>
            <p className="mt-1">
              这是 runtime-owned startup guard blocker，不是策略失败，不是 PG 注册失败，也不是账户事实失败。离线报告、PG metadata、Markdown packet 只能说明准备材料已存在，不能代表 runtime guard 已 armed。
            </p>
            <p className="mt-1">
              当前 Owner 选择是继续完善控制台验收，不继续 runtime-bound preflight；因此 trial 仍然未启动，execution intent 和 order 都不存在。
            </p>
            <div className="mt-2">
              <Badge variant="outline">technical: blocked_startup_guard_runtime_coupled</Badge>
            </div>
          </div>
          {blockingChecks.length > 0 ? (
            <ul className="list-disc space-y-1 pl-5">
              {blockingChecks.map((item) => (
                <li key={item.check}>
                  <span className="font-semibold">{item.check}:</span> {item.evidence}
                </li>
              ))}
            </ul>
          ) : (
            <p>No blocking checks currently reported.</p>
          )}
        </div>

        <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1fr_1fr]">
          <div className="rounded-sm border border-zinc-200 bg-white/60 p-3 dark:border-zinc-800 dark:bg-zinc-950/50">
            <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-zinc-500">Readiness checklist</p>
            <div className="space-y-2">
              {data.readiness.checks.map((item) => (
                <div key={item.check} className="grid grid-cols-[1fr_auto] gap-2 border-b border-zinc-100 pb-2 last:border-0 last:pb-0 dark:border-zinc-800">
                  <div>
                    <p className="font-semibold text-zinc-900 dark:text-zinc-100">{item.check}</p>
                    <p className="text-zinc-500">{item.evidence}</p>
                  </div>
                  <div className="text-right">
                    <StatusBadge state={checkStatus(item.status, item.blocking)} />
                    {item.blocking && <p className="mt-1 text-[10px] font-bold uppercase text-rose-600 dark:text-rose-300">blocking</p>}
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-sm border border-zinc-200 bg-white/60 p-3 dark:border-zinc-800 dark:bg-zinc-950/50">
            <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-zinc-500">Evidence limitations</p>
            <ul className="list-disc space-y-1 pl-5">
              {data.evidence.limitations.map((item) => <li key={item}>{item}</li>)}
            </ul>
            <p className="mt-3 mb-2 text-[10px] font-bold uppercase tracking-widest text-zinc-500">Risk prohibitions</p>
            <ul className="list-disc space-y-1 pl-5">
              {data.risk_policy.prohibitions.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1fr_1fr]">
          <div className="rounded-sm border border-zinc-200 bg-white/60 p-3 dark:border-zinc-800 dark:bg-zinc-950/50">
            <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-zinc-500">Golden path progress</p>
            <GoldenPathRows data={data} currentCampaign={currentCampaign} reviewPacket={reviewPacket} evidence={evidence} />
          </div>
          <div className="rounded-sm border border-zinc-200 bg-white/60 p-3 dark:border-zinc-800 dark:bg-zinc-950/50">
            <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-zinc-500">Non-permissions</p>
            <div className="grid grid-cols-1 gap-2 text-[11px] md:grid-cols-2">
              <QuickFact label="No execution permission" value={boolText(data.non_permissions.no_execution_permission)} />
              <QuickFact label="No order permission" value={boolText(data.non_permissions.no_order_permission)} />
              <QuickFact label="No runtime start" value={boolText(data.non_permissions.no_runtime_start)} />
              <QuickFact label="No leverage change" value={boolText(data.non_permissions.no_leverage_change)} />
              <QuickFact label="No order capability" value={boolText(data.non_permissions.no_order_capability)} />
              <QuickFact label="No automatic trial start" value={boolText(data.non_permissions.no_automatic_trial_start)} />
            </div>
          </div>
        </div>
        <div className="rounded-sm border border-zinc-200 bg-white/60 p-3 dark:border-zinc-800 dark:bg-zinc-950/50">
          <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-zinc-500">Allowed next / forbidden next</p>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
            <p className="rounded-sm border border-emerald-500/30 bg-emerald-500/[0.04] p-2 text-emerald-800 dark:text-emerald-200">
              Allowed: read readiness, review MI-001 SOL evidence, inspect account facts, inspect campaign metadata, and resolve the startup guard blocker in a separately authorized runtime-control task.
            </p>
            <p className="rounded-sm border border-rose-500/30 bg-rose-500/[0.04] p-2 text-rose-800 dark:text-rose-200">
              Forbidden: live trading, runtime start, trial start, execution intent creation, order creation, order placement, cancel, close, flatten, transfer, withdrawal, or permission mutation.
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function ExecutionPermissionPanel({
  readiness,
  accountFacts,
}: {
  readiness: ReadinessResponse;
  accountFacts: AccountFactsResponse | null;
}) {
  const boundary = readiness.environment_boundary || {};
  return (
    <Card className="border-blue-500/30 bg-blue-500/[0.04]">
      <CardHeader>
        <CardTitle>Execution Permission</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
        <div className="grid grid-cols-1 gap-2 lg:grid-cols-4">
          <QuickFact label="TRADING_ENV" value={envText(boundary)} />
          <QuickFact label="BRC_EXECUTION_PERMISSION_MAX" value={stringAt(boundary, 'brc_execution_permission_max', 'read_only')} />
          <QuickFact label="resolved permission" value={permissionText(boundary)} />
          <QuickFact label="live read-only" value={boolFrom(boundary, 'live_read_only') ? 'Live 只读 / Intent Recording' : 'not active'} />
        </div>
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
          <p className="rounded-sm border border-emerald-500/30 bg-emerald-500/[0.04] p-2 text-emerald-800 dark:text-emerald-200">
            Execution intent allowed: {boolFrom(boundary, 'execution_intent_allowed') ? 'yes' : 'no'}; order allowed: {boolFrom(boundary, 'order_allowed') ? 'yes' : 'no'}.
          </p>
          <p className="rounded-sm border border-zinc-200 bg-white/70 p-2 dark:border-zinc-800 dark:bg-zinc-950/50">
            Account fact source: {accountFacts?.source || 'not reported yet'}; truth level: {accountFacts?.truth_level || 'not reported yet'}.
          </p>
        </div>
        <p className="rounded-sm border border-amber-500/30 bg-amber-500/[0.05] p-2 text-amber-800 dark:text-amber-200">
          live 只表示当前环境字段；这里的 live 是 Live 只读 / Intent Recording，不是 live trading enabled。signal_loop_enabled、signal_generated、strategy_active、runtime_started 或 trial_trade_intent evidence 都不会授予下单权限。
        </p>
      </CardContent>
    </Card>
  );
}

function GoldenPathRows({
  data,
  currentCampaign,
  reviewPacket,
  evidence,
}: {
  data: Mi001SolReadinessResponse;
  currentCampaign: Record<string, unknown> | null;
  reviewPacket: Record<string, unknown> | null;
  evidence: Record<string, unknown> | null;
}) {
  const rows = [
    ['broad smoke', 'ready', `${data.evidence.signal_count} signal rows; research evidence only`],
    ['Owner acceptance', 'ready', data.source_refs.find((ref) => ref.includes('owner')) || 'reported by MI-001 readiness'],
    ['bounded trial plan', 'ready', 'funded validation plan reported; not trial started'],
    ['account equity mapping', 'ready', `${data.risk_policy.account_equity} equity / ${data.risk_policy.available_margin} available margin`],
    ['PG registration refs', 'ready', data.source_refs.filter((ref) => ref.includes('brc_')).join(', ') || 'not reported yet'],
    ['final pre-start review', reviewPacket ? 'ready' : 'warning', reviewPacket ? 'review packet reported' : 'not reported yet'],
    ['campaign metadata', currentCampaign ? 'ready' : 'warning', currentCampaign ? stringAt(currentCampaign, 'campaign_id', 'current campaign reported') : 'not reported yet'],
    ['signal / trial trade intent evidence', evidence ? 'warning' : 'warning', evidence ? 'evidence reported; not order' : 'not reported yet'],
    ['terminal state', data.readiness.verdict.includes('blocked') ? 'blocked' : 'ready', data.readiness.verdict],
  ];
  return (
    <div className="space-y-2">
      {rows.map(([label, status, value]) => (
        <div key={label} className="grid grid-cols-[1fr_auto] gap-2 border-b border-zinc-100 pb-2 last:border-0 last:pb-0 dark:border-zinc-800">
          <div>
            <p className="font-semibold text-zinc-900 dark:text-zinc-100">{label}</p>
            <p className="text-zinc-500">{value}</p>
          </div>
          <StatusBadge state={status} />
        </div>
      ))}
    </div>
  );
}

function BoundaryPanel({
  latestAudit,
  nextStep,
  testnetReason,
  operationLayerReadyCount,
}: {
  latestAudit?: Record<string, unknown> | null;
  nextStep: string;
  testnetReason: string;
  operationLayerReadyCount: number;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Why trial has not started</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
        <p>Trial has not started because the terminal blocker is startup guard/runtime coupling. No execution intent exists and no order exists.</p>
        <p>Next allowed work is inspection and resolving the runtime-owned guard blocker under explicit Owner authorization. Current next step: {nextStep}</p>
        {testnetReason && <p className="text-amber-700 dark:text-amber-300">Readiness reason: {testnetReason}</p>}
        <QuickFact label="operation preflight capability count" value={String(operationLayerReadyCount)} />
        <QuickFact label="latest audit" value={latestAudit ? stringAt(latestAudit, 'title', stringAt(latestAudit, 'type', 'event')) : 'not reported yet'} />
      </CardContent>
    </Card>
  );
}

function boolText(value: boolean) {
  return value ? 'true' : 'false';
}

function boolFrom(source: Record<string, unknown>, key: string): boolean {
  const value = source[key];
  return value === true || value === 'true';
}

function envText(source: Record<string, unknown>): string {
  return stringAt(source, 'trading_env', stringAt(source, 'current', 'unknown'));
}

function permissionText(source: Record<string, unknown>): string {
  return stringAt(source, 'resolved_permission', stringAt(source, 'brc_execution_permission_max', 'read_only'));
}

function checkStatus(status: string, blocking: boolean): string {
  if (blocking) return 'blocked';
  if (status === 'pass') return 'ready';
  if (status === 'not_checked') return 'future_phase';
  if (status === 'warning') return 'warning';
  return status;
}

function signalLoopStatus(campaign: Record<string, unknown> | null): string {
  const metadata = recordAt(campaign, 'metadata_json');
  return stringAt(metadata, 'signal_loop_status', stringAt(campaign, 'signal_loop_status', 'not reported yet'));
}

function trialTradeIntentStatus(campaign: Record<string, unknown> | null, evidence: Record<string, unknown> | null): string {
  const metadata = recordAt(campaign, 'metadata_json');
  const value = stringAt(metadata, 'trial_trade_intent', stringAt(evidence, 'trial_trade_intent', 'not reported yet'));
  return value === 'not reported yet' ? value : `${value} (evidence, not order)`;
}

function Phase0ActionCard({
  action,
  capability,
  onOpen,
  onOperationOpen,
}: {
  action: ReadinessResponse['action_cards'][number];
  capability?: OperationCapability;
  onOpen: () => void;
  onOperationOpen: () => void;
}) {
  const badge = capability ? capabilityBadgeLabel(capability.status) : capabilityForActionCard(action);
  const canOpenFixedRehearsal = action.action_type === 'testnet_rehearsal' && action.enabled;
  const canOpenOperation = Boolean(capability && canOpenOperationPreflight(capability));
  return (
    <Card className={action.enabled ? 'border-blue-500/20 bg-blue-500/[0.03]' : 'opacity-80'}>
      <CardHeader>
        <CardTitle className="flex items-center justify-between gap-2">
          <span>{action.title}</span>
          <CapabilityBadge status={badge} />
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
        <p>{action.what_will_change}</p>
        <p className="text-zinc-500">{action.what_will_not_change}</p>
        {!action.enabled && (
          <p className="rounded-sm border border-amber-500/30 bg-amber-500/[0.05] p-2 text-amber-700 dark:text-amber-300">
            {action.disabled_reason || 'Readiness has not enabled this action.'}
          </p>
        )}
        {badge !== 'Available now' && badge !== 'Operation Preflight available' && badge !== 'Legacy/dev path' && (
          <p className="rounded-sm border border-zinc-200 bg-zinc-50 p-2 text-zinc-500 dark:border-zinc-800 dark:bg-zinc-950">
            {capability?.current_reason || 'Phase 0 only shows this as readiness/design surface. Backend Operation execute is not enabled.'}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onOpen}
            className="inline-flex min-h-9 items-center justify-center rounded-sm border border-zinc-300 px-3 py-2 text-xs font-bold text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
          >
            View summary
          </button>
          {canOpenOperation && (
            <button
              type="button"
              onClick={onOperationOpen}
              className="inline-flex min-h-9 items-center justify-center rounded-sm border border-emerald-600 bg-emerald-600 px-3 py-2 text-xs font-bold text-white hover:bg-emerald-500"
            >
              {capability?.executable_through_operation ? 'Operation Preflight' : 'Preflight planning'}
            </button>
          )}
          {canOpenFixedRehearsal && (
            <Link
              to="/fixed-testnet-rehearsal"
              className="inline-flex min-h-9 items-center justify-center rounded-sm border border-blue-500 bg-blue-600 px-3 py-2 text-xs font-bold text-white hover:bg-blue-500"
            >
              Open fixed rehearsal
            </Link>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function OperationActionCard({
  capability,
  currentPlaybookId,
  onOpen,
}: {
  capability?: OperationCapability;
  currentPlaybookId: string;
  onOpen: () => void;
}) {
  const executable = Boolean(capability?.executable_through_operation);
  return (
    <Card className={executable ? 'border-emerald-500/30 bg-emerald-500/[0.04]' : 'border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900/50'}>
      <CardHeader>
        <CardTitle className="flex items-center justify-between gap-2">
          <span>Switch Playbook</span>
          <CapabilityBadge status={capability ? capabilityBadgeLabel(capability.status) : 'Unavailable'} />
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
        <QuickFact label="Current" value={currentPlaybookId} />
        <QuickFact label="Target" value="PB-004-BRC-CONTROLLED-TESTNET" />
        <p>
          Backend Operation Preflight checks playbook allowlist, campaign state, audit writability,
          confirmation binding, and local account/order drift before execution.
        </p>
        <p className="text-zinc-500">
          No orders are placed. Attempts, PnL, and loss lock are not reset.
        </p>
        {capability?.current_reason && (
          <p className="rounded-sm border border-zinc-200 bg-white/60 p-2 text-zinc-500 dark:border-zinc-800 dark:bg-zinc-950/50">
            {capability.current_reason}
          </p>
        )}
        <button
          type="button"
          onClick={onOpen}
          disabled={!executable}
          className={executable
            ? 'inline-flex min-h-9 items-center justify-center rounded-sm border border-emerald-600 bg-emerald-600 px-3 py-2 text-xs font-bold text-white hover:bg-emerald-500'
            : 'inline-flex min-h-9 cursor-not-allowed items-center justify-center rounded-sm border border-zinc-300 px-3 py-2 text-xs font-bold text-zinc-500 dark:border-zinc-700'}
        >
          Operation Preflight
        </button>
      </CardContent>
    </Card>
  );
}

function CapabilityMatrix({ capabilities }: { capabilities: OperationCapability[] }) {
  const priority = [
    'start_review',
    'write_review_decision',
    'run_fixed_testnet_rehearsal',
    'enter_observe',
    'enter_pause',
    'enter_strategy_or_monitor',
    'pause_new_entries',
    'emergency_stop_runtime',
    'emergency_flatten',
    'live_execution',
    'withdrawal',
    'transfer',
    'llm_direct_execution',
  ];
  const rows = priority
    .map((type) => capabilities.find((item) => item.operation_type === type))
    .filter(Boolean) as OperationCapability[];
  return (
    <Card>
      <CardHeader>
        <CardTitle>Capabilities</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {rows.map((capability) => (
          <div
            key={capability.operation_type}
            className="grid grid-cols-[minmax(0,1fr)_auto] gap-2 rounded-sm border border-zinc-200 p-2 text-xs dark:border-zinc-800"
          >
            <div className="min-w-0">
              <p className="truncate font-bold text-zinc-900 dark:text-zinc-100">{capability.display_name}</p>
              <p className="mt-0.5 line-clamp-2 text-zinc-500">{capability.current_reason}</p>
            </div>
            <CapabilityBadge status={capabilityBadgeLabel(capability.status)} />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export type OperationPreflightState = {
  loading: boolean;
  phrase: string;
  error: string | null;
  preflight: OperationPreflightResponse | null;
  result: OperationConfirmResponse | null;
  submitting?: boolean;
};

export function OperationPreflightModal({
  state,
  onClose,
  onStateChange,
  onRefresh,
}: {
  state: OperationPreflightState | null;
  onClose: () => void;
  onStateChange: (state: OperationPreflightState | null) => void;
  onRefresh: () => Promise<void>;
}) {
  if (!state) return null;
  const preflight = state.preflight;
  const phrase = preflight?.confirmation_requirement.phrase || '';
  const actualExecutionAvailable = Boolean(preflight?.after?.actual_execution_available);
  const planningOnly = Boolean(preflight?.after?.planning_only);
  const isRuntimeStop = preflight?.operation_type === 'emergency_stop_runtime';
  const isFlattenDryRun = preflight?.operation_type === 'emergency_flatten'
    && Boolean(preflight?.after?.dry_run_only);
  const confirmLabel = isFlattenDryRun ? 'Confirm dry-run record' : 'Confirm once';
  const confirmDisabled = !preflight
    || state.submitting
    || state.result !== null
    || !preflight.confirmation_requirement.required
    || preflight.status !== 'awaiting_confirmation'
    || state.phrase !== phrase;

  const update = (patch: Partial<OperationPreflightState>) => onStateChange({ ...state, ...patch });
  const confirm = async () => {
    if (!preflight || confirmDisabled) return;
    update({ submitting: true, error: null });
    try {
      const result = await brcApi.confirmOperation(preflight.operation_id, {
        preflight_id: preflight.preflight_id,
        confirmation_phrase: state.phrase,
        idempotency_key: preflight.idempotency_key,
      });
      update({ submitting: false, result });
      await onRefresh();
    } catch (err) {
      update({ submitting: false, error: messageFromError(err) });
    }
  };
  const cancel = async () => {
    if (!preflight || state.submitting || state.result) return;
    update({ submitting: true, error: null });
    try {
      const result = await brcApi.cancelOperation(preflight.operation_id);
      update({ submitting: false, result });
      await onRefresh();
    } catch (err) {
      update({ submitting: false, error: messageFromError(err) });
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/70 p-4">
      <div className="max-h-[92vh] w-full max-w-3xl overflow-auto rounded-sm border border-zinc-200 bg-white shadow-xl dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex items-start justify-between gap-3 border-b border-zinc-200 p-4 dark:border-zinc-800">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-600">Operation Preflight</p>
            <h2 className="mt-1 text-base font-bold text-zinc-950 dark:text-zinc-100">
              {preflight?.operation_type || 'Loading operation'}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-sm border border-zinc-300 p-1.5 text-zinc-600 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
            title="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="space-y-3 p-4 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
          <div className="rounded-sm border border-emerald-500/30 bg-emerald-500/[0.05] p-3 text-emerald-800 dark:text-emerald-200">
            This operation is authorized through the backend Operation layer.
            Confirmation is one-time and bound to this preflight snapshot when backend execution is available.
          </div>
          {state.loading && <div className="text-zinc-500">Building preflight...</div>}
          {state.error && (
            <div className="rounded-sm border border-rose-500/30 bg-rose-500/[0.05] p-3 text-rose-700 dark:text-rose-300">
              {state.error}
            </div>
          )}
          {preflight && (
            <>
              <div className="flex flex-wrap gap-2">
                <StatusBadge state={preflight.decision} />
                <StatusBadge state={state.result?.status ?? preflight.status} />
                <Badge variant="outline">{preflight.preflight_id}</Badge>
              </div>
              <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{preflight.summary}</p>
              {planningOnly && (
                <div className="rounded-sm border border-amber-500/30 bg-amber-500/[0.05] p-3 text-amber-800 dark:text-amber-200">
                  This is planning-only. Flatten planning does not execute flatten unless a backend executor is available.
                  Stop Runtime does not flatten or cancel orders by itself. Unknown or unmanaged exchange exposure blocks emergency execution.
                </div>
              )}
              {isFlattenDryRun && (
                <div className="rounded-sm border border-amber-500/30 bg-amber-500/[0.05] p-3 text-amber-800 dark:text-amber-200">
                  Dry-run only. No orders will be cancelled. No positions will be closed.
                  Candidate rows are diagnostic candidates, not executable actions.
                </div>
              )}
              {isRuntimeStop && (
                <div className="rounded-sm border border-blue-500/30 bg-blue-500/[0.05] p-3 text-blue-800 dark:text-blue-200">
                  Stop Runtime does not flatten positions. Stop Runtime does not cancel orders.
                  It only stops the runtime or strategy carrier where the backend Operation executor is available.
                </div>
              )}
              <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                <QuickFact label="operation_type" value={preflight.operation_type} />
                <QuickFact label="operation_id" value={<span className="font-mono">{preflight.operation_id}</span>} />
                <QuickFact label="expires_at" value={new Date(preflight.confirmation_requirement.expires_at_ms).toLocaleString()} />
                <QuickFact label="idempotency" value={<span className="font-mono">{preflight.idempotency_key}</span>} />
                <QuickFact label="actual_execution" value={actualExecutionAvailable ? 'available' : 'unavailable'} />
                {isFlattenDryRun && <QuickFact label="dry_run_only" value="true" />}
                <QuickFact label="account_source" value={stringAt(preflight.account_order_summary, 'source', stringAt(preflight.account_order_summary, 'data_source', 'unknown'))} />
                <QuickFact label="truth_level" value={stringAt(preflight.account_order_summary, 'truth_level', 'summary')} />
                <QuickFact label="reconciliation" value={stringAt(recordAt(preflight.account_order_summary, 'reconciliation_status'), 'status', stringAt(preflight.account_order_summary, 'reconciliation_status_value', 'unknown'))} />
                <QuickFact label="checked_sources" value={arrayAt(preflight.account_order_summary, 'checked_sources').length ? arrayAt(preflight.account_order_summary, 'checked_sources').join(', ') : 'none'} />
                <QuickFact label="mismatch_count" value={String(valueAt(preflight.account_order_summary, 'mismatch_count', 0))} />
                <QuickFact label="unmanaged_orders" value={String(arrayAt(preflight.account_order_summary, 'unknown_or_unmanaged_orders').length || valueAt(preflight.account_order_summary, 'unknown_or_unmanaged_order_count', 0))} />
                <QuickFact label="unmanaged_positions" value={String(arrayAt(preflight.account_order_summary, 'unknown_or_unmanaged_positions').length || valueAt(preflight.account_order_summary, 'unknown_or_unmanaged_position_count', 0))} />
                <QuickFact label="evidence_refs" value={String(arrayAt(preflight.account_order_summary, 'evidence_refs').length)} />
              </div>
              <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                <JsonDetails data={preflight.before} label="Before" />
                <JsonDetails data={preflight.after} label="After" />
                {isFlattenDryRun && <JsonDetails data={recordAt(preflight.after, 'dry_run_plan')} label="Dry-run candidates" />}
                <JsonDetails data={preflight.account_order_summary} label="Account / Order summary" />
                <JsonDetails data={preflight.runtime_summary} label="Runtime summary" />
                <JsonDetails data={preflight.campaign_summary} label="Campaign summary" />
                <JsonDetails data={preflight.playbook_summary} label="Playbook summary" />
              </div>
              <RiskList title="Warnings" items={preflight.risk_summary.warnings || []} tone="warning" />
              <RiskList title="Blockers" items={preflight.risk_summary.blockers || []} tone="danger" />
              {preflight.confirmation_requirement.required && !state.result && (
                <div className="space-y-2 rounded-sm border border-zinc-200 p-3 dark:border-zinc-800">
                  <QuickFact label="Confirmation phrase" value={<span className="font-mono">{phrase}</span>} />
                  <input
                    value={state.phrase}
                    onChange={(event) => update({ phrase: event.target.value })}
                    className="min-h-10 w-full rounded-sm border border-zinc-300 bg-white px-3 py-2 font-mono text-xs text-zinc-900 outline-none focus:border-emerald-500 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
                    placeholder={phrase}
                    disabled={state.submitting}
                  />
                </div>
              )}
              {state.result && (
                <div className="rounded-sm border border-zinc-200 p-3 dark:border-zinc-800">
                  <div className="mb-2 flex items-center gap-2">
                    <span className="font-bold">Result</span>
                    <StatusBadge state={state.result.status} />
                  </div>
                  <JsonDetails data={state.result} label="Operation result" />
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={confirm}
                  disabled={confirmDisabled}
                  className={confirmDisabled
                    ? 'inline-flex min-h-9 cursor-not-allowed items-center justify-center rounded-sm border border-zinc-300 px-3 py-2 text-xs font-bold text-zinc-500 dark:border-zinc-700'
                    : 'inline-flex min-h-9 items-center justify-center rounded-sm border border-emerald-600 bg-emerald-600 px-3 py-2 text-xs font-bold text-white hover:bg-emerald-500'}
                >
                  {state.submitting ? 'Submitting...' : confirmLabel}
                </button>
                <button
                  type="button"
                  onClick={cancel}
                  disabled={!preflight || Boolean(state.result) || state.submitting}
                  className="inline-flex min-h-9 items-center justify-center rounded-sm border border-zinc-300 px-3 py-2 text-xs font-bold text-zinc-700 hover:bg-zinc-100 disabled:cursor-not-allowed disabled:text-zinc-400 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
                >
                  Cancel operation
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function RiskList({ title, items, tone }: { title: string; items: string[]; tone: 'warning' | 'danger' }) {
  if (items.length === 0) return null;
  const color = tone === 'danger'
    ? 'border-rose-500/30 bg-rose-500/[0.05] text-rose-700 dark:text-rose-300'
    : 'border-amber-500/30 bg-amber-500/[0.05] text-amber-700 dark:text-amber-300';
  return (
    <div className={`rounded-sm border p-3 ${color}`}>
      <p className="mb-1 text-[10px] font-bold uppercase tracking-widest">{title}</p>
      <ul className="list-disc space-y-1 pl-5">
        {items.map((item) => <li key={item}>{item}</li>)}
      </ul>
    </div>
  );
}

function CompactPanel({
  icon,
  title,
  rows,
}: {
  icon: ReactNode;
  title: string;
  rows: Array<[string, ReactNode]>;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">{icon}{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        {rows.map(([label, value]) => (
          <QuickFact key={label} label={label} value={value} />
        ))}
      </CardContent>
    </Card>
  );
}

function recordAt(source: Record<string, unknown> | undefined | null, key: string): Record<string, unknown> {
  const value = source?.[key];
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function valueAt(source: Record<string, unknown> | undefined | null, key: string, fallback: unknown): unknown {
  return source && key in source ? source[key] : fallback;
}

function stringAt(source: Record<string, unknown> | undefined | null, key: string, fallback: string): string {
  const value = valueAt(source, key, fallback);
  return typeof value === 'string' ? value : String(value);
}

function arrayAt(source: Record<string, unknown> | undefined | null, key: string): string[] {
  const value = source?.[key];
  return Array.isArray(value) ? value.map((item) => String(item)) : [];
}

function riskText(decision: string): string {
  const labels: Record<string, string> = {
    ALLOW_READ: '只读',
    ALLOW_MONITOR: '可监控',
    BLOCK_TESTNET: '阻断',
    ATTENTION_REQUIRED: '需处理',
    BLOCK_ALL_STATE_CHANGE: '全阻断',
  };
  return labels[decision] || decision;
}

function riskTone(decision: string): 'info' | 'success' | 'warning' | 'danger' | 'outline' {
  if (decision === 'ALLOW_MONITOR') return 'success';
  if (decision === 'ALLOW_READ') return 'info';
  if (decision === 'BLOCK_ALL_STATE_CHANGE') return 'danger';
  return 'warning';
}

function stateText(state: string): string {
  const labels: Record<string, string> = {
    observe: '观察',
    monitor: '监控',
    testnet_rehearsal: '演练',
    paused: '暂停',
    stopped: '停止',
    flattening: '收平',
    attention_required: '需处理',
  };
  return labels[state] || state;
}

function stateTone(state: string): 'info' | 'success' | 'warning' | 'danger' | 'outline' {
  if (state === 'monitor' || state === 'observe') return 'success';
  if (state === 'attention_required') return 'danger';
  if (state === 'paused' || state === 'flattening') return 'warning';
  return 'outline';
}

function accountImpactText(value: string): string {
  return value === 'none' ? '无' : value;
}

function capabilityBadgeLabel(status: OperationCapabilityStatus): CapabilityStatus {
  const labels: Record<OperationCapabilityStatus, CapabilityStatus> = {
    enabled: 'Operation Preflight available',
    available: 'Available now',
    operation_preflight_available: 'Operation Preflight available',
    preflight_planning_available: 'Preflight planning',
    preflight_dry_run_available: 'Preflight planning',
    legacy_dev_path: 'Legacy/dev path',
    requires_operation_layer: 'Requires Operation Layer',
    design_surface_with_preflight: 'Preflight planning',
    design_surface: 'Design surface',
    unavailable: 'Unavailable',
    forbidden: 'Forbidden',
    not_implemented: 'Unavailable',
  };
  return labels[status] || 'Unavailable';
}

function canOpenOperationPreflight(capability: OperationCapability): boolean {
  return capability.executable_through_operation
    || capability.dry_run_only === true
    || capability.status === 'preflight_planning_available'
    || capability.status === 'preflight_dry_run_available'
    || capability.status === 'design_surface_with_preflight';
}

function operationTypeForAction(actionType: ReadinessResponse['action_cards'][number]['action_type']): string {
  const mapping: Record<ReadinessResponse['action_cards'][number]['action_type'], string> = {
    read_status: 'enter_observe',
    enter_monitor: 'enter_strategy_or_monitor',
    testnet_rehearsal: 'run_fixed_testnet_rehearsal',
    pause_new_entries: 'pause_new_entries',
    emergency_stop_runtime: 'emergency_stop_runtime',
    emergency_flatten: 'emergency_flatten',
  };
  return mapping[actionType];
}

function operationInputForAction(
  action: ReadinessResponse['action_cards'][number],
  readiness: ReadinessResponse,
): Record<string, unknown> {
  const operationType = operationTypeForAction(action.action_type);
  const common = {
    reason: `Owner confirmed ${action.title} from Command Center.`,
    source_action_card_id: action.action_card_id,
    fact_snapshot_id: action.fact_snapshot_id,
  };
  if (operationType === 'enter_observe') {
    return { ...common, target_state: 'observe' };
  }
  if (operationType === 'enter_pause') {
    return { ...common, target_state: 'paused' };
  }
  if (operationType === 'enter_strategy_or_monitor') {
    return {
      ...common,
      carrier: 'monitor',
      current_runtime_state: readiness.runtime_state,
      unrestricted_auto_trading: false,
    };
  }
  return common;
}

function messageFromError(error: unknown): string {
  if (typeof error === 'object' && error && 'message' in error) {
    return String((error as { message?: unknown }).message);
  }
  return String(error);
}
