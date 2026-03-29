import { useState } from 'react';
import { useApi } from '../lib/api';
import { format } from 'date-fns';
import { zhCN } from 'date-fns/locale';
import { Filter, X, ChevronLeft, ChevronRight, Trash2, CheckSquare, Square } from 'lucide-react';
import { cn } from '../lib/utils';
import { deleteAttempts, type SignalAttempt, type TraceNode } from '../lib/api';
import TraceTreeViewer from '../components/TraceTreeViewer';

// Strategy badge colors
const STRATEGY_COLORS: Record<string, string> = {
  pinbar: 'bg-purple-100 text-purple-700',
  engulfing: 'bg-orange-100 text-orange-700',
};

const getStrategyBadgeClass = (strategy?: string): string => {
  if (!strategy) return 'bg-gray-100 text-gray-500';
  const key = strategy.toLowerCase();
  return STRATEGY_COLORS[key] || 'bg-gray-100 text-gray-500';
};

const translateStrategy = (strategy?: string): string => {
  if (!strategy) return '-';
  const key = strategy.toLowerCase();
  if (key === 'pinbar') return 'Pinbar';
  if (key === 'engulfing') return 'Engulfing';
  return strategy;
};

const translateFinalResult = (result: string): string => {
  switch (result) {
    case 'SIGNAL_FIRED': return '信号触发';
    case 'NO_PATTERN': return '无形态';
    case 'FILTERED': return '被过滤';
    default: return result;
  }
};

const getFinalResultBadgeClass = (result: string): string => {
  switch (result) {
    case 'SIGNAL_FIRED': return 'bg-apple-green/10 text-apple-green';
    case 'NO_PATTERN': return 'bg-gray-100 text-gray-600';
    case 'FILTERED': return 'bg-apple-red/10 text-apple-red';
    default: return 'bg-gray-100 text-gray-600';
  }
};

const translateFilterStage = (stage?: string | null): string => {
  if (!stage) return '-';
  switch (stage) {
    case 'ema_trend': return 'EMA 趋势过滤';
    case 'mtf': return 'MTF 过滤';
    default: return stage;
  }
};

/**
 * 将 details JSON 翻译为可读的中文报告
 */
const renderDetailsReport = (details?: Record<string, any>): string => {
  if (!details) return '无详细数据';

  const lines: string[] = [];

  // Pattern 部分
  if (details.pattern) {
    const pattern = details.pattern;
    lines.push('【形态检测】');
    if (pattern.direction) {
      lines.push(`  方向：${pattern.direction === 'long' ? '做多' : '做空'}`);
    }
    if (pattern.type) {
      const typeMap: Record<string, string> = {
        pinbar: 'Pinbar 形态',
        engulfing: '吞没形态',
        doji: '十字星',
        hammer: '锤头线',
      };
      lines.push(`  类型：${typeMap[pattern.type] || pattern.type}`);
    }
    if (pattern.score !== undefined && pattern.score !== null) {
      lines.push(`  评分：${(Number(pattern.score) * 100).toFixed(0)}%`);
    }
    if (pattern.wick_ratio !== undefined) {
      lines.push(`  影线占比：${(Number(pattern.wick_ratio) * 100).toFixed(0)}%`);
    }
    if (pattern.body_ratio !== undefined) {
      lines.push(`  实体占比：${(Number(pattern.body_ratio) * 100).toFixed(0)}%`);
    }
    lines.push('');
  }

  // Filters 部分
  if (details.filters && details.filters.length > 0) {
    lines.push('【过滤器结果】');
    details.filters.forEach((f: any, i: number) => {
      const filterNameMap: Record<string, string> = {
        ema: 'EMA 趋势',
        ema_trend: 'EMA 趋势',
        mtf: '多周期确认',
        atr: 'ATR 波动率',
        volume_surge: '成交量突增',
        volatility_filter: '波动率过滤',
        time_filter: '时间过滤',
        price_action: '价格行为',
      };
      const name = filterNameMap[f.name] || f.name;
      const status = f.passed ? '✅ 通过' : '❌ 失败';
      lines.push(`  ${i + 1}. ${name}: ${status}`);
      if (!f.passed && f.reason) {
        lines.push(`     原因：${f.reason}`);
      }
    });
  }

  return lines.join('\n');
};

