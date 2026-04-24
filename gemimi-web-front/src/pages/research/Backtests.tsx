import React, { useEffect, useState } from 'react';
import { getBacktests } from '@/src/services/mockApi';
import { BacktestRecord } from '@/src/types';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/src/components/ui/Table';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { Badge } from '@/src/components/ui/Badge';
import { Loader2 } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function Backtests() {
  const { refreshCount } = useRefreshContext();
  const [backtests, setBacktests] = useState<BacktestRecord[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    getBacktests().then(res => {
      if (active) {
        setBacktests(res);
        setLoading(false);
      }
    });
    return () => { active = false; };
  }, [refreshCount]);

  if (loading && backtests.length === 0) {
    return <div className="flex h-32 items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-zinc-500" /></div>;
  }

  const formatPct = (val: number) => `${(val * 100).toFixed(1)}%`;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-end">
        <div>
          <h2 className="text-xl font-bold tracking-tight">回测记录 (Backtests)</h2>
          <p className="text-xs text-zinc-500 mt-1 max-w-xl">
            系统内所有策略和规则集产生的历史回测执行记录。
          </p>
        </div>
        <Link to="/research/compare" className="text-sm font-medium bg-blue-600 hover:bg-blue-700 text-zinc-900 dark:text-white px-4 py-2 rounded transition">
          对比分析 (Compare)
        </Link>
      </div>

      <Card>
        <CardHeader><CardTitle>近期记录 (Recent Runs)</CardTitle></CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>回测 ID</TableHead>
                <TableHead>候选依赖</TableHead>
                <TableHead>交易对 / 周期</TableHead>
                <TableHead>测试区间</TableHead>
                <TableHead>状态</TableHead>
                <TableHead className="text-right">总收益 (Ret)</TableHead>
                <TableHead className="text-right">夏普 (Sharpe)</TableHead>
                <TableHead className="text-right">最大回撤 (MDD)</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {backtests.map(bt => (
                <TableRow key={bt.id}>
                  <TableCell className="font-mono text-xs text-blue-400">{bt.id}</TableCell>
                  <TableCell>
                    <Link to={`/research/candidates/${bt.candidate_ref}`} className="hover:underline font-mono text-xs text-zinc-700 dark:text-zinc-300">
                      {bt.candidate_ref}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <span className="font-semibold">{bt.symbol}</span> <span className="text-zinc-500 text-xs ml-1">{bt.timeframe}</span>
                  </TableCell>
                  <TableCell className="text-xs text-zinc-600 dark:text-zinc-400">
                    {bt.start_date} ~ {bt.end_date}
                  </TableCell>
                  <TableCell>
                    <Badge variant={bt.status === 'COMPLETED' ? 'success' : bt.status === 'FAILED' ? 'danger' : 'info'}>
                      {bt.status === 'COMPLETED' ? '已完成' : bt.status === 'FAILED' ? '失败' : bt.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right font-mono font-medium text-emerald-400">
                    {bt.status === 'COMPLETED' ? formatPct(bt.metrics.total_return) : '-'}
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    {bt.status === 'COMPLETED' ? bt.metrics.sharpe.toFixed(2) : '-'}
                  </TableCell>
                  <TableCell className="text-right font-mono text-amber-500">
                    {bt.status === 'COMPLETED' ? formatPct(bt.metrics.max_drawdown) : '-'}
                  </TableCell>
                </TableRow>
              ))}
              {backtests.length === 0 && (
                <TableRow><TableCell colSpan={8} className="text-center py-6 text-zinc-500">暂无回测记录 (No backtest data)</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
