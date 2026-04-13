import { useState, useCallback, useEffect } from 'react';
import {
  Play,
  Activity,
  Filter,
  Zap,
  Upload,
  History,
  XCircle,
  BarChart3,
  TrendingUp,
  TrendingDown,
} from 'lucide-react';
import { cn } from '../lib/utils';
import {
  runPMSBacktest,
  PMSBacktestRequest,
  StrategyDefinition,
  RiskConfig,
  PMSBacktestReport,
  fetchBacktestSignals,
  type Signal,
} from '../lib/api';
import { configApi, type Strategy } from '../api/config';
import StrategyBuilder from '../components/StrategyBuilder';
import QuickDateRangePicker from '../components/QuickDateRangePicker';
import StrategyTemplatePicker from '../components/StrategyTemplatePicker';
import SignalDetailsDrawer from '../components/SignalDetailsDrawer';
import {
  BacktestOverviewCards,
  EquityComparisonChart,
  TradeStatisticsTable,
  PnLDistributionHistogram,
  MonthlyReturnHeatmap,
} from '../components/v3/backtest';
import { Select } from 'antd';

// Timeframe options
const TIMEFRAMES = [
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
};

// Default initial balance for PMS backtest
const DEFAULT_INITIAL_BALANCE = '10000';

export default function PMSBacktest() {
  // Form state
  const [symbol, setSymbol] = useState('BTC/USDT:USDT');
  const [timeframe, setTimeframe] = useState('1h');
  const [startTime, setStartTime] = useState<number | null>(null);
  const [endTime, setEndTime] = useState<number | null>(null);
  const [initialBalance, setInitialBalance] = useState(DEFAULT_INITIAL_BALANCE);

  // Strategy definitions
  const [strategies, setStrategies] = useState<StrategyDefinition[]>([]);
  const [riskOverrides, setRiskOverrides] = useState<Partial<RiskConfig>>(
    DEFAULT_RISK_OVERRIDES
  );

  // Execution state
  const [isRunning, setIsRunning] = useState(false);
  const [report, setReport] = useState<PMSBacktestReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Strategy template picker state
  const [showTemplatePicker, setShowTemplatePicker] = useState(false);
  const [templates, setTemplates] = useState<Strategy[]>([]);
  const [isLoadingTemplates, setIsLoadingTemplates] = useState(false);

  // Backtest signals history state
  const [showHistory, setShowHistory] = useState(false);
  const [backtestSignals, setBacktestSignals] = useState<Signal[]>([]);
  const [isLoadingSignals, setIsLoadingSignals] = useState(false);

  // Signal details drawer state
  const [selectedSignal, setSelectedSignal] = useState<Signal | null>(null);
  const [showDetailsDrawer, setShowDetailsDrawer] = useState(false);

  // Quick strategy selector state
  const [savedStrategies, setSavedStrategies] = useState<Strategy[]>([]);
  const [selectedStrategyId, setSelectedStrategyId] = useState<string | undefined>();
  const [isLoadingSaved, setIsLoadingSaved] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Fetch templates on mount
  useEffect(() => {
    const loadTemplates = async () => {
      setIsLoadingTemplates(true);
      try {
        const response = await configApi.getStrategies();
        setTemplates(response.data);
      } catch (err) {
        console.error('Failed to fetch strategies:', err);
      } finally {
        setIsLoadingTemplates(false);
      }
    };
    loadTemplates();
  }, []);

  // Fetch saved strategies for quick selector on mount
  useEffect(() => {
    const loadSavedStrategies = async () => {
      setIsLoadingSaved(true);
      setLoadError(null);
      try {
        const { data } = await configApi.getStrategies();
        setSavedStrategies(data);
      } catch (err) {
        console.error('Failed to fetch saved strategies:', err);
        // Silent failure - doesn't affect backtest usage
      } finally {
        setIsLoadingSaved(false);
      }
    };
    loadSavedStrategies();
  }, []);

  // Handle loading a saved strategy into the PMS backtest form
  const handleLoadStrategy = useCallback(async () => {
    if (!selectedStrategyId) return;
    try {
      const { data: strategy } = await configApi.getStrategy(selectedStrategyId);
      const converted = mapStrategyToDefinition(strategy);
      setStrategies([converted]);
      setSelectedStrategyId(undefined);
      setLoadError(null);
    } catch (err) {
      console.error('Failed to load strategy:', err);
      setLoadError('加载策略失败，请重试');
    }
  }, [selectedStrategyId]);

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

  // Handle PMS backtest execution
  const handleRunPMSBacktest = useCallback(async () => {
    if (!validateForm()) return;

    setIsRunning(true);
    setError(null);
    setReport(null);

    try {
      const payload: PMSBacktestRequest = {
        symbol,
        timeframe,
        start_time: startTime!,
        end_time: endTime!,
        strategies,
        risk_overrides: riskOverrides,
        initial_balance: parseFloat(initialBalance) || 10000,
      };

      const result = await runPMSBacktest(payload);
      setReport(result);
    } catch (err: any) {
      // Handle 422 validation errors - detail might be an array of objects
      let errorMessage = 'PMS 回测执行失败，请重试';
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
    initialBalance,
    validateForm,
  ]);

  // Handle strategy template import
  const handleImportTemplate = useCallback(async (templateStrategy: StrategyDefinition) => {
    // Fetch full strategy details from new config API
    try {
      const response = await configApi.getStrategy(templateStrategy.id);
      const strategy = response.data;
      if (strategy) {
        // Convert Strategy to StrategyDefinition format for backtest engine
        setStrategies([{
          id: strategy.id,
          name: strategy.name,
          trigger: {
            id: `${strategy.id}-trigger`,
            type: strategy.trigger_config.type,
            enabled: true,
            params: strategy.trigger_config.params,
          },
          filters: strategy.filter_configs.map((fc, i) => ({
            id: `${strategy.id}-filter-${i}`,
            type: fc.type,
            enabled: fc.enabled,
            params: fc.params,
          })),
          filter_logic: strategy.filter_logic,
          is_global: true,
          apply_to: [...new Set(
            strategy.symbols.flatMap(s => strategy.timeframes.map(t => `${s}:${t}`))
          )],
        }]);
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
          <h1 className="text-2xl font-bold text-gray-900">PMS 回测报告</h1>
          <p className="text-sm text-gray-500 mt-1">
            v3.0 PMS 模式回测 - 仓位级追踪与详细统计分析
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
            从策略配置导入
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
          <h3 className="text-sm font-semibold text-blue-900">PMS 回测 vs 经典回测</h3>
          <div className="mt-2 text-sm text-blue-700 space-y-1">
            <p><strong>PMS 模式（本页面）:</strong> 仓位级追踪，包含订单执行、滑点、手续费、止盈止损等完整交易流程模拟</p>
            <p><strong>经典模式:</strong> 信号级统计，仅展示信号触发和过滤器拦截情况</p>
            <p><strong>使用建议:</strong> PMS 模式更适合验证实际交易策略的盈利能力，经典模式适合快速验证信号逻辑</p>
          </div>
        </div>
      </div>

      {/* Quick Strategy Selector */}
      {savedStrategies.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-4 flex items-center gap-3">
          <div className="flex items-center gap-2 flex-shrink-0">
            <Zap className="w-4 h-4 text-amber-500" />
            <span className="text-sm font-medium text-gray-700">快捷加载已保存策略</span>
          </div>
          <Select
            allowClear
            showSearch
            placeholder="选择策略"
            value={selectedStrategyId}
            onChange={setSelectedStrategyId}
            options={savedStrategies.map((s) => ({
              label: s.name,
              value: s.id,
            }))}
            className="flex-1"
            loading={isLoadingSaved}
            disabled={isLoadingSaved}
            optionFilterProp="label"
          />
          <button
            onClick={handleLoadStrategy}
            disabled={!selectedStrategyId || isLoadingSaved}
            className={cn(
              'px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-1',
              !selectedStrategyId || isLoadingSaved
                ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                : 'bg-black text-white hover:bg-gray-800'
            )}
          >
            加载
          </button>
          {loadError && (
            <span className="text-xs text-red-500">{loadError}</span>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Control Panel */}
        <div className="lg:col-span-1 space-y-4">
          {/* Time & Asset Selection */}
          <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
            <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
              <Activity className="w-4 h-4" />
              时间序列与资产维度
            </h2>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                交易对
              </label>
              <select
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-black transition-colors"
              >
                {SYMBOLS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                时间周期
              </label>
              <select
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-black transition-colors"
              >
                {TIMEFRAMES.map((tf) => (
                  <option key={tf.value} value={tf.value}>
                    {tf.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                时间范围
              </label>
              <QuickDateRangePicker
                startTime={startTime}
                endTime={endTime}
                onStartChange={setStartTime}
                onEndChange={setEndTime}
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                初始资金 (USDT)
              </label>
              <input
                type="number"
                step="100"
                min="100"
                max="1000000"
                value={initialBalance}
                onChange={(e) => setInitialBalance(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-black transition-colors"
              />
            </div>
          </div>

          {/* Strategy Builder */}
          <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
            <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
              <Zap className="w-4 h-4" />
              策略组装工作台
            </h2>
            <StrategyBuilder
              strategies={strategies}
              onChange={setStrategies}
              readOnly={false}
            />
          </div>

          {/* Risk Overrides */}
          <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
            <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
              <Filter className="w-4 h-4" />
              风控参数覆写
            </h2>

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

          {/* Execute Button */}
          <button
            onClick={handleRunPMSBacktest}
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
                PMS 回测引擎运行中...
              </>
            ) : (
              <>
                <Play className="w-5 h-5" />
                执行 PMS 回测
              </>
            )}
          </button>

          {/* Error Display */}
          {error && (
            <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm flex items-start gap-3">
              <XCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-medium">PMS 回测失败</p>
                <p className="mt-1">{error}</p>
              </div>
            </div>
          )}
        </div>

        {/* Right: Results Dashboard */}
        <div className="lg:col-span-2 space-y-4">
          {!report ? (
            // Empty state
            <div className="h-full min-h-[400px] bg-white rounded-xl border border-gray-200 flex flex-col items-center justify-center p-8 text-center">
              <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mb-4">
                <BarChart3 className="w-8 h-8 text-gray-400" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900">等待执行 PMS 回测</h3>
              <p className="text-sm text-gray-500 mt-2 max-w-sm">
                配置左侧的时间范围、交易对、初始资金和策略组合，然后点击"执行 PMS 回测"按钮开始分析
              </p>
            </div>
          ) : (
            // Results Dashboard
            <div className="space-y-4">
              {/* Overview Cards */}
              <BacktestOverviewCards report={report} />

              {/* Equity Curve */}
              <EquityComparisonChart report={report} />

              {/* Trade Statistics */}
              <TradeStatisticsTable report={report} />

              {/* PnL Distribution */}
              <PnLDistributionHistogram report={report} />

              {/* Monthly Return Heatmap */}
              <MonthlyReturnHeatmap report={report} />
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

/**
 * Map Strategy (from config API) to StrategyDefinition (backtest format)
 *
 * Handles field name differences:
 * - trigger_config → trigger
 * - filter_configs → filters (with generated IDs)
 * - symbols + timeframes → apply_to
 */
function mapStrategyToDefinition(strategy: Strategy): StrategyDefinition {
  const id = crypto.randomUUID();

  // Map trigger_config → trigger (add id + enabled)
  const trigger = {
    id: `${id}-trigger`,
    type: strategy.trigger_config.type,
    enabled: true,
    params: strategy.trigger_config.params || {},
  };

  // Map filter_configs → filters (add id field if missing)
  const filters = (strategy.filter_configs || []).map((f) => ({
    id: `${id}-filter-${f.type}`,
    type: f.type,
    enabled: f.enabled,
    params: f.params || {},
  }));

  // Map symbols + timeframes → apply_to
  const applyTo: string[] = [];
  for (const sym of strategy.symbols || []) {
    for (const tf of strategy.timeframes || []) {
      applyTo.push(`${sym}:${tf}`);
    }
  }

  return {
    id: strategy.id,
    name: strategy.name,
    trigger,
    filters,
    filter_logic: strategy.filter_logic,
    is_global: applyTo.length === 0,
    apply_to: applyTo,
    logic_tree: undefined,
  };
}
