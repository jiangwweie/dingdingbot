import { Badge, Card, EnvelopeStatus, NotAvailableValue, PageHeader, PageSummary, SourceBadge } from '@/components/ui';
import { asArray, displayValue, isNotAvailable, useReadModel } from '@/lib/tradingConsoleApi';
import { formatMoney, pageSummaryFromEnvelope, protectionStatusLabel } from '@/lib/ownerViewModel';

export default function AccountRisk() {
  const { envelope, loading, error } = useReadModel<any>('/api/trading-console/account-risk?include_exchange=true');

  if (loading) return <div className="p-4 text-sm text-slate-500">正在读取当前内容...</div>;

  const pageData = envelope?.data || {};
  const account = pageData.account || {};
  const positions = asArray(pageData.positions);
  const openOrders = asArray(pageData.open_orders);
  const riskState = String(pageData.risk_state || 'unknown');
  const riskVariant = riskState === 'healthy' ? 'normal' : riskState === 'unknown' ? 'warning' : 'danger';
  const summary = pageSummaryFromEnvelope(
    envelope,
    positions.length === 0 ? '当前无仓位敞口。' : '当前存在仓位，请确认保护状态。'
  );
  const protectionOwnership = pageData.protection_ownership || {};
  const protectionStatus = String(protectionOwnership.status || 'unknown');
  const marginLabel = (key: string) => {
    const labels: Record<string, string> = {
      equity: '账户权益',
      total_balance: '账户权益',
      available_balance: '可用余额',
      available_margin: '可用保证金',
      margin_ratio: '保证金比例',
      unrealized_pnl: '未实现盈亏',
      liquidation_risk: '强平风险',
    };
    return labels[key] || key.replaceAll('_', ' ');
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <PageHeader
        title="账户总览"
        subtitle="查看资金、仓位、挂单和仓位保护状态。"
        status={envelope?.freshness_status}
      />

      <PageSummary mood={summary.mood} title={summary.title} description={summary.description} />

      <EnvelopeStatus envelope={envelope} error={error} />

      <Card className="p-4 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <div className="text-sm text-slate-500">账户状态</div>
          <div className="mt-1"><Badge variant={riskVariant}>{riskState === 'healthy' ? '正常' : riskState === 'degraded' ? '需关注' : '无法确认'}</Badge></div>
          {riskState === 'unknown' && (
            <div className="text-xs text-amber-600 dark:text-amber-400 mt-2">不可假定账户健康。</div>
          )}
        </div>
        <div className="text-right">
          <div className="text-sm text-slate-500">账户权益</div>
          <div className="font-mono text-lg">{isNotAvailable(account.total_balance) ? <NotAvailableValue /> : formatMoney(account.total_balance)}</div>
          <div className="text-xs text-slate-500 mt-1">可用余额：{formatMoney(account.available_balance)}</div>
        </div>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card className="p-4">
          <h2 className="text-base font-medium mb-3">资金与风险摘要</h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
            {Object.entries(pageData.margin_facts || {}).map(([key, value]) => (
              <div key={key} className="bg-slate-50 dark:bg-slate-800/40 rounded p-3">
                <div className="text-xs text-slate-500 mb-1">{marginLabel(key)}</div>
                <div className="font-mono">{displayValue(value)}</div>
              </div>
            ))}
          </div>
        </Card>
        <Card className="p-4">
          <h2 className="text-base font-medium mb-3">仓位保护状态</h2>
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-lg font-semibold">{protectionStatusLabel(protectionStatus)}</div>
              <p className="text-sm text-slate-500 mt-1">保护单覆盖情况以交易所和本地记录聚合判断。</p>
            </div>
            <Badge variant={protectionStatus === 'protected' ? 'normal' : protectionStatus === 'unknown' ? 'warning' : 'danger'}>
              {protectionStatusLabel(protectionStatus)}
            </Badge>
          </div>
          <div className="grid grid-cols-2 gap-3 mt-4 text-sm">
            <div className="rounded bg-slate-50 dark:bg-slate-800/40 p-3">
              <div className="text-xs text-slate-500">止盈单</div>
              <div className="font-mono">{displayValue(protectionOwnership.tp_count, '0')}</div>
            </div>
            <div className="rounded bg-slate-50 dark:bg-slate-800/40 p-3">
              <div className="text-xs text-slate-500">止损单</div>
              <div className="font-mono">{displayValue(protectionOwnership.sl_count, '0')}</div>
            </div>
          </div>
        </Card>
      </div>

      <Card className="overflow-x-auto">
        <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 font-medium">仓位列表</div>
        {positions.length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-500">当前没有可展示仓位</div>
        ) : (
          <table className="w-full text-sm text-left">
            <thead className="bg-slate-50 dark:bg-slate-800/50 text-slate-500">
              <tr>
                <th className="px-4 py-2 font-medium">来源</th>
                <th className="px-4 py-2 font-medium">标的</th>
                <th className="px-4 py-2 font-medium">方向</th>
                <th className="px-4 py-2 font-medium">数量</th>
                <th className="px-4 py-2 font-medium">标记价格</th>
                <th className="px-4 py-2 font-medium">未实现盈亏</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800/50">
              {positions.map((pos: any, idx: number) => (
                <tr key={idx} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/20">
                  <td className="px-4 py-2"><SourceBadge source={pos.source || 'unknown'} /></td>
                  <td className="px-4 py-2 font-mono">{displayValue(pos.symbol, '暂无')}</td>
                  <td className="px-4 py-2">{displayValue(pos.side, '无法确认')}</td>
                  <td className="px-4 py-2 font-mono">{displayValue(pos.quantity)}</td>
                  <td className="px-4 py-2 font-mono">{isNotAvailable(pos.mark_price) ? <NotAvailableValue /> : displayValue(pos.mark_price)}</td>
                  <td className="px-4 py-2 font-mono">
                    {isNotAvailable(pos.unrealized_pnl) ? <NotAvailableValue /> : (
                      <span className={Number(pos.unrealized_pnl) >= 0 ? 'text-emerald-500' : 'text-rose-500'}>
                        {pos.unrealized_pnl}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card className="p-4">
        <h2 className="text-base font-medium mb-2">挂单摘要</h2>
        <div className="text-sm text-slate-500">当前聚合挂单：{openOrders.length}</div>
      </Card>
    </div>
  );
}
