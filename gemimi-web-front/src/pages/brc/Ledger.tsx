import { useEffect, useState } from 'react';
import { History } from 'lucide-react';
import { brcApi, ReadinessResponse } from '@/src/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { DeveloperDetails, EmptyState, ErrorState, JsonDetails, OwnerSummary, StageStrip, StatusBadge } from './ConsolePrimitives';
import { actionDisabledReason, isActionEnabled, whyText } from './readiness';

export default function Ledger() {
  const [actions, setActions] = useState<Array<Record<string, unknown>>>([]);
  const [workflows, setWorkflows] = useState<Array<Record<string, unknown>>>([]);
  const [reviews, setReviews] = useState<Array<Record<string, unknown>>>([]);
  const [selected, setSelected] = useState<unknown>(null);
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    brcApi.readiness()
      .then((payload) => {
        setReadiness(payload);
        if (!isActionEnabled(payload, 'view_ledger')) return undefined;
        return Promise.all([
          brcApi.listActions(),
          brcApi.listWorkflows(),
          brcApi.listReviewDecisions(),
        ]).then(([actionPayload, workflowPayload, reviewPayload]) => {
          setActions(actionPayload.actions);
          setWorkflows(workflowPayload.workflows);
          setReviews(reviewPayload.review_decisions);
        });
      })
      .catch(setError);
  }, []);

  if (error) return <ErrorState error={error} />;
  const canViewLedger = isActionEnabled(readiness, 'view_ledger');
  const ledgerDisabledReason = actionDisabledReason(readiness, 'view_ledger');

  return (
    <div className="space-y-4">
      <StageStrip
        current="BRC-R4 ledger"
        next="用数据库事实源查看 Owner 操作、workflow 和复盘记录。"
        global="后续 Feishu 和云部署审批需要复用这套审计链路。"
      />
      <OwnerSummary
        conclusion={canViewLedger ? '这里是操作记录，不是交易入口' : '当前不能读取 BRC 操作记录'}
        why={canViewLedger ? whyText(readiness) : ledgerDisabledReason}
        canDo={canViewLedger ? '查看记录、点击记录展开 JSON 明细，用于复盘和审计。' : '查看禁用原因；不会直接向后端 ledger API 发起读取。'}
        cannotDo="不能下单、不能重放 workflow、不能修改历史记录。"
        accountImpact="不会影响真实账户。读取 ledger 不会触发任何 runtime 或 exchange 动作。"
        next={canViewLedger ? '选择一条记录查看摘要，需要时展开技术详情。' : '先回到 Guide 查看当前 readiness。'}
        tone={canViewLedger ? 'info' : 'warning'}
      />

      {!canViewLedger && (
        <Card>
          <CardHeader>
            <CardTitle>当前无法读取操作记录</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
            <p>原因：{ledgerDisabledReason}</p>
            <p>这不会触发任何交易风险。操作记录 API 未被调用。</p>
            <DeveloperDetails data={readiness} />
          </CardContent>
        </Card>
      )}

      {canViewLedger && <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <LedgerColumn title="Operator Actions" items={actions} idKey="action_id" statusKey="decision_result" onSelect={setSelected} />
        <LedgerColumn title="Workflow Runs" items={workflows} idKey="workflow_run_id" statusKey="status" onSelect={setSelected} />
        <LedgerColumn title="Review Decisions" items={reviews} idKey="review_id" statusKey="decision" onSelect={setSelected} />
      </div>}

      <JsonDetails data={selected} label="查看选中记录 JSON" />
    </div>
  );
}

function LedgerColumn({
  title,
  items,
  idKey,
  statusKey,
  onSelect,
}: {
  title: string;
  items: Array<Record<string, unknown>>;
  idKey: string;
  statusKey: string;
  onSelect: (item: unknown) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <History className="h-3.5 w-3.5 text-blue-500" />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <EmptyState title="暂无记录" body="执行操作或写入复盘后，这里会出现事实记录。" />
        ) : (
          <div className="space-y-2">
            {items.map((item) => (
              <button
                key={String(item[idKey])}
                className="block w-full rounded-sm border border-zinc-200 p-3 text-left hover:border-blue-500 dark:border-zinc-800"
                onClick={() => onSelect(item)}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate font-mono text-xs text-zinc-700 dark:text-zinc-300">{String(item[idKey])}</span>
                  <StatusBadge state={item[statusKey]} />
                </div>
                <p className="mt-1 line-clamp-2 text-xs text-zinc-500">
                  {summaryForLedgerItem(item)}
                </p>
                <p className="mt-1 text-[11px] leading-4 text-zinc-500">
                  账户影响：不会影响真实账户。{String(item.blocked_reason || '') ? `Blocked 原因：${String(item.blocked_reason)}` : '这是已持久化记录摘要。'}
                </p>
              </button>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function summaryForLedgerItem(item: Record<string, unknown>): string {
  if (item.source_text) return `Owner 输入：${String(item.source_text)}`;
  if (item.reason_text) return `复盘原因：${String(item.reason_text)}`;
  if (item.next_recommended_task) return `下一步：${String(item.next_recommended_task)}`;
  if (item.action) return `Workflow 动作：${String(item.action)}`;
  return '已记录的治理动作。';
}
