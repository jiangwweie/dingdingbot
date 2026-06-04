import { Card, EnvelopeStatus, PageHeader, PageSummary } from '@/components/ui';
import { useReadModel } from '@/lib/tradingConsoleApi';
import { pageSummaryFromEnvelope } from '@/lib/ownerViewModel';

export default function SignalMarkerFeed() {
  const { envelope, loading, error } = useReadModel<any>('/api/trading-console/signal-marker-feed');

  if (loading) return <div className="p-4 text-sm text-slate-500">正在读取当前内容...</div>;

  const summary = pageSummaryFromEnvelope(envelope, '信号图表为后续功能预留。');

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <PageHeader title="信号图表预留" subtitle="后续用于展示信号、建仓、止盈、止损和恢复事件。" status={envelope?.freshness_status} />

      <PageSummary mood={summary.mood} title="后续功能预留" description="当前不展示完整信号台账，也不接入 TradingView 图表。" />

      <EnvelopeStatus envelope={envelope} error={error} />

      <Card className="p-5">
        <div className="font-medium">后续功能预留</div>
        <p className="mt-2 text-sm text-slate-500">
          信号图表为后续功能预留。后续将用于展示信号、建仓、止盈、止损和恢复事件。
        </p>
      </Card>
    </div>
  );
}
