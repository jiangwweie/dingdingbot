import { FormEvent, useEffect, useState } from 'react';
import { CheckCircle2 } from 'lucide-react';
import { brcApi, ReadinessResponse, ReviewDecisionResponse } from '@/src/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { DeveloperDetails, ErrorState, JsonDetails, OwnerSummary, StageStrip, StatusBadge } from './ConsolePrimitives';
import { actionDisabledReason, isActionEnabled, whyText } from './readiness';

export default function Review() {
  const [campaignId, setCampaignId] = useState('');
  const [decision, setDecision] = useState('accepted');
  const [reason, setReason] = useState('BRC R4 local console reviewed');
  const [nextTask, setNextTask] = useState('BRC-R4 local UI/API acceptance');
  const [result, setResult] = useState<ReviewDecisionResponse | null>(null);
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [packet, setPacket] = useState<Record<string, unknown> | null>(null);
  const [eligibility, setEligibility] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    brcApi.readiness()
      .then((payload) => {
        setReadiness(payload);
        const latestCampaignId = String(payload.latest_campaign?.campaign_id || '');
        setCampaignId(latestCampaignId);
        if (isActionEnabled(payload, 'write_review_decision')) {
          return Promise.all([
            brcApi.reviewPacket().then(setPacket).catch(() => setPacket(null)),
            brcApi.nextEligibility().then(setEligibility).catch(() => setEligibility(null)),
          ]);
        }
        setPacket(null);
        setEligibility(null);
        return undefined;
      })
      .catch(setError);
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!canSubmitReview) return;
    setLoading(true);
    setError(null);
    try {
      setResult(await brcApi.createReviewDecision({
        campaign_id: campaignId,
        decision,
        reason_text: reason,
        next_recommended_task: nextTask,
      }));
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  const canSubmitReview = isActionEnabled(readiness, 'write_review_decision') && Boolean(campaignId);
  const reviewDisabledReason = actionDisabledReason(readiness, 'write_review_decision');
  const latestCampaign = readiness?.latest_campaign || null;

  return (
    <div className="space-y-4">
      <StageStrip
        current="BRC-R4 review decision"
        next="把 Owner 复盘结论写入数据库事实源。"
        global="复盘闭环是后续 Feishu 卡片和云部署审批链路的基础。"
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
      {error && <ErrorState error={error} />}

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

      <JsonDetails data={result} label="查看 review decision JSON" />
    </div>
  );
}
