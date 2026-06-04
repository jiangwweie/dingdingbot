import { Badge, Card, DeferredActionSlot, EnvelopeStatus, PageHeader, PageSummary, TechnicalDetails } from '@/components/ui';
import { actionSlotEntries, displayValue, useReadModel } from '@/lib/tradingConsoleApi';
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
    </div>
  );
}
