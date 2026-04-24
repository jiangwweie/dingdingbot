import React, { useEffect, useState } from 'react';
import { getRuntimeSignals, getRuntimeAttempts } from '@/src/services/mockApi';
import { Signal, Attempt } from '@/src/types';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/src/components/ui/Table';
import { Badge } from '@/src/components/ui/Badge';
import { Loader2 } from 'lucide-react';
import { format } from 'date-fns';

export default function Signals() {
  const { refreshCount } = useRefreshContext();
  const [signals, setSignals] = useState<Signal[]>([]);
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([getRuntimeSignals(), getRuntimeAttempts()]).then(([sig, att]) => {
      if (active) {
        setSignals(sig);
        setAttempts(att);
        setLoading(false);
      }
    });
    return () => { active = false; };
  }, [refreshCount]);

  if (loading && signals.length === 0) return <div className="flex h-32 items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-zinc-500" /></div>;

  const getDirectionBadge = (dir: string) => {
    if (dir === 'LONG') return <Badge variant="success">多 (LONG)</Badge>;
    if (dir === 'SHORT') return <Badge variant="danger">空 (SHORT)</Badge>;
    return <Badge variant="info">平 (FLAT)</Badge>;
  };

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold tracking-tight">交易信号与尝试 (Signals & Attempts)</h2>

      <Card>
        <CardHeader><CardTitle>近期尝试 - 过滤管道 (Recent Attempts)</CardTitle></CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>时间 (Time)</TableHead>
                <TableHead>交易对 (Symbol)</TableHead>
                <TableHead>策略 (Strategy)</TableHead>
                <TableHead>方向 (Direction)</TableHead>
                <TableHead>过滤器 (Filters)</TableHead>
                <TableHead>结果 (Result)</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {attempts.map(att => (
                <TableRow key={att.id}>
                  <TableCell className="font-mono text-xs text-zinc-400">{format(new Date(att.timestamp), 'HH:mm:ss')}</TableCell>
                  <TableCell className="font-medium text-zinc-300">{att.symbol}</TableCell>
                  <TableCell>{att.strategy_name}</TableCell>
                  <TableCell>{getDirectionBadge(att.direction)}</TableCell>
                  <TableCell>
                    <span className="text-zinc-400 text-xs">{att.filter_results_summary}</span>
                    {att.reject_reason && <div className="text-rose-400 text-[10px] mt-0.5">{att.reject_reason}</div>}
                  </TableCell>
                  <TableCell>
                    <Badge variant={att.final_result === 'ACCEPTED' ? 'success' : 'danger'}>{att.final_result === 'ACCEPTED' ? '已接受' : '已拒绝'}</Badge>
                  </TableCell>
                </TableRow>
              ))}
              {attempts.length === 0 && <TableRow><TableCell colSpan={6} className="text-center py-4 text-zinc-500">暂无尝试记录</TableCell></TableRow>}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>最近触发信号 (Recent Fired Signals)</CardTitle></CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>时间 (Time)</TableHead>
                <TableHead>ID</TableHead>
                <TableHead>策略 (Strategy)</TableHead>
                <TableHead>方向 (Direction)</TableHead>
                <TableHead>得分 (Score)</TableHead>
                <TableHead>状态 (Status)</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {signals.map(sig => (
                <TableRow key={sig.id}>
                  <TableCell className="font-mono text-xs text-zinc-400">{format(new Date(sig.created_at), 'HH:mm:ss')}</TableCell>
                  <TableCell className="font-mono text-xs text-zinc-500">{sig.id}</TableCell>
                  <TableCell>{sig.strategy_name}</TableCell>
                  <TableCell>{getDirectionBadge(sig.direction)}</TableCell>
                  <TableCell className="font-mono text-blue-400">{sig.score.toFixed(2)}</TableCell>
                  <TableCell><Badge variant="default">{sig.status}</Badge></TableCell>
                </TableRow>
              ))}
              {signals.length === 0 && <TableRow><TableCell colSpan={6} className="text-center py-4 text-zinc-500">暂无信号记录</TableCell></TableRow>}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
