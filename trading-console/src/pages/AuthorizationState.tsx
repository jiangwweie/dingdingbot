import { Badge, Card, DeferredActionSlot, EnvelopeStatus, PageHeader, PageSummary, TechnicalDetails } from '@/components/ui';
import { actionSlotEntries, asArray, displayValue, useReadModel } from '@/lib/tradingConsoleApi';
import { ShieldCheck, CalendarX, AlertOctagon, CheckCircle2, XCircle } from 'lucide-react';
import { authorizationStatusLabel, blockingReasonLabel, pageSummaryFromEnvelope } from '@/lib/ownerViewModel';

export default function AuthorizationState() {
  const { envelope, loading, error } = useReadModel<any>('/api/trading-console/authorization-state');

  if (loading) return <div className="p-4 text-sm text-slate-500">正在读取当前内容...</div>;

  const pageData = envelope?.data || {};
  const futureActionSlots = actionSlotEntries(pageData.future_action_slots);
  const summary = pageSummaryFromEnvelope(envelope, pageData.is_actionable ? '当前授权可继续进入前置检查。' : '当前授权不可直接行动。');

  const renderStatus = () => {
    if (pageData.is_consumed) return <Badge variant="muted" className="flex items-center gap-1"><CheckCircle2 className="w-3 h-3"/> 已消费</Badge>;
    if (pageData.is_expired) return <Badge variant="danger" className="flex items-center gap-1"><CalendarX className="w-3 h-3"/> 已过期</Badge>;
    if (pageData.is_cancelled) return <Badge variant="danger" className="flex items-center gap-1"><AlertOctagon className="w-3 h-3"/> 已取消</Badge>;
    if (pageData.is_actionable !== true) return <Badge variant="danger" className="flex items-center gap-1"><XCircle className="w-3 h-3"/> 不可行动</Badge>;
    return <Badge variant="warning">{authorizationStatusLabel(pageData.status)}</Badge>;
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <PageHeader title="有界实盘授权" subtitle="查看授权是否存在、是否还能使用，以及为什么不能继续。" status={envelope?.freshness_status} />

      <PageSummary mood={summary.mood} title={summary.title} description={summary.description} />

      <EnvelopeStatus envelope={envelope} error={error} />

      <Card className="p-6">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center border-b border-slate-100 dark:border-slate-800 pb-4 mb-4 gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 rounded-lg">
              <ShieldCheck className="w-6 h-6" />
            </div>
            <div>
              <div className="text-sm text-slate-500">授权状态</div>
              <div className="font-medium">{authorizationStatusLabel(pageData.status)}</div>
            </div>
          </div>
          <div>{renderStatus()}</div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
          <div>
            <div className="text-sm text-slate-500 mb-1">授权对象</div>
            <div>{displayValue(pageData.carrier_id, '暂无')}</div>
          </div>
          <div>
            <div className="text-sm text-slate-500 mb-1">范围核验</div>
            <div>
              {pageData.scope_match === 'not_checked' ? <Badge variant="warning">未核验</Badge> :
               pageData.scope_match === 'matched' ? <Badge variant="normal">已匹配</Badge> :
               <Badge variant="danger">{displayValue(pageData.scope_match, '无法确认')}</Badge>}
            </div>
          </div>
          <div>
            <div className="text-sm text-slate-500 mb-1">生命周期</div>
            <div className="text-sm">{pageData.is_consumed ? '已消费' : pageData.is_expired ? '已过期' : pageData.is_cancelled ? '已取消' : '未消费'}</div>
          </div>
          <div>
            <div className="text-sm text-slate-500 mb-1">是否可行动</div>
            <Badge variant={pageData.is_actionable === true ? 'warning' : 'danger'}>{pageData.is_actionable === true ? '是' : '否'}</Badge>
          </div>
        </div>

        {pageData.blocking_reason && (
          <div className="bg-red-50 dark:bg-red-900/10 border border-red-100 dark:border-red-900/30 rounded-md p-4 mb-6">
            <h4 className="text-sm font-semibold text-red-800 dark:text-red-400 mb-1">不能继续的原因</h4>
            <p className="text-sm text-red-700 dark:text-red-300">{blockingReasonLabel(pageData.blocking_reason)}</p>
          </div>
        )}

        <Card className="p-4 mb-6 bg-slate-50 dark:bg-slate-950">
          <h4 className="text-sm font-medium mb-3">授权范围摘要</h4>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
            <div>标的：{displayValue(pageData.scope?.symbol, '未知')}</div>
            <div>方向：{displayValue(pageData.scope?.side, '未知')}</div>
            <div>最大名义金额：{displayValue(pageData.scope?.max_notional, '未知')}</div>
            <div>数量：{displayValue(pageData.scope?.quantity, '未知')}</div>
          </div>
        </Card>

        <TechnicalDetails title="后续可开放的授权动作">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {futureActionSlots.map((slot) => (
              <DeferredActionSlot key={slot.name} actionName={slot.name === 'void_authorization' ? '作废授权' : slot.name === 'cancel_authorization' ? '变更授权' : slot.name} reason="当前不可操作" />
            ))}
            {futureActionSlots.length === 0 && (
              <div className="text-sm text-slate-500 col-span-2">当前无开放动作槽位</div>
            )}
          </div>
        </TechnicalDetails>
      </Card>

      <RuntimeSafetyReadinessPanel />
    </div>
  );
}

