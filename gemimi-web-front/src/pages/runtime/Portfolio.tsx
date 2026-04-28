import React, { useEffect, useState } from 'react';
import { getPortfolioContext } from '@/src/services/api';
import { PortfolioContext } from '@/src/types';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/src/components/ui/Table';
import { Badge } from '@/src/components/ui/Badge';
import { cn } from '@/src/lib/utils';
import { fmtMoney, fmtDec } from '@/src/lib/console-utils';
import {
  riskLevel,
  riskBarColor,
  riskTextColor,
  pnlColor,
  formatPercent,
} from '@/src/lib/runtime-format';
import {
  Loader2,
  DollarSign,
  PieChart,
  Activity,
  AlertCircle,
  ShieldAlert,
  Lock,
} from 'lucide-react';

// ─── Risk progress bar sub-component ─────────────────────

function RiskBar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  const level = riskLevel(pct);
  return (
    <div className="w-full bg-zinc-200 dark:bg-zinc-800 h-1.5 mt-2 rounded overflow-hidden">
      <div
        className={cn('h-full rounded transition-all duration-500', riskBarColor(level))}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

// ─── Main component ──────────────────────────────────────

export default function Portfolio() {
  const { refreshCount } = useRefreshContext();
  const [data, setData] = useState<PortfolioContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    getPortfolioContext()
      .then((res) => {
        if (active) {
          setData(res);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (active) {
          setError(err instanceof Error ? err.message : 'Failed to load portfolio data');
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [refreshCount]);

  // ─── Loading state ──────────────────────────────────────

  if (loading && !data) {
    return (
      <div className="flex h-32 items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-zinc-500" />
      </div>
    );
  }

  // ─── Error state ────────────────────────────────────────

  if (error && !data) {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="text-xl font-bold tracking-tight">资金与风险 (Portfolio)</h2>
        </div>
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12 text-center">
            <AlertCircle className="w-10 h-10 text-red-400 mb-3" />
            <p className="text-sm text-zinc-500">无法加载资金与风险数据</p>
            <p className="text-xs text-zinc-400 mt-1 font-mono">{error}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!data) return null;

  // ─── Derived values ─────────────────────────────────────

  const exposurePct = data.max_total_exposure > 0
    ? (data.total_exposure / data.max_total_exposure) * 100
    : 0;
  const exposureLevel = riskLevel(exposurePct);

  const dailyLossPct = data.daily_loss_limit > 0
    ? (data.daily_loss_used / data.daily_loss_limit) * 100
    : 0;
  const dailyLossLevel = riskLevel(dailyLossPct);

  const maxLeverage = 20; // backend limit constant
  const leveragePct = (data.leverage_usage / maxLeverage) * 100;
  const leverageLevel = riskLevel(leveragePct);

  // ─── Render ─────────────────────────────────────────────

  return (
    <div className="space-y-4 max-w-[1600px] mx-auto">
      {/* Page header */}
      <div className="flex items-center justify-between bg-zinc-50 dark:bg-zinc-900/40 p-2.5 rounded-sm border border-zinc-200 dark:border-zinc-800">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-widest text-zinc-700 dark:text-zinc-300">资金与风险 (Portfolio)</h2>
        </div>
        <div>
          <span className="text-[10px] text-zinc-500 font-mono hidden sm:inline-block">LIVE RISK MONITORING</span>
        </div>
      </div>

      {/* Stale data warning when error exists but fallback data is shown */}
      {error && data && (
        <div className="flex items-center gap-2 rounded-sm border border-yellow-700/50 bg-yellow-900/20 px-3 py-1.5 text-[11px] text-yellow-400">
          <AlertCircle className="w-3.5 h-3.5 shrink-0" />
          <span>数据可能过期: {error}</span>
        </div>
      )}

      {/* ─── KPI Cards ──────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-2">
        {/* Total Equity */}
        <Card>
          <CardHeader>
            <CardTitle className="text-zinc-500 flex items-center gap-1.5">
              <DollarSign className="w-3.5 h-3.5 text-zinc-500" />
              总权益 (Equity)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-lg font-bold font-mono tracking-tight text-zinc-900 dark:text-zinc-100 leading-none">
              ${fmtMoney(data.total_equity)}
            </div>
            <p className="text-[10px] text-zinc-500 mt-1.5">
              可用余额:{' '}
              <span className="font-mono text-zinc-700 dark:text-zinc-300">
                ${fmtMoney(data.available_balance)}
              </span>
            </p>
          </CardContent>
        </Card>

        {/* Unrealized PnL */}
        <Card>
          <CardHeader>
            <CardTitle className="text-zinc-500 flex items-center gap-1.5">
              <Activity className="w-3.5 h-3.5 text-zinc-500" />
              未实现盈亏 (uPnL)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className={cn('text-lg font-bold font-mono tracking-tight leading-none', pnlColor(data.unrealized_pnl))}>
              {data.unrealized_pnl >= 0 ? '+' : ''}$
              {fmtMoney(data.unrealized_pnl)}
            </div>
            <p className={cn('text-[10px] mt-1.5 font-mono', pnlColor(data.unrealized_pnl))}>
              {data.total_equity > 0
                ? formatPercent((data.unrealized_pnl / data.total_equity) * 100)
                : '0.00%'}{' '}
              占权益
            </p>
          </CardContent>
        </Card>

        {/* Total Exposure */}
        <Card>
          <CardHeader>
            <CardTitle className="text-zinc-500 flex items-center gap-1.5">
              <PieChart className="w-3.5 h-3.5 text-zinc-500" />
              总敞口 (Exposure)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-end justify-between">
              <div className={cn('text-lg font-bold font-mono tracking-tight leading-none', riskTextColor(exposureLevel))}>
                ${fmtMoney(data.total_exposure)}
              </div>
              <div className="text-[10px] text-zinc-500 font-mono tracking-tighter">
                / ${fmtMoney(data.max_total_exposure, 0)}
              </div>
            </div>
            <RiskBar value={data.total_exposure} max={data.max_total_exposure} />
          </CardContent>
        </Card>

        {/* Daily Loss Limit */}
        <Card>
          <CardHeader>
            <CardTitle className="text-zinc-500 flex items-center gap-1.5">
              <ShieldAlert className="w-3.5 h-3.5 text-zinc-500" />
              日内回撤 (Drawdown)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-end justify-between">
              <div className={cn('text-lg font-bold font-mono tracking-tight leading-none', riskTextColor(dailyLossLevel))}>
                ${fmtMoney(data.daily_loss_used)}
              </div>
              <div className="text-[10px] text-zinc-500 font-mono tracking-tighter">
                / ${fmtMoney(data.daily_loss_limit, 0)}
              </div>
            </div>
            <RiskBar value={data.daily_loss_used} max={data.daily_loss_limit} />
          </CardContent>
        </Card>

        {/* Leverage Usage */}
        <Card className="col-span-2 lg:col-span-1">
          <CardHeader>
            <CardTitle className="text-zinc-500 flex items-center gap-1.5">
              <Activity className="w-3.5 h-3.5 text-zinc-500" />
              杠杆 (Leverage)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-end justify-between">
              <div className={cn('text-lg font-bold font-mono tracking-tight leading-none', riskTextColor(leverageLevel))}>
                {fmtDec(data.leverage_usage)}x
              </div>
              <div className="text-[10px] text-zinc-500 font-mono tracking-tighter">
                / {maxLeverage}.0x (Max)
              </div>
            </div>
            <RiskBar value={data.leverage_usage} max={maxLeverage} />
          </CardContent>
        </Card>
      </div>

      {/* ─── Positions Table ────────────────────────────── */}
      <Card>
        <CardHeader className="bg-zinc-100/50 dark:bg-zinc-900/80 items-center">
          <CardTitle>当前持仓 (Open Positions)</CardTitle>
          <span className="text-[10px] bg-zinc-200 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 px-1.5 py-0.5 rounded font-mono font-bold tracking-widest">{data.positions.length} ACTIVE</span>
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
                <TableHead className="text-right">杠杆</TableHead>
                <TableHead className="text-right">未实现盈亏</TableHead>
                <TableHead className="text-right">盈亏比例</TableHead>
                <TableHead className="text-right">持仓时长</TableHead>
                <TableHead className="text-right">保护单</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.positions.map((pos, i) => {
                const isProfitable = pos.unrealized_pnl >= 0;
                return (
                  <TableRow key={i}>
                    <TableCell className="font-semibold font-sans">{pos.symbol}</TableCell>
                    <TableCell>
                      <Badge variant={pos.direction === 'LONG' ? 'success' : 'danger'} className="text-[9px] px-1 py-0 border-transparent bg-transparent mt-0.5">
                        {pos.direction}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{pos.quantity}</TableCell>
                    <TableCell className="text-right text-zinc-600 dark:text-zinc-400 tabular-nums">
                      {fmtDec(pos.entry_price)}
                    </TableCell>
                    <TableCell className="text-right text-zinc-600 dark:text-zinc-400 tabular-nums">
                      {fmtDec(pos.current_price)}
                    </TableCell>
                    <TableCell className="text-right text-zinc-500 tabular-nums">
                      {pos.leverage}x
                    </TableCell>
                    <TableCell
                      className={cn(
                        'text-right tracking-tight tabular-nums',
                        isProfitable
                          ? 'text-emerald-500 dark:text-emerald-400'
                          : 'text-rose-500 dark:text-rose-400',
                      )}
                    >
                      <div className="font-bold">
                        {isProfitable ? '+' : ''}$
                        {fmtMoney(pos.unrealized_pnl)}
                      </div>
                      <div className="text-[9px] opacity-80 leading-none">
                        {isProfitable ? '+' : ''}
                        {fmtDec(pos.pnl_percent * 100)}%
                      </div>
                    </TableCell>
                    <TableCell
                      className={cn(
                        'text-right font-bold tabular-nums',
                        isProfitable
                          ? 'text-emerald-500 dark:text-emerald-400'
                          : 'text-rose-500 dark:text-rose-400',
                      )}
                    >
                      {formatPercent(pos.pnl_percent * 100)}
                    </TableCell>
                    <TableCell className="text-right text-zinc-500">
                      暂无数据
                    </TableCell>
                    <TableCell className="text-right text-zinc-500">
                      暂不可判断
                    </TableCell>
                    <TableCell className="text-right">
                      <span className="group relative inline-flex">
                        <button
                          disabled
                          className="inline-flex items-center gap-1 rounded px-2 py-1 text-[10px] font-medium bg-zinc-200 dark:bg-zinc-800 text-zinc-400 dark:text-zinc-600 cursor-not-allowed"
                        >
                          <Lock className="w-3 h-3" />
                          平仓
                        </button>
                        <span className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 whitespace-nowrap rounded bg-zinc-900 px-2 py-1 text-[10px] text-zinc-300 opacity-0 transition-opacity group-hover:opacity-100">
                          需后端安全接口 (Coming Soon)
                        </span>
                      </span>
                    </TableCell>
                  </TableRow>
                );
              })}
              {data.positions.length === 0 && (
                <TableRow>
                  <TableCell colSpan={11} className="text-center py-6 text-zinc-500">
                    当前没有持仓
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
