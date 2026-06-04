import { useMemo, useState } from 'react';
import { Badge, Card, EnvelopeStatus, NotAvailableValue, PageHeader, PageSummary, SourceBadge } from '@/components/ui';
import { asArray, displayValue, formatTimestampMs, isNotAvailable, useReadModel } from '@/lib/tradingConsoleApi';
import { orderClassLabel, orderRoleLabel, orderStatusLabel, ownerSourceLabel, pageSummaryFromEnvelope, sideLabel } from '@/lib/ownerViewModel';

export default function OrderLedger() {
  const { envelope, loading, error } = useReadModel<any>('/api/trading-console/order-ledger?include_exchange=true');

  const pageData = envelope?.data || {};
  const orders = asArray(pageData.orders);
  const [sourceFilter, setSourceFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [roleFilter, setRoleFilter] = useState('all');
  const [riskFilter, setRiskFilter] = useState('all');
  const [symbolFilter, setSymbolFilter] = useState('all');
  const [timeFilter, setTimeFilter] = useState('all');
  const [customFrom, setCustomFrom] = useState('');
  const [customTo, setCustomTo] = useState('');
  const [pageSize, setPageSize] = useState(20);
  const [page, setPage] = useState(1);
  const summary = pageSummaryFromEnvelope(envelope, orders.length === 0 ? '当前没有订单需要核对。' : '订单已聚合，可按来源、状态和风险分类筛选。');

  const getClassificationBadge = (cls: string) => {
    switch (cls) {
      case 'matched': return <Badge variant="normal">{orderClassLabel(cls)}</Badge>;
      case 'pg_unchecked': return <Badge variant="caution">{orderClassLabel(cls)}</Badge>;
      case 'pg_only': return <Badge variant="warning">{orderClassLabel(cls)}</Badge>;
      case 'exchange_only': return <Badge variant="warning">{orderClassLabel(cls)}</Badge>;
      case 'mismatch': return <Badge variant="danger">{orderClassLabel(cls)}</Badge>;
      case 'orphan_protection': return <Badge variant="danger">{orderClassLabel(cls)}</Badge>;
      default: return <Badge variant="caution">{orderClassLabel(cls)}</Badge>;
    }
  };
  const symbols = useMemo(() => Array.from(new Set(orders.map((order: any) => String(order.symbol || 'unknown')))), [orders]);
  const filteredOrders = useMemo(() => {
    const now = Date.now();
    const customFromMs = customFrom ? new Date(customFrom).getTime() : null;
    const customToMs = customTo ? new Date(customTo).getTime() : null;
    return orders.filter((order: any) => {
      const source = String(order.source || 'unknown');
      const status = String(order.status || 'unknown').toLowerCase();
      const role = String(order.order_role || '').toLowerCase();
      const cls = String(order.classification || 'unknown');
      const symbol = String(order.symbol || 'unknown');
      const orderTime = Number(order.updated_at || order.created_at || 0);
      const sourceOk =
        sourceFilter === 'all' ||
        (sourceFilter === 'exchange' && source.includes('exchange')) ||
        (sourceFilter === 'local' && source === 'pg') ||
        (sourceFilter === 'exchange_only' && cls === 'exchange_only') ||
        (sourceFilter === 'pg_only' && cls === 'pg_only');
      const statusOk = statusFilter === 'all' || status === statusFilter;
      const roleOk =
        roleFilter === 'all' ||
        (roleFilter === 'entry' && role.includes('entry')) ||
        (roleFilter === 'tp' && role.includes('tp')) ||
        (roleFilter === 'sl' && role.includes('sl')) ||
        (roleFilter === 'protection' && (role.includes('tp') || role.includes('sl') || role.includes('protect'))) ||
        (roleFilter === 'recovery' && role.includes('recover')) ||
        (roleFilter === 'unknown' && !role);
      const riskOk =
        riskFilter === 'all' ||
        (riskFilter === 'normal' && cls === 'matched') ||
        (riskFilter === 'unchecked' && cls === 'pg_unchecked') ||
        (riskFilter === 'mismatch' && cls === 'mismatch') ||
        (riskFilter === 'orphan' && cls === 'orphan_protection') ||
        (riskFilter === 'unknown' && cls === 'unknown');
      const symbolOk = symbolFilter === 'all' || symbol === symbolFilter;
      const timeOk =
        timeFilter === 'all' ||
        (timeFilter === '1h' && Number.isFinite(orderTime) && orderTime >= now - 60 * 60 * 1000) ||
        (timeFilter === '24h' && Number.isFinite(orderTime) && orderTime >= now - 24 * 60 * 60 * 1000) ||
        (timeFilter === '7d' && Number.isFinite(orderTime) && orderTime >= now - 7 * 24 * 60 * 60 * 1000) ||
        (timeFilter === 'custom' &&
          Number.isFinite(orderTime) &&
          (customFromMs === null || orderTime >= customFromMs) &&
          (customToMs === null || orderTime <= customToMs));
      return sourceOk && statusOk && roleOk && riskOk && symbolOk && timeOk;
    });
  }, [orders, sourceFilter, statusFilter, roleFilter, riskFilter, symbolFilter, timeFilter, customFrom, customTo]);
  const totalPages = Math.max(1, Math.ceil(filteredOrders.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const visibleOrders = filteredOrders.slice((safePage - 1) * pageSize, safePage * pageSize);
  const summaryCards = [
    ['订单总数', orders.length],
    ['交易所订单', orders.filter((item: any) => String(item.source || '').includes('exchange')).length],
    ['本地订单', orders.filter((item: any) => item.source === 'pg').length],
    ['状态不一致', orders.filter((item: any) => item.classification === 'mismatch').length],
    ['孤儿保护单', orders.filter((item: any) => item.classification === 'orphan_protection').length],
    ['未核验订单', orders.filter((item: any) => item.classification === 'pg_unchecked').length],
  ];
  const Select = ({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: Array<[string, string]> }) => (
    <label className="block">
      <span className="block text-xs text-slate-500 mb-1">{label}</span>
      <select value={value} onChange={(event) => { onChange(event.target.value); setPage(1); }} className="w-full rounded-md border border-slate-200 bg-white px-2 py-2 text-sm dark:border-slate-800 dark:bg-slate-950">
        {options.map(([optionValue, optionLabel]) => <option key={optionValue} value={optionValue}>{optionLabel}</option>)}
      </select>
    </label>
  );

  if (loading) return <div className="p-4 text-sm text-slate-500">正在读取当前内容...</div>;

  return (
    <div className="max-w-[1400px] mx-auto space-y-6">
      <PageHeader title="订单台账" subtitle="核对本地系统、交易所订单和保护单状态。" status={envelope?.freshness_status} />

      <PageSummary mood={summary.mood} title={summary.title} description={summary.description} />

      <EnvelopeStatus envelope={envelope} error={error} />

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-2">
        {summaryCards.map(([key, val]) => (
          <Card key={key} className="p-3">
            <div className="text-xs text-slate-500 truncate mb-1">{key}</div>
            <div className="font-mono text-lg">{String(val)}</div>
          </Card>
        ))}
      </div>

      <Card className="p-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7 gap-3">
          <Select label="来源" value={sourceFilter} onChange={setSourceFilter} options={[
            ['all', '全部'], ['exchange', '交易所'], ['local', '本地系统'], ['exchange_only', '仅交易所'], ['pg_only', '仅本地'],
          ]} />
          <Select label="状态" value={statusFilter} onChange={setStatusFilter} options={[
            ['all', '全部'], ['open', 'open'], ['filled', 'filled'], ['partially_filled', 'partially filled'], ['canceled', 'canceled'], ['rejected', 'rejected'], ['unknown', 'unknown'],
          ]} />
          <Select label="角色" value={roleFilter} onChange={setRoleFilter} options={[
            ['all', '全部'], ['entry', '建仓单'], ['tp', '止盈单'], ['sl', '止损单'], ['protection', '保护单'], ['recovery', '恢复单'], ['unknown', '未知'],
          ]} />
          <Select label="风险分类" value={riskFilter} onChange={setRiskFilter} options={[
            ['all', '全部'], ['normal', '正常'], ['unchecked', '未核验'], ['mismatch', '不一致'], ['orphan', '无法归属保护单'], ['unknown', '无法判断'],
          ]} />
          <Select label="标的" value={symbolFilter} onChange={setSymbolFilter} options={[
            ['all', '全部'], ...symbols.map((symbol) => [symbol, symbol] as [string, string]),
          ]} />
          <Select label="时间范围" value={timeFilter} onChange={setTimeFilter} options={[
            ['all', '全部'], ['1h', '最近 1 小时'], ['24h', '最近 24 小时'], ['7d', '最近 7 天'], ['custom', '自定义'],
          ]} />
          <Select label="每页" value={String(pageSize)} onChange={(value) => setPageSize(Number(value))} options={[
            ['20', '20'], ['50', '50'], ['100', '100'],
          ]} />
        </div>
        {timeFilter === 'custom' && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
            <label className="block">
              <span className="block text-xs text-slate-500 mb-1">开始时间</span>
              <input type="datetime-local" value={customFrom} onChange={(event) => { setCustomFrom(event.target.value); setPage(1); }} className="w-full rounded-md border border-slate-200 bg-white px-2 py-2 text-sm dark:border-slate-800 dark:bg-slate-950" />
            </label>
            <label className="block">
              <span className="block text-xs text-slate-500 mb-1">结束时间</span>
              <input type="datetime-local" value={customTo} onChange={(event) => { setCustomTo(event.target.value); setPage(1); }} className="w-full rounded-md border border-slate-200 bg-white px-2 py-2 text-sm dark:border-slate-800 dark:bg-slate-950" />
            </label>
          </div>
        )}
      </Card>

      <Card className="flex flex-col">
        <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 font-medium flex justify-between items-center bg-slate-50/50 dark:bg-slate-900/50">
          <span>订单列表</span>
          <div className="text-xs text-slate-500">显示 {visibleOrders.length} / {filteredOrders.length}</div>
        </div>

        <div className="overflow-x-auto">
          {visibleOrders.length === 0 ? (
            <div className="p-8 text-center text-sm text-slate-500">当前没有可展示订单</div>
          ) : (
            <table className="w-full text-xs text-left whitespace-nowrap">
              <thead className="bg-slate-100 dark:bg-slate-800 text-slate-500 sticky top-0">
                <tr>
                  <th className="px-3 py-2 font-medium">分类</th>
                  <th className="px-3 py-2 font-medium">来源</th>
                  <th className="px-3 py-2 font-medium">标的</th>
                  <th className="px-3 py-2 font-medium">方向</th>
                  <th className="px-3 py-2 font-medium">角色</th>
                  <th className="px-3 py-2 font-medium">状态</th>
                  <th className="px-3 py-2 font-medium">价格</th>
                  <th className="px-3 py-2 font-medium">触发价</th>
                  <th className="px-3 py-2 font-medium">数量</th>
                  <th className="px-3 py-2 font-medium">成交数量</th>
                  <th className="px-3 py-2 font-medium">成交均价</th>
                  <th className="px-3 py-2 font-medium">本地订单 ID</th>
                  <th className="px-3 py-2 font-medium">交易所订单 ID</th>
                  <th className="px-3 py-2 font-medium">时间</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {visibleOrders.map((ord: any, idx: number) => (
                  <tr key={idx} className="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
                    <td className="px-3 py-2 align-top space-y-1">
                      <div>{getClassificationBadge(String(ord.classification || 'unknown'))}</div>
                    </td>
                    <td className="px-3 py-2 align-top">
                      <SourceBadge source={ord.source || 'unknown'} />
                      <div className="text-[11px] text-slate-400 mt-1">{ownerSourceLabel(ord.source)}</div>
                    </td>
                    <td className="px-3 py-2 align-top font-mono font-medium">{displayValue(ord.symbol, '暂无')}</td>
                    <td className="px-3 py-2 align-top">
                      <span className={String(ord.side || ord.direction).toLowerCase() === 'buy' || String(ord.side || ord.direction).toLowerCase() === 'long' ? 'text-emerald-500' : 'text-rose-500'}>
                        {sideLabel(ord.side || ord.direction)}
                      </span>
                    </td>
                    <td className="px-3 py-2 align-top">{orderRoleLabel(ord.order_role)}</td>
                    <td className="px-3 py-2 align-top text-slate-500">{orderStatusLabel(ord.status)}</td>
                    <td className="px-3 py-2 align-top font-mono">{isNotAvailable(ord.price) ? '-' : displayValue(ord.price)}</td>
                    <td className="px-3 py-2 align-top font-mono">{isNotAvailable(ord.trigger_price) ? '-' : displayValue(ord.trigger_price)}</td>
                    <td className="px-3 py-2 align-top font-mono">{displayValue(ord.requested_qty)}</td>
                    <td className="px-3 py-2 align-top font-mono">
                      <span className={Number(ord.filled_qty) > 0 ? 'text-blue-500' : ''}>{displayValue(ord.filled_qty, '0')}</span>
                    </td>
                    <td className="px-3 py-2 align-top font-mono text-slate-500">
                      {isNotAvailable(ord.average_exec_price) ? <NotAvailableValue /> : displayValue(ord.average_exec_price)}
                    </td>
                    <td className="px-3 py-2 align-top font-mono text-[11px] text-slate-500">{displayValue(ord.order_id, '暂无')}</td>
                    <td className="px-3 py-2 align-top font-mono text-[11px] text-slate-500">{displayValue(ord.exchange_order_id, '暂无')}</td>
                    <td className="px-3 py-2 align-top text-[10px] text-slate-400 font-mono">
                      <div>创建：{formatTimestampMs(ord.created_at)}</div>
                      <div>更新：{formatTimestampMs(ord.updated_at)}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div className="flex items-center justify-between border-t border-slate-200 px-4 py-3 text-sm dark:border-slate-800">
          <span className="text-slate-500">第 {safePage} / {totalPages} 页</span>
          <div className="flex gap-2">
            <button type="button" onClick={() => setPage(Math.max(1, safePage - 1))} disabled={safePage <= 1} className="rounded border border-slate-200 px-3 py-1 disabled:cursor-not-allowed disabled:opacity-40 dark:border-slate-800">上一页</button>
            <button type="button" onClick={() => setPage(Math.min(totalPages, safePage + 1))} disabled={safePage >= totalPages} className="rounded border border-slate-200 px-3 py-1 disabled:cursor-not-allowed disabled:opacity-40 dark:border-slate-800">下一页</button>
          </div>
        </div>
      </Card>

    </div>
  );
}
