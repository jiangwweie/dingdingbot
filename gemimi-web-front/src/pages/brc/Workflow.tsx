import { useEffect, useState } from 'react';
import { GitBranch, PlayCircle } from 'lucide-react';
import { brcApi, ReadinessResponse, WorkflowResponse } from '@/src/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { ChainExplanation, EmptyState, ErrorState, JsonDetails, OwnerSummary, StageStrip, StatusBadge } from './ConsolePrimitives';
import { actionDisabledReason, isActionEnabled, whyText } from './readiness';

const TESTNET_CONFIRM = 'CONFIRM_BRC_TESTNET_REHEARSAL';

export default function Workflow() {
  const [text, setText] = useState('帮我准备下一轮 testnet 演练');
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
  const canCreateWorkflow = isActionEnabled(readiness, 'create_workflow');
  const canRunTestnet = isActionEnabled(readiness, 'run_controlled_testnet_workflow');
  const workflowDisabledReason = actionDisabledReason(readiness, 'create_workflow');
  const testnetDisabledReason = actionDisabledReason(readiness, 'run_controlled_testnet_workflow');
  const mode = blocked
    ? 'forbidden'
    : requiresTestnet
      ? 'testnet'
      : 'readonly';

  return (
    <div className="space-y-4">
      <StageStrip
        current="BRC-R4 LLM workflow"
        next="LLM 只能归一化意图；执行前必须 Owner 手动确认。"
        global="后续可扩展多轮对话、计划修订和飞书卡片审批。"
      />
      <OwnerSummary
        conclusion={!canCreateWorkflow
          ? '当前不能创建 BRC Workflow'
          : requiresTestnet
            ? '这是受控 testnet workflow，需要更高确认'
            : '这里先识别意图，不会自动执行'}
        why={!canCreateWorkflow
          ? workflowDisabledReason
          : requiresTestnet
            ? `${whyText(readiness)} 请求涉及固定 testnet 演练，必须通过 runtime/testnet/profile/guard 检查和专用确认短语。`
            : 'LLM 只做意图归一化和计划编排，不能授权交易或绕过 Owner confirmation。'}
        canDo={canCreateWorkflow ? '创建 workflow，查看识别结果、风险分类和需要满足的门槛。' : '查看禁用原因，回到 Guide 或 Runtime Safety 补齐门槛。'}
        cannotDo="不能请求实盘、提现、自动下单、自动 sizing 或扩展到策略池执行。"
        accountImpact={requiresTestnet ? '仅可能影响 Binance testnet；不会触碰真实账户或提现。' : '不会影响真实账户。创建 workflow 本身不执行动作。'}
        next={!canCreateWorkflow
          ? '按钮已禁用，不会调用 workflow API。'
          : requiresTestnet
            ? '确认风险分类后，只有在条件满足时才输入 CONFIRM_BRC_TESTNET_REHEARSAL。'
            : '先创建 workflow，再根据确认卡决定是否输入确认短语。'}
        tone={!canCreateWorkflow || requiresTestnet ? 'warning' : 'info'}
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
            disabled={loading || !text.trim() || !canCreateWorkflow}
            title={!canCreateWorkflow ? workflowDisabledReason : undefined}
          >
            <GitBranch className="h-3.5 w-3.5" />
            创建 Workflow
          </button>
          {!canCreateWorkflow && (
            <p className="text-xs leading-5 text-amber-700 dark:text-amber-300">
              当前禁用原因：{workflowDisabledReason}
            </p>
          )}
        </CardContent>
      </Card>

      <ChainExplanation ownerText={text} intent={action} action={workflow} blocked={blocked || undefined} mode={mode} />

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
            {requiresTestnet && !canRunTestnet && (
              <p className="rounded-sm border border-amber-500/30 bg-amber-500/[0.05] px-2 py-1 text-xs leading-5 text-amber-700 dark:text-amber-300">
                Controlled Testnet 当前不可确认：{testnetDisabledReason}
              </p>
            )}
            <input
              className="w-full rounded-sm border border-zinc-300 bg-white px-3 py-2 font-mono text-sm outline-none focus:border-blue-500 dark:border-zinc-800 dark:bg-zinc-950"
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              placeholder={confirmPhrase}
            />
            <button
              className="inline-flex items-center gap-2 rounded-sm border border-amber-500 bg-amber-500 px-3 py-2 text-xs font-bold uppercase tracking-widest text-white disabled:opacity-60"
              onClick={confirmWorkflow}
              disabled={loading || confirmation !== confirmPhrase || Boolean(blocked) || (requiresTestnet && !canRunTestnet)}
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
