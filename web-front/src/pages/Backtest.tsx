import { useState, useCallback, useMemo, useEffect } from 'react';
import {
  Play,
  Clock,
  Activity,
  TrendingUp,
  TrendingDown,
  AlertCircle,
  CheckCircle,
  XCircle,
  Filter,
  BarChart3,
  PieChart,
  Table as TableIcon,
  Zap,
  Upload,
  History,
  ChevronDown,
  Settings,
} from 'lucide-react';
import { cn } from '../lib/utils';
import {
  runSignalBacktest,
  BacktestRequest,
  BacktestReport,
  StrategyDefinition,
  RiskConfig,
  TraceEvent,
  fetchStrategyTemplates,
  fetchBacktestSignals,
  type Signal,
} from '../lib/api';
import StrategyBuilder from '../components/StrategyBuilder';
import QuickDateRangePicker from '../components/QuickDateRangePicker';
import StrategyTemplatePicker from '../components/StrategyTemplatePicker';
import SignalDetailsDrawer from '../components/SignalDetailsDrawer';
import { Collapse } from 'antd';

// Timeframe options
const TIMEFRAMES = [
  { value: '1m', label: '1 分钟' },
  { value: '5m', label: '5 分钟' },
  { value: '15m', label: '15 分钟' },
  { value: '1h', label: '1 小时' },
  { value: '4h', label: '4 小时' },
  { value: '1d', label: '1 天' },
  { value: '1w', label: '1 周' },
];

// Symbol options (core + common)
const SYMBOLS = [
  'BTC/USDT:USDT',
  'ETH/USDT:USDT',
  'SOL/USDT:USDT',
  'BNB/USDT:USDT',
  'XRP/USDT:USDT',
  'ADA/USDT:USDT',
  'DOGE/USDT:USDT',
  'MATIC/USDT:USDT',
];

// Default risk overrides
const DEFAULT_RISK_OVERRIDES: Partial<RiskConfig> = {
  max_loss_percent: 0.01,
  max_leverage: 10,
  default_leverage: 5,
};

