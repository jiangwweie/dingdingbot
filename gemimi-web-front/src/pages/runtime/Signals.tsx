import React, { useEffect, useState, useMemo } from 'react';
import { getRuntimeSignals } from '@/src/services/api';
import { Signal } from '@/src/types';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Card, CardContent } from '@/src/components/ui/Card';
import { Badge } from '@/src/components/ui/Badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/src/components/ui/Table';
import { Loader2, AlertCircle } from 'lucide-react';
import { fmtDash, fmtDateTime, fmtDec } from '@/src/lib/console-utils';
import { useTableSort, compareTimestamp, comparePrimitive, FilterSelect, EmptyFilterRow, emptyDataCard } from '@/src/lib/table-utils';

const DIRECTION_OPTIONS = [
  { value: 'ALL', label: '全部方向' },
  { value: 'LONG', label: 'LONG' },
  { value: 'SHORT', label: 'SHORT' },
];

export default function Signals() {
  const { refreshCount } = useRefreshContext();
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [directionFilter, setDirectionFilter] = useState('ALL');
  const sort = useTableSort<Signal>('created_at', 'desc');

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(false);
    getRuntimeSignals().then(res => {
      if (active) { setSignals(res); setLoading(false); }
    }).catch(() => {
      if (active) { setError(true); setLoading(false); }
    });
    return () => { active = false; };
  }, [refreshCount]);

  const filtered = useMemo(() => {
    let rows = signals;
    if (directionFilter !== 'ALL') rows = rows.filter(s => s.direction === directionFilter);
    return [...rows].sort((a, b) => {
      switch (sort.sortField) {
        case 'created_at': return compareTimestamp(a.created_at, b.created_at, sort.sortOrder);
        case 'symbol': return comparePrimitive(a.symbol, b.symbol, sort.sortOrder);
        case 'direction': return comparePrimitive(a.direction, b.direction, sort.sortOrder);
        case 'score': return comparePrimitive(a.score, b.score, sort.sortOrder);
        default: return 0;
      }
    });
  }, [signals, directionFilter, sort.sortField, sort.sortOrder]);

  if (loading && signals.length === 0) return <div className="flex h-32 items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-zinc-500" /></div>;
  if (error && signals.length === 0) return <div className="flex h-32 items-center justify-center text-rose-400 gap-2"><AlertCircle className="w-5 h-5" /><span>信号数据加载失败</span></div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold tracking-tight">信号列表</h2>
        <span className="text-sm text-zinc-500">{signals.length} 条记录</span>
      </div>

      {error && signals.length > 0 && (
        <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/50 text-amber-700 dark:text-amber-400 px-4 py-2 rounded text-sm">
          部分数据刷新失败，显示缓存内容
        </div>
      )}

      {signals.length === 0 ? (
        <Card><CardContent>{emptyDataCard('暂无信号记录')}</CardContent></Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="flex items-center gap-3 px-4 py-2 border-b border-zinc-200 dark:border-zinc-800">
              <span className="text-xs text-zinc-500">方向</span>
              <FilterSelect value={directionFilter} onChange={setDirectionFilter} options={DIRECTION_OPTIONS} />
            </div>
            <Table>
              <TableHeader>
                <TableRow className="bg-zinc-50 dark:bg-zinc-900/50">
                  <TableHead className="cursor-pointer select-none" onClick={() => sort.toggleSort('created_at')}>时间{sort.sortIndicator('created_at')}</TableHead>
                  <TableHead className="cursor-pointer select-none" onClick={() => sort.toggleSort('symbol')}>交易对{sort.sortIndicator('symbol')}</TableHead>
                  <TableHead>周期</TableHead>
                  <TableHead className="cursor-pointer select-none" onClick={() => sort.toggleSort('direction')}>方向{sort.sortIndicator('direction')}</TableHead>
                  <TableHead>入场价</TableHead>
                  <TableHead>止损</TableHead>
                  <TableHead>仓位</TableHead>
                  <TableHead>策略</TableHead>
                  <TableHead className="cursor-pointer select-none" onClick={() => sort.toggleSort('score')}>评分{sort.sortIndicator('score')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.length === 0 ? (
                  <EmptyFilterRow colSpan={9} />
                ) : filtered.map((s, idx) => (
                  <TableRow key={idx}>
                    <TableCell className="font-mono text-xs">{fmtDateTime(s.created_at)}</TableCell>
                    <TableCell className="font-mono font-medium text-blue-400">{fmtDash(s.symbol)}</TableCell>
                    <TableCell className="font-mono">{fmtDash(s.timeframe)}</TableCell>
                    <TableCell>
                      <Badge variant={s.direction === 'LONG' ? 'success' : 'danger'}>
                        {fmtDash(s.direction)}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono">{fmtDash(s.entry_price)}</TableCell>
                    <TableCell className="font-mono">{fmtDash(s.stop_loss)}</TableCell>
                    <TableCell className="font-mono">{fmtDash(s.position_size)}</TableCell>
                    <TableCell className="text-xs">{fmtDash(s.strategy_name)}</TableCell>
                    <TableCell className="font-mono">{fmtDec(s.score)}</TableCell>
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