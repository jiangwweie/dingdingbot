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
  risk_tier: 'tiny',
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

const SYMBOL_OPTIONS = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'BNB/USDT:USDT'];

const regimeLabel: Record<string, string> = {
  trend: '趋势',
  volatility_expansion: '波动扩张',
  mean_reversion: '区间/震荡',
};

const riskTierLabel: Record<string, string> = {
  tiny: 'Tiny',
  small: 'Small',
  custom: 'Custom',
};

const proposalRoleLabel: Record<string, string> = {
  trend_candidate: '趋势候选',
  range_candidate: '区间/震荡候选',
  volatility_candidate: '波动候选',
  unknown: '候选',
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
  return `/api/trading-console/owner-action-flow?${params.toString()}`;
}

function variantForActionState(value?: string) {
  if (value === 'ready_for_owner_scope_final_gate') return 'warning' as const;
  if (value === 'proposal_only') return 'caution' as const;
  return 'danger' as const;
}

function variantForFlowStep(value?: string) {
  if (value === 'ready' || value === 'available') return 'normal' as const;
  if (value === 'warning' || value === 'pending' || value === 'empty') return 'caution' as const;
  return 'danger' as const;
}

function regimeForFamily(family: string, fallback: string): string {
  if (family === 'Trend') return 'trend';
  if (family === 'Volatility expansion') return 'volatility_expansion';
  if (family === 'Mean reversion') return 'mean_reversion';
  return fallback;
}

function firstDisplayValue(item: any, keys: string[], fallback = '暂无'): string {
  for (const key of keys) {
    const value = item?.[key];
    if (value !== undefined && value !== null && value !== '') return String(value);
  }
  return fallback;
}

