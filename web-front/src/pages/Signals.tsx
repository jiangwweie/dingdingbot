import { useState, useEffect, useCallback, Fragment } from 'react';
import { useApi } from '../lib/api';
import { Filter, X, ChevronLeft, ChevronRight, ArrowRight, Trash2, CheckSquare, Square, Settings, GripVertical, ChevronUp, ChevronDown, MoreVertical, Calendar, SlidersHorizontal, ArrowUpDown, AlertTriangle } from 'lucide-react';
import { cn, formatBeijingTime } from '../lib/utils';
import SignalDetailsModal from '../components/SignalDetailsDrawer';
import { deleteSignals, type Signal, SignalStatus } from '../lib/api';
import { SignalStatusBadge } from '../components/SignalStatusBadge';

// Strategy badge colors
const STRATEGY_COLORS: Record<string, string> = {
  pinbar: 'bg-purple-100 text-purple-700',
  engulfing: 'bg-orange-100 text-orange-700',
};

// Column configuration types and defaults
interface ColumnConfig {
  id: string;
  label: string;
  visible: boolean;
}

const DEFAULT_COLUMNS: ColumnConfig[] = [
  { id: 'time', label: '时间', visible: true },
  { id: 'symbol', label: '币种', visible: true },
  { id: 'timeframe', label: '周期', visible: true },
  { id: 'direction', label: '方向', visible: true },
  { id: 'strategy', label: '生成策略', visible: true },
  { id: 'score', label: '形态评分', visible: true },
  { id: 'entry_price', label: '入场价', visible: true },
  { id: 'stop_loss', label: '止损价', visible: true },
  { id: 'position_size', label: '建议仓位', visible: true },
  { id: 'leverage', label: '杠杆', visible: true },
  { id: 'ema_trend', label: 'EMA 趋势', visible: true },
  { id: 'mtf_status', label: 'MTF 状态', visible: true },
  { id: 'status', label: '信号状态', visible: true },
  { id: 'pnl_ratio', label: '盈亏比', visible: true },
  { id: 'coverage', label: '信号覆盖', visible: true },  // 新增：信号覆盖信息
  { id: 'action', label: '操作', visible: true },
];

const STORAGE_KEY = 'signal_table_columns_config';

const getStrategyBadgeClass = (strategy?: string | null): string => {
  if (!strategy) return 'bg-gray-100 text-gray-500';
  const key = strategy.toLowerCase();
  return STRATEGY_COLORS[key] || 'bg-gray-100 text-gray-500';
};

const translateStrategy = (strategy?: string | null): string => {
  if (!strategy) return '-';
  const key = strategy.toLowerCase();
  if (key === 'pinbar') return 'Pinbar';
  if (key === 'engulfing') return 'Engulfing';
  return strategy;
};

const renderScore = (score?: number | string | null): string | { percentage: number; width: number } => {
  if (!score || Number(score) === 0) return '-';
  const scoreNum = typeof score === 'string' ? parseFloat(score) : score;
  if (isNaN(scoreNum) || scoreNum <= 0) return '-';
  const percentage = Math.round(scoreNum * 100);
  return { percentage, width: percentage };
};

