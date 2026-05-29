import { useEffect, useState } from 'react';
import { BookOpenCheck, ListChecks } from 'lucide-react';
import { Link } from 'react-router-dom';
import { brcApi, ReadinessResponse } from '@/src/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { DeveloperDetails, ErrorState, JsonDetails, OwnerSummary, StageStrip, StatusBadge } from './ConsolePrimitives';
import { whyText } from './readiness';

export default function Campaigns() {
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [currentCampaign, setCurrentCampaign] = useState<Record<string, unknown> | null>(null);
  const [decisions, setDecisions] = useState<Array<Record<string, unknown>>>([]);
  const [bindings, setBindings] = useState<Array<Record<string, unknown>>>([]);
  const [evidence, setEvidence] = useState<Record<string, unknown> | null>(null);
  const [packet, setPacket] = useState<Record<string, unknown> | null>(null);
  const [eligibility, setEligibility] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    brcApi.readiness()
      .then(async (payload) => {
        setReadiness(payload);
        await Promise.all([
          brcApi.currentCampaign().then((result) => setCurrentCampaign(result.campaign || null)).catch(() => setCurrentCampaign(null)),
          brcApi.listAdmissionDecisions().then((result) => setDecisions(result as unknown as Array<Record<string, unknown>>)).catch(() => setDecisions([])),
          brcApi.listTrialBindings().then((result) => setBindings(result as unknown as Array<Record<string, unknown>>)).catch(() => setBindings([])),
          brcApi.evidence().then(setEvidence).catch(() => setEvidence(null)),
          brcApi.reviewPacket().then(setPacket).catch(() => setPacket(null)),
          brcApi.nextEligibility().then(setEligibility).catch(() => setEligibility(null)),
        ]);
      })
      .catch(setError);
  }, []);

  if (error) return <ErrorState error={error} />;
  if (!readiness) return <div className="text-xs text-zinc-500">加载 Campaign 状态...</div>;

  const campaign = currentCampaign || readiness.latest_campaign;
  const latestDecision = decisions[0] || {};
  const latestBinding = bindings[0] || {};
  const metadata = recordAt(campaign, 'metadata_json');
  return (
    <div className="space-y-4">
      <StageStrip
        current="Campaign"
        next="Review the business state, playbook, attempts, timeline evidence, and next campaign eligibility."
        global="Campaign is the business view. Account and order facts are shown in Markets & Orders."
      />
      <OwnerSummary
        conclusion={campaign ? '已找到最近 Campaign，可查看复盘证据' : '当前没有已启动 Campaign。MI-001 SOL 仍处于 pre-start readiness 阶段，因此没有可复盘 campaign。请在 Command Center 查看 readiness 和 blocker。'}
        why={campaign ? whyText(readiness) : '这是 trial 未启动导致的安全空态，不是数据丢失；页面不会要求 Owner 手填 Campaign ID。'}
        canDo={campaign ? '查看状态、attempt 次数、mock PnL、profit protect、loss lock 和 next eligibility。' : '查看空态说明，并回到 Command Center 核对 readiness checklist 与 startup guard blocker。'}
        cannotDo="不能通过本页创建 campaign、重置 loss counter 或绕过 review。"
        accountImpact="只读展示，不影响真实账户。"
        next={campaign ? '继续核对 admission chain、runtime metadata、signal/evidence 是否只是记录而非交易。' : '保留 observe-only；不要手填 Campaign ID、创建 campaign 或启动 trial。'}
        tone={campaign ? 'info' : 'warning'}
      />

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ListChecks className="h-3.5 w-3.5 text-blue-500" />
              最近 Campaign 摘要
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
            {campaign ? (
              <>
                <Row label="状态 Status" value={<StatusBadge state={campaign.status} />} />
                <Row label="Outcome 结果" value={String(campaign.outcome || '未结束')} />
                <Row label="Playbook" value={String(campaign.current_playbook_id || 'unknown')} />
                <Row label="admission_decision_id" value={stringAt(metadata, 'admission_decision_id', stringAt(latestDecision, 'admission_decision_id', 'not reported yet'))} />
                <Row label="binding_id" value={stringAt(metadata, 'admission_binding_id', stringAt(latestBinding, 'binding_id', 'not reported yet'))} />
                <Row label="constraint_snapshot_id" value={stringAt(metadata, 'constraint_snapshot_id', stringAt(latestBinding, 'trial_constraint_snapshot_id', 'not reported yet'))} />
                <Row label="strategy_family_version_id" value={stringAt(metadata, 'strategy_family_version_id', stringAt(latestBinding, 'strategy_family_version_id', 'not reported yet'))} />
                <Row label="playbook_id" value={stringAt(metadata, 'playbook_id', String(campaign.current_playbook_id || latestBinding.playbook_id || 'not reported yet'))} />
                <Row label="execution_mode" value={stringAt(metadata, 'execution_mode', stringAt(latestBinding, 'execution_mode', 'not reported yet'))} />
                <Row label="runtime_status" value={stringAt(metadata, 'runtime_status', stringAt(campaign, 'status', 'not reported yet'))} />
                <Row label="strategy_state" value={stringAt(metadata, 'strategy_state', 'not reported yet')} />
                <Row label="signal_loop status" value={stringAt(metadata, 'signal_loop_status', 'not reported yet')} />
                <Row label="signal_evaluated" value={stringAt(metadata, 'signal_evaluated', evidence ? 'reported' : 'not reported yet')} />
                <Row label="trial_trade_intent" value={`${stringAt(metadata, 'trial_trade_intent', 'not reported yet')} (evidence, not order)`} />
                <Row label="Attempts 尝试次数" value={`${String(campaign.attempt_count || 0)} / ${String(campaign.max_attempts || 'unknown')}`} />
                <Row label="Realized / Mock P&L" value={String(campaign.realized_pnl ?? 'unknown')} />
                <Row label="Max campaign loss" value={String(campaign.max_campaign_loss ?? 'unknown')} />
                <Row label="Profit protect trigger" value={String(campaign.profit_protect_trigger ?? 'unknown')} />
                <JsonDetails data={campaign} label="展开 Campaign 技术详情" />
              </>
            ) : (
              <div className="space-y-2 rounded-sm border border-amber-500/30 bg-amber-500/[0.05] p-3 text-amber-900 dark:text-amber-100">
                <p className="font-semibold">当前没有已启动 Campaign。</p>
                <p>MI-001 SOL 仍处于 pre-start readiness 阶段，trial 未启动，所以没有可复盘 campaign。这不是 campaign 数据丢失。</p>
                <p>请在 Command Center 查看 readiness checklist 和 startup guard blocker；本页不会要求 Owner 手填 Campaign ID，也不会提供创建或启动入口。</p>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BookOpenCheck className="h-3.5 w-3.5 text-emerald-500" />
              证据与下一轮资格
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
            <Row label="Review 可写" value={readiness.review_summary.review_available ? '可以，已自动绑定最近 campaign' : '暂不可用'} />
            <Row label="最近 Review" value={readiness.review_summary.latest_review_present ? '已记录' : '暂无记录'} />
            <Row label="下一轮判断" value={String((eligibility?.eligibility as Record<string, unknown> | undefined)?.decision || '暂无')} />
            <p className="text-[11px] leading-4 text-zinc-500">
              下一轮 campaign 不能通过切换 playbook 重置亏损状态。
            </p>
            {campaign && (
              <Link className="inline-flex rounded-sm border border-blue-500 bg-blue-600 px-3 py-2 text-[11px] font-bold uppercase tracking-widest text-white" to="/review">
                写 Review Decision
              </Link>
            )}
            <JsonDetails data={packet} label="展开 review packet" />
            <JsonDetails data={eligibility} label="展开 next eligibility" />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Status chain: every state below is not a trade</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-4">
          {[
            ['binding_reserved', stringAt(latestBinding, 'binding_status', 'not reported yet')],
            ['campaign_created', campaign ? 'reported' : 'not reported yet'],
            ['constraints_installed', stringAt(metadata, 'constraints_installed', 'not reported yet')],
            ['carrier_ready', stringAt(metadata, 'carrier_ready', 'not reported yet')],
            ['runtime_started_strategy_inactive', stringAt(metadata, 'runtime_status', 'not reported yet')],
            ['strategy_active_no_execution', stringAt(metadata, 'strategy_active', 'not reported yet')],
            ['signal_evaluated', stringAt(metadata, 'signal_evaluated', evidence ? 'reported' : 'not reported yet')],
            ['intent recorded', stringAt(metadata, 'trial_trade_intent', 'not reported yet')],
          ].map(([label, value]) => (
            <div key={label} className="rounded-sm border border-zinc-200 bg-zinc-50 p-2 text-xs dark:border-zinc-800 dark:bg-zinc-950">
              <p className="font-bold text-zinc-900 dark:text-zinc-100">{label}</p>
              <p className="text-zinc-500">{value}</p>
              <p className="mt-1 text-amber-700 dark:text-amber-300">not a trade</p>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card className="border-rose-500/30 bg-rose-500/[0.04]">
        <CardHeader>
          <CardTitle>Execution boundary</CardTitle>
        </CardHeader>
        <CardContent className="text-xs leading-5 text-rose-800 dark:text-rose-200">
          trial 未启动；execution intent 未创建；order 未创建。Campaign metadata、runtime_status、strategy_state、signal_evaluated 和 trial_trade_intent 都是 evidence 字段，不是交易动作。
        </CardContent>
      </Card>

      <DeveloperDetails data={{ readiness, currentCampaign, decisions, bindings, packet, eligibility, evidence }} />
    </div>
  );
}

function recordAt(source: Record<string, unknown> | undefined | null, key: string): Record<string, unknown> {
  const value = source?.[key];
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function stringAt(source: Record<string, unknown> | undefined | null, key: string, fallback: string): string {
  const value = source?.[key];
  return value === undefined || value === null || value === '' ? fallback : String(value);
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-zinc-100 pb-2 last:border-0 last:pb-0 dark:border-zinc-800">
      <span className="text-zinc-500">{label}</span>
      <span className="max-w-[60%] text-right font-medium">{value}</span>
    </div>
  );
}