function EvidenceList({
  title,
  items,
  emptyText,
  describe,
}: {
  title: string;
  items: any[];
  emptyText: string;
  describe: (item: any) => { primary: string; secondary: string };
}) {
  return (
    <div className="rounded-md border border-slate-200 p-3 dark:border-slate-800">
      <h3 className="text-xs font-semibold text-slate-500">{title}</h3>
      {items.length === 0 ? (
        <div className="mt-2 text-sm text-slate-500">{emptyText}</div>
      ) : (
        <div className="mt-2 space-y-2">
          {items.slice(0, 3).map((item, index) => {
            const row = describe(item);
            return (
              <div key={index} className="rounded bg-slate-50 p-2 dark:bg-slate-800/40">
                <div className="truncate text-sm font-medium">{row.primary}</div>
                <div className="mt-1 truncate text-xs text-slate-500">{row.secondary}</div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function ActionEntry() {
  const [draftInput, setDraftInput] = useState<ActionEntryInput>(INITIAL_INPUT);
  const [committedInput, setCommittedInput] = useState<ActionEntryInput>(INITIAL_INPUT);
  const endpoint = useMemo(() => queryFromInput(committedInput), [committedInput]);
  const { envelope, loading, error } = useReadModel<any>(endpoint);

  const pageData = envelope?.data || {};
  const candidateOutput = asArray<any>(pageData.candidate_output);
  const genericSpecs = asArray<any>(pageData.generic_action_specs);
  const payloadContracts = asArray<any>(pageData.action_entry_payload_contracts);
  const selected = pageData.selected_candidate || {};
  const selectedAction = selected.action_entry || {};
  const selectedSpec = selected.generic_action_spec || {};
  const scopeReview = selected.scope_review || {};
  const riskReview = pageData.risk_review || {};
  const finalGate = pageData.final_gate_result || {};
  const actionState = pageData.action_state || {};
  const authorizationPath = pageData.authorization_draft_path || {};
  const postAction = pageData.post_action_state || {};
  const postSummary = postAction.summary || {};
  const postIntents = asArray<any>(postSummary.intents);
  const postEntryOrders = asArray<any>(postSummary.entry_orders);
  const postProtectionOrders = asArray<any>(postSummary.tp_sl_orders);
  const postReviews = asArray<any>(postSummary.reviews);
  const postAuditEvents = asArray<any>(postSummary.audit_events);
  const ownerActionFlow = pageData.owner_action_flow || {};
  const flowSteps = asArray<any>(ownerActionFlow.flow_steps);
  const budgetRecommendation = pageData.budget_recommendation || {};
  const budgetSummary = ownerActionFlow.budget_summary || {};
  const candidateChoices = asArray<any>(ownerActionFlow.market_selection?.candidate_choices);
  const recommendedSymbols = asArray<any>(ownerActionFlow.market_selection?.recommended_symbols || budgetSummary.recommended_symbols || budgetRecommendation.recommended_symbols);
  const selectedProposal = ownerActionFlow.selected_action_proposal || {};
  const budgetMissingFacts = asArray<string>(budgetSummary.missing_facts);
  const budgetHardBlockers = asArray<any>(budgetSummary.hard_blockers);
  const summaryMood = actionState.enabled === true
    ? 'ok'
    : finalGate.status === 'proposal_only'
      ? 'unknown'
      : 'blocked';

  const updateField = (field: keyof ActionEntryInput, value: string) => {
    setDraftInput((current) => ({ ...current, [field]: value }));
  };

  const updateSymbol = (value: string) => {
    setDraftInput((current) => ({ ...current, symbol: value, symbol_preference: value }));
  };

  const selectCandidate = (candidate: any) => {
    const family = String(candidate.family || '');
    const carrierId = String(candidate.carrier_id || '');
    const spec = genericSpecs.find((item) => (
      (carrierId && item.carrier_id === carrierId) || item.family === family
    )) || {};
    const payloadContract = payloadContracts.find((item) => (
      (carrierId && item.carrier_id === carrierId) || item.family === family
    ));
    const requiredScope = payloadContract?.required_owner_scope || {};
    setDraftInput((current) => ({
      ...current,
      market_regime: regimeForFamily(family, current.market_regime),
      family,
      strategy_family_id: String(candidate.strategy_family_id || carrierId),
      carrier_id: carrierId,
      symbol_preference: String(requiredScope.symbol || spec.symbol || current.symbol_preference),
      symbol: String(requiredScope.symbol || spec.symbol || ''),
      side: String(requiredScope.side || spec.side || 'long'),
      quantity: String(spec.recommended_quantity || requiredScope.quantity || spec.quantity || ''),
      max_notional: String(spec.recommended_max_notional || requiredScope.max_notional || spec.max_notional || ''),
      leverage: String(requiredScope.leverage || spec.leverage || '1'),
      max_attempts: String(requiredScope.max_attempts || spec.max_attempts || '1'),
      protection_mode: String(requiredScope.protection_mode || spec.protection_mode || 'single_tp_plus_sl'),
      review_requirement: String(requiredScope.review_requirement || spec.review_requirement || 'post_action_review_required'),
    }));
  };

  if (loading) return <div className="p-4 text-sm text-slate-500">正在读取当前内容...</div>;

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <PageHeader title="Owner Action Flow" subtitle="从行情判断进入候选选择、风险复核、授权草案路径、最终门禁和行动状态。" status={envelope?.freshness_status}>
        <Badge variant="muted">只读入口</Badge>
      </PageHeader>

      <PageSummary
        mood={summaryMood}
        title={actionState.enabled === true ? '后端返回可行动状态' : '当前不可直接执行'}
        description={actionState.enabled === true ? '仍需通过官方执行链路提交。' : displayValue(actionState.disabled_reason, '等待 Owner 授权、最终门禁和证据检查。')}
      />

      <EnvelopeStatus envelope={envelope} error={error} />

      <Card className="p-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-base font-medium">行动流</h2>
          <Badge variant={ownerActionFlow.status === 'actionable' ? 'normal' : 'caution'}>
            {ownerActionFlow.status === 'actionable' ? '可行动' : '不可直接执行'}
          </Badge>
        </div>
        <div className="mt-4 grid grid-cols-1 md:grid-cols-7 gap-2">
          {flowSteps.map((step) => (
            <div key={step.step} className="rounded-md border border-slate-200 p-3 dark:border-slate-800">
              <div className="flex items-center justify-between gap-2">
                <div className="truncate text-xs font-medium text-slate-500">{displayValue(step.label, '步骤')}</div>
                <Badge variant={variantForFlowStep(step.status)}>{displayValue(step.status, '未知')}</Badge>
              </div>
              <div className="mt-2 line-clamp-2 text-xs text-slate-600 dark:text-slate-400">
                {displayValue(step.summary, '暂无')}
              </div>
            </div>
          ))}
        </div>
      </Card>

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
                <option value="mean_reversion">区间/震荡</option>
              </select>
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-xs font-medium text-slate-500">标的</span>
              <select value={draftInput.symbol || draftInput.symbol_preference} onChange={(event) => updateSymbol(event.target.value)} className="w-full rounded-md border border-slate-200 bg-white p-2 text-sm dark:border-slate-800 dark:bg-slate-950">
                {SYMBOL_OPTIONS.map((symbol) => (
                  <option key={symbol} value={symbol}>{symbol}</option>
                ))}
              </select>
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
                <option value="tiny">Tiny</option>
                <option value="small">Small</option>
                <option value="custom">Custom</option>
              </select>
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-xs font-medium text-slate-500">数量</span>
              <input value={draftInput.quantity} onChange={(event) => updateField('quantity', event.target.value)} className="w-full rounded-md border border-slate-200 bg-white p-2 text-sm dark:border-slate-800 dark:bg-slate-950" />
            </label>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-6 gap-3">
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
              <span className="text-xs font-medium text-slate-500">尝试次数</span>
              <input value={draftInput.max_attempts} onChange={(event) => updateField('max_attempts', event.target.value)} className="w-full rounded-md border border-slate-200 bg-white p-2 text-sm dark:border-slate-800 dark:bg-slate-950" />
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-xs font-medium text-slate-500">保护模式</span>
              <select value={draftInput.protection_mode} onChange={(event) => updateField('protection_mode', event.target.value)} className="w-full rounded-md border border-slate-200 bg-white p-2 text-sm dark:border-slate-800 dark:bg-slate-950">
                <option value="single_tp_plus_sl">single_tp_plus_sl</option>
              </select>
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-xs font-medium text-slate-500">复盘要求</span>
              <select value={draftInput.review_requirement} onChange={(event) => updateField('review_requirement', event.target.value)} className="w-full rounded-md border border-slate-200 bg-white p-2 text-sm dark:border-slate-800 dark:bg-slate-950">
                <option value="post_action_review_required">post_action_review_required</option>
              </select>
            </label>
          </div>

          <label className="block space-y-1 text-sm">
            <span className="text-xs font-medium text-slate-500">Owner 备注</span>
            <textarea value={draftInput.note} onChange={(event) => updateField('note', event.target.value)} rows={2} className="w-full rounded-md border border-slate-200 bg-white p-2 text-sm dark:border-slate-800 dark:bg-slate-950" placeholder="可记录行情判断，不会作为授权事实写入。" />
          </label>
        </form>
      </Card>

      <Card className="p-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-medium">Budget Envelope</h2>
            <div className="mt-1 text-xs text-slate-500">
              {displayValue(budgetSummary.account_capacity_status, displayValue(budgetRecommendation.account_capacity?.status, 'not_available'))}
            </div>
          </div>
          <Badge variant={budgetSummary.status === 'available' ? 'normal' : 'danger'}>
            {displayValue(budgetSummary.status, budgetRecommendation.budget_envelope?.status || 'not_available')}
          </Badge>
        </div>
        <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">
            <div className="text-xs text-slate-500">Account</div>
            <div className="font-mono">{displayValue(budgetSummary.account_equity, '暂无')}</div>
          </div>
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">
            <div className="text-xs text-slate-500">Capacity</div>
            <div className="font-mono">{displayValue(budgetSummary.max_usable_notional, '暂无')}</div>
          </div>
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">
            <div className="text-xs text-slate-500">Max notional</div>
            <div className="font-mono">{displayValue(budgetSummary.recommended_max_notional_per_action, '暂无')}</div>
          </div>
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">
            <div className="text-xs text-slate-500">Leverage</div>
            <div className="font-mono">{displayValue(budgetSummary.recommended_leverage, '1')}</div>
          </div>
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">
            <div className="text-xs text-slate-500">Owner symbol</div>
            <div className="font-mono">{displayValue(budgetSummary.selected_symbol, draftInput.symbol || '暂无')}</div>
          </div>
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">
            <div className="text-xs text-slate-500">Owner max</div>
            <div className="font-mono">{displayValue(budgetSummary.selected_max_notional, draftInput.max_notional || '暂无')}</div>
          </div>
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">
            <div className="text-xs text-slate-500">Owner qty</div>
            <div className="font-mono">{displayValue(budgetSummary.selected_quantity, draftInput.quantity || '暂无')}</div>
          </div>
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">
            <div className="text-xs text-slate-500">Owner selection</div>
            <div className="font-mono">{displayValue(budgetSummary.owner_selection_status, 'not_provided')}</div>
          </div>
        </div>
        <div className="mt-4">
          <h3 className="text-xs font-semibold text-slate-500">Recommended symbols</h3>
          <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2">
            {recommendedSymbols.map((item) => (
              <button
                key={item.symbol}
                type="button"
                onClick={() => updateSymbol(String(item.symbol || ''))}
                className="rounded-md border border-slate-200 p-3 text-left text-sm hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{displayValue(item.symbol, '暂无')}</span>
                  <Badge variant={item.status === 'blocked' ? 'danger' : item.status === 'warning' ? 'caution' : 'normal'}>
                    {displayValue(item.status, 'selectable')}
                  </Badge>
                </div>
                <div className="mt-2 line-clamp-2 text-xs text-slate-500">{displayValue(item.reason, 'Owner 可选择后进入预算核验。')}</div>
                <div className="mt-2 text-xs text-slate-500">
                  W {asArray(item.warnings).length} / B {asArray(item.blockers).length}
                </div>
              </button>
            ))}
          </div>
        </div>
        <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-3">
          <EvidenceList
            title="Missing facts"
            items={budgetMissingFacts}
            emptyText="暂无缺失事实"
            describe={(item) => ({ primary: String(item), secondary: 'Budget recommendation degraded until refreshed.' })}
          />
          <EvidenceList
            title="Budget hard blockers"
            items={budgetHardBlockers}
            emptyText="暂无预算硬阻断"
            describe={(item) => ({
              primary: firstDisplayValue(item, ['id', 'stage']),
              secondary: firstDisplayValue(item, ['evidence', 'retry_condition']),
            })}
          />
        </div>
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
                {proposalRoleLabel[String(candidateChoices.find((item) => item.carrier_id === candidate.carrier_id)?.proposal_role || 'unknown')]}
              </Badge>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs text-slate-600 dark:text-slate-400">
              <div>准入：{candidate.admission_level}</div>
              <div>警告：{candidate.warning_count}</div>
              <div>阻断：{candidate.hard_blocker_count}</div>
              <div>Registry：{candidate.action_registry_supported ? '支持' : '未支持'}</div>
              <div>Max：{displayValue(candidate.recommended_sizing?.max_notional_per_action, '暂无')}</div>
              <div>预算：{displayValue(candidate.recommended_sizing?.status, '暂无')}</div>
              <div className="col-span-2">支持标的：{displayValue(candidateChoices.find((item) => item.carrier_id === candidate.carrier_id)?.supported_symbols?.join(', '), '暂无')}</div>
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
            <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">推荐 Max：{displayValue(selectedProposal.recommended_max_notional || selectedSpec.recommended_max_notional, '暂无')}</div>
            <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">提案：{proposalRoleLabel[selectedProposal.proposal_role] || '候选'}</div>
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
        <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-3">
          <EvidenceList
            title="执行意图"
            items={postIntents}
            emptyText="暂无执行意图"
            describe={(item) => ({
              primary: firstDisplayValue(item, ['intent_id', 'id', 'authorization_id']),
              secondary: `状态 ${firstDisplayValue(item, ['status'])} · ${firstDisplayValue(item, ['symbol', 'carrier_id'])}`,
            })}
          />
          <EvidenceList
            title="Entry"
            items={postEntryOrders}
            emptyText="暂无 Entry 订单"
            describe={(item) => ({
              primary: `${firstDisplayValue(item, ['order_id', 'id'])} · ${firstDisplayValue(item, ['status'])}`,
              secondary: `Ex ${firstDisplayValue(item, ['exchange_order_id'])} · 数量 ${firstDisplayValue(item, ['requested_qty', 'quantity'])} / ${firstDisplayValue(item, ['filled_qty'])}`,
            })}
          />
          <EvidenceList
            title="TP/SL"
            items={postProtectionOrders}
            emptyText="暂无 TP/SL 保护单"
            describe={(item) => ({
              primary: `${firstDisplayValue(item, ['role', 'order_role'])} · ${firstDisplayValue(item, ['status'])}`,
              secondary: `Ex ${firstDisplayValue(item, ['exchange_order_id'])} · 价格 ${firstDisplayValue(item, ['trigger_price', 'price'])}`,
            })}
          />
          <EvidenceList
            title="复盘"
            items={postReviews}
            emptyText="暂无复盘记录"
            describe={(item) => ({
              primary: firstDisplayValue(item, ['review_id', 'id']),
              secondary: `结果 ${firstDisplayValue(item, ['decision', 'status'])} · ${firstDisplayValue(item, ['campaign_id', 'authorization_id'])}`,
            })}
          />
          <EvidenceList
            title="审计"
            items={postAuditEvents}
            emptyText="暂无审计事件"
            describe={(item) => ({
              primary: firstDisplayValue(item, ['event_type', 'type']),
              secondary: `订单 ${firstDisplayValue(item, ['order_id'])} · ${firstDisplayValue(item, ['created_at', 'created_at_ms'])}`,
            })}
          />
        </div>
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