export default function Signals() {
  const [page, setPage] = useState(1);
  const limit = 20;

  // Column configuration state
  const [columns, setColumns] = useState<ColumnConfig[]>(DEFAULT_COLUMNS);
  const [isColumnConfigOpen, setIsColumnConfigOpen] = useState(false);

  // Load column config from localStorage on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        // Merge with defaults to handle any new columns
        const merged = DEFAULT_COLUMNS.map(defaultCol => {
          const savedCol = parsed.find((c: ColumnConfig) => c.id === defaultCol.id);
          return savedCol || defaultCol;
        });
        // Add any saved columns that aren't in defaults (for future expansion)
        const savedOnly = parsed.filter((c: ColumnConfig) =>
          !DEFAULT_COLUMNS.some(dc => dc.id === c.id)
        );
        setColumns([...merged, ...savedOnly]);
      }
    } catch (e) {
      console.error('Failed to load column config:', e);
    }
  }, []);

  // Save column config to localStorage whenever it changes
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(columns));
    } catch (e) {
      console.error('Failed to save column config:', e);
    }
  }, [columns]);

  // Toggle column visibility
  const toggleColumn = (columnId: string) => {
    setColumns(cols => cols.map(col =>
      col.id === columnId ? { ...col, visible: !col.visible } : col
    ));
  };

  // Move column up or down
  const moveColumn = (index: number, direction: 'up' | 'down') => {
    setColumns(cols => {
      const newCols = [...cols];
      const newIndex = direction === 'up' ? index - 1 : index + 1;
      if (newIndex < 0 || newIndex >= newCols.length) return cols;
      [newCols[index], newCols[newIndex]] = [newCols[newIndex], newCols[index]];
      return newCols;
    });
  };

  // Reset columns to defaults
  const resetColumns = () => {
    setColumns(DEFAULT_COLUMNS);
  };

  // Get visible columns
  const visibleColumns = columns.filter(col => col.visible);

  // Helper to render cell content based on column id
  const renderCell = (signal: Signal, columnId: string) => {
    const isLong = signal.direction === 'long';
    const statusClass = getStatusBadgeClass(signal.status);
    const pnlRatio = signal.pnl_ratio !== null && signal.pnl_ratio !== undefined ? parseFloat(signal.pnl_ratio) : null;
    const pnlColorClass = pnlRatio !== null
      ? (pnlRatio >= 0 ? 'text-apple-green' : 'text-apple-red')
      : 'text-gray-400';

    // Use kline_timestamp if available, fallback to created_at
    // Display in Beijing Time (UTC+8) for consistency with Binance App
    const displayTime = signal.kline_timestamp
      ? formatBeijingTime(signal.kline_timestamp, 'short')
      : formatBeijingTime(signal.created_at, 'short');

    switch (columnId) {
      case 'time':
        return <td className="px-6 py-4 text-gray-500">{displayTime}</td>;
      case 'symbol':
        return (
          <td className="px-6 py-4 font-semibold text-gray-900">
            {signal.symbol.replace(':USDT', '')}
          </td>
        );
      case 'timeframe':
        return (
          <td className="px-6 py-4">
            <span className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs font-mono">
              {signal.timeframe}
            </span>
          </td>
        );
      case 'direction':
        return (
          <td className="px-6 py-4">
            <span className={cn(
              "px-2 py-1 rounded text-xs font-medium",
              isLong ? "bg-apple-green/10 text-apple-green" : "bg-apple-red/10 text-apple-red"
            )}>
              {isLong ? '多' : '空'}
            </span>
          </td>
        );
      case 'strategy':
        return (
          <td className="px-6 py-4">
            <span className={cn(
              "px-2 py-1 rounded text-xs font-medium",
              getStrategyBadgeClass(signal.strategy_name)
            )}>
              {translateStrategy(signal.strategy_name)}
            </span>
          </td>
        );
      case 'score': {
        const scoreResult = renderScore(signal.score);
        if (typeof scoreResult === 'object') {
          return (
            <td className="px-6 py-4">
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono text-gray-700 w-8">
                  {scoreResult.percentage}%
                </span>
                <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className={cn(
                      "h-full rounded-full transition-all",
                      scoreResult.percentage >= 70 ? "bg-apple-green" :
                      scoreResult.percentage >= 40 ? "bg-yellow-500" :
                      "bg-apple-red"
                    )}
                    style={{ width: `${scoreResult.width}%` }}
                  />
                </div>
              </div>
            </td>
          );
        } else {
          return <td className="px-6 py-4"><span className="text-gray-400 text-xs">-</span></td>;
        }
      }
      case 'entry_price':
        return <td className="px-6 py-4 text-right font-mono text-gray-900">{signal.entry_price}</td>;
      case 'stop_loss':
        return <td className="px-6 py-4 text-right font-mono text-gray-500">{signal.stop_loss}</td>;
      case 'position_size':
        return <td className="px-6 py-4 text-right font-mono text-gray-900">{signal.position_size}</td>;
      case 'leverage':
        return <td className="px-6 py-4 text-right text-gray-500">{signal.leverage}x</td>;
      case 'ema_trend':
        return (
          <td className="px-6 py-4">
            <span className={cn(
              "text-xs font-medium",
              signal.ema_trend === 'bullish' ? "text-apple-green" : "text-apple-red"
            )}>
              {translateEmaTrend(signal.ema_trend)}
            </span>
          </td>
        );
      case 'mtf_status':
        return <td className="px-6 py-4 text-gray-600 text-xs">{translateMtfStatus(signal.mtf_status)}</td>;
      case 'status':
        return (
          <td className="px-6 py-4">
            <div className="flex items-center gap-2">
              {signal.status ? (
                <SignalStatusBadge status={signal.status} />
              ) : (
                <span className="text-gray-400 text-xs">-</span>
              )}
              {/* 被替代提示 */}
              {signal.superseded_by && (
                <span className="text-xs text-gray-500" title="已被更高分信号替代">
                  被替代
                </span>
              )}
            </div>
          </td>
        );
      case 'pnl_ratio':
        return (
          <td className="px-6 py-4 text-right font-mono text-xs">
            {pnlRatio !== undefined && pnlRatio !== null ? (
              <span className={pnlColorClass}>
                {pnlRatio > 0 ? '+' : ''}{pnlRatio.toFixed(2)}
              </span>
            ) : (
              <span className="text-gray-400">-</span>
            )}
          </td>
        );
      case 'coverage':
        return (
          <td className="px-6 py-4">
            <div className="flex items-center gap-2">
              {/* 被替代提示 */}
              {signal.superseded_by ? (
                <span className="px-2 py-1 rounded text-xs font-medium bg-gray-100 text-gray-600" title="已被更高分信号替代">
                  已被替代
                </span>
              ) : signal.opposing_signal_id ? (
                /* 对立信号提示 */
                <div className="flex items-center gap-1.5">
                  <AlertTriangle className="w-4 h-4 text-amber-500" />
                  <span className="text-xs text-amber-700">
                    反向信号 {signal.opposing_signal_score ? `(分 ${(parseFloat(String(signal.opposing_signal_score)) * 100).toFixed(0)})` : ''}
                  </span>
                </div>
              ) : (
                <span className="text-gray-400 text-xs">-</span>
              )}
            </div>
          </td>
        );
      case 'action':
        return (
          <td className="px-6 py-4">
            <button
              onClick={(e) => {
                e.stopPropagation();
                openModal(signal.id);
              }}
              className="opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1 text-xs text-apple-blue hover:underline"
            >
              详情 <ArrowRight className="w-3 h-3" />
            </button>
          </td>
        );
      default:
        return <td className="px-6 py-4" />;
    }
  };

  // Filters
  const [symbolFilter, setSymbolFilter] = useState('');
  const [directionFilter, setDirectionFilter] = useState('');
  const [timeframeFilter, setTimeframeFilter] = useState('');
  const [strategyFilter, setStrategyFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');  // '' = all, 'live', 'backtest'
  const [hideSuperseded, setHideSuperseded] = useState(false);  // 隐藏被替代信号
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [sortBy, setSortBy] = useState('created_at');
  const [order, setOrder] = useState('desc');

  // Selection
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isDeleting, setIsDeleting] = useState(false);
  const [showActionMenu, setShowActionMenu] = useState(false);

  // Modal
  const [selectedSignalId, setSelectedSignalId] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const offset = (page - 1) * limit;

  // Build URL with all filters
  let url = `/api/signals?limit=${limit}&offset=${offset}`;
  if (symbolFilter) url += `&symbol=${symbolFilter}`;
  if (directionFilter) url += `&direction=${directionFilter}`;
  if (timeframeFilter) url += `&timeframe=${timeframeFilter}`;
  if (strategyFilter) url += `&strategy_name=${strategyFilter}`;
  if (statusFilter) url += `&status=${statusFilter.toUpperCase()}`;
  if (sourceFilter) url += `&source=${sourceFilter}`;
  if (startDate) url += `&start_time=${startDate}T00:00:00Z`;
  if (endDate) url += `&end_time=${endDate}T23:59:59Z`;
  if (sortBy) url += `&sort_by=${sortBy}`;
  if (order) url += `&order=${order}`;
  if (hideSuperseded) url += `&exclude_superseded=true`;

  const { data, error, mutate } = useApi<{ total: number; data: Signal[] }>(url);

  const isLoading = !data && !error;
  const signals = data?.data || [];
  const total = data?.total || 0;
  const totalPages = Math.ceil(total / limit);

  // Clear all filters
  const clearFilters = () => {
    setSymbolFilter('');
    setDirectionFilter('');
    setTimeframeFilter('');
    setStrategyFilter('');
    setStatusFilter('');
    setSourceFilter('');
    setHideSuperseded(false);
    setStartDate('');
    setEndDate('');
    setSortBy('created_at');
    setOrder('desc');
    setPage(1);
  };

  // Checkbox handlers
  const toggleSelectAll = () => {
    if (selectedIds.size === signals.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(signals.map(s => s.id)));
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

  // Modal handlers
  const openModal = (signalId: string) => {
    setSelectedSignalId(signalId);
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setSelectedSignalId(null);
  };

  // Delete handlers
  const handleDeleteSelected = async () => {
    if (selectedIds.size === 0) return;
    if (!confirm(`确定要删除选中的 ${selectedIds.size} 条信号记录吗？此操作不可恢复。`)) return;

    setIsDeleting(true);
    try {
      await deleteSignals({ ids: Array.from(selectedIds) });
      await mutate();
      setSelectedIds(new Set());
    } catch (err) {
      alert('删除失败，请重试');
    } finally {
      setIsDeleting(false);
    }
  };

  const handleClearAllHistory = async () => {
    if (!confirm('⚠️ 危险操作警告：此操作将删除所有历史信号记录，包括所有币种、所有策略的数据。\n\n确定要继续吗？此操作不可恢复。')) return;

    setIsDeleting(true);
    try {
      await deleteSignals({ delete_all: true });
      await mutate();
      setSelectedIds(new Set());
      setPage(1);
      clearFilters();
      setShowActionMenu(false);
    } catch (err) {
      alert('删除失败，请重试');
    } finally {
      setIsDeleting(false);
    }
  };

  const handleDeleteFiltered = async () => {
    const filterDesc = [];
    if (symbolFilter) filterDesc.push(`币种=${symbolFilter}`);
    if (directionFilter) filterDesc.push(`方向=${directionFilter === 'long' ? '做多' : '做空'}`);
    if (strategyFilter) filterDesc.push(`策略=${strategyFilter}`);
    if (statusFilter) filterDesc.push(`状态=${statusFilter}`);
    if (sourceFilter) filterDesc.push(`来源=${sourceFilter === 'live' ? '实盘' : '回测'}`);
    if (startDate) filterDesc.push(`开始日期=${startDate}`);
    if (endDate) filterDesc.push(`结束日期=${endDate}`);

    const filterText = filterDesc.length > 0 ? `（当前筛选：${filterDesc.join(', ')}）` : '（全部数据）';
    if (!confirm(`警告：此操作将删除所有匹配的信号记录${filterText}。\n\n确定要继续吗？此操作不可恢复。`)) return;

    setIsDeleting(true);
    try {
      const payload: any = { delete_all: true };
      if (symbolFilter) payload.symbol = symbolFilter;
      if (directionFilter) payload.direction = directionFilter;
      if (strategyFilter) payload.strategy_name = strategyFilter;
      if (statusFilter) payload.status = statusFilter.toUpperCase();
      if (sourceFilter) payload.source = sourceFilter;
      if (startDate) payload.start_time = `${startDate}T00:00:00Z`;
      if (endDate) payload.end_time = `${endDate}T23:59:59Z`;

      await deleteSignals(payload);
      await mutate();
      setSelectedIds(new Set());
      setPage(1);
      setShowActionMenu(false);
    } catch (err) {
      alert('删除失败，请重试');
    } finally {
      setIsDeleting(false);
    }
  };

  // Translation helpers
  const translateEmaTrend = (trend: string) => {
    if (trend === 'bullish') return '多头趋势';
    if (trend === 'bearish') return '空头趋势';
    return trend;
  };

  const translateMtfStatus = (status: string) => {
    switch (status) {
      case 'confirmed': return '已确认';
      case 'rejected': return '已拒绝';
      case 'disabled': return '已禁用';
      case 'unavailable': return '数据未就绪';
      default: return status;
    }
  };

  const translateSignalStatus = (status: string) => {
    switch (status) {
      case 'pending': return '监控中';
      case 'won': return '止盈';
      case 'lost': return '止损';
      default: return status;
    }
  };

  const getStatusBadgeClass = (status: string) => {
    switch (status) {
      case 'pending': return 'bg-gray-100 text-gray-600';
      case 'won': return 'bg-apple-green/10 text-apple-green';
      case 'lost': return 'bg-apple-red/10 text-apple-red';
      default: return 'bg-gray-100 text-gray-600';
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">信号历史</h1>
          <p className="text-sm text-gray-500 mt-1">查询和筛选所有历史信号记录</p>
        </div>

        <div className="flex items-center gap-3">
          {/* Action Menu */}
          <div className="relative">
            <button
              onClick={() => setShowActionMenu(!showActionMenu)}
              className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
            >
              <MoreVertical className="w-4 h-4" />
              操作
            </button>

            {showActionMenu && (
              <>
                <div
                  className="fixed inset-0 z-10"
                  onClick={() => setShowActionMenu(false)}
                />
                <div className="absolute right-0 mt-1 w-56 bg-white rounded-xl shadow-lg border border-gray-100 py-1 z-20">
                  {/* Delete Selected */}
                  <button
                    onClick={handleDeleteSelected}
                    disabled={isDeleting || selectedIds.size === 0}
                    className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50"
                  >
                    <Trash2 className="w-4 h-4" />
                    <div className="text-left">
                      <div>删除选中项</div>
                      <div className="text-xs text-gray-400">
                        {selectedIds.size > 0 ? `已选中 ${selectedIds.size} 条记录` : '请选择要删除的记录'}
                      </div>
                    </div>
                  </button>
                  <div className="h-px bg-gray-100 my-1" />
                  {/* Delete Filtered */}
                  <button
                    onClick={handleDeleteFiltered}
                    disabled={isDeleting}
                    className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-apple-red hover:bg-red-50 transition-colors disabled:opacity-50"
                  >
                    <Trash2 className="w-4 h-4" />
                    <div className="text-left">
                      <div>删除当前筛选匹配项</div>
                      <div className="text-xs text-gray-400">仅删除符合筛选条件的记录</div>
                    </div>
                  </button>
                  <div className="h-px bg-gray-100 my-1" />
                  {/* Clear All History */}
                  <button
                    onClick={handleClearAllHistory}
                    disabled={isDeleting}
                    className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-apple-red hover:bg-red-50 transition-colors disabled:opacity-50"
                  >
                    <Trash2 className="w-4 h-4" />
                    <div className="text-left">
                      <div>清空所有历史信号</div>
                      <div className="text-xs text-gray-400">删除全部记录，不可恢复</div>
                    </div>
                  </button>
                </div>
              </>
            )}
          </div>

          {/* Column Configuration */}
          <button
            onClick={() => setIsColumnConfigOpen(!isColumnConfigOpen)}
            className="flex items-center gap-1.5 px-3 py-2 text-sm text-gray-600 bg-white rounded-lg border border-gray-200 hover:bg-gray-50 transition-colors"
          >
            <Settings className="w-4 h-4" />
            自定义列
          </button>
        </div>
      </div>

      {/* Sort Controls - Independent Row */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 text-xs text-gray-500 uppercase tracking-wide">
            <ArrowUpDown className="w-3 h-3" />
            排序
          </div>
          <div className="h-4 w-px bg-gray-200" />
          <select
            value={sortBy}
            onChange={(e) => { setSortBy(e.target.value); setPage(1); }}
            className="bg-gray-50 border-none text-sm rounded-lg focus:ring-0 py-1.5 px-3 outline-none"
            title="排序字段"
          >
            <option value="created_at">按时间</option>
            <option value="pattern_score">按形态评分</option>
          </select>
          <select
            value={order}
            onChange={(e) => { setOrder(e.target.value); setPage(1); }}
            className="bg-gray-50 border-none text-sm rounded-lg focus:ring-0 py-1.5 px-3 outline-none"
            title="排序顺序"
          >
            <option value="desc">降序</option>
            <option value="asc">升序</option>
          </select>
        </div>
      </div>

      {/* Filters - Two Rows with Visual Groups */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 space-y-3">
        {/* Basic Filters */}
        <div className="space-y-1.5">
          <div className="flex items-center gap-2 text-xs text-gray-500 uppercase tracking-wide">
            <SlidersHorizontal className="w-3 h-3" />
            基础筛选
          </div>
          <div className="flex flex-wrap items-center gap-2">
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
              value={directionFilter}
              onChange={(e) => { setDirectionFilter(e.target.value); setPage(1); }}
              className="bg-gray-50 border-none text-sm rounded-lg focus:ring-0 py-1.5 px-3 outline-none"
            >
              <option value="">全部方向</option>
              <option value="long">做多</option>
              <option value="short">做空</option>
            </select>

            <select
              value={timeframeFilter}
              onChange={(e) => { setTimeframeFilter(e.target.value); setPage(1); }}
              className="bg-gray-50 border-none text-sm rounded-lg focus:ring-0 py-1.5 px-3 outline-none"
            >
              <option value="">全部周期</option>
              <option value="15m">15m</option>
              <option value="1h">1h</option>
              <option value="4h">4h</option>
              <option value="1d">1d</option>
            </select>

            <select
              value={statusFilter}
              onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
              className="bg-gray-50 border-none text-sm rounded-lg focus:ring-0 py-1.5 px-3 outline-none"
            >
              <option value="">全部状态</option>
              <option value="active">监控中</option>
              <option value="superseded">已替代</option>
              <option value="won">止盈</option>
              <option value="lost">止损</option>
            </select>

            {/* 隐藏被替代信号开关 */}
            <label className="flex items-center gap-2 px-3 py-1.5 bg-amber-50 border border-amber-200 rounded-lg cursor-pointer hover:bg-amber-100 transition-colors">
              <input
                type="checkbox"
                checked={hideSuperseded}
                onChange={(e) => { setHideSuperseded(e.target.checked); setPage(1); }}
                className="w-4 h-4 text-apple-blue border-gray-300 rounded focus:ring-apple-blue"
              />
              <span className="text-sm text-amber-800 font-medium">仅看有效信号</span>
            </label>
          </div>
        </div>

        {/* Advanced Filters */}
        <div className="space-y-1.5 pt-2 border-t border-gray-100">
          <div className="flex items-center gap-2 text-xs text-gray-500 uppercase tracking-wide">
            <Calendar className="w-3 h-3" />
            高级筛选
          </div>
          <div className="flex flex-wrap items-center gap-2">
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
              value={sourceFilter}
              onChange={(e) => { setSourceFilter(e.target.value); setPage(1); }}
              className="bg-gray-50 border-none text-sm rounded-lg focus:ring-0 py-1.5 px-3 outline-none"
            >
              <option value="">全部来源</option>
              <option value="live">实盘信号</option>
              <option value="backtest">回测信号</option>
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

            {(symbolFilter || directionFilter || strategyFilter || statusFilter || sourceFilter || startDate || endDate) && (
              <button
                onClick={clearFilters}
                className="flex items-center gap-1 px-2 py-1.5 text-xs text-gray-500 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <X className="w-3.5 h-3.5" />
                清空筛选
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Column Configuration Panel */}
      <div className="relative">
        <button
          onClick={() => setIsColumnConfigOpen(!isColumnConfigOpen)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-600 bg-white rounded-lg border border-gray-200 hover:bg-gray-50 transition-colors"
        >
          <Settings className="w-4 h-4" />
          自定义列
        </button>

        {isColumnConfigOpen && (
          <>
            {/* Backdrop */}
            <div
              className="fixed inset-0 z-40"
              onClick={() => setIsColumnConfigOpen(false)}
            />

            {/* Panel */}
            <div className="absolute right-0 top-full mt-2 w-72 bg-white rounded-xl shadow-lg border border-gray-100 z-50 overflow-hidden">
              <div className="p-4 border-b border-gray-100 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-gray-900">自定义列</h3>
                <button
                  onClick={resetColumns}
                  className="text-xs text-gray-500 hover:text-gray-900"
                >
                  重置为默认
                </button>
              </div>

              <div className="max-h-96 overflow-y-auto p-2">
                {columns.map((col, index) => (
                  <div
                    key={col.id}
                    className="flex items-center gap-2 p-2 rounded-lg hover:bg-gray-50 group"
                  >
                    <GripVertical className="w-4 h-4 text-gray-400 flex-shrink-0" />

                    <button
                      onClick={() => toggleColumn(col.id)}
                      className={`w-5 h-5 rounded border flex items-center justify-center flex-shrink-0 transition-colors ${
                        col.visible
                          ? 'bg-apple-blue border-apple-blue text-white'
                          : 'bg-white border-gray-300 text-transparent'
                      }`}
                    >
                      <CheckSquare className="w-4 h-4" />
                    </button>

                    <span className={`flex-1 text-sm ${col.visible ? 'text-gray-900' : 'text-gray-400'}`}>
                      {col.label}
                    </span>

                    <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={() => moveColumn(index, 'up')}
                        disabled={index === 0}
                        className="p-0.5 hover:bg-gray-200 rounded disabled:opacity-30 disabled:cursor-not-allowed"
                      >
                        <ChevronUp className="w-3 h-3" />
                      </button>
                      <button
                        onClick={() => moveColumn(index, 'down')}
                        disabled={index === columns.length - 1}
                        className="p-0.5 hover:bg-gray-200 rounded disabled:opacity-30 disabled:cursor-not-allowed"
                      >
                        <ChevronDown className="w-3 h-3" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              <div className="p-3 border-t border-gray-100 bg-gray-50">
                <p className="text-xs text-gray-500">
                  勾选以显示/隐藏列，使用上下箭头调整顺序
                </p>
                <p className="text-xs text-gray-400 mt-1">
                  配置会自动保存到本地
                </p>
              </div>
            </div>
          </>
        )}
      </div>

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
                    title={selectedIds.size === signals.length ? '取消全选' : '全选'}
                  >
                    {selectedIds.size === signals.length && signals.length > 0 ? (
                      <CheckSquare className="w-4 h-4 text-apple-blue" />
                    ) : (
                      <Square className="w-4 h-4" />
                    )}
                  </button>
                </th>
                {visibleColumns.map((col) => (
                  <th key={col.id} className="px-6 py-4 font-medium">
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {isLoading ? (
                [...Array(10)].map((_, i) => (
                  <tr key={i} className="animate-pulse">
                    <td className="px-6 py-4"><div className="h-4 bg-gray-100 rounded w-4" /></td>
                    {visibleColumns.map((col) => (
                      <td key={col.id} className="px-6 py-4">
                        <div className="h-4 bg-gray-100 rounded w-20" />
                      </td>
                    ))}
                  </tr>
                ))
              ) : signals.length === 0 ? (
                <tr>
                  <td colSpan={visibleColumns.length + 1} className="px-6 py-20 text-center text-gray-400">
                    没有找到符合条件的信号记录
                  </td>
                </tr>
              ) : (
                signals.map((signal) => {
                  const isSelected = selectedIds.has(signal.id);
                  const isSuperseded = signal.status === SignalStatus.SUPERSEDED;
                  const hasOpposingSignal = signal.opposing_signal_id != null && signal.opposing_signal_id !== '';

                  return (
                    <tr
                      key={String(signal.id)}
                      onClick={() => openModal(signal.id)}
                      className={cn(
                        "hover:bg-gray-50/50 transition-colors cursor-pointer group",
                        isSelected && "bg-apple-blue/5",
                        isSuperseded && "bg-gray-100"
                      )}
                    >
                      <td className="px-6 py-4">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            toggleSelectOne(signal.id);
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
                      {visibleColumns.map((col) => (
                        <Fragment key={col.id}>
                          {renderCell(signal, col.id)}
                        </Fragment>
                      ))}
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="p-4 border-t border-gray-100 flex items-center justify-between bg-gray-50/30">
          <div className="text-sm text-gray-500">
            共 <span className="font-medium text-gray-900">{total}</span> 条 / 第 <span className="font-medium text-gray-900">{page}</span> 页
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

      {/* Signal Details Modal */}
      <SignalDetailsModal
        signalId={selectedSignalId || ''}
        isOpen={isModalOpen}
        onClose={closeModal}
      />
    </div>
  );
}
