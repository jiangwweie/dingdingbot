import { useState, useEffect } from 'react';
import { useApi, fetchSystemConfig, updateSystemConfig, StrategyDefinition } from '../lib/api';
import { Plus, Trash2, Edit2, Save, X, AlertCircle, CheckCircle, Zap, ChevronDown, ChevronRight, Upload } from 'lucide-react';
import { cn } from '../lib/utils';
import StrategyBuilder from '../components/StrategyBuilder';
import { generateId, getDefaultTriggerParams, TriggerType } from '../lib/api';

interface CustomStrategy {
  id: number;
  name: string;
  description?: string;
  strategy?: any;
  strategy_json?: string;
  created_at?: string;
  updated_at?: string;
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
        setEditingStrategy([data.strategy]);
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
      const res = await fetch('/api/strategies', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newStrategyName,
          description: newStrategyDesc || null,
          strategy: {
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
          },
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
                    key={strategy.id}
                    onClick={() => loadStrategyDetails(strategy.id)}
                    className={cn(
                      "w-full p-4 text-left hover:bg-gray-50 transition-colors flex items-center gap-3 cursor-pointer",
                      selectedStrategy?.id === strategy.id && "bg-blue-50"
                    )}
                  >
                    <div className={cn(
                      "w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0",
                      selectedStrategy?.id === strategy.id
                        ? "bg-blue-100 text-blue-600"
                        : "bg-amber-100 text-amber-600"
                    )}>
                      <Zap className="w-5 h-5" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900 truncate">{strategy.name}</p>
                      {strategy.description && (
                        <p className="text-xs text-gray-500 truncate">{strategy.description}</p>
                      )}
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteStrategy(strategy.id);
                      }}
                      className="p-1.5 hover:bg-red-100 rounded transition-colors opacity-0 group-hover:opacity-100"
                    >
                      <Trash2 className="w-4 h-4 text-red-500" />
                    </button>
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
              <div className="p-4">
                <StrategyBuilder
                  strategies={editingStrategy}
                  onChange={setEditingStrategy}
                  readOnly={false}
                />
              </div>
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
