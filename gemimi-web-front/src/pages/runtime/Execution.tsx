import React, { useEffect, useState, useMemo } from 'react';
import { getRuntimeExecutionIntents } from '@/src/services/api';
import { ExecutionIntent } from '@/src/types';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Card, CardContent } from '@/src/components/ui/Card';
import { Badge } from '@/src/components/ui/Badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/src/components/ui/Table';
import { Loader2, AlertCircle } from 'lucide-react';
import { fmtDash, fmtDateTime } from '@/src/lib/console-utils';
import { useTableSort, compareTimestamp, comparePrimitive, FilterSelect, EmptyFilterRow, emptyDataCard } from '@/src/lib/table-utils';

const intentStatusVariant = (s: string): 'success' | 'warning' | 'danger' | 'info' | 'default' => {
  switch (s) {
    case 'COMPLETED': return 'success';
    case 'EXECUTING': return 'info';
    case 'PENDING': return 'warning';
    case 'FAILED': return 'danger';
    default: return 'default';
  }
};

const STATUS_OPTIONS = [
  { value: 'ALL', label: '全部状态' },
  { value: 'PENDING', label: 'PENDING' },
  { value: 'EXECUTING', label: 'EXECUTING' },
  { value: 'COMPLETED', label: 'COMPLETED' },
  { value: 'FAILED', label: 'FAILED' },
];

export default function Execution() {
  const { refreshCount } = useRefreshContext();
  const [data, setData] = useState<ExecutionIntent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [statusFilter, setStatusFilter] = useState('ALL');
  const sort = useTableSort<ExecutionIntent>('created_at', 'desc');

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(false);
    getRuntimeExecutionIntents().then(res => {
      if (active) { setData(res); setLoading(false); }
    }).catch(() => {
      if (active) { setError(true); setLoading(false); }
    });
    return () => { active = false; };
  }, [refreshCount]);

  const filtered = useMemo(() => {
    let rows = data;
    if (statusFilter !== 'ALL') rows = rows.filter(e => e.status === statusFilter);
    return [...rows].sort((a, b) => {
      switch (sort.sortField) {
        case 'created_at': return compareTimestamp(a.created_at, b.created_at, sort.sortOrder);
        case 'symbol': return comparePrimitive(a.symbol, b.symbol, sort.sortOrder);
        case 'direction': return comparePrimitive(a.direction, b.direction, sort.sortOrder);
        case 'status': return comparePrimitive(a.status, b.status, sort.sortOrder);
        default: return 0;
      }
    });
  }, [data, statusFilter, sort.sortField, sort.sortOrder]);

  if (loading && data.length === 0) return <div className="flex h-32 items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-zinc-500" /></div>;
  if (error && data.length === 0) return <div className="flex h-32 items-center justify-center text-rose-400 gap-2"><AlertCircle className="w-5 h-5" /><span>执行数据加载失败</span></div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold tracking-tight">执行意图</h2>
        <span className="text-sm text-zinc-500">{data.length} 条记录</span>
      </div>

      {error && data.length > 0 && (
        <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/50 text-amber-700 dark:text-amber-400 px-4 py-2 rounded text-sm">
          部分数据刷新失败，显示缓存内容
        </div>
      )}

      {data.length === 0 ? (
        <Card><CardContent>{emptyDataCard('暂无执行记录')}</CardContent></Card>
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
                  <TableHead className="cursor-pointer select-none" onClick={() => sort.toggleSort('created_at')}>时间{sort.sortIndicator('created_at')}</TableHead>
                  <TableHead className="cursor-pointer select-none" onClick={() => sort.toggleSort('symbol')}>交易对{sort.sortIndicator('symbol')}</TableHead>
                  <TableHead className="cursor-pointer select-none" onClick={() => sort.toggleSort('direction')}>方向{sort.sortIndicator('direction')}</TableHead>
                  <TableHead>类型</TableHead>
                  <TableHead className="cursor-pointer select-none" onClick={() => sort.toggleSort('status')}>状态{sort.sortIndicator('status')}</TableHead>
                  <TableHead>触发信号</TableHead>
                  <TableHead className="text-right">金额</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.length === 0 ? (
                  <EmptyFilterRow colSpan={7} />
                ) : filtered.map((e, idx) => (
                  <TableRow key={idx}>
                    <TableCell className="font-mono text-xs">{fmtDateTime(e.created_at)}</TableCell>
                    <TableCell className="font-mono font-medium text-blue-400">{fmtDash(e.symbol)}</TableCell>
                    <TableCell>
                      <Badge variant={e.direction === 'LONG' ? 'success' : 'danger'}>
                        {fmtDash(e.direction)}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs">{fmtDash(e.intent_type)}</TableCell>
                    <TableCell><Badge variant={intentStatusVariant(e.status)}>{fmtDash(e.status)}</Badge></TableCell>
                    <TableCell className="font-mono text-xs text-zinc-500">{fmtDash(e.signal_ref)}</TableCell>
                    <TableCell className="font-mono text-right">{fmtDash(e.amount)}</TableCell>
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