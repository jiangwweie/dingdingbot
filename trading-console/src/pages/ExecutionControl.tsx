import { Badge, Card, DeferredActionSlot, EnvelopeStatus, NotAvailableValue, PageHeader, PageSummary } from '@/components/ui';
import { asArray, displayValue, useReadModel } from '@/lib/tradingConsoleApi';
import { blockingReasonLabel, gateCodeLabel, gateStatusLabel, pageSummaryFromEnvelope } from '@/lib/ownerViewModel';

export default function ExecutionControl() {
  const { envelope, loading, error } = useReadModel<any>('/api/trading-console/execution-control-state?include_exchange=true');

  if (loading) return <div className="p-4 text-sm text-slate-500">正在读取当前内容...</div>;

  const pageData = envelope?.data || {};
  const hardGate = pageData.hard_gate || {};
  const gates = asArray(hardGate.gates);
  const summary = pageSummaryFromEnvelope(envelope, hardGate.status === 'pass' ? '执行前置检查通过。' : '当前执行链路不可继续。');

  const gateVariant = (status: string) => {
    if (status === 'pass' || status === 'read_only_no_execute_endpoint') return 'normal';
    if (status === 'warning') return 'warning';
    return 'danger';
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <PageHeader title="实盘执行控制" subtitle="查看当前为什么不能执行，以及执行链路卡在哪一步。" status={envelope?.freshness_status} />

      <PageSummary mood={summary.mood} title={summary.title} description={summary.description} />
      <EnvelopeStatus envelope={envelope} error={error} />

      <Card className="p-6">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-lg font-medium">执行状态</h2>
          <Badge variant={gateVariant(String(hardGate.status || 'unknown'))}>
            {gateStatusLabel(hardGate.status)}
          </Badge>
        </div>

        <div className="space-y-4 mb-8">
          <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300">Gate 检查结果</h3>
          <div className="border border-slate-200 dark:border-slate-800 rounded-md divide-y divide-slate-100 dark:divide-slate-800/50">
            {gates.map((gate: any, idx: number) => (
              <div key={idx} className="p-3 flex justify-between items-center hover:bg-slate-50 dark:hover:bg-slate-800/30">
                <div>
                  <div className="font-medium text-sm">{gateCodeLabel(gate.code)}</div>
                  {gate.message && <div className="text-xs text-slate-500 mt-0.5">{blockingReasonLabel(gate.message)}</div>}
                </div>
                <Badge variant={gateVariant(String(gate.status || 'unknown'))}>
                  {gateStatusLabel(gate.status)}
                </Badge>
              </div>
            ))}
            {gates.length === 0 && (
              <div className="p-4 text-center text-sm text-amber-600 dark:text-amber-400">没有 Gate 数据，不能假定可执行。</div>
            )}
          </div>
        </div>

        <div className="space-y-4 mb-8">
          <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300">执行预览</h3>
          <div className="bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-4 rounded-md text-sm">
            {pageData.execution_preview?.status === 'not_available' || !pageData.execution_preview ? (
              <div className="flex items-center gap-2"><span className="text-slate-500">执行预览：</span> <NotAvailableValue /></div>
            ) : (
              <div className="text-sm text-slate-600 dark:text-slate-400">执行预览可用。详情请在技术审计中核对。</div>
            )}
          </div>
        </div>

        <div>
          <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-3">执行动作</h3>
          {pageData.deferred_execute_endpoint ? (
            <DeferredActionSlot actionName="实盘执行" reason="执行动作尚未开放" />
          ) : (
            <div className="text-sm text-slate-500 p-3 bg-slate-50 dark:bg-slate-800/50 rounded text-center">
              当前不可操作。
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
