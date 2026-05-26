import { useEffect, useState } from 'react';
import { GitBranch, PlayCircle } from 'lucide-react';
import { brcApi, WorkflowResponse } from '@/src/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { ChainExplanation, EmptyState, ErrorState, JsonDetails, StageStrip, StatusBadge } from './ConsolePrimitives';

const TESTNET_CONFIRM = 'CONFIRM_BRC_TESTNET_REHEARSAL';

export default function Workflow() {
  const [text, setText] = useState('帮我准备下一轮 testnet 演练');
  const [confirmation, setConfirmation] = useState('');
  const [workflow, setWorkflow] = useState<WorkflowResponse | null>(null);
  const [items, setItems] = useState<Array<Record<string, unknown>>>([]);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    brcApi.listWorkflows().then((payload) => setItems(payload.workflows)).catch(() => setItems([]));
  }, []);

  async function createWorkflow() {
    setLoading(true);
    setError(null);
    try {
      const payload = await brcApi.createWorkflow(text);
      setWorkflow(payload);
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

  const action = String(workflow?.workflow?.action || workflow?.intent?.action || '等待生成');
  const blocked = String(workflow?.workflow?.blocked_reason || workflow?.intent?.blocked_reason || '');
  const requiresTestnet = action === 'request_testnet_rehearsal';
  const confirmPhrase = requiresTestnet ? TESTNET_CONFIRM : 'CONFIRM_READ_ONLY_BRC';

  return (
    <div className="space-y-4">
      <StageStrip
        current="BRC-R4 LLM workflow"
        next="LLM 只能归一化意图；执行前必须 Owner 手动确认。"
        global="后续可扩展多轮对话、计划修订和飞书卡片审批。"
      />
      {error && <ErrorState error={error} />}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <GitBranch className="h-3.5 w-3.5 text-blue-500" />
            Workflow（操作流程）
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <textarea
            className="min-h-24 w-full rounded-sm border border-zinc-300 bg-white p-3 text-sm leading-6 outline-none focus:border-blue-500 dark:border-zinc-800 dark:bg-zinc-950"
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
          <button
            className="inline-flex items-center gap-2 rounded-sm border border-blue-500 bg-blue-600 px-3 py-2 text-xs font-bold uppercase tracking-widest text-white disabled:opacity-60"
            onClick={createWorkflow}
            disabled={loading || !text.trim()}
          >
            <GitBranch className="h-3.5 w-3.5" />
            创建 Workflow
          </button>
        </CardContent>
      </Card>

      <ChainExplanation ownerText={text} intent={action} action={workflow} blocked={blocked || undefined} />

      {workflow && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <PlayCircle className="h-3.5 w-3.5 text-amber-500" />
              手动确认
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-xs leading-5 text-zinc-600 dark:text-zinc-400">
              需要输入 <span className="font-mono font-bold">{confirmPhrase}</span>。固定 testnet rehearsal 才允许使用 testnet 确认短语。
            </p>
            <input
              className="w-full rounded-sm border border-zinc-300 bg-white px-3 py-2 font-mono text-sm outline-none focus:border-blue-500 dark:border-zinc-800 dark:bg-zinc-950"
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              placeholder={confirmPhrase}
            />
            <button
              className="inline-flex items-center gap-2 rounded-sm border border-amber-500 bg-amber-500 px-3 py-2 text-xs font-bold uppercase tracking-widest text-white disabled:opacity-60"
              onClick={confirmWorkflow}
              disabled={loading || confirmation !== confirmPhrase}
            >
              <PlayCircle className="h-3.5 w-3.5" />
              确认并继续
            </button>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>最近 Workflow Runs</CardTitle>
        </CardHeader>
        <CardContent>
          {items.length === 0 ? (
            <EmptyState title="还没有 workflow" body="创建 workflow 后，这里会显示状态、动作和结果。" />
          ) : (
            <div className="space-y-2">
              {items.map((item) => (
                <div key={String(item.workflow_run_id)} className="rounded-sm border border-zinc-200 p-3 dark:border-zinc-800">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs text-zinc-700 dark:text-zinc-300">{String(item.workflow_run_id)}</span>
                    <StatusBadge state={item.status} />
                  </div>
                  <p className="mt-1 text-xs text-zinc-500">{String(item.action || '')}</p>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <JsonDetails data={workflow} label="查看 workflow JSON" />
    </div>
  );
}
