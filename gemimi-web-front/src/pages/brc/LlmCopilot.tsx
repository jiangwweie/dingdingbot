import { useEffect, useState } from 'react';
import { Bot, GitBranch, PlayCircle, SendHorizonal } from 'lucide-react';
import { brcApi, ReadinessResponse, WorkflowResponse } from '@/src/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import {
  ApplicationActionCard,
  DeveloperDetails,
  EmptyState,
  ErrorState,
  JsonDetails,
  OwnerSummary,
  StageStrip,
  StatusBadge,
} from './ConsolePrimitives';
import { actionDisabledReason, isActionEnabled, whyText } from './readiness';

const TESTNET_CONFIRM = 'CONFIRM_BRC_TESTNET_REHEARSAL';
const READ_ONLY_CONFIRM = 'CONFIRM_READ_ONLY_BRC';

const EXAMPLES = [
  '现在系统能不能动？',
  '帮我准备下一轮 testnet 演练',
  '为什么现在不能继续？',
  '帮我只读查看最近的 review 和 evidence',
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

  if (!readiness && !error) return <div className="text-xs text-zinc-500">正在打开 LLM Copilot...</div>;
  if (!readiness && error) return <ErrorState error={error} />;

  const action = String(workflow?.workflow?.action || workflow?.intent?.action || '等待识别');
  const blocked = String(workflow?.workflow?.blocked_reason || workflow?.intent?.blocked_reason || '');
  const requiresTestnet = action === 'request_testnet_rehearsal';
  const confirmPhrase = requiresTestnet ? TESTNET_CONFIRM : READ_ONLY_CONFIRM;
  const canCreateWorkflow = isActionEnabled(readiness, 'create_workflow');
  const canRunTestnet = isActionEnabled(readiness, 'run_controlled_testnet_workflow');
  const workflowDisabledReason = actionDisabledReason(readiness, 'create_workflow');
  const testnetDisabledReason = actionDisabledReason(readiness, 'run_controlled_testnet_workflow');
  const actionCards = readiness?.action_cards || [];

  return (
    <div className="space-y-4">
      <StageStrip
        current="LLM Copilot 对话入口"
        next="先说你的意图，再看右侧 Action Card 是否允许继续。"
        global="LLM 负责解释和建议；应用层检查、Owner 确认和审计才决定是否执行。"
      />
      <OwnerSummary
        conclusion={!canCreateWorkflow
          ? '现在还不能创建对话流程'
          : requiresTestnet
            ? '这是 testnet 演练请求，需要更严格确认'
            : '这里只是识别意图，不会自动执行'}
        why={!canCreateWorkflow
          ? workflowDisabledReason
          : requiresTestnet
            ? `${whyText(readiness)} testnet 演练必须通过环境、账户、风控和确认短语。`
            : 'LLM 只解释你的意思和风险，不能替你点确认，也不能直接执行。'}
        canDo={canCreateWorkflow ? '输入一句话，让系统识别意图、风险和下一步建议。' : '先查看为什么不能创建 workflow。'}
        cannotDo="不能让 LLM 直接下单、改参数、开 live、转账或跳过确认。"
        accountImpact={requiresTestnet ? '只允许影响 Binance testnet；不影响真实账户。' : '创建对话流程本身不影响账户。'}
        next={requiresTestnet ? '如果右侧 Action Card 也放行，再输入确认短语。' : '先生成一次识别结果，再决定是否继续。'}
        tone={!canCreateWorkflow || requiresTestnet ? 'warning' : 'info'}
      />
      {error && <ErrorState error={error} />}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(340px,0.9fr)]">
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Bot className="h-3.5 w-3.5 text-blue-500" />
                对 LLM 说一句话
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap gap-2">
                {EXAMPLES.map((item) => (
                  <button
                    key={item}
                    className="rounded-sm border border-zinc-300 px-2 py-1 text-[11px] text-zinc-600 hover:border-blue-500 hover:text-blue-500 dark:border-zinc-700 dark:text-zinc-400"
                    onClick={() => setText(item)}
                  >
                    {item}
                  </button>
                ))}
              </div>
              <textarea
                className="min-h-28 w-full rounded-sm border border-zinc-300 bg-white p-3 text-sm leading-6 outline-none focus:border-blue-500 dark:border-zinc-800 dark:bg-zinc-950"
                value={text}
                onChange={(event) => setText(event.target.value)}
              />
              <button
                className="inline-flex items-center gap-2 rounded-sm border border-blue-500 bg-blue-600 px-3 py-2 text-xs font-bold uppercase tracking-widest text-white disabled:opacity-60"
                onClick={createWorkflow}
                disabled={loading || !text.trim() || !canCreateWorkflow}
                title={!canCreateWorkflow ? workflowDisabledReason : undefined}
              >
                <SendHorizonal className="h-3.5 w-3.5" />
                识别意图
              </button>
              {!canCreateWorkflow && (
                <p className="text-xs leading-5 text-amber-700 dark:text-amber-300">
                  当前不能继续：{workflowDisabledReason}
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between gap-2">
                识别结果
                <StatusBadge state={action} />
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
              <Row label="Owner 输入" value={text} />
              <Row label="系统理解" value={action} />
              <Row label="风险提示" value={blocked || (requiresTestnet ? '需要 testnet 确认' : '只读或等待确认')} />
              <Row label="下一步" value={workflow ? `输入 ${confirmPhrase} 后由应用层继续检查。` : '先点击“识别意图”。'} />
              <JsonDetails data={workflow} label="展开 workflow 明细" />
            </CardContent>
          </Card>

          {workflow && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <PlayCircle className="h-3.5 w-3.5 text-amber-500" />
                  Owner 确认
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-xs leading-5 text-zinc-600 dark:text-zinc-400">
                  需要手动输入 <span className="font-mono font-bold">{confirmPhrase}</span>。这个按钮属于应用层 Action Card，不属于 LLM 回复。
                </p>
                {requiresTestnet && !canRunTestnet && (
                  <p className="rounded-sm border border-amber-500/30 bg-amber-500/[0.05] px-2 py-1 text-xs leading-5 text-amber-700 dark:text-amber-300">
                    testnet 当前不可确认：{testnetDisabledReason}
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
        </div>

        <aside className="space-y-3">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <GitBranch className="h-3.5 w-3.5 text-blue-500" />
                Action Card Panel
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
              <p>这里是应用层生成的可操作卡片。LLM 可以建议，但不能替它放行。</p>
              <Row label="Risk" value={<StatusBadge state={readiness?.risk_decision} />} />
              <Row label="State" value={<StatusBadge state={readiness?.runtime_state} />} />
            </CardContent>
          </Card>
          {actionCards.map((item) => (
            <ApplicationActionCard key={item.action_card_id} action={item} />
          ))}
        </aside>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>最近的对话流程</CardTitle>
        </CardHeader>
        <CardContent>
          {items.length === 0 ? (
            <EmptyState title="还没有记录" body="识别一次意图后，这里会显示 workflow id、状态和结果。" />
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

      <DeveloperDetails data={{ readiness, workflow }} label="展开技术数据" />
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-zinc-100 pb-2 last:border-0 last:pb-0 dark:border-zinc-800">
      <span className="text-zinc-500">{label}</span>
      <span className="max-w-[65%] text-right font-medium">{value}</span>
    </div>
  );
}
