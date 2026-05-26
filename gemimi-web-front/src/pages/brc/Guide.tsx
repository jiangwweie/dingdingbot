import { useEffect, useState, type ReactNode } from 'react';
import { BookOpenCheck, ListChecks } from 'lucide-react';
import { brcApi, ReadinessResponse } from '@/src/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import {
  ActionCard,
  DeveloperDetails,
  ErrorState,
  GuardNote,
  JsonDetails,
  OwnerSummary,
  StageStrip,
  StatusBadge,
} from './ConsolePrimitives';
import { whyText } from './readiness';

export default function Guide() {
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    brcApi.readiness().then(setReadiness).catch(setError);
  }, []);

  if (error) return <ErrorState error={error} />;
  if (!readiness) return <div className="text-xs text-zinc-500">加载 Guide 操作向导...</div>;

  const canDo = readiness.available_actions.length > 0
    ? readiness.available_actions.map((action) => action.title).join('；')
    : '当前没有可执行动作。';
  const cannotDo = readiness.disabled_actions.length > 0
    ? readiness.disabled_actions.map((action) => action.title).join('；')
    : '仍不能做真实实盘、提现、转账、自动下单或策略池执行。';

  return (
    <div className="space-y-4">
      <StageStrip
        current="BRC-R4.1 delivery owner guide"
        next={readiness.next_step}
        global="Bounded Risk Campaign System 主线；飞书、云部署、策略池和真实实盘仍是后续独立阶段。"
      />
      <OwnerSummary
        conclusion={readiness.current_conclusion}
        why={whyText(readiness)}
        canDo={canDo}
        cannotDo={cannotDo}
        accountImpact={readiness.account_impact}
        next={readiness.next_step}
        tone={readiness.mode === 'testnet_ready' ? 'warning' : readiness.mode === 'standalone_console' ? 'danger' : 'info'}
      />
      <GuardNote />

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ListChecks className="h-3.5 w-3.5 text-blue-500" />
              最近 Campaign（风险试错轮次）
            </CardTitle>
          </CardHeader>
          <CardContent>
            {readiness.latest_campaign ? (
              <div className="grid grid-cols-1 gap-2 text-xs leading-5 text-zinc-700 dark:text-zinc-300 md:grid-cols-2">
                <SummaryItem label="状态 Status" value={<StatusBadge state={readiness.latest_campaign.status} />} />
                <SummaryItem label="结果 Outcome" value={String(readiness.latest_campaign.outcome || '未结束')} />
                <SummaryItem label="尝试次数 Attempts" value={`${readiness.latest_campaign.attempt_count || 0} / ${readiness.latest_campaign.max_attempts || 'unknown'}`} />
                <SummaryItem label="累计 P&L" value={String(readiness.latest_campaign.realized_pnl ?? 'unknown')} />
                <SummaryItem label="Playbook" value={String(readiness.latest_campaign.current_playbook_id || 'unknown')} />
                <SummaryItem label="Finalized" value={String(readiness.latest_campaign.finalized_at_ms || 'not finalized')} />
                <div className="md:col-span-2">
                  <JsonDetails data={readiness.latest_campaign} label="展开 Campaign 技术详情" />
                </div>
              </div>
            ) : (
              <p className="text-xs leading-5 text-zinc-500">
                当前没有 latest campaign。Review 复盘会被禁用，Owner 不需要手填 Campaign ID。
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BookOpenCheck className="h-3.5 w-3.5 text-emerald-500" />
              最近 Review / Ledger 摘要
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
            <p>Review 是否可写：{readiness.review_summary.review_available ? '可以，已找到 campaign' : '暂不可用，需要先有 campaign'}</p>
            <p>最近复盘：{readiness.review_summary.latest_review_present ? '已记录' : '暂无记录'}</p>
            <p>最近操作记录：{readiness.review_summary.latest_operator_action_present ? '已记录' : '暂无记录'}</p>
            <p>这一区域只显示摘要；完整 JSON 保留在 Developer Detail。</p>
            <JsonDetails data={readiness.review_summary.latest_review} label="展开最近 review" />
            <JsonDetails data={readiness.review_summary.latest_operator_action} label="展开最近 operator action" />
          </CardContent>
        </Card>
      </div>

      <div>
        <h3 className="mb-2 text-xs font-bold uppercase tracking-widest text-zinc-500">可用动作</h3>
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          {readiness.available_actions.map((action) => <ActionCard key={action.action_id} action={action} />)}
        </div>
      </div>

      <div>
        <h3 className="mb-2 text-xs font-bold uppercase tracking-widest text-zinc-500">不可用动作</h3>
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          {readiness.disabled_actions.map((action) => <ActionCard key={action.action_id} action={action} />)}
        </div>
      </div>

      <DeveloperDetails
        data={{
          runtime_summary: readiness.runtime_summary,
          developer_details: readiness.developer_details,
          raw_readiness: readiness,
        }}
      />
    </div>
  );
}

function SummaryItem({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-sm border border-zinc-200 p-3 dark:border-zinc-800">
      <p className="mb-1 text-[10px] font-bold uppercase tracking-widest text-zinc-500">{label}</p>
      <div>{value}</div>
    </div>
  );
}
