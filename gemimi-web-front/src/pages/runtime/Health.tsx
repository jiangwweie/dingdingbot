import React, { useEffect, useState } from 'react';
import { getRuntimeHealth } from '@/src/services/api';
import { RuntimeHealth as IRuntimeHealth } from '@/src/types';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { Badge } from '@/src/components/ui/Badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/src/components/ui/Table';
import { Loader2, AlertCircle } from 'lucide-react';
import { fmtDash, runtimeHealthVariant, runtimeHealthLabel, gateResultVariant } from '@/src/lib/console-utils';

export default function Health() {
  const { refreshCount } = useRefreshContext();
  const [data, setData] = useState<IRuntimeHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(false);
    getRuntimeHealth().then(res => {
      if (active) { setData(res); setLoading(false); }
    }).catch(() => {
      if (active) { setError(true); setLoading(false); }
    });
    return () => { active = false; };
  }, [refreshCount]);

  if (loading && !data) return <div className="flex h-32 items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-zinc-500" /></div>;
  if (error && !data) return <div className="flex h-32 items-center justify-center text-rose-400 gap-2"><AlertCircle className="w-5 h-5" /><span>健康数据加载失败</span></div>;

  if (!data) return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold tracking-tight">系统健康</h2>
      <Card><CardContent className="py-10 text-center text-zinc-500">暂无健康数据</CardContent></Card>
    </div>
  );

  const statusCards = [
    { title: '交易所 API', status: data.exchange_status },
    { title: '数据库 (PG)', status: data.pg_status },
    { title: '通知推送', status: data.notification_status },
  ];

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold tracking-tight">系统健康</h2>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {statusCards.map(card => (
          <Card key={card.title}>
            <CardHeader><CardTitle>{card.title}</CardTitle></CardHeader>
            <CardContent className="flex items-center gap-3">
              <Badge variant={runtimeHealthVariant(card.status)}>{runtimeHealthLabel(card.status)}</Badge>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader><CardTitle>启动检查</CardTitle></CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="bg-zinc-50 dark:bg-zinc-900/50">
                <TableHead>检查项</TableHead>
                <TableHead>结果</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {Object.entries(data.startup_markers).map(([key, value]) => (
                <TableRow key={key}>
                  <TableCell className="font-medium">{fmtDash(key)}</TableCell>
                  <TableCell><Badge variant={gateResultVariant(String(value))}>{fmtDash(value)}</Badge></TableCell>
                </TableRow>
              ))}
              {Object.keys(data.startup_markers).length === 0 && (
                <TableRow>
                  <TableCell colSpan={2} className="py-6 text-center text-zinc-500 text-sm">暂无启动检查记录</TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>熔断器</CardTitle></CardHeader>
        <CardContent>
          <div className="flex items-center gap-4 text-sm">
            <span>累计触发: <strong>{data.breaker_summary.total_tripped}</strong></span>
            {data.breaker_summary.active_breakers.length > 0 && (
              <span>活跃熔断: <strong>{data.breaker_summary.active_breakers.join(', ')}</strong></span>
            )}
            {data.breaker_summary.last_trip_time && (
              <span className="text-xs text-zinc-500">最近触发: {fmtDash(data.breaker_summary.last_trip_time)}</span>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>恢复任务</CardTitle></CardHeader>
        <CardContent>
          <div className="flex items-center gap-4 text-sm">
            <span>待处理: <strong>{data.recovery_summary.pending_tasks}</strong></span>
            <span>已完成: <strong>{data.recovery_summary.completed_tasks}</strong></span>
            {data.recovery_summary.last_recovery_time && (
              <span className="text-xs text-zinc-500">最近恢复: {fmtDash(data.recovery_summary.last_recovery_time)}</span>
            )}
          </div>
        </CardContent>
      </Card>

      {(data.recent_warnings.length > 0 || data.recent_errors.length > 0) && (
        <Card>
          <CardHeader><CardTitle>最近告警</CardTitle></CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow className="bg-zinc-50 dark:bg-zinc-900/50">
                  <TableHead>级别</TableHead>
                  <TableHead>消息</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.recent_errors.map((msg, i) => (
                  <TableRow key={`err-${i}`}>
                    <TableCell><Badge variant="danger">ERROR</Badge></TableCell>
                    <TableCell className="text-xs">{fmtDash(msg)}</TableCell>
                  </TableRow>
                ))}
                {data.recent_warnings.map((msg, i) => (
                  <TableRow key={`warn-${i}`}>
                    <TableCell><Badge variant="warning">WARN</Badge></TableCell>
                    <TableCell className="text-xs">{fmtDash(msg)}</TableCell>
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
