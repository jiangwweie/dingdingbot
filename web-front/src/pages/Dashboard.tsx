import { useApi } from '../lib/api';
import { formatBeijingTime } from '../lib/utils';
import { Activity, ArrowRight, BarChart3, Clock, TrendingDown, TrendingUp, Target, Wallet, AlertCircle, Settings } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { cn } from '../lib/utils';
import ConfigStatusCard from '../components/ConfigStatusCard';
import SettingsPanel from '../components/SettingsPanel';
import { useState } from 'react';

export default function Dashboard() {
  const { data: health, error: healthError } = useApi<any>('/api/health');
  const { data: stats, error: statsError } = useApi<any>('/api/signals/stats');
  const { data: signalsData, error: signalsError } = useApi<any>('/api/signals?limit=5');
  const { data: diagnostics, error: diagError } = useApi<any>('/api/diagnostics?hours=24');
  const { data: accountData, error: accountError } = useApi<any>('/api/account', 60000);

  const [settingsOpen, setSettingsOpen] = useState(false);

  const isLoading = !health && !healthError;

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-24 bg-white rounded-2xl shadow-sm border border-gray-100" />
          ))}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 h-96 bg-white rounded-2xl shadow-sm border border-gray-100" />
          <div className="h-96 bg-white rounded-2xl shadow-sm border border-gray-100" />
        </div>
      </div>
    );
  }

  const isOnline = health?.status === 'ok';
  const signals = signalsData?.data || [];
  const diagSummary = diagnostics?.summary;
  const unPnl = accountData?.unrealized_pnl ? parseFloat(accountData.unrealized_pnl) : 0;

  return (
    <div className="space-y-6">
      {/* Section 0: Account Overview (from Account.tsx) */}
      {accountData && accountData.status !== 'unavailable' && (
        <div>
          <div className="flex justify-between items-end mb-4">
            <div>
              <h2 className="text-lg font-semibold tracking-tight">账户概览</h2>
              <p className="text-sm text-gray-500 mt-1">资金状态与当前持仓</p>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Total Balance */}
            <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
              <div className="flex items-center gap-2 text-gray-500 mb-4">
                <Wallet className="w-4 h-4" />
                <h3 className="text-sm font-medium">总权益 (USDT)</h3>
              </div>
              <div className="text-4xl font-semibold tracking-tight font-mono">
                {parseFloat(accountData?.total_balance || '0').toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </div>
            </div>

            {/* Available Balance */}
            <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
              <div className="flex items-center gap-2 text-gray-500 mb-4">
                <div className="w-4 h-4 rounded-full border-2 border-gray-400" />
                <h3 className="text-sm font-medium">可用余额 (USDT)</h3>
              </div>
              <div className="text-4xl font-semibold tracking-tight font-mono">
                {parseFloat(accountData?.available_balance || '0').toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </div>
            </div>

            {/* Unrealized PnL */}
            <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
              <div className="flex items-center gap-2 text-gray-500 mb-4">
                {unPnl >= 0 ? <TrendingUp className="w-4 h-4 text-apple-green" /> : <TrendingDown className="w-4 h-4 text-apple-red" />}
                <h3 className="text-sm font-medium">未实现盈亏 (USDT)</h3>
              </div>
              <div className={cn(
                "text-4xl font-semibold tracking-tight font-mono",
                unPnl > 0 ? "text-apple-green" : unPnl < 0 ? "text-apple-red" : "text-gray-900"
              )}>
                {unPnl > 0 ? '+' : ''}{unPnl.toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Section 1.5: Config Status Card */}
      <ConfigStatusCard onOpenSettings={() => setSettingsOpen(true)} />

      {/* Section 1: System Status */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Health Card */}
        <div className="bg-white p-5 rounded-2xl shadow-sm border border-gray-100 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-gray-500">系统状态</h3>
            <Activity className="w-4 h-4 text-gray-400" />
          </div>
          <div className="mt-4 flex items-center gap-2">
            <div className={cn("w-3 h-3 rounded-full", isOnline ? "bg-apple-green" : "bg-apple-red")} />
            <span className="text-2xl font-semibold tracking-tight">
              {isOnline ? '在线' : '离线'}
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-2">
            {health?.timestamp ? `${formatBeijingTime(health.timestamp, 'time')} 更新` : '未知'}更新
          </p>
        </div>

        {/* Today Signals Card */}
        <div className="bg-white p-5 rounded-2xl shadow-sm border border-gray-100 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-gray-500">今日信号</h3>
            <Clock className="w-4 h-4 text-gray-400" />
          </div>
          <div className="mt-4">
            <span className="text-3xl font-semibold tracking-tight">{stats?.today || 0}</span>
          </div>
          <p className="text-xs text-gray-400 mt-2">过去 24 小时触发</p>
        </div>

        {/* Total Signals Card */}
        <div className="bg-white p-5 rounded-2xl shadow-sm border border-gray-100 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-gray-500">历史总计</h3>
            <BarChart3 className="w-4 h-4 text-gray-400" />
          </div>
          <div className="mt-4">
            <span className="text-3xl font-semibold tracking-tight">{stats?.total || 0}</span>
          </div>
          <p className="text-xs text-gray-400 mt-2">系统运行以来</p>
        </div>

        {/* Win Rate Card */}
        <div className="bg-white p-5 rounded-2xl shadow-sm border border-gray-100 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-gray-500">近期胜率</h3>
            <Target className="w-4 h-4 text-gray-400" />
          </div>
          <div className="mt-4">
            {stats?.win_rate !== undefined && stats?.win_rate !== null && stats.win_rate > 0 ? (
              <span className="text-3xl font-semibold tracking-tight">{(stats.win_rate * 100).toFixed(1)}%</span>
            ) : (
              <span className="text-3xl font-semibold tracking-tight text-gray-300">暂无数据</span>
            )}
          </div>
          <p className="text-xs text-gray-400 mt-2">已结算信号胜率</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Section 2: Latest Signals */}
        <div className="lg:col-span-2 bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden flex flex-col">
          <div className="p-5 border-b border-gray-100 flex justify-between items-center">
            <h2 className="text-lg font-semibold tracking-tight">最新信号</h2>
            <Link to="/signals" className="text-sm text-apple-blue hover:underline flex items-center gap-1">
              查看全部 <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
          <div className="p-2 flex-1">
            {signals.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-gray-400 py-12">
                <BarChart3 className="w-12 h-12 mb-3 opacity-20" />
                <p>暂无最新信号</p>
              </div>
            ) : (
              <div className="space-y-2">
                {signals.map((signal: any) => {
                  const isLong = signal.direction === 'long';
                  const symbol = signal.symbol.replace(':USDT', '');
                  return (
                    <Link
                      key={String(signal.id)}
                      to={`/signals?highlight=${signal.id}`}
                      className="block p-4 rounded-xl hover:bg-gray-50 transition-colors border border-transparent hover:border-gray-100"
                    >
                      <div className="flex justify-between items-start">
                        <div className="flex items-center gap-3">
                          <div className={cn(
                            "w-10 h-10 rounded-full flex items-center justify-center font-bold text-lg",
                            isLong ? "bg-apple-green/10 text-apple-green" : "bg-apple-red/10 text-apple-red"
                          )}>
                            {isLong ? '多' : '空'}
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-bold text-lg">{symbol}</span>
                              <span className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs font-mono">{signal.timeframe}</span>
                            </div>
                            <div className="text-sm text-gray-500 mt-1 flex items-center gap-3">
                              <span>入场: <span className="font-mono text-gray-900">{signal.entry_price}</span></span>
                              <span>止损: <span className="font-mono text-gray-900">{signal.stop_loss}</span></span>
                            </div>
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="text-sm font-medium text-gray-900">
                            {signal.position_size} <span className="text-gray-400 font-normal">({signal.leverage}x)</span>
                          </div>
                          <div className="text-xs text-gray-400 mt-1">
                            {formatBeijingTime(signal.created_at, 'short')}
                          </div>
                        </div>
                      </div>
                    </Link>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Section 3: Diagnostics Summary */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden flex flex-col">
          <div className="p-5 border-b border-gray-100">
            <h2 className="text-lg font-semibold tracking-tight">今日诊断摘要</h2>
            <p className="text-xs text-gray-400 mt-1">过去 24 小时 K 线处理</p>
          </div>
          <div className="p-5 flex-1 flex flex-col">
            {diagSummary ? (
              <>
                <div className="mb-6">
                  <div className="flex justify-between text-sm mb-2">
                    <span className="text-gray-500">处理总数</span>
                    <span className="font-semibold">{diagSummary.total_klines} 根</span>
                  </div>
                  
                  <div className="space-y-3 mt-4">
                    <div>
                      <div className="flex justify-between text-xs mb-1">
                        <span className="text-gray-500">触发信号</span>
                        <span className="font-medium text-apple-green">{diagSummary.signal_fired}</span>
                      </div>
                      <div className="w-full h-1.5 bg-gray-100 rounded-full overflow-hidden">
                        <div className="bg-apple-green h-full" style={{ width: `${(diagSummary.signal_fired / diagSummary.total_klines) * 100}%` }} />
                      </div>
                    </div>
                    
                    <div>
                      <div className="flex justify-between text-xs mb-1">
                        <span className="text-gray-500">识别形态但被过滤</span>
                        <span className="font-medium text-apple-orange">{diagSummary.filtered}</span>
                      </div>
                      <div className="w-full h-1.5 bg-gray-100 rounded-full overflow-hidden">
                        <div className="bg-apple-orange h-full" style={{ width: `${(diagSummary.filtered / diagSummary.total_klines) * 100}%` }} />
                      </div>
                    </div>

                    <div>
                      <div className="flex justify-between text-xs mb-1">
                        <span className="text-gray-500">未识别形态</span>
                        <span className="font-medium text-gray-400">{diagSummary.no_pattern}</span>
                      </div>
                      <div className="w-full h-1.5 bg-gray-100 rounded-full overflow-hidden">
                        <div className="bg-gray-300 h-full" style={{ width: `${(diagSummary.no_pattern / diagSummary.total_klines) * 100}%` }} />
                      </div>
                    </div>
                  </div>
                </div>

                <div className="mt-auto pt-4 border-t border-gray-100">
                  <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">过滤原因分布</h4>
                  <div className="space-y-2">
                    {Object.entries(diagSummary.filter_breakdown || {}).map(([key, value]: [string, any]) => {
                      const label = key === 'ema_trend' ? 'EMA 趋势过滤' : key === 'mtf' ? '多周期过滤' : key;
                      const maxVal = Math.max(...Object.values(diagSummary.filter_breakdown || {}) as number[]);
                      return (
                        <div key={key} className="flex items-center gap-2">
                          <span className="text-xs text-gray-600 w-24 truncate" title={label}>{label}</span>
                          <div className="flex-1 h-4 bg-gray-100 rounded-sm overflow-hidden flex">
                            <div className="bg-apple-orange h-full" style={{ width: `${(value / maxVal) * 100}%` }} />
                          </div>
                          <span className="text-xs font-mono text-gray-500 w-8 text-right">{value}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </>
            ) : (
              <div className="h-full flex items-center justify-center text-gray-400">
                暂无诊断数据
              </div>
            )}
          </div>
        </div>
      </div>
      <SettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}

