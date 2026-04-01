'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { fetcher } from '../lib/api';
import { AccountOverviewCards } from '../components/v3/AccountOverviewCards';
import { PnLStatisticsCards } from '../components/v3/PnLStatisticsCards';
import { EquityCurveChart, type DateRangeType } from '../components/v3/EquityCurveChart';
import { PositionDistributionPie } from '../components/v3/PositionDistributionPie';
import { DateRangeSelector } from '../components/v3/DateRangeSelector';
import { DecimalDisplay } from '../components/v3/DecimalDisplay';
import { cn } from '../lib/utils';

/**
 * v3.0 账户页面
 * 显示账户余额、权益曲线、盈亏统计
 */
export default function Account() {
  const [dateRange, setDateRange] = useState<DateRangeType>('7days');

  // Fetch account snapshot
  const { data: accountData, error: accountError } = useSWR(
    '/api/v3/account/snapshot',
    fetcher,
    { refreshInterval: 30000 }
  );

  // Fetch positions for distribution pie
  const { data: positionsData, error: positionsError } = useSWR(
    '/api/v3/positions?is_closed=false',
    fetcher,
    { refreshInterval: 30000 }
  );

  // Fetch historical signals for PnL calculation
  const { data: signalsData, error: signalsError } = useSWR(
    '/api/signals?limit=200',
    fetcher,
    { refreshInterval: 60000 }
  );

  // Fetch historical snapshots for equity curve
  const { data: historicalData, error: historicalError } = useSWR(
    `/api/v3/account/snapshots/historical?days=${dateRange === '7days' ? 7 : dateRange === '30days' ? 30 : 90}`,
    fetcher,
    { refreshInterval: 60000 }
  );

  const isLoading = !accountData && !accountError;

  // Calculate PnL statistics from signals
  const pnlStats = (() => {
    if (!signalsData?.data) {
      return { daily: '0', weekly: '0', monthly: '0', total: '0' };
    }

    const signals = signalsData.data;
    const now = Date.now();
    const oneDay = 24 * 60 * 60 * 1000;
    const oneWeek = 7 * oneDay;
    const oneMonth = 30 * oneDay;

    let dailyPnl = 0;
    let weeklyPnl = 0;
    let monthlyPnl = 0;
    let totalPnl = 0;

    signals.forEach((signal: any) => {
      if (signal.pnl_ratio) {
        const pnl = parseFloat(signal.pnl_ratio);
        const signalTime = new Date(signal.created_at).getTime();
        const age = now - signalTime;

        totalPnl += pnl;

        if (age <= oneDay) {
          dailyPnl += pnl;
        }
        if (age <= oneWeek) {
          weeklyPnl += pnl;
        }
        if (age <= oneMonth) {
          monthlyPnl += pnl;
        }
      }
    });

    return {
      daily: dailyPnl.toString(),
      weekly: weeklyPnl.toString(),
      monthly: monthlyPnl.toString(),
      total: totalPnl.toString(),
    };
  })();

  // Use real historical snapshots from API
  const snapshots = historicalData?.snapshots || [];

  const positions = positionsData?.items || [];

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-28 bg-white rounded-2xl shadow-sm border border-gray-100" />
          ))}
        </div>
        <div className="h-96 bg-white rounded-2xl shadow-sm border border-gray-100" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">账户详情</h2>
          <p className="text-sm text-gray-500 mt-1">
            实时查看账户权益、盈亏统计与仓位分布
          </p>
        </div>
      </div>

      {/* Section 1: Account Overview Cards */}
      <AccountOverviewCards
        totalEquity={accountData?.total_equity}
        availableBalance={accountData?.available_balance}
        unrealizedPnl={accountData?.total_unrealized_pnl}
        marginUsed={accountData?.total_margin_used}
        isLoading={isLoading}
      />

      {/* Section 2: PnL Statistics */}
      <div>
        <h3 className="text-lg font-semibold tracking-tight mb-4">盈亏统计</h3>
        <PnLStatisticsCards
          dailyPnl={pnlStats.daily}
          weeklyPnl={pnlStats.weekly}
          monthlyPnl={pnlStats.monthly}
          totalPnl={pnlStats.total}
          isLoading={signalsError}
        />
      </div>

      {/* Section 3: Equity Curve Chart */}
      <div className="flex flex-col gap-4">
        <div className="flex justify-between items-center">
          <h3 className="text-lg font-semibold tracking-tight">净值走势</h3>
          <DateRangeSelector value={dateRange} onChange={setDateRange} />
        </div>
        <EquityCurveChart
          snapshots={snapshots}
          dateRange={dateRange}
          isLoading={isLoading}
        />
      </div>

      {/* Section 4: Position Distribution */}
      <PositionDistributionPie
        positions={positions}
        isLoading={positionsError}
      />

      {/* Section 5: Account Details Table */}
      <div className={cn(
        "bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden",
        isLoading && "animate-pulse"
      )}>
        <div className="px-6 py-4 border-b border-gray-100">
          <h3 className="text-lg font-semibold tracking-tight">账户明细</h3>
        </div>
        {isLoading ? (
          <div className="p-6 space-y-4">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="flex justify-between">
                <div className="h-4 bg-gray-200 rounded w-32" />
                <div className="h-4 bg-gray-200 rounded w-48" />
              </div>
            ))}
          </div>
        ) : (
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-gray-500 bg-gray-50/50 uppercase border-b border-gray-100">
              <tr>
                <th className="px-6 py-4 font-medium">项目</th>
                <th className="px-6 py-4 font-medium">数值</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              <tr>
                <td className="px-6 py-4 text-gray-600">交易所</td>
                <td className="px-6 py-4 font-semibold">
                  <span className="text-gray-900">{accountData?.exchange || '-'}</span>
                </td>
              </tr>
              <tr>
                <td className="px-6 py-4 text-gray-600">账户类型</td>
                <td className="px-6 py-4 font-semibold">
                  <span className="text-gray-900">{accountData?.account_type || '-'}</span>
                </td>
              </tr>
              <tr>
                <td className="px-6 py-4 text-gray-600">账户杠杆</td>
                <td className="px-6 py-4 font-semibold">
                  <span className="text-gray-900">{accountData?.account_leverage ? `${accountData.account_leverage}x` : '-'}</span>
                </td>
              </tr>
              <tr>
                <td className="px-6 py-4 text-gray-600">总保证金余额</td>
                <td className="px-6 py-4 font-semibold">
                  <DecimalDisplay value={accountData?.total_margin_balance} decimals={2} />
                </td>
              </tr>
              <tr>
                <td className="px-6 py-4 text-gray-600">总钱包余额</td>
                <td className="px-6 py-4 font-semibold">
                  <DecimalDisplay value={accountData?.total_wallet_balance} decimals={2} />
                </td>
              </tr>
              <tr>
                <td className="px-6 py-4 text-gray-600">更新时间</td>
                <td className="px-6 py-4 font-mono text-gray-500">
                  {accountData?.last_updated
                    ? new Date(accountData.last_updated).toLocaleString('zh-CN')
                    : '-'}
                </td>
              </tr>
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
