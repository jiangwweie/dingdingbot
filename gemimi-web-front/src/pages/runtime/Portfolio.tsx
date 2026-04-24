import React, { useEffect, useState } from 'react';
import { getPortfolioContext } from '@/src/services/mockApi';
import { PortfolioContext } from '@/src/types';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/src/components/ui/Table';
import { Badge } from '@/src/components/ui/Badge';
import { Loader2, DollarSign, PieChart, Activity, AlertCircle } from 'lucide-react';
import { cn } from '@/src/lib/utils';

export default function Portfolio() {
  const { refreshCount } = useRefreshContext();
  const [data, setData] = useState<PortfolioContext | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    getPortfolioContext().then(res => {
      if (active) {
        setData(res);
        setLoading(false);
      }
    });
    return () => { active = false; };
  }, [refreshCount]);

  if (loading && !data) {
    return <div className="flex h-32 items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-zinc-500" /></div>;
  }

  if (!data) return null;

  const pnlColor = data.unrealized_pnl >= 0 ? "text-emerald-500 dark:text-emerald-400" : "text-rose-500 dark:text-rose-400";
  const dailyLossPct = (data.daily_loss_used / data.daily_loss_limit) * 100;
  
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold tracking-tight">投资组合 (Portfolio)</h2>
        <p className="text-xs text-zinc-500 mt-1 max-w-xl">
          当前交易账户由于各种因素暴露出的总敞口与风险指标，并跟踪仓位细节。
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-zinc-500 flex items-center justify-between">
              总权益 (Total Equity)
              <DollarSign className="w-4 h-4 text-zinc-600" />
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-mono text-zinc-900 dark:text-zinc-100">${data.total_equity.toLocaleString(undefined, { minimumFractionDigits: 2 })}</div>
            <p className="text-xs text-zinc-500 mt-1">
              可用余额: <span className="font-mono text-zinc-700 dark:text-zinc-300">${data.available_balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-zinc-500 flex items-center justify-between">
              未结盈亏 (Unrealized PnL)
              <Activity className="w-4 h-4 text-zinc-600" />
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className={cn("text-2xl font-mono", pnlColor)}>
              {data.unrealized_pnl >= 0 ? '+' : ''}${data.unrealized_pnl.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-zinc-500 flex items-center justify-between">
              总敞口 (Total Exposure)
              <PieChart className="w-4 h-4 text-zinc-600" />
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-end justify-between">
              <div className="text-2xl font-mono text-zinc-900 dark:text-zinc-100">${data.total_exposure.toLocaleString(undefined, { minimumFractionDigits: 2 })}</div>
              <div className="text-xs text-zinc-500 mb-1 font-mono">/ ${data.max_total_exposure.toLocaleString()}</div>
            </div>
            <div className="w-full bg-zinc-200 dark:bg-zinc-800 h-1.5 mt-2 rounded overflow-hidden">
               <div className="h-full bg-blue-500" style={{ width: `${Math.min((data.total_exposure / data.max_total_exposure) * 100, 100)}%` }} />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-zinc-500 flex items-center justify-between">
              日内最大回撤 (Daily Loss Limit)
              <AlertCircle className="w-4 h-4 text-zinc-600" />
            </CardTitle>
          </CardHeader>
          <CardContent>
             <div className="flex items-end justify-between">
               <div className="text-2xl font-mono text-amber-600 dark:text-amber-500">${data.daily_loss_used.toLocaleString(undefined, { minimumFractionDigits: 2 })}</div>
               <div className="text-xs text-zinc-500 mb-1 font-mono">/ ${data.daily_loss_limit.toLocaleString()}</div>
             </div>
             <div className="w-full bg-zinc-200 dark:bg-zinc-800 h-1.5 mt-2 rounded overflow-hidden">
               <div className="h-full bg-amber-500" style={{ width: `${Math.min(dailyLossPct, 100)}%` }} />
             </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-zinc-500 flex items-center justify-between">
              杠杆使用率 (Leverage Usage)
              <Activity className="w-4 h-4 text-zinc-600" />
            </CardTitle>
          </CardHeader>
          <CardContent>
             <div className="flex items-end justify-between">
               <div className="text-2xl font-mono text-zinc-900 dark:text-zinc-100">{data.leverage_usage.toFixed(2)}x</div>
               <div className="text-xs text-zinc-500 mb-1 font-mono">/ 20.0x (Max)</div>
             </div>
             <div className="w-full bg-zinc-200 dark:bg-zinc-800 h-1.5 mt-2 rounded overflow-hidden">
               <div className="h-full bg-purple-500" style={{ width: `${Math.min((data.leverage_usage / 20) * 100, 100)}%` }} />
             </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>当前持仓 (Open Positions)</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>交易对</TableHead>
                <TableHead>方向</TableHead>
                <TableHead className="text-right">数量</TableHead>
                <TableHead className="text-right">开仓均价</TableHead>
                <TableHead className="text-right">当前价格</TableHead>
                <TableHead className="text-right">杠杆率</TableHead>
                <TableHead className="text-right">未结盈亏</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.positions.map((pos, i) => {
                const isProfitable = pos.unrealized_pnl >= 0;
                return (
                  <TableRow key={i}>
                    <TableCell className="font-semibold">{pos.symbol}</TableCell>
                    <TableCell>
                      <Badge variant={pos.direction === 'LONG' ? 'success' : 'danger'}>{pos.direction}</Badge>
                    </TableCell>
                    <TableCell className="text-right font-mono">{pos.quantity}</TableCell>
                    <TableCell className="text-right font-mono text-zinc-600 dark:text-zinc-400">{pos.entry_price.toFixed(2)}</TableCell>
                    <TableCell className="text-right font-mono text-zinc-600 dark:text-zinc-400">{pos.current_price.toFixed(2)}</TableCell>
                    <TableCell className="text-right font-mono text-zinc-500">{pos.leverage}x</TableCell>
                    <TableCell className={cn("text-right font-mono", isProfitable ? "text-emerald-500 dark:text-emerald-400" : "text-rose-500 dark:text-rose-400")}>
                      {isProfitable ? '+' : ''}{pos.unrealized_pnl.toLocaleString(undefined, { minimumFractionDigits: 2 })}<br/>
                      <span className="text-[10px] opacity-80">{isProfitable ? '+' : ''}{(pos.pnl_percent * 100).toFixed(2)}%</span>
                    </TableCell>
                  </TableRow>
                );
              })}
              {data.positions.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-6 text-zinc-500">当前没有持仓</TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      
    </div>
  );
}
