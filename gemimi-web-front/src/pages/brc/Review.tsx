import { FormEvent, useCallback, useEffect, useState } from 'react';
import { CheckCircle2 } from 'lucide-react';
import { brcApi, ReadinessResponse } from '@/src/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { DeveloperDetails, ErrorState, JsonDetails, OwnerSummary, StageStrip, StatusBadge } from './ConsolePrimitives';
import { actionDisabledReason, isActionEnabled, whyText } from './readiness';
import { OperationPreflightModal, OperationPreflightState } from './CommandCenter';

export default function Review() {
  const [campaignId, setCampaignId] = useState('');
  const [decision, setDecision] = useState('accepted');
  const [reason, setReason] = useState('BRC R4 local console reviewed');
  const [nextTask, setNextTask] = useState('BRC-R4 local UI/API acceptance');
  const [operationModal, setOperationModal] = useState<OperationPreflightState | null>(null);
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [packet, setPacket] = useState<Record<string, unknown> | null>(null);
  const [evidence, setEvidence] = useState<Record<string, unknown> | null>(null);
  const [accountFacts, setAccountFacts] = useState<Record<string, unknown> | null>(null);
  const [mi001, setMi001] = useState<Record<string, unknown> | null>(null);
  const [decisions, setDecisions] = useState<Array<Record<string, unknown>>>([]);
  const [bindings, setBindings] = useState<Array<Record<string, unknown>>>([]);
  const [eligibility, setEligibility] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    await brcApi.readiness()
      .then((payload) => {
        setReadiness(payload);
        const latestCampaignId = String(payload.latest_campaign?.campaign_id || '');
        setCampaignId(latestCampaignId);
        return Promise.all([
          brcApi.reviewPacket().then(setPacket).catch(() => setPacket(null)),
          brcApi.evidence().then(setEvidence).catch(() => setEvidence(null)),
          brcApi.accountFacts().then((result) => setAccountFacts(result as unknown as Record<string, unknown>)).catch(() => setAccountFacts(null)),
          brcApi.mi001SolReadiness().then((result) => setMi001(result as unknown as Record<string, unknown>)).catch(() => setMi001(null)),
          brcApi.listAdmissionDecisions().then((result) => setDecisions(result as unknown as Array<Record<string, unknown>>)).catch(() => setDecisions([])),
          brcApi.listTrialBindings().then((result) => setBindings(result as unknown as Array<Record<string, unknown>>)).catch(() => setBindings([])),
          brcApi.nextEligibility().then(setEligibility).catch(() => setEligibility(null)),
        ]);
      })
      .catch(setError);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!canSubmitReview) return;
    setLoading(true);
    setError(null);
    try {
      const preflight = await brcApi.preflightOperation({
        operation_type: 'write_review_decision',
        input_params: {
          campaign_id: campaignId,
          decision,
          reason_text: reason,
          next_recommended_task: nextTask,
          metadata: { source: 'review_page_operation' },
        },
        source: { kind: 'review_page', ref: campaignId },
      });
      setOperationModal({ loading: false, phrase: '', error: null, preflight, result: null });
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  async function startReviewOperation() {
    setOperationModal({ loading: true, phrase: '', error: null, preflight: null, result: null });
    setError(null);
    try {
      const preflight = await brcApi.preflightOperation({
        operation_type: 'start_review',
        input_params: { campaign_id: campaignId || undefined },
        source: { kind: 'review_page', ref: campaignId || 'latest' },
      });
      setOperationModal({ loading: false, phrase: '', error: null, preflight, result: null });
    } catch (err) {
      setOperationModal({ loading: false, phrase: '', error: String((err as { message?: unknown }).message || err), preflight: null, result: null });
    }
  }

  const canSubmitReview = isActionEnabled(readiness, 'write_review_decision') && Boolean(campaignId);
  const reviewDisabledReason = actionDisabledReason(readiness, 'write_review_decision');
  const latestCampaign = readiness?.latest_campaign || null;
  const latestDecision = decisions[0] || {};
  const latestBinding = bindings[0] || {};
  const metadata = recordAt(latestCampaign, 'metadata_json');
  const miReadiness = recordAt(mi001, 'readiness');
  const miRisk = recordAt(mi001, 'risk_policy');

  return (
    <div className="space-y-4">
      <StageStrip
        current="Review / Evidence"
        next="Review packet, evidence packet, next eligibility, review decisions, and audit-derived facts."
        global="Phase 0 keeps review and evidence read-heavy; review decisions are ledger records, not execution authorization."
      />
      <OwnerSummary
        conclusion={canSubmitReview ? '可以基于最近 campaign 写复盘结论' : '当前不能写复盘结论'}
        why={canSubmitReview ? whyText(readiness) : reviewDisabledReason}
        canDo={canSubmitReview ? '查看当前 campaign 摘要、填写 Owner 决策、记录下一步任务。' : '查看为什么 Review 不可用；Owner 不需要手填 Campaign ID。'}
        cannotDo="不会创建 campaign，不会触发 testnet，不会授权实盘或提现。"
        accountImpact="不会影响真实账户。Review decision 只是写入复盘事实。"
        next={canSubmitReview ? '先确认摘要和系统建议，再填写最终决定与原因。' : '等待产生 latest campaign 后再写复盘。'}
        tone={canSubmitReview ? 'success' : 'warning'}
      />
      <button
        type="button"
        onClick={startReviewOperation}
        disabled={loading}
        className="inline-flex min-h-9 items-center justify-center rounded-sm border border-zinc-300 px-3 py-2 text-xs font-bold text-zinc-700 hover:bg-zinc-100 disabled:opacity-60 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
      >
        Start Review Operation
      </button>
      {error && <ErrorState error={error} />}

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Final pre-start review packet</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
            <div className="rounded-sm border border-blue-500/30 bg-blue-500/[0.05] p-3 text-sm leading-6 text-blue-900 dark:text-blue-100">
              Final pre-start review 已完成；当前 blocker 是 startup guard runtime-coupled。Review / Evidence 仅用于复盘和验收，不授权 execution intent 或 order。
              <div className="mt-2">
                <StatusBadge state={stringAt(miReadiness, 'verdict', 'blocked_startup_guard_runtime_coupled')} />
              </div>
            </div>
            <ReviewFact label="review packet" value={packet ? 'reported' : 'not reported yet'} />
            <ReviewFact label="risk disclosure" value={stringAt(latestDecision, 'risk_disclosure_json', 'not reported yet')} />
            <ReviewFact label="Owner acceptance" value={stringAt(latestDecision, 'owner_risk_acceptance_id', stringAt(latestBinding, 'owner_risk_acceptance_id', 'not reported yet'))} />
            <ReviewFact label="account equity mapping" value={stringAt(miRisk, 'account_equity', stringAt(accountFacts, 'account_summary', 'not reported yet'))} />
            <ReviewFact label="terminal blocker" value={stringAt(miReadiness, 'verdict', 'not reported yet')} />
            <p className="rounded-sm border border-amber-500/30 bg-amber-500/[0.05] p-2 text-amber-800 dark:text-amber-200">
              Startup Guard runtime-coupled blocker 是 runtime-owned safety blocker，不是策略失败。技术标签：blocked_startup_guard_runtime_coupled。
            </p>
            <JsonDetails data={{ packet, mi001, latestDecision, latestBinding, accountFacts }} label="展开 final pre-start evidence" />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Signal / trial trade intent evidence</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
            <ReviewFact label="signal evaluation" value={evidence ? 'reported' : 'not reported yet'} />
            <ReviewFact label="signal_evaluated" value={stringAt(metadata, 'signal_evaluated', evidence ? 'reported' : 'not reported yet')} />
            <ReviewFact label="trial_trade_intent" value={`${stringAt(metadata, 'trial_trade_intent', 'not reported yet')} (evidence, not order)`} />
            <ReviewFact label="execution intent" value="none" />
            <ReviewFact label="order" value="none" />
            <p className="rounded-sm border border-zinc-200 bg-zinc-50 p-2 dark:border-zinc-800 dark:bg-zinc-950">
              trial_trade_intent 只是 evidence，不是 order、order request、execution intent、live permission 或 runtime command。signal / intent 缺失时保持 not reported yet，不伪造数据。
            </p>
            <JsonDetails data={evidence} label="展开 signal / trial evidence" />
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>当前 Campaign 摘要</CardTitle>
          </CardHeader>
          <CardContent>
            {latestCampaign ? (
              <div className="space-y-2 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
                <p>状态 Status：<StatusBadge state={latestCampaign.status} /></p>
                <p>结果 Outcome：{String(latestCampaign.outcome || '未结束')}</p>
                <p>尝试次数 Attempts：{String(latestCampaign.attempt_count || 0)} / {String(latestCampaign.max_attempts || 'unknown')}</p>
                <p>累计 P&L：{String(latestCampaign.realized_pnl ?? 'unknown')}</p>
                <p>Profit Protect（盈利保护）：{String((packet?.review_packet as Record<string, unknown> | undefined)?.profit_protect_triggered ?? '由证据包确认')}</p>
                <p>Loss Lock（亏损锁定）：{String((packet?.review_packet as Record<string, unknown> | undefined)?.loss_lock_triggered ?? '由证据包确认')}</p>
                <p>Final flatness（最终无持仓/挂单）：{String((packet?.review_packet as Record<string, unknown> | undefined)?.final_inventory_flat ?? '由证据包确认')}</p>
                <JsonDetails data={packet} label="展开 review packet" />
              </div>
            ) : (
              <p className="text-xs leading-5 text-zinc-500">
                当前没有 latest campaign，因此 Review 暂不可用。页面不会要求你手填 Campaign ID。
              </p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>系统建议</CardTitle>
          </CardHeader>
          <CardContent>
            {eligibility ? (
              <div className="space-y-2 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
                <p>下一轮是否允许：{String((eligibility.eligibility as Record<string, unknown> | undefined)?.next_campaign_allowed ?? 'unknown')}</p>
                <p>结论：{String((eligibility.eligibility as Record<string, unknown> | undefined)?.decision || 'unknown')}</p>
                <JsonDetails data={eligibility} label="展开 next eligibility" />
              </div>
            ) : (
              <p className="text-xs leading-5 text-zinc-500">
                暂无自动建议。默认不要跳过 Owner 复盘，也不要通过手填 ID 绕过 readiness。
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
            Review Decision（复盘结论）
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form className="grid grid-cols-1 gap-3 lg:grid-cols-2" onSubmit={submit}>
            <div className="rounded-sm border border-zinc-200 p-3 text-xs leading-5 text-zinc-600 dark:border-zinc-800 dark:text-zinc-400">
              <p className="text-[11px] font-bold uppercase tracking-widest text-zinc-500">绑定 Campaign</p>
              <p>{campaignId ? '已自动绑定最近 campaign。' : '暂无 campaign，不能提交复盘。'}</p>
              <DeveloperDetails data={{ campaign_id: campaignId || null }} label="Campaign ID 技术详情" />
            </div>
            <label className="block">
              <span className="text-[11px] font-bold uppercase tracking-widest text-zinc-500">Decision</span>
              <select
                className="mt-1 w-full rounded-sm border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 dark:border-zinc-800 dark:bg-zinc-950"
                value={decision}
                onChange={(event) => setDecision(event.target.value)}
              >
                <option value="accepted">accepted（接受）</option>
                <option value="needs_followup">needs_followup（需要跟进）</option>
                <option value="next_campaign_blocked">next_campaign_blocked（阻止下一轮）</option>
                <option value="testnet_rehearsal_authorized">testnet_rehearsal_authorized（授权 testnet 验收）</option>
              </select>
            </label>
            <label className="block lg:col-span-2">
              <span className="text-[11px] font-bold uppercase tracking-widest text-zinc-500">原因</span>
              <textarea
                className="mt-1 min-h-24 w-full rounded-sm border border-zinc-300 bg-white p-3 text-sm leading-6 outline-none focus:border-blue-500 dark:border-zinc-800 dark:bg-zinc-950"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
            </label>
            <label className="block lg:col-span-2">
              <span className="text-[11px] font-bold uppercase tracking-widest text-zinc-500">下一步建议</span>
              <input
                className="mt-1 w-full rounded-sm border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 dark:border-zinc-800 dark:bg-zinc-950"
                value={nextTask}
                onChange={(event) => setNextTask(event.target.value)}
              />
            </label>
            <button
              className="inline-flex items-center justify-center gap-2 rounded-sm border border-emerald-500 bg-emerald-600 px-3 py-2 text-xs font-bold uppercase tracking-widest text-white disabled:opacity-60"
              disabled={loading || !canSubmitReview || !reason.trim() || !nextTask.trim()}
              title={!canSubmitReview ? reviewDisabledReason : undefined}
            >
              <CheckCircle2 className="h-3.5 w-3.5" />
              写入复盘结论
            </button>
            {!canSubmitReview && (
              <p className="text-xs leading-5 text-amber-700 dark:text-amber-300">
                当前禁用原因：{reviewDisabledReason}
              </p>
            )}
          </form>
        </CardContent>
      </Card>

      <OperationPreflightModal
        state={operationModal}
        onClose={() => setOperationModal(null)}
        onStateChange={setOperationModal}
        onRefresh={load}
      />
      <DeveloperDetails data={{ readiness, packet, evidence, accountFacts, mi001, decisions, bindings, eligibility }} />
    </div>
  );
}

function recordAt(source: Record<string, unknown> | undefined | null, key: string): Record<string, unknown> {
  const value = source?.[key];
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function stringAt(source: Record<string, unknown> | undefined | null, key: string, fallback: string): string {
  const value = source?.[key];
  if (value === undefined || value === null || value === '') return fallback;
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function ReviewFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-zinc-100 pb-2 last:border-0 dark:border-zinc-800">
      <span className="text-zinc-500">{label}</span>
      <span className="max-w-[60%] break-words text-right font-medium">{value}</span>
    </div>
  );
}