export default function Backtest() {
  // Form state
  const [symbol, setSymbol] = useState('BTC/USDT:USDT');
  const [timeframe, setTimeframe] = useState('1h');
  const [startTime, setStartTime] = useState<number | null>(null);
  const [endTime, setEndTime] = useState<number | null>(null);

  // Strategy definitions
  const [strategies, setStrategies] = useState<StrategyDefinition[]>([]);
  const [riskOverrides, setRiskOverrides] = useState<Partial<RiskConfig>>(
    DEFAULT_RISK_OVERRIDES
  );

  // Execution state
  const [isRunning, setIsRunning] = useState(false);
  const [report, setReport] = useState<BacktestReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  // View mode for results
  const [viewMode, setViewMode] = useState<'dashboard' | 'logs'>('dashboard');

  // 高级配置折叠状态 (FE-01 新增)
  const [advancedConfigExpanded, setAdvancedConfigExpanded] = useState(false);

  // Strategy template picker state
  const [showTemplatePicker, setShowTemplatePicker] = useState(false);
  const [templates, setTemplates] = useState<Array<{ id: number; name: string; description: string | null }>>([]);
  const [isLoadingTemplates, setIsLoadingTemplates] = useState(false);

  // Backtest signals history state
  const [showHistory, setShowHistory] = useState(false);
  const [backtestSignals, setBacktestSignals] = useState<Signal[]>([]);
  const [isLoadingSignals, setIsLoadingSignals] = useState(false);

  // Signal details drawer state
  const [selectedSignal, setSelectedSignal] = useState<Signal | null>(null);
  const [showDetailsDrawer, setShowDetailsDrawer] = useState(false);

  // Fetch templates on mount
  useEffect(() => {
    const loadTemplates = async () => {
      setIsLoadingTemplates(true);
      try {
        const data = await fetchStrategyTemplates();
        setTemplates(data);
      } catch (err) {
        console.error('Failed to fetch strategy templates:', err);
      } finally {
        setIsLoadingTemplates(false);
      }
    };
    loadTemplates();
  }, []);

  // Validate form
  const validateForm = useCallback((): boolean => {
    if (!startTime || !endTime) {
      setError('请选择起始和结束时间');
      return false;
    }
    if (startTime >= endTime) {
      setError('起始时间必须早于结束时间');
      return false;
    }
    if (strategies.length === 0) {
      setError('请至少配置一个策略');
      return false;
    }
    return true;
  }, [startTime, endTime, strategies.length]);

  // Handle backtest execution
  const handleRunBacktest = useCallback(async () => {
    if (!validateForm()) return;

    setIsRunning(true);
    setError(null);
    setReport(null);

    try {
      const payload: BacktestRequest = {
        symbol,
        timeframe,
        start_time: startTime!,
        end_time: endTime!,
        strategies,
        risk_overrides: riskOverrides,
      };

      const result = await runSignalBacktest(payload);
      setReport(result);
    } catch (err: any) {
      // Handle 422 validation errors - detail might be an array of objects
      let errorMessage = '回测执行失败，请重试';
      if (err.info?.detail) {
        if (Array.isArray(err.info.detail)) {
          // FastAPI validation errors are arrays
          errorMessage = err.info.detail
            .map((d: any) => {
              const path = d.loc?.join('.') || '未知字段';
              const msg = d.msg || '验证失败';
              return `${path}: ${msg}`;
            })
            .join('; ');
        } else if (typeof err.info.detail === 'string') {
          errorMessage = err.info.detail;
        } else if (typeof err.info.detail === 'object') {
          // Object with error messages
          errorMessage = Object.entries(err.info.detail)
            .map(([key, value]) => `${key}: ${value}`)
            .join('; ');
        }
      } else if (err.message) {
        errorMessage = err.message;
      }
      setError(errorMessage);
    } finally {
      setIsRunning(false);
    }
  }, [
    symbol,
    timeframe,
    startTime,
    endTime,
    strategies,
    riskOverrides,
    validateForm,
  ]);

  // Filter breakdown stats
  const filterStats = useMemo(() => {
    if (!report) return null;
    return report.signal_stats?.filtered_by_filters || report.filtered_by_filters || {};
  }, [report]);

  // Get total filtered
  const totalFiltered = useMemo(() => {
    if (!report) return 0;
    const values = Object.values(filterStats || {}) as number[];
    return values.reduce((a, b) => a + b, 0);
  }, [report, filterStats]);

  // Handle strategy template import
  const handleImportTemplate = useCallback(async (templateStrategy: StrategyDefinition) => {
    // Fetch full strategy details
    try {
      const res = await fetch(`/api/strategies/${templateStrategy.id}`);
      const data = await res.json();
      if (data.strategy) {
        setStrategies([data.strategy]);
      }
    } catch (err) {
      console.error('Failed to fetch strategy details:', err);
    }
    setShowTemplatePicker(false);
  }, []);

  // Handle fetch backtest signals history
  const handleFetchHistory = useCallback(async () => {
    setIsLoadingSignals(true);
    setShowHistory(true);
    try {
      const data = await fetchBacktestSignals({ limit: 100 });
      setBacktestSignals(data.signals || []);
    } catch (err) {
      console.error('Failed to fetch backtest signals:', err);
      setError('加载回测历史失败');
    } finally {
      setIsLoadingSignals(false);
    }
  }, []);

  // Handle signal click to show details
  const handleSignalClick = useCallback((signal: Signal) => {
    setSelectedSignal(signal);
    setShowDetailsDrawer(true);
  }, []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">回测沙箱</h1>
          <p className="text-sm text-gray-500 mt-1">
            配置策略组合，执行历史数据回测验证
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleFetchHistory}
            className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
          >
            <History className="w-4 h-4" />
            回测历史
          </button>
          <button
            onClick={() => setShowTemplatePicker(true)}
            className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
          >
            <Upload className="w-4 h-4" />
            从策略工作台导入
          </button>
        </div>
      </div>

      {/* Info Banner */}
      <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 flex items-start gap-3">
        <div className="flex-shrink-0 w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center">
          <svg className="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-blue-900">如何使用回测沙箱</h3>
          <div className="mt-2 text-sm text-blue-700 space-y-1">
            <p><strong>第 1 步：</strong> 前往 <button onClick={() => window.location.href = '/strategies'} className="text-blue-600 hover:underline font-medium">策略工作台</button> 创建或编辑策略组合</p>
            <p><strong>第 2 步：</strong> 使用"预览"功能快速验证策略逻辑（单根 K 线）</p>
            <p><strong>第 3 步：</strong> 点击右上角"从策略工作台导入"，选择已保存的策略执行历史回测</p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Control Panel */}
        <div className="lg:col-span-1 space-y-4">
          {/* 快速配置区 (FE-01 优化 - 显眼区域) */}
          <div data-testid="quick-config-section" className="bg-gradient-to-br from-blue-50 to-blue-100/50 rounded-xl border-2 border-blue-200 p-5 space-y-4 shadow-sm">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-blue-900 flex items-center gap-2">
                <Activity className="w-4 h-4" />
                快速配置
              </h2>
              <span className="text-xs text-blue-600 bg-blue-200 px-2 py-1 rounded-full">
                Level 3
              </span>
            </div>

            <div>
              <label className="block text-sm font-medium text-blue-900 mb-1">
                🪙 交易对
              </label>
              <select
                data-testid="symbol-select"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                className="w-full rounded-lg border border-blue-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-200 transition-colors bg-white"
              >
                {SYMBOLS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-blue-900 mb-1">
                📊 时间周期
              </label>
              <select
                data-testid="timeframe-select"
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value)}
                className="w-full rounded-lg border border-blue-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-200 transition-colors bg-white"
              >
                {TIMEFRAMES.map((tf) => (
                  <option key={tf.value} value={tf.value}>
                    {tf.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-blue-900 mb-1">
                📅 时间范围
              </label>
              <QuickDateRangePicker
                startTime={startTime}
                endTime={endTime}
                onStartChange={setStartTime}
                onEndChange={setEndTime}
              />
            </div>
          </div>

          {/* 高级配置折叠区 (FE-01 新增) */}
          <div data-testid="advanced-config-section" className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div
              data-testid="advanced-config-toggle"
              className="flex items-center justify-between px-5 py-3 bg-gray-50 cursor-pointer hover:bg-gray-100 transition-colors"
              onClick={() => setAdvancedConfigExpanded(!advancedConfigExpanded)}
            >
              <div className="flex items-center gap-2">
                <Settings className="w-4 h-4 text-gray-600" />
                <span className="text-sm font-semibold text-gray-700">高级配置</span>
              </div>
              <ChevronDown
                className={cn(
                  'w-4 h-4 text-gray-500 transition-transform',
                  advancedConfigExpanded ? 'rotate-180' : ''
                )}
              />
            </div>

            {advancedConfigExpanded && (
              <div data-testid="advanced-config-content" className="p-5 space-y-4 border-t border-gray-200">
                {/* 策略组装工作台 */}
                <div>
                  <h3 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2">
                    <Zap className="w-4 h-4" />
                    策略组装工作台
                  </h3>
                  <StrategyBuilder
                    strategies={strategies}
                    onChange={setStrategies}
                    readOnly={false}
                  />
                </div>

                {/* 风控参数覆写 */}
                <div>
                  <h3 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2">
                    <Filter className="w-4 h-4" />
                    风控参数覆写
                  </h3>

                  <div className="space-y-3">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        最大亏损比例
                      </label>
                      <input
                        type="number"
                        step="0.005"
                        min="0.001"
                        max="0.1"
                        value={riskOverrides.max_loss_percent}
                        onChange={(e) =>
                          setRiskOverrides((prev) => ({
                            ...prev,
                            max_loss_percent: parseFloat(e.target.value) || 0,
                          }))
                        }
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-black transition-colors"
                      />
                      <p className="mt-1 text-xs text-gray-500">0.01 = 1%</p>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        测试杠杆倍数
                      </label>
                      <input
                        type="number"
                        step="1"
                        min="1"
                        max="125"
                        value={riskOverrides.max_leverage}
                        onChange={(e) =>
                          setRiskOverrides((prev) => ({
                            ...prev,
                            max_leverage: parseInt(e.target.value) || 1,
                          }))
                        }
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-black transition-colors"
                      />
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Execute Button */}
          <button
            data-testid="run-backtest-btn"
            onClick={handleRunBacktest}
            disabled={isRunning || strategies.length === 0}
            className={cn(
              'w-full py-3 rounded-xl font-semibold transition-all flex items-center justify-center gap-2 shadow-lg',
              isRunning || strategies.length === 0
                ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                : 'bg-black text-white hover:bg-gray-800 hover:shadow-xl'
            )}
          >
            {isRunning ? (
              <>
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                回测引擎运行中...
              </>
            ) : (
              <>
                <Play className="w-5 h-5" />
                一键执行回测
              </>
            )}
          </button>

          {/* Error Display */}
          {error && (
            <div data-testid="error-message" className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm flex items-start gap-3">
              <XCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-medium">回测失败</p>
                <p className="mt-1">{error}</p>
              </div>
            </div>
          )}
        </div>

        {/* Right: Results Dashboard */}
        <div className="lg:col-span-2">
          {!report ? (
            // Empty state
            <div className="h-full min-h-[400px] bg-white rounded-xl border border-gray-200 flex flex-col items-center justify-center p-8 text-center">
              <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mb-4">
                <BarChart3 className="w-8 h-8 text-gray-400" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900">等待执行回测</h3>
              <p className="text-sm text-gray-500 mt-2 max-w-sm">
                配置左侧的时间范围、交易对和策略组合，然后点击"一键执行回测"按钮开始分析
              </p>
            </div>
          ) : (
            // Results Dashboard
            <div className="space-y-4">
              {/* View Mode Tabs */}
              <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                <div className="flex border-b border-gray-200">
                  <button
                    onClick={() => setViewMode('dashboard')}
                    className={cn(
                      'px-4 py-3 text-sm font-medium flex items-center gap-2 transition-colors',
                      viewMode === 'dashboard'
                        ? 'bg-black/5 text-black border-b-2 border-black'
                        : 'text-gray-500 hover:text-gray-700'
                    )}
                  >
                    <PieChart className="w-4 h-4" />
                    指标看板
                  </button>
                  <button
                    onClick={() => setViewMode('logs')}
                    className={cn(
                      'px-4 py-3 text-sm font-medium flex items-center gap-2 transition-colors',
                      viewMode === 'logs'
                        ? 'bg-black/5 text-black border-b-2 border-black'
                        : 'text-gray-500 hover:text-gray-700'
                    )}
                  >
                    <TableIcon className="w-4 h-4" />
                    日志流水
                  </button>
                </div>

                {viewMode === 'dashboard' ? (
                  <div className="p-6">
                    {/* Summary Metrics */}
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                      {/* Total Signals */}
                      <div className="p-4 bg-gradient-to-br from-green-50 to-green-100/50 rounded-xl border border-green-200">
                        <div className="flex items-center gap-2 text-green-700 mb-2">
                          <CheckCircle className="w-5 h-5" />
                          <span className="text-sm font-medium">符合策略信号</span>
                        </div>
                        <p className="text-3xl font-bold text-green-900">
                          {report.signal_stats?.signals_fired ?? report.total_signals ?? 0}
                        </p>
                        <p className="text-xs text-green-600 mt-1">
                          触发开仓的信号总数
                        </p>
                      </div>

                      {/* Total Filtered */}
                      <div className="p-4 bg-gradient-to-br from-red-50 to-red-100/50 rounded-xl border border-red-200">
                        <div className="flex items-center gap-2 text-red-700 mb-2">
                          <Filter className="w-5 h-5" />
                          <span className="text-sm font-medium">被拦截信号</span>
                        </div>
                        <p className="text-3xl font-bold text-red-900">
                          {totalFiltered}
                        </p>
                        <p className="text-xs text-red-600 mt-1">
                          被过滤器阻拦的总数
                        </p>
                      </div>

                      {/* Klines Analyzed */}
                      <div className="p-4 bg-gradient-to-br from-blue-50 to-blue-100/50 rounded-xl border border-blue-200">
                        <div className="flex items-center gap-2 text-blue-700 mb-2">
                          <Activity className="w-5 h-5" />
                          <span className="text-sm font-medium">分析 K 线数</span>
                        </div>
                        <p className="text-3xl font-bold text-blue-900">
                          {((report.klines_analyzed !== undefined ? report.klines_analyzed : report.candles_analyzed) || 0).toLocaleString()}
                        </p>
                        <p className="text-xs text-blue-600 mt-1">
                          扫描的 K 线总数
                        </p>
                      </div>

                      {/* Execution Time */}
                      <div className="p-4 bg-gradient-to-br from-purple-50 to-purple-100/50 rounded-xl border border-purple-200">
                        <div className="flex items-center gap-2 text-purple-700 mb-2">
                          <Clock className="w-5 h-5" />
                          <span className="text-sm font-medium">执行耗时</span>
                        </div>
                        <p className="text-3xl font-bold text-purple-900">
                          {report.execution_time_ms}
                          <span className="text-lg font-normal text-purple-600 ml-1">ms</span>
                        </p>
                        <p className="text-xs text-purple-600 mt-1">
                          回测引擎运行时间
                        </p>
                      </div>
                    </div>

                    {/* Filter Breakdown */}
                    <div className="bg-gray-50 rounded-xl p-5">
                      <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
                        <Filter className="w-4 h-4" />
                        过滤器拦截分布
                      </h3>
                      <div className="space-y-3">
                        {Object.entries(filterStats || {}).length === 0 ? (
                          <p className="text-sm text-gray-400 italic">暂无过滤数据</p>
                        ) : (
                          Object.entries(filterStats || {}).map(([filterType, count]) => {
                            const percentage = totalFiltered > 0 ? ((count as number) / totalFiltered) * 100 : 0;
                            return (
                              <div key={filterType}>
                                <div className="flex items-center justify-between text-sm mb-1">
                                  <span className="text-gray-600 flex items-center gap-2">
                                    <Filter className="w-4 h-4" />
                                    {getFilterDisplayName(filterType)}
                                  </span>
                                  <span className="font-medium text-gray-900">
                                    {count}
                                  </span>
                                </div>
                                <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                                  <div
                                    className="h-full bg-gradient-to-r from-red-500 to-red-600 transition-all"
                                    style={{ width: `${percentage}%` }}
                                  />
                                </div>
                              </div>
                            );
                          })
                        )}
                      </div>
                    </div>
                  </div>
                ) : (
                  // Logs View
                  <div className="max-h-[600px] overflow-auto">
                    <table className="w-full text-sm">
                      <thead className="bg-gray-50 sticky top-0">
                        <tr>
                          <th className="px-4 py-3 text-left font-medium text-gray-600">时间戳</th>
                          <th className="px-4 py-3 text-left font-medium text-gray-600">策略</th>
                          <th className="px-4 py-3 text-left font-medium text-gray-600">触发器</th>
                          <th className="px-4 py-3 text-left font-medium text-gray-600">过滤器</th>
                          <th className="px-4 py-3 text-left font-medium text-gray-600">结果</th>
                          <th className="px-4 py-3 text-left font-medium text-gray-600">详情</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {(report.signal_logs || report.attempts || []).map((log: any, index: number) => {
                          // Derived legacy compat values
                          const timestamp = log.timestamp || log.kline_timestamp;
                          const filters = log.filters_passed || log.filter_results || [];
                          const signalFired = log.signal_fired || log.final_result === 'SIGNAL_FIRED';
                          const rejectReason = log.filter_reason || (log.final_result === 'NO_PATTERN' ? '未形成形态' : log.final_result);
                          const hasTrigger = log.trigger_type || log.final_result;
                          const triggerPassed = log.trigger_passed !== false && log.final_result !== 'NO_PATTERN';
                          
                          return (
                          <tr key={index} className="hover:bg-gray-50">
                            <td className="px-4 py-3 text-gray-600">
                              {new Date(timestamp).toLocaleString()}
                            </td>
                            <td className="px-4 py-3">
                              <span className="text-xs text-gray-700">
                                {log.strategy_name || '-'}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              {hasTrigger ? (
                                <span
                                  className={cn(
                                    'px-2 py-1 rounded-full text-xs font-medium',
                                    triggerPassed
                                      ? 'bg-green-100 text-green-700'
                                      : 'bg-red-100 text-red-700'
                                  )}
                                >
                                  {triggerPassed ? (
                                    <CheckCircle className="w-3 h-3 inline mr-1" />
                                  ) : (
                                    <XCircle className="w-3 h-3 inline mr-1" />
                                  )}
                                  {log.trigger_type ? getTriggerDisplayName(log.trigger_type) : (triggerPassed ? '触发成功' : '未触发')}
                                </span>
                              ) : (
                                <span className="text-gray-400 text-xs">-</span>
                              )}
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex flex-wrap gap-1">
                                {filters.length > 0 ? (
                                  filters.map((f: any, i: number) => (
                                    <span
                                      key={i}
                                      className={cn(
                                        'px-2 py-0.5 rounded-full text-xs font-medium',
                                        f.passed
                                          ? 'bg-blue-100 text-blue-700'
                                          : 'bg-red-100 text-red-700'
                                      )}
                                      title={f.reason}
                                    >
                                      {f.stage || f.filter}
                                    </span>
                                  ))
                                ) : (
                                  <span className="text-gray-400 text-xs">-</span>
                                )}
                              </div>
                            </td>
                            <td className="px-4 py-3">
                              {signalFired ? (
                                <span className="px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-700 flex items-center gap-1 w-fit">
                                  <CheckCircle className="w-3 h-3" />
                                  开仓信号
                                </span>
                              ) : (
                                <span className="px-2 py-1 rounded-full text-xs font-medium bg-red-100 text-red-700 flex items-center gap-1 w-fit">
                                  <Filter className="w-3 h-3 inline mr-1" />
                                  {rejectReason || '被拦截'}
                                </span>
                              )}
                            </td>
                            <td className="px-4 py-3 text-gray-500 text-xs max-w-[200px] truncate">
                              {log.direction
                                ? log.direction === 'long'
                                  ? '做多 📈'
                                  : '做空 📉'
                                : log.entry_price
                                ? `入场：${log.entry_price}`
                                : '-'}
                            </td>
                          </tr>
                        )})}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Strategy Template Picker */}
      <StrategyTemplatePicker
        open={showTemplatePicker}
        onClose={() => setShowTemplatePicker(false)}
        onSelect={handleImportTemplate}
        templates={templates}
        isLoading={isLoadingTemplates}
      />

      {/* Backtest Signals History Drawer */}
      {showHistory && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl shadow-xl max-w-4xl w-full mx-4 max-h-[80vh] flex flex-col">
            <div className="p-4 border-b border-gray-200 flex items-center justify-between">
              <h3 className="text-lg font-semibold flex items-center gap-2">
                <History className="w-5 h-5" />
                回测信号历史
              </h3>
              <button
                onClick={() => setShowHistory(false)}
                className="p-1 hover:bg-gray-100 rounded transition-colors"
              >
                <XCircle className="w-5 h-5 text-gray-400" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              {isLoadingSignals ? (
                <div className="text-center py-8 text-gray-400">
                  <div className="w-5 h-5 border-2 border-gray-300 border-t-black rounded-full animate-spin mx-auto" />
                  <p className="mt-2 text-sm">加载中...</p>
                </div>
              ) : backtestSignals.length === 0 ? (
                <div className="text-center py-8 text-gray-400">
                  <History className="w-10 h-10 mx-auto mb-2 opacity-20" />
                  <p className="text-sm">暂无回测信号记录</p>
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 sticky top-0">
                    <tr>
                      <th className="px-4 py-3 text-left font-medium text-gray-600">时间</th>
                      <th className="px-4 py-3 text-left font-medium text-gray-600">币种</th>
                      <th className="px-4 py-3 text-left font-medium text-gray-600">周期</th>
                      <th className="px-4 py-3 text-left font-medium text-gray-600">方向</th>
                      <th className="px-4 py-3 text-left font-medium text-gray-600">策略</th>
                      <th className="px-4 py-3 text-left font-medium text-gray-600">入场价</th>
                      <th className="px-4 py-3 text-left font-medium text-gray-600">止损价</th>
                      <th className="px-4 py-3 text-left font-medium text-gray-600">操作</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {backtestSignals.map((signal, index) => (
                      <tr
                        key={index}
                        className="hover:bg-gray-50 cursor-pointer"
                        onClick={() => handleSignalClick(signal)}
                      >
                        <td className="px-4 py-3 text-gray-600">
                          {new Date(signal.created_at).toLocaleString()}
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-xs text-gray-700">{signal.symbol}</span>
                        </td>
                        <td className="px-4 py-3 text-gray-500 text-xs">
                          {signal.timeframe}
                        </td>
                        <td className="px-4 py-3">
                          {signal.direction === 'long' ? (
                            <span className="px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-700 flex items-center gap-1 w-fit">
                              <TrendingUp className="w-3 h-3" />
                              做多
                            </span>
                          ) : (
                            <span className="px-2 py-1 rounded-full text-xs font-medium bg-red-100 text-red-700 flex items-center gap-1 w-fit">
                              <TrendingDown className="w-3 h-3" />
                              做空
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <span className={cn(
                            'px-2 py-1 rounded-full text-xs font-medium',
                            getStrategyBadgeClass(signal.strategy_name)
                          )}>
                            {translateStrategy(signal.strategy_name)}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-gray-600 text-xs">
                          {signal.entry_price}
                        </td>
                        <td className="px-4 py-3 text-gray-600 text-xs">
                          {signal.stop_loss}
                        </td>
                        <td className="px-4 py-3">
                          <button className="text-xs text-blue-600 hover:underline">
                            查看详情
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Signal Details Drawer */}
      {selectedSignal && (
        <SignalDetailsDrawer
          signal={selectedSignal}
          open={showDetailsDrawer}
          onClose={() => {
            setShowDetailsDrawer(false);
            setSelectedSignal(null);
          }}
        />
      )}
    </div>
  );
}

// Helper function to get filter display name
function getFilterDisplayName(type: string): string {
  const names: Record<string, string> = {
    ema_trend: 'EMA 趋势',
    mtf_validation: 'MTF 验证',
    volume_surge: '成交量激增',
    volatility_filter: '波动率过滤',
    time_filter: '时间窗口',
    price_action: '价格行为',
    pattern: '形态过滤',
  };
  return names[type] || type;
}

// Helper function to get trigger display name
function getTriggerDisplayName(type: string): string {
  const names: Record<string, string> = {
    pinbar: 'Pinbar',
    engulfing: 'Engulfing',
    doji: 'Doji',
    hammer: 'Hammer',
  };
  return names[type] || type;
}

// Helper function to get strategy badge class
function getStrategyBadgeClass(strategy?: string | null): string {
  if (!strategy) return 'bg-gray-100 text-gray-500';
  const key = strategy.toLowerCase();
  const colors: Record<string, string> = {
    pinbar: 'bg-purple-100 text-purple-700',
    engulfing: 'bg-orange-100 text-orange-700',
  };
  return colors[key] || 'bg-gray-100 text-gray-500';
}

// Helper function to translate strategy name
function translateStrategy(strategy?: string | null): string {
  if (!strategy) return '-';
  const key = strategy.toLowerCase();
  if (key === 'pinbar') return 'Pinbar';
  if (key === 'engulfing') return 'Engulfing';
  return strategy;
}
