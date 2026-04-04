import { useState, useEffect } from 'react';
import { useApi, fetchSystemConfig, updateSystemConfig, StrategyDefinition, previewStrategy, PreviewRequest, PreviewResponse, TraceNode, applyStrategy, convertStrategyToLogicNode } from '../lib/api';
import { Plus, Trash2, Edit2, Save, X, AlertCircle, CheckCircle, Zap, ChevronDown, ChevronRight, Upload, Play } from 'lucide-react';
import { cn } from '../lib/utils';
import StrategyBuilder from '../components/StrategyBuilder';
import TraceTreeViewer from '../components/TraceTreeViewer';
import { generateId, getDefaultTriggerParams, TriggerType } from '../lib/api';
import { LogicNode } from '../types/strategy';

interface CustomStrategy {
  id: number;
  name: string;
  description?: string;
  strategy?: any;
  strategy_json?: string;
  created_at?: string;
  updated_at?: string;
}

/**
 * 初始化策略的 logic_tree 字段（如果缺失）
 */
function ensureLogicTree(strategy: StrategyDefinition): StrategyDefinition {
  if (!strategy.logic_tree) {
    return {
      ...strategy,
      logic_tree: convertStrategyToLogicNode(strategy),
    };
  }
  return strategy;
}

export default function StrategyWorkbench() {
  const [strategies, setStrategies] = useState<CustomStrategy[]>([]);
  const [selectedStrategy, setSelectedStrategy] = useState<CustomStrategy | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [newStrategyName, setNewStrategyName] = useState('');
  const [newStrategyDesc, setNewStrategyDesc] = useState('');
  const [editingStrategy, setEditingStrategy] = useState<StrategyDefinition[]>([]);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [errorMessage, setErrorMessage] = useState('');
  const [deployStatus, setDeployStatus] = useState<'idle' | 'deploying' | 'deployed' | 'error'>('idle');
  const [applyStatus, setApplyStatus] = useState<'idle' | 'applying' | 'applied' | 'error'>('idle');
  const [showApplyConfirm, setShowApplyConfirm] = useState(false);
  const [strategyToApply, setStrategyToApply] = useState<CustomStrategy | null>(null);

  // Preview state
  const [previewStatus, setPreviewStatus] = useState<'idle' | 'previewing' | 'previewed' | 'error'>('idle');
  const [previewResult, setPreviewResult] = useState<PreviewResponse | null>(null);
  const [previewSymbol, setPreviewSymbol] = useState('BTC/USDT:USDT');
  const [previewTimeframe, setPreviewTimeframe] = useState('15m');

  // Fetch custom strategies list
  const { data: strategiesData, mutate: mutateStrategies } = useApi<{ strategies: CustomStrategy[] }>('/api/strategies');

  useEffect(() => {
    if (strategiesData?.strategies) {
      setStrategies(strategiesData.strategies);
    }
  }, [strategiesData]);

  // Load strategy details when selected
  const loadStrategyDetails = async (strategyId: number) => {
    try {
      const res = await fetch(`/api/strategies/${strategyId}`);
      const data = await res.json();
      if (data.strategy) {
        setSelectedStrategy(data);
        // Ensure logic_tree is initialized
        setEditingStrategy([ensureLogicTree(data.strategy)]);
      }
    } catch (err) {
      console.error('Failed to load strategy details:', err);
    }
  };

  // Create new strategy
  const handleCreateStrategy = async () => {
    if (!newStrategyName.trim()) return;

    setSaveStatus('saving');
    try {
      const newStrategy: StrategyDefinition = {
        id: generateId(),
        name: newStrategyName,
        trigger: {
          id: generateId(),
          type: 'pinbar' as TriggerType,
          enabled: true,
          params: getDefaultTriggerParams('pinbar'),
        },
        filters: [],
        filter_logic: 'AND' as const,
        is_global: true,
        apply_to: [],
        logic_tree: convertStrategyToLogicNode({
          id: generateId(),
          name: newStrategyName,
          trigger: {
            id: generateId(),
            type: 'pinbar' as TriggerType,
            enabled: true,
            params: getDefaultTriggerParams('pinbar'),
          },
          filters: [],
          filter_logic: 'AND' as const,
          is_global: true,
          apply_to: [],
        }),
      };

      const res = await fetch('/api/strategies', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newStrategyName,
          description: newStrategyDesc || null,
          strategy: newStrategy,
        }),
      });

      if (!res.ok) throw new Error('创建失败');

      await mutateStrategies();
      setNewStrategyName('');
      setNewStrategyDesc('');
      setIsCreating(false);
      setSaveStatus('saved');
      setTimeout(() => setSaveStatus('idle'), 2000);
    } catch (err) {
      setErrorMessage('创建策略失败，请重试');
      setSaveStatus('error');
    }
  };

  // Save edited strategy
  const handleSaveStrategy = async () => {
    if (!selectedStrategy || editingStrategy.length === 0) return;

    setSaveStatus('saving');
    try {
      const res = await fetch(`/api/strategies/${selectedStrategy.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: editingStrategy[0].name,
          strategy: editingStrategy[0],
        }),
      });

      if (!res.ok) throw new Error('保存失败');

      await mutateStrategies();
      setSaveStatus('saved');
      setTimeout(() => setSaveStatus('idle'), 2000);
    } catch (err) {
      setErrorMessage('保存策略失败，请重试');
      setSaveStatus('error');
    }
  };

  // Delete strategy
  const handleDeleteStrategy = async (strategyId: number) => {
    if (!confirm('确定要删除这个策略模板吗？此操作不可恢复。')) return;

    try {
      const res = await fetch(`/api/strategies/${strategyId}`, {
        method: 'DELETE',
      });

      if (!res.ok) throw new Error('删除失败');

      await mutateStrategies();
      setSelectedStrategy(null);
      setEditingStrategy([]);
    } catch (err) {
      setErrorMessage('删除策略失败，请重试');
    }
  };

  // Deploy strategy to live trading engine
  const handleDeployStrategy = async () => {
    if (!selectedStrategy || editingStrategy.length === 0) return;

    setDeployStatus('deploying');
    try {
      // Step 1: Fetch current system config
      const currentConfig = await fetchSystemConfig();

      // Step 2: Get the strategy to deploy
      const strategyToDeploy = editingStrategy[0];

      // Remove any existing strategy with the same name to avoid duplicates
      const existingStrategies = (currentConfig.active_strategies || []).filter(
        s => s.name !== strategyToDeploy.name
      );

      // Append the new strategy
      const newActiveStrategies = [...existingStrategies, strategyToDeploy];

      // Step 3: Update system config
      await updateSystemConfig({
        active_strategies: newActiveStrategies,
      });

      setDeployStatus('deployed');
      setTimeout(() => setDeployStatus('idle'), 3000);
    } catch (err) {
      console.error('Failed to deploy strategy:', err);
      setDeployStatus('error');
      setTimeout(() => setDeployStatus('idle'), 3000);
    }
  };

  // Preview strategy (Hot Preview / Dry Run)
  const handlePreviewStrategy = async () => {
    if (editingStrategy.length === 0) return;

    setPreviewStatus('previewing');
    setPreviewResult(null);

    try {
      const strategy = editingStrategy[0];

      // Build logic tree from strategy
      // For backward compatibility, convert flat trigger+filters to logic tree
      const logicTree: LogicNode = {
        gate: 'AND',
        children: [
          {
            type: 'trigger',
            id: strategy.trigger.id,
            config: strategy.trigger,
          },
          ...strategy.filters.map(f => ({
            type: 'filter' as const,
            id: f.id,
            config: f,
          })),
        ],
      };

      const payload: PreviewRequest = {
        logic_tree: logicTree,
        symbol: previewSymbol,
        timeframe: previewTimeframe,
      };

      const result = await previewStrategy(payload);
      setPreviewResult(result);
      setPreviewStatus('previewed');
    } catch (err: any) {
      console.error('Preview failed:', err);
      setErrorMessage(err.info?.detail || '预览失败，请重试');
      setPreviewStatus('error');
    }
  };

  // Apply strategy to live trading engine
  const handleApplyStrategy = async () => {
    if (!strategyToApply) return;

    setApplyStatus('applying');
    try {
      await applyStrategy(String(strategyToApply.id));
      setApplyStatus('applied');
      setShowApplyConfirm(false);
      setStrategyToApply(null);
      await mutateStrategies();
      setTimeout(() => setApplyStatus('idle'), 3000);
    } catch (err: any) {
      console.error('Apply strategy failed:', err);
      setErrorMessage(err.info?.detail || '应用策略失败，请重试');
      setApplyStatus('error');
      setTimeout(() => setApplyStatus('idle'), 3000);
    }
  };

  // Confirm apply dialog handlers
  const confirmApply = (strategy: CustomStrategy) => {
    setStrategyToApply(strategy);
    setShowApplyConfirm(true);
  };

  const cancelApply = () => {
    setShowApplyConfirm(false);
    setStrategyToApply(null);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">策略工作台</h1>
          <p className="text-sm text-gray-500 mt-1">管理和编辑自定义策略模板</p>
        </div>
        {!selectedStrategy && !isCreating && (
          <button
            onClick={() => setIsCreating(true)}
            className="flex items-center gap-2 px-4 py-2 bg-black text-white rounded-lg hover:bg-gray-800 transition-colors"
          >
            <Plus className="w-4 h-4" />
            新建策略
          </button>
        )}
      </div>

      {/* Info Banner */}
      <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 flex items-start gap-3">
        <div className="flex-shrink-0 w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center">
          <svg className="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-blue-900">策略工作台 vs 回测沙箱</h3>
          <div className="mt-2 text-sm text-blue-700 space-y-1">
            <p><strong>策略工作台：</strong> 创建/编辑策略组合，使用"预览"功能快速验证策略逻辑（单根 K 线），可将策略部署到实盘</p>
            <p><strong>回测沙箱：</strong> 导入已保存的策略，在历史数据上执行完整回测，查看详细绩效报告</p>
            <p className="text-blue-600/80 mt-2">💡 建议工作流程：在工作台创建策略 → 预览验证 → 保存到模板 → 导入回测沙箱执行历史回测</p>
          </div>
        </div>
      </div>

      {/* Error Message */}
      {errorMessage && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm text-red-800 font-medium">{errorMessage}</p>
          </div>
          <button onClick={() => setErrorMessage('')} className="ml-auto">
            <X className="w-4 h-4 text-red-400" />
          </button>
        </div>
      )}

      {/* Save Status */}
      {saveStatus === 'saved' && (
        <div className="p-4 bg-green-50 border border-green-200 rounded-lg flex items-center gap-3">
          <CheckCircle className="w-5 h-5 text-green-600" />
          <p className="text-sm text-green-800 font-medium">操作成功</p>
        </div>
      )}

      {/* Deploy Status */}
      {deployStatus === 'deployed' && (
        <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg flex items-center gap-3">
          <CheckCircle className="w-5 h-5 text-blue-600" />
          <div>
            <p className="text-sm text-blue-800 font-medium">策略已挂载，实盘引擎热重载成功！</p>
            <p className="text-xs text-blue-600 mt-0.5">策略现在开始对指定币种和周期生效</p>
          </div>
        </div>
      )}

      {deployStatus === 'error' && (
        <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm text-amber-800 font-medium">策略下发失败</p>
            <p className="text-xs text-amber-600 mt-0.5">请检查系统配置接口是否正常</p>
          </div>
        </div>
      )}

      {/* Apply Status */}
      {applyStatus === 'applied' && (
        <div className="p-4 bg-green-50 border border-green-200 rounded-lg flex items-center gap-3">
          <CheckCircle className="w-5 h-5 text-green-600" />
          <div>
            <p className="text-sm text-green-800 font-medium">策略已应用到实盘引擎！</p>
            <p className="text-xs text-green-600 mt-0.5">策略现在开始对指定币种和周期生效</p>
          </div>
        </div>
      )}

      {applyStatus === 'error' && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm text-red-800 font-medium">应用策略失败</p>
            <p className="text-xs text-red-600 mt-0.5">请检查后端接口是否正常</p>
          </div>
        </div>
      )}

      {/* Apply Confirmation Dialog */}
      {showApplyConfirm && strategyToApply && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl shadow-xl max-w-md w-full mx-4 p-6">
            <div className="flex items-center gap-3 mb-4">
              <AlertCircle className="w-6 h-6 text-amber-600" />
              <h3 className="text-lg font-semibold">确认应用到实盘</h3>
            </div>
            <div className="space-y-3">
              <p className="text-sm text-gray-600">
                确定要将策略模板 <span className="font-medium text-gray-900">"{strategyToApply.name}"</span> 应用到实盘引擎吗？
              </p>
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                <p className="text-xs text-amber-800">
                  <strong>注意：</strong> 此操作会将策略配置下发到实盘引擎，策略将立即对配置的币种和周期生效。
                </p>
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button
                onClick={cancelApply}
                className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleApplyStrategy}
                disabled={applyStatus === 'applying'}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <Upload className="w-4 h-4" />
                {applyStatus === 'applying' ? '应用中...' : '确认应用'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Creation Form */}
      {isCreating && (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold">创建新策略</h2>
            <button onClick={() => setIsCreating(false)} className="p-1 hover:bg-gray-100 rounded">
              <X className="w-5 h-5 text-gray-400" />
            </button>
          </div>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">策略名称</label>
              <input
                type="text"
                value={newStrategyName}
                onChange={(e) => setNewStrategyName(e.target.value)}
                placeholder="输入策略名称"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 outline-none focus:border-black transition-colors"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">描述（可选）</label>
              <textarea
                value={newStrategyDesc}
                onChange={(e) => setNewStrategyDesc(e.target.value)}
                placeholder="描述策略特点..."
                rows={2}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 outline-none focus:border-black transition-colors resize-none"
              />
            </div>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setIsCreating(false)}
                className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleCreateStrategy}
                disabled={!newStrategyName.trim() || saveStatus === 'saving'}
                className="flex items-center gap-2 px-4 py-2 bg-black text-white rounded-lg hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {saveStatus === 'saving' ? '创建中...' : '创建策略'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Strategy List and Editor */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Strategies List */}
        <div className="lg:col-span-1">
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
            <div className="p-4 border-b border-gray-100">
              <h2 className="text-sm font-semibold text-gray-900">策略模板列表</h2>
            </div>
            <div className="divide-y divide-gray-100 max-h-[600px] overflow-y-auto">
              {strategies.length === 0 ? (
                <div className="p-8 text-center text-gray-400">
                  <Zap className="w-10 h-10 mx-auto mb-2 opacity-20" />
                  <p className="text-sm">暂无策略模板</p>
                </div>
              ) : (
                strategies.map((strategy) => (
                  <div
                    key={String(strategy.id)}
                    className={cn(
                      "w-full p-4 text-left hover:bg-gray-50 transition-colors flex items-center gap-3 group",
                      selectedStrategy?.id === strategy.id && "bg-blue-50"
                    )}
                  >
                    <div
                      onClick={() => loadStrategyDetails(strategy.id)}
                      className="flex-1 min-w-0 cursor-pointer"
                    >
                      <div className="flex items-center gap-3">
                        <div className={cn(
                          "w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0",
                          selectedStrategy?.id === strategy.id
                            ? "bg-blue-100 text-blue-600"
                            : "bg-amber-100 text-amber-600"
                        )}>
                          <Zap className="w-5 h-5" />
                        </div>
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-gray-900 truncate">{strategy.name}</p>
                          {strategy.description && (
                            <p className="text-xs text-gray-500 truncate">{strategy.description}</p>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          confirmApply(strategy);
                        }}
                        className="p-1.5 hover:bg-blue-100 rounded transition-colors opacity-0 group-hover:opacity-100"
                        title="应用到实盘"
                      >
                        <Upload className="w-4 h-4 text-blue-600" />
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteStrategy(strategy.id);
                        }}
                        className="p-1.5 hover:bg-red-100 rounded transition-colors opacity-0 group-hover:opacity-100"
                        title="删除策略"
                      >
                        <Trash2 className="w-4 h-4 text-red-500" />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Strategy Editor */}
        <div className="lg:col-span-2">
          {selectedStrategy ? (
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
              <div className="p-4 border-b border-gray-100 flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold">{selectedStrategy.name}</h2>
                  {selectedStrategy.description && (
                    <p className="text-xs text-gray-500 mt-1">{selectedStrategy.description}</p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setSelectedStrategy(null)}
                    className="px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
                  >
                    返回列表
                  </button>
                  <button
                    onClick={handlePreviewStrategy}
                    disabled={previewStatus === 'previewing'}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
                  >
                    <Play className="w-4 h-4" />
                    {previewStatus === 'previewing' ? '预览中...' : '立即测试'}
                  </button>
                  <button
                    onClick={handleDeployStrategy}
                    disabled={deployStatus === 'deploying'}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
                  >
                    <Upload className="w-4 h-4" />
                    {deployStatus === 'deploying' ? '下发中...' : '下发到实盘'}
                  </button>
                  <button
                    onClick={handleSaveStrategy}
                    disabled={saveStatus === 'saving'}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-black text-white rounded-lg hover:bg-gray-800 disabled:opacity-50 transition-colors"
                  >
                    <Save className="w-4 h-4" />
                    {saveStatus === 'saving' ? '保存中...' : '保存'}
                  </button>
                </div>
              </div>

              {/* Preview Controls */}
              {previewStatus === 'previewed' && previewResult && (
                <div className="p-4 bg-gray-50 border-b border-gray-100">
                  <div className="flex items-center gap-4 mb-3">
                    <label className="text-sm font-medium text-gray-700">币种:</label>
                    <select
                      value={previewSymbol}
                      onChange={(e) => setPreviewSymbol(e.target.value)}
                      className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm outline-none focus:border-black transition-colors"
                    >
                      <option value="BTC/USDT:USDT">BTC/USDT</option>
                      <option value="ETH/USDT:USDT">ETH/USDT</option>
                      <option value="SOL/USDT:USDT">SOL/USDT</option>
                      <option value="BNB/USDT:USDT">BNB/USDT</option>
                    </select>

                    <label className="text-sm font-medium text-gray-700">周期:</label>
                    <select
                      value={previewTimeframe}
                      onChange={(e) => setPreviewTimeframe(e.target.value)}
                      className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm outline-none focus:border-black transition-colors"
                    >
                      <option value="5m">5m</option>
                      <option value="15m">15m</option>
                      <option value="1h">1h</option>
                      <option value="4h">4h</option>
                      <option value="1d">1d</option>
                    </select>

                    <button
                      onClick={handlePreviewStrategy}
                      disabled={previewStatus !== 'previewed'}
                      className="flex items-center gap-1 px-3 py-1.5 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
                    >
                      <Play className="w-3 h-3" />
                      重新测试
                    </button>
                  </div>
                </div>
              )}
              <div className="p-4">
                <StrategyBuilder
                  strategies={editingStrategy}
                  onChange={setEditingStrategy}
                  readOnly={false}
                />
              </div>

              {/* Preview Result - Trace Tree Viewer */}
              {previewStatus === 'previewed' && previewResult && (
                <div className="p-4 border-t border-gray-100 space-y-4">
                  {/* 提示信息 */}
                  <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                    <div className="flex items-start gap-2">
                      <AlertCircle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
                      <div className="text-sm text-amber-800">
                        <p className="font-medium">关于立即测试</p>
                        <p className="mt-1 text-amber-700">
                          仅评估<strong>当前最新一根 K 线</strong>，如果未检测到信号属于正常现象。
                          Pinbar 等形态在市场中较为稀缺，通常需要等待合适的 K 线形态出现。
                        </p>
                        <p className="mt-2 text-amber-700">
                          <strong>想查看历史表现？</strong>前往 <a href="/backtest" className="underline font-medium hover:text-amber-900">回测沙箱</a> 查看策略在历史数据上的表现。
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* 结果状态 */}
                  <div className={cn(
                    "rounded-lg p-3 border",
                    previewResult.signal_fired
                      ? "bg-green-50 border-green-200"
                      : "bg-gray-50 border-gray-200"
                  )}>
                    <p className={cn(
                      "text-sm font-medium",
                      previewResult.signal_fired ? "text-green-800" : "text-gray-600"
                    )}>
                      {previewResult.signal_fired
                        ? "✅ 当前 K 线满足策略条件，信号触发！"
                        : "ℹ️ 当前 K 线不满足策略条件，未检测到信号"}
                    </p>
                    {!previewResult.signal_fired && (
                      <p className="text-xs text-gray-500 mt-1">
                        原因：{previewResult.trace_tree?.reason || '未知'}
                      </p>
                    )}
                  </div>

                  {/* 评估报告 */}
                  {previewResult.evaluation_summary && (
                    <div className="mt-4">
                      <div className="flex items-center justify-between mb-2">
                        <h4 className="text-sm font-semibold text-gray-700">评估报告</h4>
                        <button
                          onClick={() => {
                            alert(`评估报告:\n\n${previewResult.evaluation_summary}`);
                          }}
                          className="text-xs text-apple-blue hover:underline"
                        >
                          查看详情
                        </button>
                      </div>
                      <pre className="bg-gray-50 border border-gray-200 rounded-lg p-3 text-xs text-gray-700 whitespace-pre-wrap font-sans">
                        {previewResult.evaluation_summary}
                      </pre>
                    </div>
                  )}

                  <TraceTreeViewer
                    traceTree={previewResult.trace_tree}
                    signalFired={previewResult.signal_fired}
                  />
                </div>
              )}
            </div>
          ) : !isCreating ? (
            <div className="h-full min-h-[400px] flex flex-col items-center justify-center text-gray-400 bg-white rounded-2xl shadow-sm border border-gray-100">
              <Zap className="w-16 h-16 mb-4 opacity-20" />
              <p className="text-sm">从左侧选择一个策略模板进行编辑</p>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
