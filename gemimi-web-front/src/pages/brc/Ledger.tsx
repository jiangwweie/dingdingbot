import { useEffect, useState } from 'react';
import { History } from 'lucide-react';
import { brcApi } from '@/src/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { EmptyState, ErrorState, JsonDetails, StageStrip, StatusBadge } from './ConsolePrimitives';

export default function Ledger() {
  const [actions, setActions] = useState<Array<Record<string, unknown>>>([]);
  const [workflows, setWorkflows] = useState<Array<Record<string, unknown>>>([]);
  const [reviews, setReviews] = useState<Array<Record<string, unknown>>>([]);
  const [selected, setSelected] = useState<unknown>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    Promise.all([
      brcApi.listActions(),
      brcApi.listWorkflows(),
      brcApi.listReviewDecisions(),
    ])
      .then(([actionPayload, workflowPayload, reviewPayload]) => {
        setActions(actionPayload.actions);
        setWorkflows(workflowPayload.workflows);
        setReviews(reviewPayload.review_decisions);
      })
      .catch(setError);
  }, []);

  if (error) return <ErrorState error={error} />;

  return (
    <div className="space-y-4">
      <StageStrip
        current="BRC-R4 ledger"
        next="用数据库事实源查看 Owner 操作、workflow 和复盘记录。"
        global="后续 Feishu 和云部署审批需要复用这套审计链路。"
      />

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <LedgerColumn title="Operator Actions" items={actions} idKey="action_id" statusKey="decision_result" onSelect={setSelected} />
        <LedgerColumn title="Workflow Runs" items={workflows} idKey="workflow_run_id" statusKey="status" onSelect={setSelected} />
        <LedgerColumn title="Review Decisions" items={reviews} idKey="review_id" statusKey="decision" onSelect={setSelected} />
      </div>

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
                  {String(item.source_text || item.reason_text || item.next_recommended_task || '')}
                </p>
              </button>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
