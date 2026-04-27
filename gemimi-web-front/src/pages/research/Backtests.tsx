import React, { useEffect, useState, useMemo } from 'react';
import { getBacktests } from '@/src/services/api';
import { BacktestRecord } from '@/src/types';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Card, CardContent } from '@/src/components/ui/Card';
import { Badge } from '@/src/components/ui/Badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/src/components/ui/Table';
import { Loader2, AlertCircle } from 'lucide-react';
import { fmtDash, fmtDateTime, fmtPct, fmtDec, fmtInt } from '@/src/lib/console-utils';
import { useTableSort, compareTimestamp, comparePrimitive, FilterSelect, EmptyFilterRow, emptyDataCard } from '@/src/lib/table-utils';

const statusVariant = (s: string): 'success' | 'warning' | 'danger' | 'info' | 'default' => {
  switch (s) {
    case 'COMPLETED': return 'success';
    case 'RUNNING': return 'info';
    case 'FAILED': return 'danger';
    case 'PENDING': return 'warning';
    default: return 'default';
  }
};

const STATUS_OPTIONS = [
  { value: 'ALL', label: '全部状态' },
  { value: 'COMPLETED', label: 'COMPLETED' },
  { value: 'RUNNING', label: 'RUNNING' },
  { value: 'FAILED', label: 'FAILED' },
  { value: 'PENDING', label: 'PENDING' },
];

export default function Backtests() {
  const { refreshCount } = useRefreshContext();
  const [data, setData] = useState<BacktestRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [statusFilter, setStatusFilter] = useState('ALL');
  const sort = useTableSort<BacktestRecord>('start_date', 'desc');

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(false);
    getBacktests().then(res => {
      if (active) { setData(res); setLoading(false); }
    }).catch(() => {
      if (active) { setError(true); setLoading(false); }
    });
    return () => { active = false; };
  }, [refreshCount]);

  const filtered = useMemo(() => {
    let rows = data;
    if (statusFilter !== 'ALL') rows = rows.filter(bt => bt.status === statusFilter);
    return [...rows].sort((a, b) => {
      switch (sort.sortField) {
        case 'start_date': return compareTimestamp(a.start_date, b.start_date, sort.sortOrder);
        case 'candidate_ref': return comparePrimitive(a.candidate_ref, b.candidate_ref, sort.sortOrder);
        case 'symbol': return comparePrimitive(a.symbol, b.symbol, sort.sortOrder);
        case 'status': return comparePrimitive(a.status, b.status, sort.sortOrder);
        case 'total_return': return comparePrimitive(a.metrics?.total_return, b.metrics?.total_return, sort.sortOrder);
        case 'sharpe': return comparePrimitive(a.metrics?.sharpe, b.metrics?.sharpe, sort.sortOrder);
        case 'max_drawdown': return comparePrimitive(a.metrics?.max_drawdown, b.metrics?.max_drawdown, sort.sortOrder);
        case 'trades': return comparePrimitive(a.metrics?.trades, b.metrics?.trades, sort.sortOrder);
        default: return 0;
      }
    });
  }, [data, statusFilter, sort.sortField, sort.sortOrder]);

  if (loading && data.length === 0) return <div className="flex h-32 items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-zinc-500" /></div>;
  if (error && data.length === 0) return <div className="flex h-32 items-center justify-center text-rose-400 gap-2"><AlertCircle className="w-5 h-5" /><span>回测数据加载失败</span></div>;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-end">
        <div>
          <h2 className="text-xl font-bold tracking-tight">回测报告</h2>
          <p className="text-xs text-zinc-500 mt-1">历史回测执行记录与指标。</p>
        </div>
      </div>

      {error && data.length > 0 && (
        <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/50 text-amber-700 dark:text-amber-400 px-4 py-2 rounded text-sm">
          部分数据刷新失败，显示缓存内容
        </div>
      )}

      {data.length === 0 ? (
        <Card><CardContent>{emptyDataCard('暂无回测记录')}</CardContent></Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="flex items-center gap-3 px-4 py-2 border-b border-zinc-200 dark:border-zinc-800">
              <span className="text-xs text-zinc-500">状态</span>
              <FilterSelect value={statusFilter} onChange={setStatusFilter} options={STATUS_OPTIONS} />
            </div>
            <Table>
              <TableHeader>
                <TableRow className="bg-zinc-50 dark:bg-zinc-900/50">
                  <TableHead>ID</TableHead>
                  <TableHead className="cursor-pointer select-none" onClick={() => sort.toggleSort('candidate_ref')}>候选{sort.sortIndicator('candidate_ref')}</TableHead>
                  <TableHead className="cursor-pointer select-none" onClick={() => sort.toggleSort('symbol')}>交易对{sort.sortIndicator('symbol')}</TableHead>
                  <TableHead>周期</TableHead>
                  <TableHead className="cursor-pointer select-none" onClick={() => sort.toggleSort('start_date')}>时间范围{sort.sortIndicator('start_date')}</TableHead>
                  <TableHead className="cursor-pointer select-none" onClick={() => sort.toggleSort('status')}>状态{sort.sortIndicator('status')}</TableHead>
                  <TableHead className="cursor-pointer select-none text-right" onClick={() => sort.toggleSort('total_return')}>Return{sort.sortIndicator('total_return')}</TableHead>
                  <TableHead className="cursor-pointer select-none text-right" onClick={() => sort.toggleSort('sharpe')}>Sharpe{sort.sortIndicator('sharpe')}</TableHead>
                  <TableHead className="cursor-pointer select-none text-right" onClick={() => sort.toggleSort('max_drawdown')}>Drawdown{sort.sortIndicator('max_drawdown')}</TableHead>
                  <TableHead className="text-right">Win Rate</TableHead>
                  <TableHead className="cursor-pointer select-none text-right" onClick={() => sort.toggleSort('trades')}>Trades{sort.sortIndicator('trades')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.length === 0 ? (
                  <EmptyFilterRow colSpan={11} />
                ) : filtered.map(bt => (
                  <TableRow key={bt.id}>
                    <TableCell className="font-mono text-xs">{fmtDash(bt.id)}</TableCell>
                    <TableCell className="font-mono text-xs text-blue-400">{fmtDash(bt.candidate_ref)}</TableCell>
                    <TableCell className="font-mono">{fmtDash(bt.symbol)}</TableCell>
                    <TableCell className="font-mono">{fmtDash(bt.timeframe)}</TableCell>
                    <TableCell className="text-xs text-zinc-500">{fmtDateTime(bt.start_date)} ~ {fmtDateTime(bt.end_date)}</TableCell>
                    <TableCell><Badge variant={statusVariant(bt.status)}>{fmtDash(bt.status)}</Badge></TableCell>
                    <TableCell className="font-mono text-right">{fmtPct(bt.metrics?.total_return)}</TableCell>
                    <TableCell className="font-mono text-right">{fmtDec(bt.metrics?.sharpe)}</TableCell>
                    <TableCell className="font-mono text-right">{fmtPct(bt.metrics?.max_drawdown)}</TableCell>
                    <TableCell className="font-mono text-right">{fmtPct(bt.metrics?.win_rate)}</TableCell>
                    <TableCell className="font-mono text-right">{fmtInt(bt.metrics?.trades)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}