const renderScore = (score?: number | string | null): string | number => {
  if (!score || Number(score) === 0) return '-';
  const scoreNum = typeof score === 'string' ? parseFloat(score) : score;
  if (isNaN(scoreNum) || scoreNum <= 0) return '-';
  return Math.round(scoreNum * 100) + '%';
};

export default function SignalAttempts() {
  const [page, setPage] = useState(1);
  const limit = 50;

  // Modal state
  const [selectedAttempt, setSelectedAttempt] = useState<SignalAttempt | null>(null);

  // Filters
  const [symbolFilter, setSymbolFilter] = useState('');
  const [timeframeFilter, setTimeframeFilter] = useState('');
  const [strategyFilter, setStrategyFilter] = useState('');
  const [resultFilter, setResultFilter] = useState('');
  const [filterStageFilter, setFilterStageFilter] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  // Selection
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isDeleting, setIsDeleting] = useState(false);

  const offset = (page - 1) * limit;

  // Build URL with all filters
  let url = `/api/attempts?limit=${limit}&offset=${offset}`;
  if (symbolFilter) url += `&symbol=${symbolFilter}`;
  if (timeframeFilter) url += `&timeframe=${timeframeFilter}`;
  if (strategyFilter) url += `&strategy_name=${strategyFilter}`;
  if (resultFilter) url += `&final_result=${resultFilter}`;
  if (filterStageFilter) url += `&filter_stage=${filterStageFilter}`;
  if (startDate) url += `&start_time=${startDate}T00:00:00Z`;
  if (endDate) url += `&end_time=${endDate}T23:59:59Z`;

  const { data, error, mutate } = useApi<{ total: number; data: SignalAttempt[] }>(url);

  const isLoading = !data && !error;
  const attempts = data?.data || [];
  const total = data?.total || 0;
  const totalPages = Math.ceil(total / limit);

  // Clear all filters
  const clearFilters = () => {
    setSymbolFilter('');
    setTimeframeFilter('');
    setStrategyFilter('');
    setResultFilter('');
    setFilterStageFilter('');
    setStartDate('');
    setEndDate('');
    setPage(1);
  };

  // Checkbox handlers
  const toggleSelectAll = () => {
    if (selectedIds.size === attempts.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(attempts.map(a => a.id)));
    }
  };

  const toggleSelectOne = (id: string) => {
    const newSet = new Set(selectedIds);
    if (newSet.has(id)) {
      newSet.delete(id);
    } else {
      newSet.add(id);
    }
    setSelectedIds(newSet);
  };

  // Delete handlers
  const handleDeleteSelected = async () => {
    if (selectedIds.size === 0) return;
    if (!confirm(`确定要删除选中的 ${selectedIds.size} 条尝试记录吗？此操作不可恢复。`)) return;

    setIsDeleting(true);
    try {
      await deleteAttempts({ ids: Array.from(selectedIds) });
      await mutate();
      setSelectedIds(new Set());
    } catch (err) {
      alert('删除失败，请重试');
    } finally {
      setIsDeleting(false);
    }
  };

  const handleDeleteAll = async () => {
    const filterDesc = [];
    if (symbolFilter) filterDesc.push(`币种=${symbolFilter}`);
    if (timeframeFilter) filterDesc.push(`周期=${timeframeFilter}`);
    if (strategyFilter) filterDesc.push(`策略=${strategyFilter}`);
    if (resultFilter) filterDesc.push(`结果=${translateFinalResult(resultFilter)}`);
    if (filterStageFilter) filterDesc.push(`过滤阶段=${translateFilterStage(filterStageFilter)}`);
    if (startDate) filterDesc.push(`开始日期=${startDate}`);
    if (endDate) filterDesc.push(`结束日期=${endDate}`);

    const filterText = filterDesc.length > 0 ? `（当前筛选：${filterDesc.join(', ')}）` : '（全部数据）';
    if (!confirm(`警告：此操作将删除所有匹配的尝试记录${filterText}。\n\n确定要继续吗？此操作不可恢复。`)) return;

    setIsDeleting(true);
    try {
      const payload: any = { delete_all: true };
      if (symbolFilter) payload.symbol = symbolFilter;
      if (timeframeFilter) payload.timeframe = timeframeFilter;
      if (strategyFilter) payload.strategy_name = strategyFilter;
      if (resultFilter) payload.final_result = resultFilter;
      if (filterStageFilter) payload.filter_stage = filterStageFilter;
      if (startDate) payload.start_time = `${startDate}T00:00:00Z`;
      if (endDate) payload.end_time = `${endDate}T23:59:59Z`;

      await deleteAttempts(payload);
      await mutate();
      setSelectedIds(new Set());
      setPage(1);
    } catch (err) {
      alert('删除失败，请重试');
    } finally {
      setIsDeleting(false);
    }
  };

  const handleClearAllHistory = async () => {
    if (!confirm('⚠️ 危险操作警告：此操作将删除所有尝试记录，包括所有币种、所有策略的数据。\n\n确定要继续吗？此操作不可恢复。')) return;

    setIsDeleting(true);
    try {
      await deleteAttempts({ delete_all: true });
      await mutate();
      setSelectedIds(new Set());
      setPage(1);
      clearFilters();
    } catch (err) {
      alert('删除失败，请重试');
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">尝试溯源日志</h1>
          <p className="text-sm text-gray-500 mt-1">查看每次 K 线触发的策略尝试与过滤详情</p>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-2 bg-white p-2 rounded-xl shadow-sm border border-gray-100">
          <div className="flex items-center gap-1.5 px-2 text-gray-400">
            <Filter className="w-4 h-4" />
          </div>

          <select
            value={symbolFilter}
            onChange={(e) => { setSymbolFilter(e.target.value); setPage(1); }}
            className="bg-gray-50 border-none text-sm rounded-lg focus:ring-0 py-1.5 px-3 outline-none"
          >
            <option value="">全部币种</option>
            <option value="BTC/USDT:USDT">BTC</option>
            <option value="ETH/USDT:USDT">ETH</option>
            <option value="SOL/USDT:USDT">SOL</option>
            <option value="BNB/USDT:USDT">BNB</option>
          </select>

          <select
            value={timeframeFilter}
            onChange={(e) => { setTimeframeFilter(e.target.value); setPage(1); }}
            className="bg-gray-50 border-none text-sm rounded-lg focus:ring-0 py-1.5 px-3 outline-none"
          >
            <option value="">全部周期</option>
            <option value="15m">15 分钟</option>
            <option value="1h">1 小时</option>
            <option value="4h">4 小时</option>
            <option value="1d">1 天</option>
          </select>

          <select
            value={strategyFilter}
            onChange={(e) => { setStrategyFilter(e.target.value); setPage(1); }}
            className="bg-gray-50 border-none text-sm rounded-lg focus:ring-0 py-1.5 px-3 outline-none"
          >
            <option value="">全部策略</option>
            <option value="pinbar">Pinbar</option>
            <option value="engulfing">Engulfing</option>
          </select>

          <select
            value={resultFilter}
            onChange={(e) => { setResultFilter(e.target.value); setPage(1); }}
            className="bg-gray-50 border-none text-sm rounded-lg focus:ring-0 py-1.5 px-3 outline-none"
          >
            <option value="">全部结果</option>
            <option value="SIGNAL_FIRED">信号触发</option>
            <option value="NO_PATTERN">无形态</option>
            <option value="FILTERED">被过滤</option>
          </select>

          <select
            value={filterStageFilter}
            onChange={(e) => { setFilterStageFilter(e.target.value); setPage(1); }}
            className="bg-gray-50 border-none text-sm rounded-lg focus:ring-0 py-1.5 px-3 outline-none"
          >
            <option value="">全部过滤阶段</option>
            <option value="ema_trend">EMA 趋势</option>
            <option value="mtf">MTF 验证</option>
          </select>

          <div className="flex items-center gap-2">
            <input
              type="date"
              value={startDate}
              onChange={(e) => { setStartDate(e.target.value); setPage(1); }}
              className="bg-gray-50 border-none text-sm rounded-lg focus:ring-0 py-1.5 px-3 outline-none"
              placeholder="开始日期"
            />
            <span className="text-gray-400 text-xs">-</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => { setEndDate(e.target.value); setPage(1); }}
              className="bg-gray-50 border-none text-sm rounded-lg focus:ring-0 py-1.5 px-3 outline-none"
              placeholder="结束日期"
            />
          </div>

          {(symbolFilter || timeframeFilter || strategyFilter || resultFilter || filterStageFilter || startDate || endDate) && (
            <button
              onClick={clearFilters}
              className="p-1.5 text-gray-400 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
              title="清空筛选"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Clear All History Button */}
        <button
          onClick={handleClearAllHistory}
          disabled={isDeleting}
          className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-apple-red rounded-lg hover:bg-apple-red/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
          title="删除所有尝试记录"
        >
          <Trash2 className="w-4 h-4" />
          清空所有尝试
        </button>
      </div>

      {/* Action Bar */}
      {selectedIds.size > 0 && (
        <div className="flex items-center justify-between bg-apple-blue/5 rounded-xl p-3 border border-apple-blue/20">
          <div className="flex items-center gap-2">
            <CheckSquare className="w-4 h-4 text-apple-blue" />
            <span className="text-sm font-medium text-apple-blue">已选中 {selectedIds.size} 条记录</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleDeleteSelected}
              disabled={isDeleting}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-apple-red rounded-lg hover:bg-apple-red/90 disabled:opacity-50 transition-colors"
            >
              <Trash2 className="w-3.5 h-3.5" />
              删除选中项
            </button>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden flex flex-col min-h-[600px]">
        <div className="overflow-x-auto flex-1">
          <table className="w-full text-sm text-left whitespace-nowrap">
            <thead className="text-xs text-gray-500 bg-gray-50/50 uppercase border-b border-gray-100">
              <tr>
                <th className="px-6 py-4 font-medium w-12">
                  <button
                    onClick={toggleSelectAll}
                    className="hover:opacity-70 transition-opacity"
                    title={selectedIds.size === attempts.length ? '取消全选' : '全选'}
                  >
                    {selectedIds.size === attempts.length && attempts.length > 0 ? (
                      <CheckSquare className="w-4 h-4 text-apple-blue" />
                    ) : (
                      <Square className="w-4 h-4" />
                    )}
                  </button>
                </th>
                <th className="px-6 py-4 font-medium">时间</th>
                <th className="px-6 py-4 font-medium">币种</th>
                <th className="px-6 py-4 font-medium">周期</th>
                <th className="px-6 py-4 font-medium">策略</th>
                <th className="px-6 py-4 font-medium">形态评分</th>
                <th className="px-6 py-4 font-medium">最终结果</th>
                <th className="px-6 py-4 font-medium">过滤阶段</th>
                <th className="px-6 py-4 font-medium">过滤原因</th>
                <th className="px-6 py-4 font-medium">详情</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {isLoading ? (
                [...Array(10)].map((_, i) => (
                  <tr key={i} className="animate-pulse">
                    <td className="px-6 py-4"><div className="h-4 bg-gray-100 rounded w-4" /></td>
                    <td className="px-6 py-4"><div className="h-4 bg-gray-100 rounded w-24" /></td>
                    <td className="px-6 py-4"><div className="h-4 bg-gray-100 rounded w-16" /></td>
                    <td className="px-6 py-4"><div className="h-4 bg-gray-100 rounded w-8" /></td>
                    <td className="px-6 py-4"><div className="h-4 bg-gray-100 rounded w-20" /></td>
                    <td className="px-6 py-4"><div className="h-4 bg-gray-100 rounded w-16" /></td>
                    <td className="px-6 py-4"><div className="h-4 bg-gray-100 rounded w-20" /></td>
                    <td className="px-6 py-4"><div className="h-4 bg-gray-100 rounded w-24" /></td>
                    <td className="px-6 py-4"><div className="h-4 bg-gray-100 rounded w-32" /></td>
                    <td className="px-6 py-4"><div className="h-4 bg-gray-100 rounded w-16" /></td>
                  </tr>
                ))
              ) : attempts.length === 0 ? (
                <tr>
                  <td colSpan={10} className="px-6 py-20 text-center text-gray-400">
                    没有找到符合条件的尝试记录
                  </td>
                </tr>
              ) : (
                attempts.map((attempt) => {
                  const isSelected = selectedIds.has(attempt.id);

                  return (
                    <tr
                      key={String(attempt.id)}
                      className={cn(
                        "hover:bg-gray-50/50 transition-colors",
                        isSelected && "bg-apple-blue/5"
                      )}
                    >
                      <td className="px-6 py-4">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            toggleSelectOne(attempt.id);
                          }}
                          className="hover:opacity-70 transition-opacity"
                        >
                          {isSelected ? (
                            <CheckSquare className="w-4 h-4 text-apple-blue" />
                          ) : (
                            <Square className="w-4 h-4" />
                          )}
                        </button>
                      </td>
                      <td className="px-6 py-4 text-gray-500">
                        {format(new Date(attempt.created_at), 'MM-dd HH:mm:ss', { locale: zhCN })}
                      </td>
                      <td className="px-6 py-4 font-semibold text-gray-900">
                        {attempt.symbol.replace(':USDT', '')}
                      </td>
                      <td className="px-6 py-4">
                        <span className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs font-mono">
                          {attempt.timeframe}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <span className={cn(
                          "px-2 py-1 rounded text-xs font-medium",
                          getStrategyBadgeClass(attempt.strategy_name)
                        )}>
                          {translateStrategy(attempt.strategy_name)}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <span className={cn(
                          "text-xs font-mono",
                          attempt.pattern_score && Number(attempt.pattern_score) > 0
                            ? "text-gray-700"
                            : "text-gray-400"
                        )}>
                          {renderScore(attempt.pattern_score)}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <span className={cn(
                          "px-2 py-1 rounded text-xs font-medium",
                          getFinalResultBadgeClass(attempt.final_result)
                        )}>
                          {translateFinalResult(attempt.final_result)}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-gray-600 text-xs">
                        {translateFilterStage(attempt.filter_stage)}
                      </td>
                      <td className="px-6 py-4 text-gray-500 text-xs max-w-xs truncate">
                        {attempt.filter_reason || '-'}
                      </td>
                      <td className="px-6 py-4">
                        {attempt.details ? (
                          <button
                            onClick={() => setSelectedAttempt(attempt)}
                            className="text-xs text-apple-blue hover:underline"
                          >
                            查看详情
                          </button>
                        ) : (
                          <span className="text-gray-400 text-xs">-</span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination & Delete All */}
        <div className="p-4 border-t border-gray-100 flex items-center justify-between bg-gray-50/30">
          <div className="flex items-center gap-4">
            <div className="text-sm text-gray-500">
              共 <span className="font-medium text-gray-900">{total}</span> 条 / 第 <span className="font-medium text-gray-900">{page}</span> 页
            </div>
            {(symbolFilter || timeframeFilter || strategyFilter || resultFilter || filterStageFilter || startDate || endDate) && (
              <button
                onClick={handleDeleteAll}
                disabled={isDeleting}
                className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-apple-red bg-white border border-apple-red/30 rounded-lg hover:bg-apple-red/5 disabled:opacity-50 transition-colors"
                title="删除当前筛选条件下的所有记录"
              >
                <Trash2 className="w-3.5 h-3.5" />
                清空当前筛选匹配项
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1 || isLoading}
              className="p-1.5 rounded-lg border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages || isLoading}
              className="p-1.5 rounded-lg border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Detail Modal */}
      {selectedAttempt && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm"
          onClick={() => setSelectedAttempt(null)}
        >
          <div
            className="bg-white rounded-2xl shadow-2xl max-w-3xl w-full max-h-[80vh] overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">尝试详情</h2>
                <p className="text-xs text-gray-500 mt-0.5">
                  {selectedAttempt.symbol} · {selectedAttempt.timeframe} · {selectedAttempt.strategy_name}
                </p>
              </div>
              <button
                onClick={() => setSelectedAttempt(null)}
                className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="px-6 py-4 overflow-y-auto max-h-[calc(80vh-120px)] space-y-4">
              {/* Priority 1: Evaluation Summary (if available) */}
              {selectedAttempt.evaluation_summary ? (
                <div className="bg-gray-50 rounded-xl p-4 border border-gray-200">
                  <h3 className="text-sm font-semibold text-gray-700 mb-2">评估报告</h3>
                  <pre className="text-sm text-gray-800 whitespace-pre-wrap font-sans leading-relaxed">
                    {selectedAttempt.evaluation_summary}
                  </pre>
                </div>
              ) : null}

              {/* Priority 2: Trace Tree Visualization (if available) */}
              {selectedAttempt.trace_tree ? (
                <TraceTreeViewer
                  traceTree={selectedAttempt.trace_tree}
                  signalFired={selectedAttempt.final_result === 'SIGNAL_FIRED'}
                />
              ) : null}

              {/* Priority 3: Fallback to legacy details rendering */}
              {(!selectedAttempt.evaluation_summary && !selectedAttempt.trace_tree) && (
                <div className="bg-gray-50 rounded-xl p-4 border border-gray-200">
                  <h3 className="text-sm font-semibold text-gray-700 mb-2">详细数据</h3>
                  <pre className="text-sm text-gray-800 whitespace-pre-wrap font-mono text-xs leading-relaxed">
                    {renderDetailsReport(selectedAttempt.details)}
                  </pre>
                </div>
              )}

              {/* Meta Info */}
              <div className="grid grid-cols-2 gap-4 pt-4 border-t border-gray-100">
                <div>
                  <div className="text-xs text-gray-500">形态评分</div>
                  <div className="text-sm font-medium text-gray-900">
                    {renderScore(selectedAttempt.pattern_score)}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-500">最终结果</div>
                  <div className="text-sm font-medium">
                    <span className={cn(
                      "px-2 py-1 rounded text-xs font-medium",
                      getFinalResultBadgeClass(selectedAttempt.final_result)
                    )}>
                      {translateFinalResult(selectedAttempt.final_result)}
                    </span>
                  </div>
                </div>
                {selectedAttempt.filter_stage && (
                  <div>
                    <div className="text-xs text-gray-500">过滤阶段</div>
                    <div className="text-sm font-medium text-gray-900">
                      {translateFilterStage(selectedAttempt.filter_stage)}
                    </div>
                  </div>
                )}
                {selectedAttempt.filter_reason && (
                  <div>
                    <div className="text-xs text-gray-500">过滤原因</div>
                    <div className="text-sm font-medium text-gray-900">
                      {selectedAttempt.filter_reason}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
