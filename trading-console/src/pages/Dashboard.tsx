import { Badge, Card, EnvelopeStatus, NotAvailableValue, PageHeader, PageSummary } from '@/components/ui';
import { asArray, countItems, displayValue, useReadModel } from '@/lib/tradingConsoleApi';
import { authorizationStatusLabel, consistencyStatusLabel, pageSummaryFromEnvelope, protectionStatusLabel } from '@/lib/ownerViewModel';

export default function Dashboard() {
  const { envelope, loading, error } = useReadModel<any>('/api/trading-console/dashboard-state?include_exchange=true');

  if (loading) return <div className="p-4 text-sm text-slate-500">正在读取当前内容...</div>;

  const pageData = envelope?.data || {};
  const account = pageData.account_snapshot_summary || {};
  const pgPositions = asArray(pageData.positions?.pg);
  const exchangePositions = asArray(pageData.positions?.exchange);
  const pgOpenOrders = pageData.orders?.pg_open;
  const exchangeOpenOrders = pageData.orders?.exchange_open;
  const openIntents = pageData.orders?.open_intents;
  const authorization = pageData.authorization || {};
  const consistency = pageData.consistency || {};
  const protection = pageData.protection || pageData.protection_health || {};
  const summary = pageSummaryFromEnvelope(
    envelope,
    pgPositions.length + exchangePositions.length === 0
      ? '当前无真实敞口，暂无待处理事项。'
      : '当前存在仓位，请确认保护和订单一致性。'
  );
  const businessItems = [
    consistency.status && consistency.status !== 'clean' && consistency.status !== 'matched'
      ? `订单一致性：${consistencyStatusLabel(consistency.status)}`
      : null,
    authorization.blocking_reason
      ? `执行阻断：${authorizationStatusLabel(authorization.status)}`
      : null,
  ].filter(Boolean);

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <PageHeader
        title="账户风险总览"
        subtitle="判断当前账户是否有需要立刻关注的风险。"
        status={envelope?.freshness_status}
      />

      <PageSummary mood={summary.mood} title={summary.title} description={summary.description}>
        <Badge variant={summary.mood === 'ok' ? 'normal' : summary.mood === 'blocked' ? 'danger' : 'warning'}>
          {summary.mood === 'ok' ? '正常' : summary.mood === 'blocked' ? '存在异常' : '需关注'}
        </Badge>
      </PageSummary>

      <EnvelopeStatus envelope={envelope} error={error} />

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        <Card className="p-4">
          <h3 className="text-sm font-medium text-slate-500 mb-2">账户资金</h3>
          <div className="text-2xl font-mono">
            {account.status === 'available' ? displayValue(account.total_balance) : <NotAvailableValue />}
          </div>
          <div className="text-xs text-slate-500 mt-2">
            可用余额：{account.status === 'available' ? displayValue(account.available_balance) : '暂无数据'}
          </div>
        </Card>

        <Card className="p-4">
          <h3 className="text-sm font-medium text-slate-500 mb-2">当前仓位</h3>
          <div className="flex justify-between items-end">
            <div>
              <div className="text-xs text-slate-400">本地系统</div>
              <div className="font-mono">{pgPositions.length}</div>
            </div>
            <div>
              <div className="text-xs text-slate-400">交易所</div>
              <div className="font-mono">{exchangePositions.length}</div>
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <h3 className="text-sm font-medium text-slate-500 mb-2">当前挂单</h3>
          <div className="flex justify-between items-end">
            <div>
              <div className="text-xs text-slate-400">本地未完成</div>
              <div className="font-mono">{countItems(pgOpenOrders)}</div>
            </div>
            <div>
              <div className="text-xs text-slate-400">交易所挂单</div>
              <div className="font-mono">{countItems(exchangeOpenOrders)}</div>
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <h3 className="text-sm font-medium text-slate-500 mb-2">授权状态</h3>
          <div className="text-sm font-medium">{authorizationStatusLabel(authorization.status)}</div>
          <div className="text-xs text-slate-500 mt-2">
            可行动：{authorization.is_actionable === true ? '是' : '否'} · 意图：{countItems(openIntents)}
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="p-4">
          <h3 className="text-sm font-medium mb-2">订单一致性</h3>
          <div className="text-lg font-semibold">{consistencyStatusLabel(consistency.status)}</div>
          <p className="text-xs text-slate-500 mt-2">不一致或未核验订单请进入订单台账查看。</p>
        </Card>
        <Card className="p-4">
          <h3 className="text-sm font-medium mb-2">保护状态</h3>
          <div className="text-lg font-semibold">{protectionStatusLabel(protection.status)}</div>
          <p className="text-xs text-slate-500 mt-2">保护是否完整以保护健康页为准。</p>
        </Card>
        <Card className="p-4">
          <h3 className="text-sm font-medium mb-2">建议查看</h3>
          <div className="space-y-1 text-sm">
            <div>订单台账：核对挂单和保护单</div>
            <div>实盘执行控制：查看阻断链路</div>
          </div>
        </Card>
      </div>

      <Card className="p-4">
        <h3 className="text-sm font-medium mb-3">需要关注的事项</h3>
        {businessItems.length === 0 ? (
          <p className="text-sm text-slate-500">当前无业务事项需要立即处理。</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {businessItems.map((item, index) => (
              <li key={index} className="flex items-start gap-2">
                <span className="mt-2 h-1.5 w-1.5 rounded-full bg-amber-500" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
