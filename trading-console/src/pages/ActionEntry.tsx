import { useMemo, useState } from 'react';
import { AlertTriangle, CircleDashed, Lock, ShieldCheck, Target } from 'lucide-react';
import { Badge, Card, DeferredActionSlot, EnvelopeStatus, PageHeader, PageSummary, TechnicalDetails } from '@/components/ui';
import { asArray, displayValue, useReadModel } from '@/lib/tradingConsoleApi';
import { blockingReasonLabel, sideLabel } from '@/lib/ownerViewModel';

type ActionEntryInput = {
  market_regime: string;
  symbol_preference: string;
  side: string;
  risk_tier: string;
  note: string;
  family: string;
  strategy_family_id: string;
  carrier_id: string;
  symbol: string;
  quantity: string;
  max_notional: string;
  leverage: string;
  max_attempts: string;
  protection_mode: string;
  review_requirement: string;
};

const INITIAL_INPUT: ActionEntryInput = {
  market_regime: 'trend',
  symbol_preference: 'SOL/USDT:USDT',
  side: 'long',
  risk_tier: 'low',
  note: '',
  family: 'Trend',
  strategy_family_id: 'TF-001-live-readonly-v0',
  carrier_id: 'TF-001-live-readonly-v0',
  symbol: 'SOL/USDT:USDT',
  quantity: '0.1',
  max_notional: '20',
  leverage: '1',
  max_attempts: '1',
  protection_mode: 'single_tp_plus_sl',
  review_requirement: 'post_action_review_required',
};

const regimeLabel: Record<string, string> = {
  trend: '趋势',
  volatility_expansion: '波动扩张',
  mean_reversion: '均值回归',
};

const riskTierLabel: Record<string, string> = {
  low: '低',
  medium: '中',
  high: '高',
};

function actionEntryStateLabel(value?: string): string {
  if (value === 'ready_for_owner_scope_final_gate') return '可进入最终门禁';
  if (value === 'proposal_only') return '仅提案';
  if (value === 'blocked') return '已阻断';
  return '无法确认';
}

function finalGateStatusLabel(value?: string): string {
  if (value === 'blocked_until_official_final_gate_passes') return '等待最终门禁';
  if (value === 'proposal_only') return '仅提案';
  if (value === 'blocked') return '阻断';
  return '无法确认';
}

function queryFromInput(input: ActionEntryInput): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(input)) {
    if (value !== '') params.set(key, value);
  }
  return `/api/trading-console/action-entry-readiness?${params.toString()}`;
}

function variantForActionState(value?: string) {
  if (value === 'ready_for_owner_scope_final_gate') return 'warning' as const;
  if (value === 'proposal_only') return 'caution' as const;
  return 'danger' as const;
}

