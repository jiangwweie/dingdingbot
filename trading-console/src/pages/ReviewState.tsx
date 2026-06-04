import { Card, EnvelopeStatus, PageHeader, PageSummary } from '@/components/ui';
import { asArray, displayValue, useReadModel } from '@/lib/tradingConsoleApi';
import { blockingReasonLabel, pageSummaryFromEnvelope } from '@/lib/ownerViewModel';

export default function ReviewState() {
  const { envelope, loading, error } = useReadModel<any>('/api/trading-console/review-state');

  if (loading) return <div className="p-4 text-sm text-slate-500">正在读取当前内容...</div>;

  const pageData = envelope?.data || {};
  const reviews = asArray(pageData.reviews);
  const filledOrderFacts = asArray(pageData.filled_order_facts);
  const positions = asArray(pageData.positions);
  const summary = pageSummaryFromEnvelope(envelope, reviews.length === 0 ? '当前没有复盘记录。' : '已有复盘记录可查看。');

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <PageHeader title="实盘复盘" subtitle="查看实盘行动结果、成交、保护和系统链路问题。" status={envelope?.freshness_status} />

      <PageSummary mood={summary.mood} title={summary.title} description={summary.description} />
      <EnvelopeStatus envelope={envelope} error={error} />

      <Card className="p-4">
        <h2 className="text-base font-medium mb-3">成本信息</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">手续费：暂无</div>
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">资金费率：暂无</div>
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">滑点：暂无</div>
        </div>
      </Card>

      <Card className="p-6">
        <h2 className="text-lg font-medium mb-4">复盘记录</h2>
        {reviews.length === 0 ? (
          <div className="text-center text-sm text-slate-500 py-8 border border-dashed border-slate-200 dark:border-slate-800 rounded">当前没有复盘记录</div>
        ) : (
          <div className="space-y-4">
            {reviews.map((review: any, i: number) => (
              <div key={i} className="border border-slate-200 dark:border-slate-800 p-4 rounded-md">
                <div className="text-sm font-semibold mb-2">结果：{displayValue(review.result || review.status, '未完成')}</div>
                <div className="text-sm text-slate-600 dark:text-slate-400">原因：{blockingReasonLabel(review.reason || review.blocker || review.summary || '暂无说明')}</div>
                <div className="text-sm text-slate-600 dark:text-slate-400 mt-1">影响：{displayValue(review.impact, '未确认完整执行结果')}</div>
                <div className="text-sm text-slate-600 dark:text-slate-400 mt-1">建议：查看技术审计</div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card className="p-4">
          <h2 className="text-base font-medium mb-4">已成交订单</h2>
          {filledOrderFacts.length === 0 ? (
            <div className="text-sm text-slate-500 text-center py-6 border border-dashed border-slate-200 dark:border-slate-800 rounded-lg">无相关成交</div>
          ) : (
            <div className="text-sm text-slate-500">已聚合成交订单：{filledOrderFacts.length}</div>
          )}
        </Card>

        <Card className="p-4">
          <h2 className="text-base font-medium mb-4">关联仓位</h2>
          {positions.length === 0 ? (
            <div className="text-sm text-slate-500 text-center py-6 border border-dashed border-slate-200 dark:border-slate-800 rounded-lg">无关联仓位</div>
          ) : (
            <div className="text-sm text-slate-500">已关联仓位：{positions.length}</div>
          )}
        </Card>
      </div>
    </div>
  );
}