function RuntimeSafetyReadinessPanel() {
  const { envelope, loading, error } = useReadModel<any>('/api/trading-console/strategy-runtimes?limit=1');
  const runtimeEnvelope: any = envelope;
  const runtimes = Array.isArray(runtimeEnvelope) ? runtimeEnvelope : asArray(runtimeEnvelope?.data);
  const runtime = runtimes[0];

  if (loading) {
    return (
      <Card className="p-6">
        <div className="text-sm text-slate-500">正在读取 runtime 安全边界...</div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="p-6">
        <RuntimeSafetyHeader status="unavailable" />
        <div className="mt-4 rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800 dark:border-rose-900/50 dark:bg-rose-950/20 dark:text-rose-200">
          {error}
        </div>
      </Card>
    );
  }

  if (!runtime?.runtime_instance_id) {
    return (
      <Card className="p-6">
        <RuntimeSafetyHeader status="not_available" />
        <div className="mt-4 grid grid-cols-1 gap-3 text-sm md:grid-cols-3">
          <RuntimeSafetyFact label="Runtime" value="暂无实例" tone="danger" />
          <RuntimeSafetyFact label="授权类型" value="one-shot" tone="warning" />
          <RuntimeSafetyFact label="执行权限" value="未授予" tone="muted" />
        </div>
      </Card>
    );
  }

  return <RuntimeSafetyReadinessDetail runtimeId={String(runtime.runtime_instance_id)} />;
}

function RuntimeSafetyReadinessDetail({ runtimeId }: { runtimeId: string }) {
  const { envelope, loading, error } = useReadModel<any>(`/api/trading-console/strategy-runtimes/${encodeURIComponent(runtimeId)}/safety-readiness`);
  const readiness: any = envelope || {};
  const blockers = asArray<string>(readiness.blockers);
  const warnings = asArray<string>(readiness.warnings);
  const confirmations = asArray<string>(readiness.required_owner_confirmations);
  const requirements = asArray<any>(readiness.requirements);

  if (loading) {
    return (
      <Card className="p-6">
        <div className="text-sm text-slate-500">正在读取 runtime 安全边界...</div>
      </Card>
    );
  }

  return (
    <Card className="p-6">
      <RuntimeSafetyHeader status={error ? 'unavailable' : readiness.status} />
      {error ? (
        <div className="mt-4 rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800 dark:border-rose-900/50 dark:bg-rose-950/20 dark:text-rose-200">
          {error}
        </div>
      ) : (
        <>
          <div className="mt-4 grid grid-cols-1 gap-3 text-sm md:grid-cols-4">
            <RuntimeSafetyFact label="Runtime" value={displayValue(readiness.runtime_instance_id, '暂无')} tone="muted" />
            <RuntimeSafetyFact label="状态" value={runtimeSafetyStatusLabel(readiness.status)} tone={blockers.length > 0 ? 'danger' : 'warning'} />
            <RuntimeSafetyFact label="阻断" value={String(blockers.length)} tone={blockers.length > 0 ? 'danger' : 'normal'} />
            <RuntimeSafetyFact label="需确认" value={String(confirmations.length)} tone={confirmations.length > 0 ? 'warning' : 'normal'} />
          </div>

          <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <RuntimeSafetyList
              title="阻断项"
              empty="当前边界事实完整"
              items={blockers}
              tone="danger"
            />
            <RuntimeSafetyList
              title="Owner / Codex 确认"
              empty="暂无待确认项"
              items={confirmations}
              tone="warning"
              mapLabel={runtimeSafetyConfirmationLabel}
            />
          </div>

          <TechnicalDetails title="Runtime safety facts">
            <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
              {requirements.slice(0, 12).map((requirement) => (
                <div key={requirement.code} className="rounded border border-slate-200 bg-white p-2 dark:border-slate-800 dark:bg-slate-950">
                  <div className="flex items-center justify-between gap-2">
                    <span>{runtimeSafetyRequirementLabel(requirement.code)}</span>
                    <Badge variant={requirement.status === 'pass' ? 'normal' : requirement.status === 'warn' ? 'warning' : 'danger'}>
                      {runtimeSafetyRequirementStatusLabel(requirement.status)}
                    </Badge>
                  </div>
                  {requirement.confirmation_key && (
                    <div className="mt-1 text-slate-500">
                      {runtimeSafetyConfirmationLabel(requirement.confirmation_key)}
                    </div>
                  )}
                </div>
              ))}
            </div>
            {warnings.length > 0 && (
              <div className="mt-3 text-amber-700 dark:text-amber-300">
                {warnings.map(runtimeSafetyRequirementLabel).join(' / ')}
              </div>
            )}
          </TechnicalDetails>
        </>
      )}
    </Card>
  );
}

