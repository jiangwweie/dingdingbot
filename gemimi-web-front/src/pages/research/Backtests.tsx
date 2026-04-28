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
import { ColumnVisibility, ColumnDef } from '@/src/components/ui/ColumnVisibility';

const BT_COLUMNS: ColumnDef[] = [
  { key: 'id', label: 'ID', defaultVisible: false },
  { key: 'candidate', label: '候选', defaultVisible: true },
  { key: 'symbol', label: '交易对', defaultVisible: true },
  { key: 'timeframe', label: '周期', defaultVisible: true },
  { key: 'window', label: '时间范围', defaultVisible: true },
  { key: 'status', label: '状态', defaultVisible: true },
  { key: 'return', label: '收益', defaultVisible: true },
  { key: 'sharpe', label: '夏普', defaultVisible: true },
  { key: 'drawdown', label: '回撤', defaultVisible: true },
  { key: 'win_rate', label: '胜率', defaultVisible: true },
  { key: 'trades', label: '交易数', defaultVisible: false },
];

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
  const [visibleColumns, setVisibleColumns] = useState<Set<string>>(new Set());
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

  if (loading && data.length === 0) return <div className="flex h-32 items-center justify-center"><Loader2 className="w-6 h-6 animate-spin text-zinc-500" /></div>;
  if (error && data.length === 0) return <div className="flex h-32 items-center justify-center text-rose-400 gap-2"><AlertCircle className="w-4 h-4" /><span className="text-sm font-medium">回测数据加载失败</span></div>;

  return (
    <div className="space-y-4 max-w-[1600px] mx-auto">
      <div className="flex items-center justify-between bg-zinc-50 dark:bg-zinc-900/40 p-2.5 rounded-sm border border-zinc-200 dark:border-zinc-800">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-widest text-zinc-700 dark:text-zinc-300">回测报告 (Legacy Backtests)</h2>
        </div>
      </div>

      {error && data.length > 0 && (
        <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/50 text-amber-700 dark:text-amber-400 px-3 py-1.5 rounded-sm text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4" />
          <span>部分数据刷新失败，显示缓存内容</span>
        </div>
      )}

      {data.length === 0 ? (
        <Card><CardContent>{emptyDataCard('暂无回测记录')}</CardContent></Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="flex flex-wrap items-center gap-2 px-3 py-2 border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/50">
              <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">状态 (STATUS)</span>
              <div className="flex items-center gap-2 ml-2">
                <FilterSelect value={statusFilter} onChange={setStatusFilter} options={STATUS_OPTIONS} />
              </div>
              <div className="ml-auto flex items-center gap-3">
                <span className="text-[10px] font-mono tracking-widest text-zinc-400 uppercase">{filtered.length} MATCHES</span>
                <ColumnVisibility columns={BT_COLUMNS} storageKey="research_backtests_cols_v1" onChange={setVisibleColumns} />
              </div>
            </div>
            <Table>
              <TableHeader>
                <TableRow className="bg-zinc-100/50 dark:bg-zinc-900/80">
                  {visibleColumns.has('id') && <TableHead className="w-24 pl-4">ID</TableHead>}
                  {visibleColumns.has('candidate') && <TableHead className="cursor-pointer select-none" onClick={() => sort.toggleSort('candidate_ref')}>候选 (CANDIDATE){sort.sortIndicator('candidate_ref')}</TableHead>}
                  {visibleColumns.has('symbol') && <TableHead className="cursor-pointer select-none" onClick={() => sort.toggleSort('symbol')}>交易对{sort.sortIndicator('symbol')}</TableHead>}
                  {visibleColumns.has('timeframe') && <TableHead>周期</TableHead>}
                  {visibleColumns.has('window') && <TableHead className="cursor-pointer select-none" onClick={() => sort.toggleSort('start_date')}>时间范围 (WINDOW){sort.sortIndicator('start_date')}</TableHead>}
                  {visibleColumns.has('status') && <TableHead className="cursor-pointer select-none" onClick={() => sort.toggleSort('status')}>状态 (STATUS){sort.sortIndicator('status')}</TableHead>}
                  {visibleColumns.has('return') && <TableHead className="cursor-pointer select-none text-right" onClick={() => sort.toggleSort('total_return')}>收益 (Return){sort.sortIndicator('total_return')}</TableHead>}
                  {visibleColumns.has('sharpe') && <TableHead className="cursor-pointer select-none text-right" onClick={() => sort.toggleSort('sharpe')}>夏普 (Sharpe){sort.sortIndicator('sharpe')}</TableHead>}
                  {visibleColumns.has('drawdown') && <TableHead className="cursor-pointer select-none text-right" onClick={() => sort.toggleSort('max_drawdown')}>回撤 (Drawdown){sort.sortIndicator('max_drawdown')}</TableHead>}
                  {visibleColumns.has('win_rate') && <TableHead className="text-right">胜率 (Win Rate)</TableHead>}
                  {visibleColumns.has('trades') && <TableHead className="cursor-pointer select-none text-right pr-4" onClick={() => sort.toggleSort('trades')}>交易数 (Trades){sort.sortIndicator('trades')}</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.length === 0 ? (
                  <EmptyFilterRow colSpan={visibleColumns.size} />
                ) : filtered.map(bt => (
                  <TableRow key={bt.id}>
                    {visibleColumns.has('id') && <TableCell className="font-mono text-xs text-zinc-500 pl-4">{fmtDash(bt.id.slice(0,8))}...</TableCell>}
                    {visibleColumns.has('candidate') && <TableCell className="font-mono text-[11px] font-bold text-blue-500 dark:text-blue-400">{fmtDash(bt.candidate_ref)}</TableCell>}
                    {visibleColumns.has('symbol') && <TableCell className="font-mono font-bold text-zinc-800 dark:text-zinc-200">{fmtDash(bt.symbol)}</TableCell>}
                    {visibleColumns.has('timeframe') && <TableCell className="font-mono text-[10px] text-zinc-500 tracking-widest">{fmtDash(bt.timeframe)}</TableCell>}
                    {visibleColumns.has('window') && <TableCell className="text-[10px] text-zinc-500 font-mono tracking-tighter leading-snug">{fmtDateTime(bt.start_date)}<br />{fmtDateTime(bt.end_date)}</TableCell>}
                    {visibleColumns.has('status') && <TableCell><Badge variant={statusVariant(bt.status)} className="text-[9px] px-1.5 py-0.5">{fmtDash(bt.status)}</Badge></TableCell>}
                    {visibleColumns.has('return') && <TableCell className="font-mono text-right font-bold tracking-tight">{fmtPct(bt.metrics?.total_return)}</TableCell>}
                    {visibleColumns.has('sharpe') && <TableCell className="font-mono text-right tabular-nums">{fmtDec(bt.metrics?.sharpe)}</TableCell>}
                    {visibleColumns.has('drawdown') && <TableCell className="font-mono text-right text-rose-600 dark:text-rose-400 tabular-nums">{fmtPct(bt.metrics?.max_drawdown)}</TableCell>}
                    {visibleColumns.has('win_rate') && <TableCell className="font-mono text-right tabular-nums">{fmtPct(bt.metrics?.win_rate)}</TableCell>}
                    {visibleColumns.has('trades') && <TableCell className="font-mono text-right tabular-nums pr-4">{fmtInt(bt.metrics?.trades)}</TableCell>}
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