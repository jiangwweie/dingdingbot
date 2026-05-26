import { FormEvent, useState } from 'react';
import { CheckCircle2 } from 'lucide-react';
import { brcApi, ReviewDecisionResponse } from '@/src/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { ErrorState, JsonDetails, StageStrip } from './ConsolePrimitives';

export default function Review() {
  const [campaignId, setCampaignId] = useState('');
  const [decision, setDecision] = useState('accepted');
  const [reason, setReason] = useState('BRC R4 local console reviewed');
  const [nextTask, setNextTask] = useState('BRC-R4 local UI/API acceptance');
  const [result, setResult] = useState<ReviewDecisionResponse | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      setResult(await brcApi.createReviewDecision({
        campaign_id: campaignId,
        decision,
        reason_text: reason,
        next_recommended_task: nextTask,
      }));
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <StageStrip
        current="BRC-R4 review decision"
        next="把 Owner 复盘结论写入数据库事实源。"
        global="复盘闭环是后续 Feishu 卡片和云部署审批链路的基础。"
      />
      {error && <ErrorState error={error} />}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
            Review Decision（复盘结论）
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form className="grid grid-cols-1 gap-3 lg:grid-cols-2" onSubmit={submit}>
            <label className="block">
              <span className="text-[11px] font-bold uppercase tracking-widest text-zinc-500">Campaign ID</span>
              <input
                className="mt-1 w-full rounded-sm border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 dark:border-zinc-800 dark:bg-zinc-950"
                value={campaignId}
                onChange={(event) => setCampaignId(event.target.value)}
                placeholder="brc_campaign_id"
              />
            </label>
            <label className="block">
              <span className="text-[11px] font-bold uppercase tracking-widest text-zinc-500">Decision</span>
              <select
                className="mt-1 w-full rounded-sm border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 dark:border-zinc-800 dark:bg-zinc-950"
                value={decision}
                onChange={(event) => setDecision(event.target.value)}
              >
                <option value="accepted">accepted（接受）</option>
                <option value="needs_followup">needs_followup（需要跟进）</option>
                <option value="next_campaign_blocked">next_campaign_blocked（阻止下一轮）</option>
                <option value="testnet_rehearsal_authorized">testnet_rehearsal_authorized（授权 testnet 验收）</option>
              </select>
            </label>
            <label className="block lg:col-span-2">
              <span className="text-[11px] font-bold uppercase tracking-widest text-zinc-500">原因</span>
              <textarea
                className="mt-1 min-h-24 w-full rounded-sm border border-zinc-300 bg-white p-3 text-sm leading-6 outline-none focus:border-blue-500 dark:border-zinc-800 dark:bg-zinc-950"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
            </label>
            <label className="block lg:col-span-2">
              <span className="text-[11px] font-bold uppercase tracking-widest text-zinc-500">下一步建议</span>
              <input
                className="mt-1 w-full rounded-sm border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 dark:border-zinc-800 dark:bg-zinc-950"
                value={nextTask}
                onChange={(event) => setNextTask(event.target.value)}
              />
            </label>
            <button
              className="inline-flex items-center justify-center gap-2 rounded-sm border border-emerald-500 bg-emerald-600 px-3 py-2 text-xs font-bold uppercase tracking-widest text-white disabled:opacity-60"
              disabled={loading || !campaignId.trim() || !reason.trim() || !nextTask.trim()}
            >
              <CheckCircle2 className="h-3.5 w-3.5" />
              写入复盘结论
            </button>
          </form>
        </CardContent>
      </Card>

      <JsonDetails data={result} label="查看 review decision JSON" />
    </div>
  );
}