function RuntimeSafetyHeader({ status }: { status: string }) {
  const blocked = status === 'blocked' || status === 'unavailable' || status === 'not_available';
  return (
    <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
      <div>
        <h2 className="text-lg font-medium">Runtime 安全边界</h2>
        <div className="mt-1 text-sm text-slate-500">执行前必须确认的边界事实</div>
      </div>
      <Badge variant={blocked ? 'danger' : 'warning'}>{runtimeSafetyStatusLabel(status)}</Badge>
    </div>
  );
}

function RuntimeSafetyFact({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: 'normal' | 'warning' | 'danger' | 'muted';
}) {
  const classes = {
    normal: 'border-blue-200 bg-blue-50 text-blue-900 dark:border-blue-900/40 dark:bg-blue-950/20 dark:text-blue-200',
    warning: 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200',
    danger: 'border-rose-200 bg-rose-50 text-rose-900 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-200',
    muted: 'border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300',
  };
  return (
    <div className={`rounded-md border p-3 ${classes[tone]}`}>
      <div className="text-xs opacity-70">{label}</div>
      <div className="mt-1 font-medium">{value}</div>
    </div>
  );
}

function RuntimeSafetyList({
  title,
  empty,
  items,
  tone,
  mapLabel = runtimeSafetyRequirementLabel,
}: {
  title: string;
  empty: string;
  items: string[];
  tone: 'warning' | 'danger';
  mapLabel?: (value: string) => string;
}) {
  const color = tone === 'danger'
    ? 'border-rose-200 text-rose-800 dark:border-rose-900/40 dark:text-rose-200'
    : 'border-amber-200 text-amber-800 dark:border-amber-900/40 dark:text-amber-200';
  return (
    <div className={`rounded-md border p-4 ${color}`}>
      <div className="mb-3 text-sm font-semibold">{title}</div>
      {items.length === 0 ? (
        <div className="text-sm opacity-75">{empty}</div>
      ) : (
        <div className="space-y-2 text-sm">
          {items.slice(0, 8).map((item) => (
            <div key={item} className="rounded bg-white/60 px-2 py-1 dark:bg-slate-950/60">
              {mapLabel(item)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function runtimeSafetyStatusLabel(status: string): string {
  const map: Record<string, string> = {
    blocked: '阻断',
    ready_for_owner_codex_confirmation: '待确认',
    not_available: '暂无 Runtime',
    unavailable: '不可用',
  };
  return map[status] || displayValue(status, '无法确认');
}

function runtimeSafetyRequirementStatusLabel(status: string): string {
  const map: Record<string, string> = {
    pass: '已具备',
    warn: '需确认',
    block: '缺失',
  };
  return map[status] || displayValue(status, '未知');
}

function runtimeSafetyRequirementLabel(code: string): string {
  const map: Record<string, string> = {
    runtime_status_active: 'Runtime 状态',
    runtime_remains_non_executing_preview: '非执行预览边界',
    symbol_side_boundary_present: '标的 / 方向边界',
    attempt_limit_available: '尝试次数边界',
    max_loss_budget_present: '最大亏损预算',
    budget_reservation_basis_required: '预算预留规则',
    max_notional_boundary_present: '单次名义金额',
    max_active_positions_boundary_present: '最大活跃仓位',
    max_leverage_boundary_present: '最大杠杆',
    margin_usage_boundary_present: '保证金占用',
    liquidation_buffer_boundary_present: '强平缓冲',
    protection_required: '硬保护要求',
    review_required: '复盘要求',
    trusted_fact_sources_required: '可信仓位事实',
    trusted_account_facts_required: '可信账户事实',
    stale_fact_behavior_required: '过期事实处理',
  };
  return map[code] || code;
}

function runtimeSafetyConfirmationLabel(code: string): string {
  const map: Record<string, string> = {
    symbol_side_boundary_confirmed: '确认标的 / 方向边界',
    attempt_consumption_rule_confirmed: '确认 attempt 消耗规则',
    max_loss_budget_confirmed: '确认最大亏损预算',
    budget_reservation_rule_confirmed: '确认预算预留规则',
    max_notional_boundary_confirmed: '确认单次名义金额',
    max_active_positions_boundary_confirmed: '确认最大活跃仓位',
    max_leverage_boundary_confirmed: '确认最大杠杆',
    margin_usage_boundary_confirmed: '确认保证金边界',
    liquidation_buffer_boundary_confirmed: '确认强平缓冲',
    protection_readiness_source_confirmed: '确认保护事实来源',
    trusted_active_position_source_confirmed: '确认仓位事实来源',
    trusted_account_fact_source_confirmed: '确认账户事实来源',
    stale_fact_behavior_confirmed: '确认过期事实阻断',
  };
  return map[code] || code;
}
