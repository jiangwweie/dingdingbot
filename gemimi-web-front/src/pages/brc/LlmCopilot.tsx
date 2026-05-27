import { useEffect, useState } from 'react';
import { Bot, PlayCircle, SendHorizonal } from 'lucide-react';
import { brcApi, ReadinessResponse, WorkflowResponse } from '@/src/services/api';
import { Badge } from '@/src/components/ui/Badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import {
  ApplicationActionCard,
  DeveloperDetails,
  EmptyState,
  ErrorState,
  JsonDetails,
  QuickFact,
  StatusBadge,
} from './ConsolePrimitives';
import { actionDisabledReason, isActionEnabled } from './readiness';

const TESTNET_CONFIRM = 'CONFIRM_BRC_TESTNET_REHEARSAL';
const READ_ONLY_CONFIRM = 'CONFIRM_READ_ONLY_BRC';

const EXAMPLES = [
  '看状态',
  '准备 testnet rehearsal',
  '为什么阻断',
  '查看 review evidence',
];

export default function LlmCopilot() {
  const [text, setText] = useState(EXAMPLES[0]);
  const [confirmation, setConfirmation] = useState('');
  const [workflow, setWorkflow] = useState<WorkflowResponse | null>(null);
  const [items, setItems] = useState<Array<Record<string, unknown>>>([]);
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    brcApi.readiness()
      .then((payload) => {
        setReadiness(payload);
        if (isActionEnabled(payload, 'create_workflow')) {
          return brcApi.listWorkflows().then((list) => setItems(list.workflows));
        }
        setItems([]);
        return undefined;
      })
      .catch(setError);
  }, []);

  async function createWorkflow() {
    if (!isActionEnabled(readiness, 'create_workflow')) return;
    setLoading(true);
    setError(null);
    try {
      const payload = await brcApi.createWorkflow(text);
      setWorkflow(payload);
      setConfirmation('');
      const list = await brcApi.listWorkflows();
      setItems(list.workflows);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  async function confirmWorkflow() {
    const runId = String(workflow?.workflow?.workflow_run_id || '');
    if (!runId) return;
    setLoading(true);
    setError(null);
    try {
      const payload = await brcApi.confirmWorkflow(runId, confirmation);
      setWorkflow(payload);
      const list = await brcApi.listWorkflows();
      setItems(list.workflows);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  if (!readiness && !error) return <div className="text-xs text-zinc-500">打开 LLM...</div>;
  if (!readiness && error) return <ErrorState error={error} />;

  const action = String(workflow?.workflow?.action || workflow?.intent?.action || '等待识别');
  const status = String(workflow?.workflow?.status || 'idle');
  const blocked = String(workflow?.workflow?.blocked_reason || workflow?.intent?.blocked_reason || '');
  const requiresTestnet = action === 'request_testnet_rehearsal';
  const confirmPhrase = requiresTestnet ? TESTNET_CONFIRM : READ_ONLY_CONFIRM;
  const canCreateWorkflow = isActionEnabled(readiness, 'create_workflow');
  const canRunTestnet = isActionEnabled(readiness, 'run_controlled_testnet_workflow');
  const workflowDisabledReason = actionDisabledReason(readiness, 'create_workflow');
  const testnetDisabledReason = actionDisabledReason(readiness, 'run_controlled_testnet_workflow');
  const actionCards = readiness?.action_cards || [];
  const canConfirm = Boolean(workflow)
    && confirmation === confirmPhrase
    && !blocked
    && status === 'awaiting_confirmation'
    && (!requiresTestnet || canRunTestnet);

  return (
    <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_380px]">
      <section className="space-y-3">
        <Card className="min-h-[420px]">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Bot className="h-4 w-4 text-blue-500" />
              LLM
            </CardTitle>
          </CardHeader>
          <CardContent className="flex h-full flex-col gap-3 p-3">
            <div className="flex flex-wrap gap-2">
              {EXAMPLES.map((item) => (
                <button
                  key={item}
                  className="rounded-sm border border-zinc-300 px-2.5 py-1.5 text-xs font-medium text-zinc-600 hover:border-blue-500 hover:text-blue-500 dark:border-zinc-700 dark:text-zinc-400"
                  onClick={() => setText(item)}
                >
                  {item}
                </button>
              ))}
            </div>

            <textarea
              className="min-h-32 w-full rounded-sm border border-zinc-300 bg-white p-3 text-base leading-6 outline-none focus:border-blue-500 dark:border-zinc-800 dark:bg-zinc-950"
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="说一句话..."
            />

            <div className="flex flex-wrap items-center gap-2">
              <button
                className="inline-flex min-h-10 items-center gap-2 rounded-sm bg-blue-600 px-4 py-2 text-sm font-bold text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
                onClick={createWorkflow}
                disabled={loading || !text.trim() || !canCreateWorkflow}
                title={!canCreateWorkflow ? workflowDisabledReason : undefined}
              >
                <SendHorizonal className="h-4 w-4" />
                识别
              </button>
              {!canCreateWorkflow && <span className="text-xs text-amber-600 dark:text-amber-300">{workflowDisabledReason}</span>}
            </div>

            {error && (
              <p className="rounded-sm border border-rose-500/30 bg-rose-500/[0.05] px-3 py-2 text-xs text-rose-600 dark:text-rose-300">
                {errorMessage(error)}
              </p>
            )}

            <div className="rounded-sm border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-950">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-xs font-bold text-zinc-700 dark:text-zinc-300">识别结果</p>
                <StatusBadge state={status} />
              </div>
              {workflow ? (
                <div className="space-y-1">
                  <QuickFact label="意图" value={intentLabel(action)} />
                  <QuickFact label="确认" value={requiresTestnet ? '强确认' : '只读确认'} />
                  <QuickFact label="阻断" value={blocked || '无'} />
                  <JsonDetails data={workflow} label="Details" />
                </div>
              ) : (
                <EmptyState title="等待识别" body="输入一句话后点击“识别”。" />
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>最近 workflow</CardTitle>
          </CardHeader>
          <CardContent>
            {items.length === 0 ? (
              <EmptyState title="暂无记录" body="识别一次后会出现 workflow。" />
            ) : (
              <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                {items.slice(0, 6).map((item) => (
                  <div key={String(item.workflow_run_id)} className="rounded-sm border border-zinc-200 p-2 dark:border-zinc-800">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-mono text-xs text-zinc-700 dark:text-zinc-300">{String(item.workflow_run_id)}</span>
                      <StatusBadge state={item.status} />
                    </div>
                    <p className="mt-1 truncate text-xs text-zinc-500">{intentLabel(String(item.action || ''))}</p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </section>

      <aside className="space-y-3">
        <Card className={requiresTestnet ? 'border-amber-500/30 bg-amber-500/[0.04]' : ''}>
          <CardHeader>
            <CardTitle className="flex items-center justify-between gap-2">
              Action Card
              <Badge variant={requiresTestnet ? 'warning' : 'info'}>{requiresTestnet ? 'testnet' : 'read'}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <QuickFact label="Risk" value={<StatusBadge state={readiness?.risk_decision} />} />
            <QuickFact label="Runtime" value={<StatusBadge state={readiness?.runtime_state} />} />
            <QuickFact label="状态" value={workflow ? workflowStatusText(status) : '先识别'} />
            {workflow && (
              <>
                <div>
                  <label className="mb-1 block text-xs font-bold text-zinc-500">确认短语</label>
                  <input
                    className="w-full rounded-sm border border-zinc-300 bg-white px-3 py-2 font-mono text-sm outline-none focus:border-blue-500 dark:border-zinc-800 dark:bg-zinc-950"
                    value={confirmation}
                    onChange={(event) => setConfirmation(event.target.value)}
                    placeholder={confirmPhrase}
                  />
                </div>
                {requiresTestnet && !canRunTestnet && (
                  <p className="rounded-sm border border-amber-500/30 bg-amber-500/[0.05] px-2 py-1 text-xs text-amber-700 dark:text-amber-300">
                    {testnetDisabledReason}
                  </p>
                )}
                <button
                  className="inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-sm bg-amber-500 px-4 py-2 text-sm font-bold text-white hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={confirmWorkflow}
                  disabled={loading || !canConfirm}
                >
                  <PlayCircle className="h-4 w-4" />
                  {canConfirm ? '确认继续' : '当前不可确认'}
                </button>
                <p className="text-xs text-zinc-500">确认按钮属于应用层检查，不属于 LLM 回复。</p>
              </>
            )}
          </CardContent>
        </Card>

        {actionCards.map((item) => (
          <ApplicationActionCard key={item.action_card_id} action={item} compact />
        ))}

        <DeveloperDetails data={{ readiness, workflow }} label="Details" />
      </aside>
    </div>
  );
}

function intentLabel(action: string): string {
  const labels: Record<string, string> = {
    read_review_packet: '看复盘',
    read_next_eligibility: '看能否继续',
    read_evidence: '看证据',
    request_testnet_rehearsal: '准备 testnet',
    unknown: '未知',
    '等待识别': '等待识别',
  };
  return labels[action] || action;
}

function workflowStatusText(status: string): string {
  const labels: Record<string, string> = {
    idle: '先识别',
    awaiting_confirmation: '等确认',
    running: '执行中',
    completed: '已完成',
    blocked: '已阻断',
    failed: '失败',
  };
  return labels[status] || status;
}

function errorMessage(error: unknown): string {
  if (typeof error === 'object' && error && 'message' in error) {
    return String((error as { message?: unknown }).message);
  }
  return String(error);
}
