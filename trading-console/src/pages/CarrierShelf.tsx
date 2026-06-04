import { Badge, Card, EnvelopeStatus, PageHeader, PageSummary } from '@/components/ui';
import { asArray, displayValue, useReadModel } from '@/lib/tradingConsoleApi';
import { blockingReasonLabel, carrierStatusLabel, pageSummaryFromEnvelope, sideLabel } from '@/lib/ownerViewModel';

export default function CarrierShelf() {
  const { envelope, loading, error } = useReadModel<any>('/api/trading-console/carrier-availability?include_exchange=true');

  if (loading) return <div className="p-4 text-sm text-slate-500">正在读取当前内容...</div>;

  const pageData = envelope?.data || {};
  const carriers = asArray(pageData.carriers);
  const summary = pageSummaryFromEnvelope(envelope, carriers.length === 0 ? '当前没有可展示行动对象。' : '当前仅展示 v1 配置的 BNB 行动。');

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <PageHeader title="行动对象" subtitle="查看当前有哪些可关注的实盘行动对象。" status={envelope?.freshness_status} />

      <PageSummary mood={summary.mood} title={summary.title} description={summary.description} />

      <EnvelopeStatus envelope={envelope} error={error} />

      <div className="grid gap-4">
        {carriers.map((carrier: any, idx: number) => (
          <Card key={idx} className="p-6 border-slate-200 dark:border-slate-700">
            <div className="flex justify-between items-start mb-4">
              <div>
                <h3 className="text-lg font-semibold">BNB 多头行动</h3>
                <div className="text-slate-500 text-sm mt-1">标的：{displayValue(carrier.symbol, '暂无')}</div>
                <div className="text-slate-500 text-xs mt-1">方向：{sideLabel(carrier.side)}</div>
              </div>
              <Badge variant={carrier.status === 'blocked' ? 'danger' : carrier.status === 'read_only_available' ? 'normal' : 'warning'}>
                {carrierStatusLabel(carrier.status)}
              </Badge>
            </div>

            {asArray<string>(carrier.blocked_reasons).length > 0 && (
              <div className="bg-red-50 dark:bg-red-900/10 border border-red-100 dark:border-red-900/30 rounded-md p-3 mb-4">
                <div className="text-sm font-semibold text-red-800 dark:text-red-400 mb-1">暂不可用原因</div>
                <ul className="list-disc list-inside text-sm text-red-700 dark:text-red-300">
                  {asArray<string>(carrier.blocked_reasons).map((reason, i) => <li key={i}>{blockingReasonLabel(reason)}</li>)}
                </ul>
              </div>
            )}

            <div className="text-sm text-slate-500">最近结果：暂无</div>
          </Card>
        ))}
        {carriers.length === 0 && (
          <div className="p-8 text-center text-sm text-slate-500 border rounded-lg border-dashed border-slate-300 dark:border-slate-700">
            当前无可展示行动对象
          </div>
        )}
      </div>
    </div>
  );
}
