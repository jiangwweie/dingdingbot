import { useEffect, useState } from 'react';
import { BookOpenCheck, ListChecks } from 'lucide-react';
import { Link } from 'react-router-dom';
import { brcApi, ReadinessResponse } from '@/src/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { DeveloperDetails, ErrorState, JsonDetails, OwnerSummary, StageStrip, StatusBadge } from './ConsolePrimitives';
import { whyText } from './readiness';

export default function Campaigns() {
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [packet, setPacket] = useState<Record<string, unknown> | null>(null);
  const [eligibility, setEligibility] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    brcApi.readiness()
      .then(async (payload) => {
        setReadiness(payload);
        if (payload.latest_campaign) {
          await Promise.all([
            brcApi.reviewPacket().then(setPacket).catch(() => setPacket(null)),
            brcApi.nextEligibility().then(setEligibility).catch(() => setEligibility(null)),
          ]);
        }
      })
      .catch(setError);
  }, []);

  if (error) return <ErrorState error={error} />;
  if (!readiness) return <div className="text-xs text-zinc-500">加载 Campaign 状态...</div>;

  const campaign = readiness.latest_campaign;
  return (
    <div className="space-y-4">
      <StageStrip
        current="Campaigns 轮次管理"
        next="查看最近 campaign 的状态、证据包和下一轮资格。"
        global="BRC 的核心是风险本金隔离、亏损锁定、盈利保护和复盘闭环。"
      />
      <OwnerSummary
        conclusion={campaign ? '已找到最近 Campaign，可查看复盘证据' : '当前没有可复盘 Campaign'}
        why={campaign ? whyText(readiness) : '数据库事实源没有 latest campaign，页面不会要求你手填 Campaign ID。'}
        canDo={campaign ? '查看状态、attempt 次数、mock PnL、profit protect、loss lock 和 next eligibility。' : '查看说明，等待受控 testnet 流程产生 campaign。'}
        cannotDo="不能通过本页创建 campaign、重置 loss counter 或绕过 review。"
        accountImpact="只读展示，不影响真实账户。"
        next={campaign ? '需要记录 Owner 复盘时，进入 Review 页面。' : '先完成受控 BRC testnet 或保留 observe-only。'}
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
                <Row label="Attempts 尝试次数" value={`${String(campaign.attempt_count || 0)} / ${String(campaign.max_attempts || 'unknown')}`} />
                <Row label="Realized / Mock P&L" value={String(campaign.realized_pnl ?? 'unknown')} />
                <Row label="Max campaign loss" value={String(campaign.max_campaign_loss ?? 'unknown')} />
                <Row label="Profit protect trigger" value={String(campaign.profit_protect_trigger ?? 'unknown')} />
                <JsonDetails data={campaign} label="展开 Campaign 技术详情" />
              </>
            ) : (
              <p className="text-zinc-500">暂无 campaign。Review 和下一轮资格判断会保持禁用，避免手工输入错误 ID。</p>
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

      <DeveloperDetails data={{ readiness, packet, eligibility }} />
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-zinc-100 pb-2 last:border-0 last:pb-0 dark:border-zinc-800">
      <span className="text-zinc-500">{label}</span>
      <span className="max-w-[60%] text-right font-medium">{value}</span>
    </div>
  );
}
