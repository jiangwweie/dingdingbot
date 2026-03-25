import { useState } from 'react';
import { useApi } from '../lib/api';
import { format } from 'date-fns';
import { Filter, X, Activity, AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';
import { cn } from '../lib/utils';

export default function Diagnostics() {
  const [hoursFilter, setHoursFilter] = useState('24');
  const [symbolFilter, setSymbolFilter] = useState('');

  let url = `/api/diagnostics?hours=${hoursFilter}`;
  if (symbolFilter) url += `&symbol=${symbolFilter}`;

  const { data, error } = useApi<any>(url);

  const isLoading = !data && !error;
  const summary = data?.summary;
  const recentAttempts = data?.recent_attempts || [];

  const clearFilters = () => {
    setHoursFilter('24');
    setSymbolFilter('');
  };

  const translateFilterStage = (stage: string) => {
    if (stage === 'ema_trend') return 'EMA 趋势过滤';
    if (stage === 'mtf') return '多周期过滤';
    return stage;
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">系统诊断</h1>
          <p className="text-sm text-gray-500 mt-1">查看 K 线处理详情与策略过滤分析</p>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-3 bg-white p-2 rounded-xl shadow-sm border border-gray-100">
          <div className="flex items-center gap-2 px-2 text-gray-400">
            <Filter className="w-4 h-4" />
          </div>
          <select
            value={hoursFilter}
            onChange={(e) => setHoursFilter(e.target.value)}
            className="bg-gray-50 border-none text-sm rounded-lg focus:ring-0 py-1.5 px-3 outline-none"
          >
            <option value="6">过去 6 小时</option>
            <option value="12">过去 12 小时</option>
            <option value="24">过去 24 小时</option>
            <option value="72">过去 72 小时</option>
          </select>

          <div className="h-4 w-px bg-gray-200" />

          <select
            value={symbolFilter}
            onChange={(e) => setSymbolFilter(e.target.value)}
            className="bg-gray-50 border-none text-sm rounded-lg focus:ring-0 py-1.5 px-3 outline-none"
          >
            <option value="">全部币种</option>
            <option value="BTC/USDT:USDT">BTC</option>
            <option value="ETH/USDT:USDT">ETH</option>
            <option value="SOL/USDT:USDT">SOL</option>
          </select>

          {(hoursFilter !== '24' || symbolFilter) && (
            <button
              onClick={clearFilters}
              className="p-1.5 text-gray-400 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
              title="清空筛选"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Section 1: Stats Overview */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white p-5 rounded-2xl shadow-sm border border-gray-100">
          <div className="flex items-center gap-2 text-gray-500 mb-2">
            <Activity className="w-4 h-4" />
            <h3 className="text-sm font-medium">处理 K 线总数</h3>
          </div>
          <div className="text-3xl font-semibold tracking-tight">{isLoading ? '-' : summary?.total_klines || 0}</div>
        </div>
        <div className="bg-white p-5 rounded-2xl shadow-sm border border-gray-100">
          <div className="flex items-center gap-2 text-gray-400 mb-2">
            <XCircle className="w-4 h-4" />
            <h3 className="text-sm font-medium">未识别形态</h3>
          </div>
          <div className="text-3xl font-semibold tracking-tight text-gray-400">{isLoading ? '-' : summary?.no_pattern || 0}</div>
        </div>
        <div className="bg-white p-5 rounded-2xl shadow-sm border border-gray-100">
          <div className="flex items-center gap-2 text-apple-green mb-2">
            <CheckCircle2 className="w-4 h-4" />
            <h3 className="text-sm font-medium text-gray-500">已触发信号</h3>
          </div>
          <div className="text-3xl font-semibold tracking-tight text-apple-green">{isLoading ? '-' : summary?.signal_fired || 0}</div>
        </div>
        <div className="bg-white p-5 rounded-2xl shadow-sm border border-gray-100">
          <div className="flex items-center gap-2 text-apple-orange mb-2">
            <AlertTriangle className="w-4 h-4" />
            <h3 className="text-sm font-medium text-gray-500">被过滤</h3>
          </div>
          <div className="text-3xl font-semibold tracking-tight text-apple-orange">{isLoading ? '-' : summary?.filtered || 0}</div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Section 2: Filter Breakdown */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
          <h2 className="text-lg font-semibold tracking-tight mb-6">过滤原因分布</h2>
          {isLoading ? (
            <div className="space-y-4 animate-pulse">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="h-6 bg-gray-100 rounded" />
              ))}
            </div>
          ) : !summary?.filter_breakdown || Object.keys(summary.filter_breakdown).length === 0 ? (
            <div className="h-32 flex items-center justify-center text-gray-400">
              暂无过滤记录
            </div>
          ) : (
            <div className="space-y-4">
              {Object.entries(summary.filter_breakdown).map(([key, value]: [string, any]) => {
                const label = translateFilterStage(key);
                const maxVal = Math.max(...Object.values(summary.filter_breakdown) as number[]);
                return (
                  <div key={key}>
                    <div className="flex justify-between text-sm mb-1.5">
                      <span className="text-gray-600 font-medium">{label}</span>
                      <span className="text-gray-900 font-mono">{value} 次</span>
                    </div>
                    <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
                      <div className="bg-apple-orange h-full rounded-full" style={{ width: `${(value / maxVal) * 100}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Section 3: Recent Attempts Table */}
        <div className="lg:col-span-2 bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden flex flex-col">
          <div className="p-5 border-b border-gray-100">
            <h2 className="text-lg font-semibold tracking-tight">最近处理记录</h2>
          </div>
          <div className="overflow-x-auto flex-1">
            <table className="w-full text-sm text-left whitespace-nowrap">
              <thead className="text-xs text-gray-500 bg-gray-50/50 uppercase border-b border-gray-100">
                <tr>
                  <th className="px-6 py-4 font-medium">时间</th>
                  <th className="px-6 py-4 font-medium">币种</th>
                  <th className="px-6 py-4 font-medium">策略</th>
                  <th className="px-6 py-4 font-medium">方向</th>
                  <th className="px-6 py-4 font-medium">形态评分</th>
                  <th className="px-6 py-4 font-medium">最终结果</th>
                  <th className="px-6 py-4 font-medium">过滤原因</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {isLoading ? (
                  [...Array(5)].map((_, i) => (
                    <tr key={i} className="animate-pulse">
                      <td className="px-6 py-4"><div className="h-4 bg-gray-100 rounded w-24" /></td>
                      <td className="px-6 py-4"><div className="h-4 bg-gray-100 rounded w-16" /></td>
                      <td className="px-6 py-4"><div className="h-4 bg-gray-100 rounded w-12" /></td>
                      <td className="px-6 py-4"><div className="h-4 bg-gray-100 rounded w-8" /></td>
                      <td className="px-6 py-4"><div className="h-4 bg-gray-100 rounded w-8" /></td>
                      <td className="px-6 py-4"><div className="h-4 bg-gray-100 rounded w-16" /></td>
                      <td className="px-6 py-4"><div className="h-4 bg-gray-100 rounded w-32" /></td>
                    </tr>
                  ))
                ) : recentAttempts.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-6 py-20 text-center text-gray-400">
                      暂无处理记录
                    </td>
                  </tr>
                ) : (
                  recentAttempts.map((attempt: any) => {
                    const isLong = attempt.direction === 'long';
                    const isShort = attempt.direction === 'short';
                    
                    return (
                      <tr key={attempt.id} className="hover:bg-gray-50/50 transition-colors">
                        <td className="px-6 py-4 text-gray-500">
                          {format(new Date(attempt.created_at), 'MM-dd HH:mm:ss')}
                        </td>
                        <td className="px-6 py-4 font-semibold text-gray-900">
                          <div className="flex items-center gap-2">
                            {attempt.symbol.replace(':USDT', '')}
                            <span className="px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded text-[10px] font-mono">
                              {attempt.timeframe}
                            </span>
                          </div>
                        </td>
                        <td className="px-6 py-4 text-gray-600">{attempt.strategy_name}</td>
                        <td className="px-6 py-4">
                          {attempt.direction ? (
                            <span className={cn(
                              "px-2 py-1 rounded text-xs font-medium",
                              isLong ? "bg-apple-green/10 text-apple-green" : "bg-apple-red/10 text-apple-red"
                            )}>
                              {isLong ? '多' : '空'}
                            </span>
                          ) : (
                            <span className="text-gray-400">—</span>
                          )}
                        </td>
                        <td className="px-6 py-4 font-mono text-gray-600">
                          {attempt.pattern_score !== null ? attempt.pattern_score.toFixed(2) : '—'}
                        </td>
                        <td className="px-6 py-4">
                          {attempt.final_result === 'SIGNAL_FIRED' && (
                            <span className="flex items-center gap-1.5 text-apple-green font-medium text-xs">
                              <div className="w-2 h-2 rounded-full bg-apple-green" /> 信号触发
                            </span>
                          )}
                          {attempt.final_result === 'FILTERED' && (
                            <span className="flex items-center gap-1.5 text-apple-orange font-medium text-xs">
                              <div className="w-2 h-2 rounded-full bg-apple-orange" /> 被过滤
                            </span>
                          )}
                          {attempt.final_result === 'NO_PATTERN' && (
                            <span className="flex items-center gap-1.5 text-gray-400 font-medium text-xs">
                              <div className="w-2 h-2 rounded-full border-2 border-gray-300" /> 无形态
                            </span>
                          )}
                        </td>
                        <td className="px-6 py-4 text-xs">
                          {attempt.filter_stage ? (
                            <div className="flex flex-col">
                              <span className="font-medium text-gray-700">{translateFilterStage(attempt.filter_stage)}</span>
                              <span className="text-gray-500 truncate max-w-[200px]" title={attempt.filter_reason}>
                                {attempt.filter_reason}
                              </span>
                            </div>
                          ) : (
                            <span className="text-gray-400">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