export default function ActionEntry() {
  const [draftInput, setDraftInput] = useState<ActionEntryInput>(INITIAL_INPUT);
  const [committedInput, setCommittedInput] = useState<ActionEntryInput>(INITIAL_INPUT);
  const endpoint = useMemo(() => queryFromInput(committedInput), [committedInput]);
  const { envelope, loading, error } = useReadModel<any>(endpoint);

  const pageData = envelope?.data || {};
  const candidateOutput = asArray<any>(pageData.candidate_output);
  const selected = pageData.selected_candidate || {};
  const selectedAction = selected.action_entry || {};
  const selectedSpec = selected.generic_action_spec || {};
  const scopeReview = selected.scope_review || {};
  const riskReview = pageData.risk_review || {};
  const finalGate = pageData.final_gate_result || {};
  const actionState = pageData.action_state || {};
  const authorizationPath = pageData.authorization_draft_path || {};
  const postAction = pageData.post_action_state || {};
  const summaryMood = actionState.enabled === true
    ? 'ok'
    : finalGate.status === 'proposal_only'
      ? 'unknown'
      : 'blocked';

  const updateField = (field: keyof ActionEntryInput, value: string) => {
    setDraftInput((current) => ({ ...current, [field]: value }));
  };

  const selectCandidate = (candidate: any) => {
    const family = String(candidate.family || '');
    const carrierId = String(candidate.carrier_id || '');
    if (family === 'Trend') {
      setDraftInput((current) => ({
        ...current,
        market_regime: 'trend',
        family,
        strategy_family_id: String(candidate.strategy_family_id || carrierId || 'TF-001-live-readonly-v0'),
        carrier_id: carrierId || 'TF-001-live-readonly-v0',
        symbol_preference: 'SOL/USDT:USDT',
        symbol: 'SOL/USDT:USDT',
        side: 'long',
        quantity: '0.1',
        max_notional: '20',
        leverage: '1',
        max_attempts: '1',
        protection_mode: 'single_tp_plus_sl',
        review_requirement: 'post_action_review_required',
      }));
      return;
    }
    setDraftInput((current) => ({
      ...current,
      market_regime: family === 'Volatility expansion' ? 'volatility_expansion' : family === 'Mean reversion' ? 'mean_reversion' : current.market_regime,
      family,
      strategy_family_id: String(candidate.strategy_family_id || carrierId),
      carrier_id: carrierId,
      symbol: '',
      quantity: '',
      max_notional: '',
    }));
  };

  if (loading) return <div className="p-4 text-sm text-slate-500">正在读取当前内容...</div>;

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <PageHeader title="行动入口" subtitle="从行情判断进入候选选择、风险复核、授权草案路径和最终门禁状态。" status={envelope?.freshness_status}>
        <Badge variant="muted">只读入口</Badge>
      </PageHeader>

      <PageSummary
        mood={summaryMood}
        title={actionState.enabled === true ? '后端返回可行动状态' : '当前不可直接执行'}
        description={actionState.enabled === true ? '仍需通过官方执行链路提交。' : displayValue(actionState.disabled_reason, '等待 Owner 授权、最终门禁和证据检查。')}
      />

      <EnvelopeStatus envelope={envelope} error={error} />

      <Card className="p-5">
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            setCommittedInput(draftInput);
          }}
        >
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-medium">Owner 行情输入</h2>
              <p className="text-xs text-slate-500 mt-1">输入只用于本页只读查询，不创建授权、不写入 PG。</p>
            </div>
            <button
              type="submit"
              className="rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              更新候选
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
            <label className="space-y-1 text-sm">
              <span className="text-xs font-medium text-slate-500">行情判断</span>
              <select value={draftInput.market_regime} onChange={(event) => updateField('market_regime', event.target.value)} className="w-full rounded-md border border-slate-200 bg-white p-2 text-sm dark:border-slate-800 dark:bg-slate-950">
                <option value="trend">趋势</option>
                <option value="volatility_expansion">波动扩张</option>
                <option value="mean_reversion">均值回归</option>
              </select>
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-xs font-medium text-slate-500">标的偏好</span>
              <input value={draftInput.symbol_preference} onChange={(event) => updateField('symbol_preference', event.target.value)} className="w-full rounded-md border border-slate-200 bg-white p-2 text-sm dark:border-slate-800 dark:bg-slate-950" />
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-xs font-medium text-slate-500">方向</span>
              <select value={draftInput.side} onChange={(event) => updateField('side', event.target.value)} className="w-full rounded-md border border-slate-200 bg-white p-2 text-sm dark:border-slate-800 dark:bg-slate-950">
                <option value="long">做多</option>
                <option value="short">做空</option>
              </select>
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-xs font-medium text-slate-500">风险层级</span>
              <select value={draftInput.risk_tier} onChange={(event) => updateField('risk_tier', event.target.value)} className="w-full rounded-md border border-slate-200 bg-white p-2 text-sm dark:border-slate-800 dark:bg-slate-950">
                <option value="low">低</option>
                <option value="medium">中</option>
                <option value="high">高</option>
              </select>
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-xs font-medium text-slate-500">数量</span>
              <input value={draftInput.quantity} onChange={(event) => updateField('quantity', event.target.value)} className="w-full rounded-md border border-slate-200 bg-white p-2 text-sm dark:border-slate-800 dark:bg-slate-950" />
            </label>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <label className="space-y-1 text-sm">
              <span className="text-xs font-medium text-slate-500">Carrier</span>
              <input value={draftInput.carrier_id} onChange={(event) => updateField('carrier_id', event.target.value)} className="w-full rounded-md border border-slate-200 bg-white p-2 text-sm dark:border-slate-800 dark:bg-slate-950" />
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-xs font-medium text-slate-500">最大名义金额</span>
              <input value={draftInput.max_notional} onChange={(event) => updateField('max_notional', event.target.value)} className="w-full rounded-md border border-slate-200 bg-white p-2 text-sm dark:border-slate-800 dark:bg-slate-950" />
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-xs font-medium text-slate-500">杠杆</span>
              <input value={draftInput.leverage} onChange={(event) => updateField('leverage', event.target.value)} className="w-full rounded-md border border-slate-200 bg-white p-2 text-sm dark:border-slate-800 dark:bg-slate-950" />
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-xs font-medium text-slate-500">保护模式</span>
              <input value={draftInput.protection_mode} onChange={(event) => updateField('protection_mode', event.target.value)} className="w-full rounded-md border border-slate-200 bg-white p-2 text-sm dark:border-slate-800 dark:bg-slate-950" />
            </label>
          </div>

          <label className="block space-y-1 text-sm">
            <span className="text-xs font-medium text-slate-500">Owner 备注</span>
            <textarea value={draftInput.note} onChange={(event) => updateField('note', event.target.value)} rows={2} className="w-full rounded-md border border-slate-200 bg-white p-2 text-sm dark:border-slate-800 dark:bg-slate-950" placeholder="可记录行情判断，不会作为授权事实写入。" />
          </label>
        </form>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {candidateOutput.map((candidate) => (
          <Card key={`${candidate.family}-${candidate.carrier_id || 'proposal'}`} className="p-4">
            <div className="flex items-start justify-between gap-3 mb-3">
              <div>
                <h3 className="text-sm font-semibold">{candidate.family}</h3>
                <div className="text-xs text-slate-500 mt-1">{displayValue(candidate.carrier_id, '暂无 Carrier')}</div>
              </div>
              <Badge variant={candidate.candidate_state === 'bounded_live_candidate' ? 'warning' : 'caution'}>
                {candidate.candidate_state === 'bounded_live_candidate' ? '候选' : '提案'}
              </Badge>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs text-slate-600 dark:text-slate-400">
              <div>准入：{candidate.admission_level}</div>
              <div>警告：{candidate.warning_count}</div>
              <div>阻断：{candidate.hard_blocker_count}</div>
              <div>Registry：{candidate.action_registry_supported ? '支持' : '未支持'}</div>
            </div>
            <button
              type="button"
              onClick={() => selectCandidate(candidate)}
              className="mt-4 w-full rounded-md border border-slate-200 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 dark:border-slate-800 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              选择候选
            </button>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-medium">候选与范围核验</h2>
            <Badge variant={variantForActionState(selectedAction.action_entry_state)}>
              {actionEntryStateLabel(selectedAction.action_entry_state)}
            </Badge>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
            <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">行情：{regimeLabel[pageData.owner_market_input?.regime] || '未选择'}</div>
            <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">映射：{displayValue(pageData.owner_market_input?.mapped_family, '暂无')}</div>
            <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">标的：{displayValue(selectedSpec.symbol || draftInput.symbol, '暂无')}</div>
            <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">方向：{sideLabel(selectedSpec.side || draftInput.side)}</div>
            <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">数量：{displayValue(selectedSpec.quantity || draftInput.quantity, '暂无')}</div>
            <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">风险：{riskTierLabel[pageData.owner_market_input?.risk_tier] || '未选择'}</div>
          </div>
          <div className="mt-4 text-sm">
            范围核验：
            <Badge className="ml-2" variant={scopeReview.verdict === 'matched' ? 'normal' : scopeReview.verdict === 'not_checked' ? 'caution' : 'danger'}>
              {scopeReview.verdict === 'matched' ? '已匹配' : scopeReview.verdict === 'not_checked' ? '未核验' : '不匹配'}
            </Badge>
          </div>
        </Card>

        <Card className="p-5">
          <h2 className="text-base font-medium mb-4">风险复核</h2>
          <div className="grid grid-cols-2 gap-3 mb-4">
            <div className="rounded bg-amber-50 p-3 text-amber-900 dark:bg-amber-950/20 dark:text-amber-200">
              <div className="text-xs">警告</div>
              <div className="font-mono text-lg">{riskReview.warning_count || 0}</div>
            </div>
            <div className="rounded bg-rose-50 p-3 text-rose-900 dark:bg-rose-950/20 dark:text-rose-200">
              <div className="text-xs">硬阻断</div>
              <div className="font-mono text-lg">{riskReview.hard_blocker_count || 0}</div>
            </div>
          </div>
          <div className="space-y-2 text-sm">
            {asArray<string>(riskReview.warnings).slice(0, 4).map((item, index) => (
              <div key={index} className="flex gap-2 text-amber-700 dark:text-amber-300">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{blockingReasonLabel(item)}</span>
              </div>
            ))}
            {asArray<string>(riskReview.hard_blockers).slice(0, 4).map((item, index) => (
              <div key={index} className="flex gap-2 text-red-700 dark:text-red-300">
                <Lock className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{blockingReasonLabel(item)}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="p-5">
          <div className="flex items-center gap-2 mb-3">
            <ShieldCheck className="h-4 w-4 text-blue-600" />
            <h2 className="text-base font-medium">授权草案路径</h2>
          </div>
          <div className="space-y-2 text-sm">
            <div>状态：{displayValue(authorizationPath.status, '无法确认')}</div>
            <div>官方路径：{authorizationPath.official_service_path_available ? '可查看' : '不可用'}</div>
            <div>本页创建授权：否</div>
          </div>
        </Card>

        <Card className="p-5">
          <div className="flex items-center gap-2 mb-3">
            <CircleDashed className="h-4 w-4 text-amber-600" />
            <h2 className="text-base font-medium">最终门禁</h2>
          </div>
          <div className="space-y-2 text-sm">
            <div>结果：{finalGateStatusLabel(finalGate.status)}</div>
            <div>证据：{finalGate.evidence_status === 'pre_action_evidence_required' ? '需执行前证据' : '无法确认'}</div>
            <div>阻断：{asArray(finalGate.blocker_ids).length}</div>
          </div>
        </Card>

        <Card className="p-5">
          <div className="flex items-center gap-2 mb-3">
            <Target className="h-4 w-4 text-slate-600 dark:text-slate-300" />
            <h2 className="text-base font-medium">行动状态</h2>
          </div>
          {actionState.enabled === true ? (
            <button type="button" className="w-full rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white">
              {displayValue(actionState.label, '有界实盘执行')}
            </button>
          ) : (
            <DeferredActionSlot actionName={displayValue(actionState.label, '有界实盘执行')} reason={displayValue(actionState.disabled_reason, '当前不可操作')} />
          )}
        </Card>
      </div>

      <Card className="p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-medium">Post-action 状态</h2>
          <Badge variant={postAction.status === 'available' ? 'normal' : 'muted'}>
            {postAction.status === 'available' ? '有历史链路' : '暂无链路'}
          </Badge>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3 text-sm">
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">意图：{postAction.intent_count || 0}</div>
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">完成：{postAction.completed_intent_count || 0}</div>
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">Entry：{postAction.entry_order_count || 0}</div>
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">TP/SL：{postAction.protection_order_count || 0}</div>
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">复盘：{postAction.review_count || 0}</div>
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">审计：{postAction.audit_event_count || 0}</div>
        </div>
        <p className="mt-3 text-xs text-slate-500">重复执行安全：{displayValue(postAction.retry_safety, '无法确认')}</p>
      </Card>

      <TechnicalDetails title="Raw / Debug：Action Entry 只读响应">
        <button
          type="button"
          onClick={() => navigator.clipboard?.writeText(JSON.stringify(pageData, null, 2))}
          className="mb-2 rounded border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-slate-100 dark:border-slate-800 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          复制
        </button>
        <pre className="overflow-auto font-mono">{JSON.stringify(pageData, null, 2)}</pre>
      </TechnicalDetails>
    </div>
  );
}
