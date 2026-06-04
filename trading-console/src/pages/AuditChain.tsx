import { Badge, Card, EnvelopeStatus, PageHeader, TechnicalDetails } from '@/components/ui';
import { asArray, displayValue, useReadModel } from '@/lib/tradingConsoleApi';
import { Search } from 'lucide-react';

export default function AuditChain() {
  const { envelope, loading, error } = useReadModel<any>('/api/trading-console/audit-chain');

  if (loading) return <div className="p-4 text-sm text-slate-500">正在读取当前内容...</div>;

  const pageData = envelope?.data || {};

  const JsonBlock = ({ title, data }: { title: string, data: any }) => {
    const isEmpty =
      !data ||
      (Array.isArray(data) && data.length === 0) ||
      (!Array.isArray(data) && typeof data === 'object' && Object.keys(data).length === 0);
    return (
      <Card className="p-4">
        <h3 className="text-sm font-medium mb-3">{title}</h3>
        <div className="text-sm text-slate-500">{isEmpty ? '当前没有匹配数据' : `匹配记录：${Array.isArray(data) ? data.length : 1}`}</div>
        {!isEmpty && (
          <TechnicalDetails title="Raw / Debug">
            <button
              type="button"
              onClick={() => navigator.clipboard?.writeText(JSON.stringify(data, null, 2))}
              className="mb-2 rounded border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-slate-100 dark:border-slate-800 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              复制
            </button>
            <pre className="overflow-auto font-mono">{JSON.stringify(data, null, 2)}</pre>
          </TechnicalDetails>
        )}
      </Card>
    );
  };

  return (
    <div className="max-w-[1400px] mx-auto space-y-6">
      <PageHeader title="技术审计" subtitle="排查授权、意图、订单、仓位和复盘之间的链路完整性。" status={envelope?.freshness_status} />

      <Card className="p-4 bg-slate-50/50 dark:bg-slate-900/50">
        <form className="flex flex-wrap gap-3 items-end" onSubmit={e => e.preventDefault()}>
          <div className="flex-1 min-w-[200px]">
             <label className="block text-xs font-medium text-slate-500 mb-1">Authorization ID</label>
             <input type="text" placeholder="e.g. auth-..." className="w-full text-sm p-2 bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded outline-none focus:border-blue-500" disabled />
          </div>
          <div className="flex-1 min-w-[200px]">
             <label className="block text-xs font-medium text-slate-500 mb-1">Intent ID / Order ID / Exchange ID</label>
             <input type="text" placeholder="Trace ID..." className="w-full text-sm p-2 bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded outline-none focus:border-blue-500" disabled />
          </div>
          <div className="w-[120px]">
             <label className="block text-xs font-medium text-slate-500 mb-1">Symbol</label>
             <input type="text" placeholder="BNB/USDT:USDT" className="w-full text-sm p-2 bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded outline-none focus:border-blue-500" disabled />
          </div>
          <button type="button" disabled className="bg-blue-600/50 text-white p-2 rounded flex items-center justify-center cursor-not-allowed">
            <Search className="w-5 h-5" />
          </button>
        </form>
        <div className="mt-2 text-xs text-slate-400">当前展示后端返回的只读链路。</div>
      </Card>

      <EnvelopeStatus envelope={envelope} error={error} />

      <Card className="p-4">
        <h2 className="text-base font-medium mb-3">链路摘要</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">链路完整性：{pageData.chain_complete === true ? '完整' : '无法确认'}</div>
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">失败步骤：{displayValue(pageData.failed_step, '暂无')}</div>
          <div className="rounded bg-slate-50 p-3 dark:bg-slate-800/40">审计事件：{asArray(pageData.audit_events).length}</div>
        </div>
      </Card>

      <TechnicalDetails title="Raw / Debug：安全与脱敏策略">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold mb-1">原始数据策略</h2>
            <p className="text-xs text-slate-500">原始 payload 默认隐藏或脱敏。</p>
          </div>
          <div>
            {pageData.raw_payload_policy === 'masked_or_omitted' ? (
              <Badge variant="normal">Masked or Omitted</Badge>
            ) : (
              <Badge variant="danger">{displayValue(pageData.raw_payload_policy, 'unknown')}</Badge>
            )}
          </div>
        </div>
      </TechnicalDetails>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <JsonBlock title="Authorization (授权状态)" data={pageData.authorization} />
        <JsonBlock title={`Intents (执行意图) ${asArray(pageData.intents).length}`} data={pageData.intents} />
        <JsonBlock title={`Orders (订单) ${asArray(pageData.orders).length}`} data={pageData.orders} />
        <JsonBlock title={`Positions (仓位) ${asArray(pageData.positions).length}`} data={pageData.positions} />
        <JsonBlock title={`Reviews (复盘) ${asArray(pageData.reviews).length}`} data={pageData.reviews} />
        <JsonBlock title={`Audit Events (审计事件) ${asArray(pageData.audit_events).length}`} data={pageData.audit_events} />
      </div>

      <TechnicalDetails title="Raw / Debug：汇总响应">
        <button
          type="button"
          onClick={() => navigator.clipboard?.writeText(JSON.stringify(envelope, null, 2))}
          className="mb-2 rounded border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-slate-100 dark:border-slate-800 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          复制
        </button>
        <pre className="overflow-auto font-mono">{JSON.stringify(envelope, null, 2)}</pre>
      </TechnicalDetails>
    </div>
  );
}
