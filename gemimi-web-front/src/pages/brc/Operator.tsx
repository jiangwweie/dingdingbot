import { useState } from 'react';
import { FileSearch, PlayCircle } from 'lucide-react';
import { brcApi, OperatorPlanResponse, OperatorRunResponse } from '@/src/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { ChainExplanation, ErrorState, GuardNote, JsonDetails, StageStrip } from './ConsolePrimitives';

const READ_ONLY_CONFIRM = 'CONFIRM_READ_ONLY_BRC';

export default function Operator() {
  const [text, setText] = useState('帮我看下一轮能不能开');
  const [confirmation, setConfirmation] = useState('');
  const [plan, setPlan] = useState<OperatorPlanResponse | null>(null);
  const [run, setRun] = useState<OperatorRunResponse | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  const actionId = String(plan?.action?.action_id || '');
  const draftAction = String(plan?.action?.draft_action || plan?.plan?.draft_action || '等待生成');
  const blockedReason = String(plan?.action?.blocked_reason || plan?.plan?.blocked_reason || '');

  async function createPlan() {
    setLoading(true);
    setError(null);
    setRun(null);
    try {
      setPlan(await brcApi.planOperator(text));
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  async function runPlan() {
    if (!actionId) return;
    setLoading(true);
    setError(null);
    try {
      setRun(await brcApi.runOperatorAction(actionId, confirmation));
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <StageStrip
        current="BRC-R4 operator plan"
        next="先生成计划，确认链路解释后手动输入确认短语。"
        global="BRC 操作治理层；自动策略、真实实盘和出金仍未授权。"
      />
      <GuardNote />
      {error && <ErrorState error={error} />}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileSearch className="h-3.5 w-3.5 text-blue-500" />
            Owner Text（自然语言输入）
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <textarea
            className="min-h-28 w-full rounded-sm border border-zinc-300 bg-white p-3 text-sm leading-6 outline-none focus:border-blue-500 dark:border-zinc-800 dark:bg-zinc-950"
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
          <button
            className="inline-flex items-center gap-2 rounded-sm border border-blue-500 bg-blue-600 px-3 py-2 text-xs font-bold uppercase tracking-widest text-white disabled:opacity-60"
            onClick={createPlan}
            disabled={loading || !text.trim()}
          >
            <FileSearch className="h-3.5 w-3.5" />
            生成计划
          </button>
        </CardContent>
      </Card>

      <ChainExplanation ownerText={text} intent={draftAction} action={plan} blocked={blockedReason || undefined} />

      {plan && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <PlayCircle className="h-3.5 w-3.5 text-amber-500" />
              Owner Confirmation（手动确认）
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-xs leading-5 text-zinc-600 dark:text-zinc-400">
              只读动作需要输入 <span className="font-mono font-bold">{READ_ONLY_CONFIRM}</span>。前端不会自动填入，避免误触。
            </p>
            <input
              className="w-full rounded-sm border border-zinc-300 bg-white px-3 py-2 font-mono text-sm outline-none focus:border-blue-500 dark:border-zinc-800 dark:bg-zinc-950"
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              placeholder={READ_ONLY_CONFIRM}
            />
            <button
              className="inline-flex items-center gap-2 rounded-sm border border-amber-500 bg-amber-500 px-3 py-2 text-xs font-bold uppercase tracking-widest text-white disabled:opacity-60"
              onClick={runPlan}
              disabled={loading || !actionId || confirmation !== READ_ONLY_CONFIRM}
            >
              <PlayCircle className="h-3.5 w-3.5" />
              执行只读动作
            </button>
          </CardContent>
        </Card>
      )}

      <JsonDetails data={run} label="查看执行结果 / Evidence" />
    </div>
  );
}
