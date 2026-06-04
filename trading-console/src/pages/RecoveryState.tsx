import { Card, DeferredActionSlot, EnvelopeStatus, PageHeader, PageSummary, TechnicalDetails } from '@/components/ui';
import { asArray, displayValue, useReadModel } from '@/lib/tradingConsoleApi';
import { AlertCircle } from 'lucide-react';
import { pageSummaryFromEnvelope } from '@/lib/ownerViewModel';

export default function RecoveryState() {
  const { envelope, loading, error } = useReadModel<any>('/api/trading-console/recovery-exception-state?include_exchange=true');

  if (loading) return <div className="p-4 text-sm text-slate-500">正在读取当前内容...</div>;

  const pageData = envelope?.data || {};
  const freshnessStatus = envelope?.freshness_status;
  const unavailable = envelope?.unavailable || [];
  const recoveryTasks = asArray(pageData.recovery_tasks);
  const mismatches = asArray(pageData.mismatches);
  const deferredActions = asArray<string>(pageData.deferred_actions);
  const summary = pageSummaryFromEnvelope(envelope, recoveryTasks.length === 0 && mismatches.length === 0 ? '当前没有活动恢复任务。' : '存在异常恢复事项需要查看。');

  const canVerifyMismatches = freshnessStatus !== 'not_live_connected' && freshnessStatus !== 'degraded' && unavailable.length === 0;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <PageHeader title="异常恢复" subtitle="查看是否有异常需要人工处理，以及应该先看哪个页面。" status={envelope?.freshness_status} />

      <PageSummary mood={summary.mood} title={summary.title} description={summary.description} />

      {pageData?.manual_action_required && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/50 p-4 rounded-lg flex gap-3 text-red-800 dark:text-red-400">
          <AlertCircle className="w-5 h-5 shrink-0" />
          <div>
            <h3 className="font-semibold">需要人工介入处理</h3>
            <p className="text-sm opacity-90 mt-1">当前存在阻塞性异常，请优先查看订单台账、保护健康和技术审计。</p>
          </div>
        </div>
      )}

      <EnvelopeStatus envelope={envelope} error={error} />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card className="p-5">
          <h2 className="text-base font-medium mb-4">恢复任务</h2>
          {recoveryTasks.length === 0 ? (
            <div className="text-sm text-slate-500">当前没有处于活动状态的恢复任务。</div>
          ) : (
            <ul className="space-y-3">
              {recoveryTasks.map((task: any, idx: number) => (
                <li key={idx} className="p-3 bg-slate-50 dark:bg-slate-800/50 rounded border border-slate-200 dark:border-slate-800 text-sm">
                  <div className="font-mono text-xs text-slate-500 mb-1">{displayValue(task.task_id || task.id, '暂无')}</div>
                  <div className="font-medium">{displayValue(task.type || task.status, '无法确认')}</div>
                  <div className="text-slate-600 dark:text-slate-400 mt-1">{displayValue(task.description || task.symbol, '暂无说明')}</div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card className="p-5">
          <h2 className="text-base font-medium mb-4">数据不一致</h2>
          {mismatches.length === 0 ? (
            canVerifyMismatches ? (
              <div className="text-sm text-slate-500">当前未发现本地系统与交易所数据不一致的情况。</div>
            ) : (
              <div className="text-sm text-amber-600 dark:text-amber-500 border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/10 p-3 rounded-md">
                当前无法确认是否存在不一致。
              </div>
            )
          ) : (
            <ul className="space-y-3">
              {mismatches.map((mm: any, idx: number) => (
                <li key={idx} className="p-3 bg-amber-50 dark:bg-amber-900/10 border border-amber-200 dark:border-amber-900/30 rounded text-sm text-amber-800 dark:text-amber-400">
                  <div className="font-semibold mb-1">{displayValue(mm.classification || mm.type, '状态不一致')}</div>
                  <div>{displayValue(mm.details || mm.order_id || mm.exchange_order_id, '暂无明细')}</div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card className="p-5">
        <h2 className="text-base font-medium mb-4">建议查看页面</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
          <div className="rounded border border-slate-200 p-3 dark:border-slate-800">订单台账</div>
          <div className="rounded border border-slate-200 p-3 dark:border-slate-800">保护健康</div>
          <div className="rounded border border-slate-200 p-3 dark:border-slate-800">技术审计</div>
        </div>
      </Card>

      <TechnicalDetails title="后续可开放的恢复动作">
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
          {deferredActions.map((action: string, idx: number) => (
            <DeferredActionSlot
              key={idx}
              actionName={
                action === 'retry_protection' ? '重试保护单' :
                action === 'cancel_order' ? '取消订单' :
                action === 'flatten_position' ? '平仓' :
                action === 'resolve_recovery_task' ? '关闭恢复任务' :
                action.replaceAll('_', ' ')
              }
              reason="当前不可操作"
            />
          ))}
          {deferredActions.length === 0 && (
            <div className="text-sm text-slate-500 col-span-full">当前无可展示处理动作。</div>
          )}
        </div>
      </TechnicalDetails>
    </div>
  );
}
