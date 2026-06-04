import { Badge, Card, DeferredActionSlot, EnvelopeStatus, PageHeader, PageSummary, TechnicalDetails } from '@/components/ui';
import { asArray, displayValue, useReadModel } from '@/lib/tradingConsoleApi';
import { blockingReasonLabel, orderRoleLabel, orderStatusLabel, pageSummaryFromEnvelope, protectionStatusLabel } from '@/lib/ownerViewModel';

export default function ProtectionHealth() {
  const { envelope, loading, error } = useReadModel<any>('/api/trading-console/protection-health?include_exchange=true');

  if (loading) return <div className="p-4 text-sm text-slate-500">正在读取当前内容...</div>;

  const pageData = envelope?.data || {};
  const protectionOrders = asArray(pageData.protection_orders);
  const currentScopeProtection = asArray(pageData.current_scope_active_protection || pageData.current_scope_protection);
  const historicalProtection = asArray(pageData.historical_protection_orders);
  const orphanProtection = asArray(pageData.orphan_protection_orders);
  const findings = asArray(pageData.findings);
  const actionsExposed = asArray(pageData.actions_exposed);
  const deferredActions = asArray<string>(pageData.deferred_actions);
  const status = String(pageData.status || 'unknown');
  const summary = pageSummaryFromEnvelope(envelope, status === 'protected' ? '当前仓位保护完整。' : '请确认仓位保护是否完整。');

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <PageHeader title="保护健康" subtitle="确认仓位是否被止盈/止损保护覆盖。" status={envelope?.freshness_status} />

      <PageSummary mood={summary.mood} title={summary.title} description={summary.description} />

      <EnvelopeStatus envelope={envelope} error={error} />

      <Card className="p-5">
        <div className="flex items-center justify-between gap-4 mb-4">
          <div>
            <h2 className="text-lg font-medium">保护状态总览</h2>
            <p className="text-sm text-slate-500 mt-1">查看保护单是否存在、是否匹配当前仓位。</p>
          </div>
          <Badge variant={status === 'protected' ? 'normal' : status === 'unknown' ? 'warning' : 'danger'}>
            {protectionStatusLabel(status)}
          </Badge>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
          <div className="bg-slate-50 dark:bg-slate-800/40 rounded p-3">
            <div className="text-xs text-slate-500 mb-1">止盈单</div>
            <div className="font-mono">{displayValue(pageData.tp_count, '0')}</div>
          </div>
          <div className="bg-slate-50 dark:bg-slate-800/40 rounded p-3">
            <div className="text-xs text-slate-500 mb-1">止损单</div>
            <div className="font-mono">{displayValue(pageData.sl_count, '0')}</div>
          </div>
          <div className="bg-slate-50 dark:bg-slate-800/40 rounded p-3">
            <div className="text-xs text-slate-500 mb-1">后续处理动作</div>
            <div className="font-mono">{actionsExposed.length}</div>
          </div>
        </div>
      </Card>

      {findings.length > 0 && (
        <Card className="p-4">
          <h2 className="text-base font-medium mb-3">异常说明</h2>
          <ul className="space-y-2 text-sm">
            {findings.map((finding: any, index) => (
              <li key={index} className="rounded-md border border-amber-200 bg-amber-50 p-3 text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200">
                {blockingReasonLabel(finding.message || finding.reason || finding.type || finding.code || '保护状态需要人工确认')}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card className="p-4">
        <div className="flex items-center justify-between gap-4 mb-3">
          <h2 className="text-base font-medium">当前活跃保护单</h2>
          <div className="text-sm text-slate-500">数量：{currentScopeProtection.length}</div>
        </div>
        {currentScopeProtection.length > 0 ? (
          <div className="space-y-2">
            {currentScopeProtection.map((order: any) => (
              <div key={order.order_id || order.exchange_order_id} className="grid grid-cols-1 md:grid-cols-5 gap-3 rounded-md border border-slate-200 dark:border-slate-800 p-3 text-sm">
                <div>
                  <div className="text-xs text-slate-500">类型</div>
                  <div className="font-medium">{orderRoleLabel(order.order_role)}</div>
                </div>
                <div>
                  <div className="text-xs text-slate-500">状态</div>
                  <div>{orderStatusLabel(order.status)}</div>
                </div>
                <div>
                  <div className="text-xs text-slate-500">价格</div>
                  <div className="font-mono">{displayValue(order.price || order.trigger_price, '暂无')}</div>
                </div>
                <div>
                  <div className="text-xs text-slate-500">数量</div>
                  <div className="font-mono">{displayValue(order.requested_qty, '暂无')}</div>
                </div>
                <div>
                  <div className="text-xs text-slate-500">交易所订单</div>
                  <div className="font-mono break-all">{displayValue(order.exchange_order_id, '暂无')}</div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-sm text-slate-500">当前没有活跃保护单。</div>
        )}
      </Card>

      {(historicalProtection.length > 0 || orphanProtection.length > 0 || protectionOrders.length > currentScopeProtection.length) && (
        <TechnicalDetails title="历史保护记录">
          <div className="space-y-2">
            {(historicalProtection.length > 0 ? historicalProtection : protectionOrders.filter((order: any) => !currentScopeProtection.includes(order))).map((order: any) => (
              <div key={order.order_id || order.exchange_order_id} className="grid grid-cols-1 md:grid-cols-5 gap-2 rounded border border-slate-200 dark:border-slate-800 p-2">
                <span>{orderRoleLabel(order.order_role)}</span>
                <span>{orderStatusLabel(order.status)}</span>
                <span>{displayValue(order.price || order.trigger_price, '暂无')}</span>
                <span>{displayValue(order.requested_qty, '暂无')}</span>
                <span className="font-mono break-all">{displayValue(order.exchange_order_id, '暂无')}</span>
              </div>
            ))}
            {historicalProtection.length === 0 && protectionOrders.length === currentScopeProtection.length && (
              <div>暂无历史保护记录。</div>
            )}
          </div>
        </TechnicalDetails>
      )}

      <TechnicalDetails title="后续可开放的处理动作">
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
          {deferredActions.map((action) => (
            <DeferredActionSlot key={action} actionName={action === 'retry_protection' ? '重试保护单' : action === 'cancel_protection' ? '取消保护单' : action} reason="当前版本不可操作" />
          ))}
          {deferredActions.length === 0 && (
            <div className="text-sm text-slate-500 col-span-full">当前无保护动作槽位。</div>
          )}
        </div>
      </TechnicalDetails>
    </div>
  );
}
