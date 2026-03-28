import { Fragment, useState, useCallback, useEffect, KeyboardEvent } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { X, Settings, Save, Plus, AlertCircle, CheckCircle } from 'lucide-react';
import { cn } from '../lib/utils';
import {
  SystemConfig,
  RiskConfig,
  StrategyDefinition,
  fetchSystemConfig,
  updateSystemConfig,
  generateId,
  convertStrategyToLogicNode,
} from '../lib/api';
import useSWR from 'swr';
import StrategyBuilder from './StrategyBuilder';

interface SettingsPanelProps {
  open: boolean;
  onClose: () => void;
}

// Tab definitions
type SettingsTab = 'strategies' | 'risk' | 'symbols';

// Validation helpers
const validateLossPercent = (value: string): boolean => {
  const num = parseFloat(value);
  return !isNaN(num) && num > 0 && num <= 1;
};

const validateLeverage = (value: string): boolean => {
  const num = parseInt(value);
  return !isNaN(num) && num >= 1 && num <= 125;
};

const validateSymbol = (value: string): boolean => {
  const regex = /^[A-Z0-9]+\/[A-Z0-9]+(:[A-Z0-9]+)?$/i;
  return regex.test(value);
};

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

export default function SettingsPanel({ open, onClose }: SettingsPanelProps) {
  const [activeTab, setActiveTab] = useState<SettingsTab>('strategies');
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});

  // Fetch current config
  const { data: config, mutate: mutateConfig } = useSWR<SystemConfig>(
    open ? '/api/config' : null,
    { refreshInterval: 0 }
  );

  // Local state for strategies
  const [strategies, setStrategies] = useState<StrategyDefinition[]>([]);

  // Local state for risk
  const [riskForm, setRiskForm] = useState<RiskConfig>({
    max_loss_percent: 0.01,
    max_leverage: 10,
    default_leverage: 5,
  });

  // Local state for symbols
  const [userSymbols, setUserSymbols] = useState<string[]>([]);
  const [newSymbol, setNewSymbol] = useState('');
  const [symbolError, setSymbolError] = useState('');

  // Sync form with fetched config
  useEffect(() => {
    if (config) {
      // Handle new format with active_strategies
      if ('active_strategies' in config) {
        // Ensure all strategies have logic_tree initialized
        const initializedStrategies = (config.active_strategies || []).map(ensureLogicTree);
        setStrategies(initializedStrategies);
      }
      setRiskForm(config.risk || riskForm);
      setUserSymbols(config.user_symbols || []);
    }
  }, [config]);

  const handleSave = useCallback(async () => {
    setIsSaving(true);
    setValidationErrors({});

    try {
      const updatePayload: Partial<SystemConfig> = {
        active_strategies: strategies,
        risk: riskForm,
        user_symbols: userSymbols,
      };

      await updateSystemConfig(updatePayload);
      await mutateConfig();

      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (error: any) {
      if (error.info?.detail) {
        setValidationErrors({ form: error.info.detail });
      } else {
        setValidationErrors({ form: '保存失败，请重试' });
      }
    } finally {
      setIsSaving(false);
    }
  }, [strategies, riskForm, userSymbols, mutateConfig]);

  // Symbol management
  const handleAddSymbol = useCallback(() => {
    if (!newSymbol.trim()) {
      setSymbolError('请输入币种代码');
      return;
    }
    if (!validateSymbol(newSymbol.trim())) {
      setSymbolError('格式错误，应为 BTC/USDT:USDT 或 BTC/USDT');
      return;
    }
    if (userSymbols.includes(newSymbol.trim().toUpperCase())) {
      setSymbolError('该币种已存在');
      return;
    }
    setUserSymbols((prev) => [...prev, newSymbol.trim().toUpperCase()]);
    setNewSymbol('');
    setSymbolError('');
  }, [newSymbol, userSymbols]);

  const handleRemoveSymbol = useCallback((symbol: string) => {
    setUserSymbols((prev) => prev.filter((s) => s !== symbol));
  }, []);

  const handleSymbolKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter') {
        handleAddSymbol();
      }
    },
    [handleAddSymbol]
  );

  return (
    <Transition appear show={open} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={onClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/25 backdrop-blur-sm" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-end">
            <Transition.Child
              as={Fragment}
              enter="transform transition ease-out duration-300"
              enterFrom="translate-x-full"
              enterTo="translate-x-0"
              leave="transform transition ease-in duration-200"
              leaveFrom="translate-x-0"
              leaveTo="translate-x-full"
            >
              <Dialog.Panel className="w-full max-w-2xl bg-white shadow-2xl">
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
                  <div className="flex items-center gap-3">
                    <Settings className="w-5 h-5 text-gray-500" />
                    <Dialog.Title className="text-lg font-semibold text-gray-900">
                      系统配置中心
                    </Dialog.Title>
                  </div>
                  <button
                    onClick={onClose}
                    className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                  >
                    <X className="w-5 h-5 text-gray-500" />
                  </button>
                </div>

                {/* Tabs */}
                <div className="flex border-b border-gray-200 px-6">
                  <button
                    onClick={() => setActiveTab('strategies')}
                    className={cn(
                      'px-4 py-3 text-sm font-medium border-b-2 transition-colors',
                      activeTab === 'strategies'
                        ? 'border-black text-black'
                        : 'border-transparent text-gray-500 hover:text-gray-700'
                    )}
                  >
                    策略工厂
                  </button>
                  <button
                    onClick={() => setActiveTab('risk')}
                    className={cn(
                      'px-4 py-3 text-sm font-medium border-b-2 transition-colors',
                      activeTab === 'risk'
                        ? 'border-black text-black'
                        : 'border-transparent text-gray-500 hover:text-gray-700'
                    )}
                  >
                    风控参数
                  </button>
                  <button
                    onClick={() => setActiveTab('symbols')}
                    className={cn(
                      'px-4 py-3 text-sm font-medium border-b-2 transition-colors',
                      activeTab === 'symbols'
                        ? 'border-black text-black'
                        : 'border-transparent text-gray-500 hover:text-gray-700'
                    )}
                  >
                    币池管理
                  </button>
                </div>

                {/* Content */}
                <div className="p-6 space-y-6 max-h-[calc(100vh-200px)] overflow-y-auto">
                  {/* Global error banner */}
                  {validationErrors.form && (
                    <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm flex items-center gap-2">
                      <AlertCircle className="w-4 h-4 flex-shrink-0" />
                      {validationErrors.form}
                    </div>
                  )}

                  {/* Success toast */}
                  {saveSuccess && (
                    <div className="p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm flex items-center gap-2">
                      <CheckCircle className="w-4 h-4 flex-shrink-0" />
                      配置已保存成功
                    </div>
                  )}

                  {/* Strategies Tab */}
                  {activeTab === 'strategies' && (
                    <div className="space-y-4">
                      <div>
                        <h3 className="text-sm font-semibold text-gray-700 mb-1">
                          策略触发器与过滤器链
                        </h3>
                        <p className="text-xs text-gray-500 mb-4">
                          配置多个策略触发器，每个触发器可串联多个过滤器。只有当触发器和所有启用的过滤器都通过时，才会产生信号。
                        </p>
                      </div>
                      <StrategyBuilder
                        strategies={strategies}
                        onChange={setStrategies}
                        readOnly={false}
                      />
                    </div>
                  )}

                  {/* Risk Tab */}
                  {activeTab === 'risk' && (
                    <div className="space-y-5">
                      <div>
                        <label className="block text-sm font-medium text-gray-700">
                          最大亏损比例 (max_loss_percent)
                        </label>
                        <input
                          type="number"
                          step="0.005"
                          min="0.001"
                          max="1"
                          value={riskForm.max_loss_percent}
                          onChange={(e) => {
                            const valid = validateLossPercent(e.target.value);
                            setValidationErrors((prev) => ({
                              ...prev,
                              max_loss_percent: valid ? '' : '有效范围：0 - 1 (0.01 = 1%)',
                            }));
                            setRiskForm((prev) => ({
                              ...prev,
                              max_loss_percent: parseFloat(e.target.value) || 0,
                            }));
                          }}
                          className={cn(
                            'mt-1 block w-full rounded-lg border px-3 py-2 text-sm outline-none transition-colors',
                            validationErrors.max_loss_percent
                              ? 'border-red-300 focus:border-red-500'
                              : 'border-gray-300 focus:border-black'
                          )}
                        />
                        <p className="mt-1 text-xs text-gray-500">
                          单笔交易允许的最大亏损比例 (0.01 = 1%)
                        </p>
                        {validationErrors.max_loss_percent && (
                          <p className="mt-1 text-xs text-red-500 flex items-center gap-1">
                            <AlertCircle className="w-3 h-3" />
                            {validationErrors.max_loss_percent}
                          </p>
                        )}
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700">
                          最大杠杆倍数 (max_leverage)
                        </label>
                        <input
                          type="number"
                          step="1"
                          min="1"
                          max="125"
                          value={riskForm.max_leverage}
                          onChange={(e) => {
                            const valid = validateLeverage(e.target.value);
                            setValidationErrors((prev) => ({
                              ...prev,
                              max_leverage: valid ? '' : '有效范围：1 - 125',
                            }));
                            setRiskForm((prev) => ({
                              ...prev,
                              max_leverage: parseInt(e.target.value) || 1,
                            }));
                          }}
                          className={cn(
                            'mt-1 block w-full rounded-lg border px-3 py-2 text-sm outline-none transition-colors',
                            validationErrors.max_leverage
                              ? 'border-red-300 focus:border-red-500'
                              : 'border-gray-300 focus:border-black'
                          )}
                        />
                        <p className="mt-1 text-xs text-gray-500">系统允许的最大杠杆倍数</p>
                        {validationErrors.max_leverage && (
                          <p className="mt-1 text-xs text-red-500 flex items-center gap-1">
                            <AlertCircle className="w-3 h-3" />
                            {validationErrors.max_leverage}
                          </p>
                        )}
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700">
                          默认杠杆倍数 (default_leverage)
                        </label>
                        <input
                          type="number"
                          step="1"
                          min="1"
                          max={riskForm.max_leverage}
                          value={riskForm.default_leverage}
                          onChange={(e) => {
                            setRiskForm((prev) => ({
                              ...prev,
                              default_leverage: parseInt(e.target.value) || 1,
                            }));
                          }}
                          className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-black transition-colors"
                        />
                        <p className="mt-1 text-xs text-gray-500">
                          信号建议的默认杠杆倍数 (不能超过最大值)
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Symbols Tab */}
                  {activeTab === 'symbols' && (
                    <div className="space-y-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          用户自定义币池
                        </label>
                        <div className="flex flex-wrap gap-2 mb-3">
                          {userSymbols.length === 0 ? (
                            <p className="text-sm text-gray-400 italic">暂无自定义币种</p>
                          ) : (
                            userSymbols.map((symbol) => (
                              <span
                                key={symbol}
                                className="inline-flex items-center gap-1 px-3 py-1 bg-black/5 text-gray-700 rounded-full text-sm"
                              >
                                {symbol}
                                <button
                                  onClick={() => handleRemoveSymbol(symbol)}
                                  className="hover:text-red-500 transition-colors"
                                >
                                  <X className="w-3 h-3" />
                                </button>
                              </span>
                            ))
                          )}
                        </div>
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          添加新币种
                        </label>
                        <div className="flex gap-2">
                          <input
                            type="text"
                            value={newSymbol}
                            onChange={(e) => {
                              setNewSymbol(e.target.value.toUpperCase());
                              setSymbolError('');
                            }}
                            onKeyDown={handleSymbolKeyDown}
                            placeholder="BTC/USDT:USDT"
                            className={cn(
                              'flex-1 rounded-lg border px-3 py-2 text-sm outline-none focus:border-black transition-colors',
                              symbolError ? 'border-red-300' : 'border-gray-300'
                            )}
                          />
                          <button
                            onClick={handleAddSymbol}
                            className="px-4 py-2 bg-black text-white rounded-lg text-sm font-medium hover:bg-gray-800 transition-colors flex items-center gap-1"
                          >
                            <Plus className="w-4 h-4" />
                            添加
                          </button>
                        </div>
                        {symbolError && (
                          <p className="mt-1 text-xs text-red-500 flex items-center gap-1">
                            <AlertCircle className="w-3 h-3" />
                            {symbolError}
                          </p>
                        )}
                        <p className="mt-2 text-xs text-gray-500">
                          格式：BTC/USDT:USDT (永续合约) 或 BTC/USDT (现货)
                        </p>
                      </div>

                      <div className="pt-4 border-t border-gray-200">
                        <p className="text-xs text-gray-500">
                          核心币种 (BTC, ETH, SOL, BNB) 为系统内置，不可移除
                        </p>
                      </div>
                    </div>
                  )}
                </div>

                {/* Footer */}
                <div className="px-6 py-4 border-t border-gray-200 bg-gray-50">
                  <button
                    onClick={handleSave}
                    disabled={isSaving}
                    className={cn(
                      'w-full py-2.5 rounded-lg font-medium transition-all flex items-center justify-center gap-2',
                      isSaving
                        ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                        : 'bg-black text-white hover:bg-gray-800'
                    )}
                  >
                    {isSaving ? (
                      <>
                        <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        保存中...
                      </>
                    ) : (
                      <>
                        <Save className="w-4 h-4" />
                        应用更改
                      </>
                    )}
                  </button>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
}
