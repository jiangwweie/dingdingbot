import React, { useState, useEffect } from 'react';
import type {
  EnrichedStrategyVersion,
  StrategyDetailTabId,
  StrategyTicketListItem,
  StrategyTicketExitPath,
  StrategyObservationFirstPath,
} from '../../types/strategies.ts';
import { StrategyTicketsTab } from './StrategyTicketsTab.tsx';
import { StrategyObservationsTab } from './StrategyObservationsTab.tsx';
import { useSelectionPreview } from '../../hooks/useControlsData.ts';
import { useDrawerDismiss } from '../../hooks/useDrawerDismiss.ts';
import { mapPreviewToDiagnostic } from '../../mapping/selectionMapping.ts';
import { cleanSymbol } from '../../utils/symbol.ts';
import { useStrategyControl } from '../../hooks/useStrategyControl.ts';
import { useSelectionControl } from '../../hooks/useSelectionControl.ts';
import { TotpActionModal } from '../TotpActionModal.tsx';
import { SelectionActionModal } from '../SelectionActionModal.tsx';
import {
  X,
  Layers,
  Activity,
  Compass,
  FileText,
  Sliders,
  CheckCircle2,
  TrendingUp,
  RefreshCw,
  Pause,
  Play,
  RotateCcw,
} from 'lucide-react';

interface StrategyDetailDrawerProps {
  strategy: EnrichedStrategyVersion | null;
  onClose: () => void;
  onSelectTicket: (ticket: StrategyTicketListItem) => void;
  onSelectTicketId?: (ticketId: string) => void;
  onSuccess?: (message: string) => void;
  from_ms?: number;
  to_ms?: number;
  activeDrawerTab?: StrategyDetailTabId;
  onTabChange?: (tab: StrategyDetailTabId) => void;
  scope?: 'natural' | 'all';
  exit_scope?:import('../../api/performanceApi').ExitScope;
  exit_path?: StrategyTicketExitPath | null;
  first_path?: StrategyObservationFirstPath | null;
  onScopeChange?: (scope: 'natural' | 'all') => void;
  onExitPathChange?: (exitPath: StrategyTicketExitPath | null) => void;
  onFirstPathChange?: (firstPath: StrategyObservationFirstPath | null) => void;
  onTicketFiltersChange?: (filters: { scope?: 'natural' | 'all'; exit_path?: StrategyTicketExitPath | null }) => void;
  isStrategiesFetching?: boolean;
}

export const StrategyDetailDrawer: React.FC<StrategyDetailDrawerProps> = ({
  strategy,
  onClose,
  onSelectTicket,
  onSelectTicketId,
  onSuccess,
  from_ms,
  to_ms,
  activeDrawerTab,
  onTabChange,
  scope,exit_scope,
  exit_path,
  first_path,
  onScopeChange,
  onExitPathChange,
  onFirstPathChange,
  onTicketFiltersChange,
  isStrategiesFetching,
}) => {
  useDrawerDismiss({
    isOpen: Boolean(strategy),
    onClose,
    drawerId: 'strategy-detail-drawer',
  });

  const [activeTab, setActiveTab] = useState<StrategyDetailTabId>(
    activeDrawerTab ?? 'performance'
  );

  // Sync tab with external prop if provided
  useEffect(() => {
    if (activeDrawerTab && activeDrawerTab !== activeTab) {
      setActiveTab(activeDrawerTab);
    }
  }, [activeDrawerTab]);

  // Reset tab when strategy changes unless already specified
  useEffect(() => {
    if (!activeDrawerTab) {
      setActiveTab('performance');
    }
  }, [strategy?.summary.strategy_version_id, activeDrawerTab]);

  const handleTabClick = (tabId: StrategyDetailTabId) => {
    setActiveTab(tabId);
    onTabChange?.(tabId);
  };

  // Selection preview query
  const strategyGroupId = strategy?.summary.strategy_group_id ?? '';
  const {
    data: rawPreview,
    isLoading: isSelectionLoading,
    isError: isSelectionError,
    error: selectionError,
  } = useSelectionPreview(strategyGroupId);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const selectionDiagnostic = mapPreviewToDiagnostic(strategyGroupId, rawPreview, now);

  if (!strategy) return null;

  const { summary, control } = strategy;
  const isRetired = summary.strategy_group_id === 'SOR-001';
  const hasControlFact =
    control != null &&
    (control.configured_state === 'enabled' || control.configured_state === 'paused') &&
    typeof control.control_version === 'number' &&
    Number.isFinite(control.control_version);

  const configuredState = hasControlFact && control ? control.configured_state : null;
  const isEnabled = configuredState === 'enabled';
  const controlVersion = hasControlFact && control ? control.control_version : null;

  const { modalProps, requestToggle, toastMessage, clearToast } = useStrategyControl({
    onSuccess: (msg) => {
      onSuccess?.(msg);
    },
  });

  const {
    modalProps: selectionModalProps,
    openSelectionModal,
    toastMessage: selectionToast,
    clearToast: clearSelectionToast,
  } = useSelectionControl({
    onSuccess: (msg) => {
      onSuccess?.(msg);
    },
  });

  useEffect(() => {
    if (selectionToast) {
      onSuccess?.(selectionToast);
      clearSelectionToast();
    }
  }, [selectionToast, onSuccess, clearSelectionToast]);

  const handleToggle = () => {
    if (!hasControlFact || configuredState == null || controlVersion == null) {
      return;
    }
    requestToggle({
      strategy_group_id: summary.strategy_group_id,
      configured_state: configuredState,
      control_version: controlVersion,
      name_zh: strategy.displayNameZh,
      is_retired: isRetired,
    });
  };

  return (
    <div
      data-testid="strategy-detail-drawer"
      className="fixed inset-y-0 right-0 z-50 flex w-full max-w-3xl flex-col bg-surface shadow-2xl border-l border-border animate-in slide-in-from-right duration-200"
    >
      {/* 1. Header */}
      <div className="flex items-center justify-between border-b border-border px-6 py-4 bg-surface-subtle">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand/10 text-brand border border-brand/20">
            <Layers className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold text-text-primary">
                {strategy.displayNameZh}
              </h2>
              <span className="rounded bg-brand/10 px-2 py-0.5 font-mono text-xs font-bold text-brand">
                {summary.strategy_group_id}
              </span>
              <span
                className={`rounded px-1.5 py-0.2 font-mono text-[10px] font-semibold uppercase ${
                  summary.is_current
                    ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                    : 'bg-surface-subtle text-text-muted border border-border'
                }`}
              >
                {summary.is_current ? '当前有效版本' : '历史版本'} · v{summary.version}
              </span>
            </div>
            <div className="flex items-center gap-2 mt-0.5 font-mono text-[11px] text-text-muted">
              <span>版本 ID: {summary.strategy_version_id}</span>
              <span>·</span>
              <span>周期: {strategy.timeframe}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2.5">
          {summary.is_current ? (
            isRetired ? (
              <span className="rounded border border-border bg-surface-subtle px-2.5 py-1 text-xs font-mono text-text-muted">
                已退役 (禁止恢复)
              </span>
            ) : !hasControlFact ? (
              <button
                type="button"
                disabled
                title="缺少真实控制事实 (configured_state / control_version)，禁止执行控制操作"
                className="inline-flex items-center gap-1.5 rounded border border-border bg-surface-subtle px-3 py-1.5 text-xs font-medium text-text-disabled cursor-not-allowed shadow-xs"
              >
                控制事实不可用
              </button>
            ) : (
              <button
                type="button"
                onClick={handleToggle}
                className={`inline-flex items-center gap-1.5 rounded border px-3 py-1.5 text-xs font-semibold shadow-xs transition-colors cursor-pointer ${
                  isEnabled
                    ? 'border-border bg-surface text-text-primary hover:border-amber-500/50 hover:bg-amber-500/10 hover:text-amber-500'
                    : 'border-border bg-surface text-text-primary hover:border-brand/50 hover:bg-brand/10 hover:text-brand'
                }`}
                title={isEnabled ? '暂停该策略新准入 (存量持仓继续受保护)' : '恢复该策略新准入 (需 TOTP 验证)'}
              >
                {isEnabled ? (
                  <>
                    <Pause className="h-3.5 w-3.5 text-amber-500" />
                    暂停新准入
                  </>
                ) : (
                  <>
                    <Play className="h-3.5 w-3.5 text-emerald-500" />
                    恢复新准入
                  </>
                )}
              </button>
            )
          ) : (
            <span className="rounded border border-border bg-surface-subtle px-2 py-0.5 text-xs text-text-muted">
              历史版本 · 仅供复盘
            </span>
          )}

          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-text-muted hover:bg-surface-elevated hover:text-text-primary transition-colors cursor-pointer"
            aria-label="关闭策略详情抽屉"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
      </div>

      {/* 2. Navigation Tabs */}
      <div className="flex border-b border-border bg-surface px-6 text-xs overflow-x-auto">
        {(
          [
            { id: 'performance', label: '表现评估 (Performance)', icon: TrendingUp },
            { id: 'runtime', label: '控制与准入 (Controls)', icon: Sliders },
            { id: 'selection', label: '动态选币 (Selection)', icon: Compass },
            { id: 'tickets', label: `交易证据 (${summary.ticket_count})`, icon: FileText },
            { id: 'observations', label: `观察证据 (${summary.observation_count})`, icon: Activity },
          ] as const
        ).map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => handleTabClick(tab.id as StrategyDetailTabId)}
              className={`flex items-center gap-1.5 py-3 px-3.5 font-medium border-b-2 transition-colors whitespace-nowrap cursor-pointer ${
                isActive
                  ? 'border-brand text-brand font-semibold'
                  : 'border-transparent text-text-secondary hover:text-text-primary'
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* 2.5 Time Range Inheritance Ribbon */}
      {from_ms && to_ms && (
        <div
          data-testid="strategy-drawer-time-banner"
          className="flex items-center justify-between border-b border-border bg-surface-subtle px-6 py-2 text-xs text-text-secondary"
        >
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1 rounded bg-brand/10 px-2 py-0.5 font-mono text-[10px] font-bold text-brand">
              时间对齐
            </span>
            <span className="text-[11px] text-text-muted">继承策略表现时间窗口:</span>
            <span className="font-mono text-[11px] font-semibold text-text-primary">
              {new Date(from_ms).toLocaleDateString('zh-CN', { timeZone: 'Asia/Shanghai' })} ~ {new Date(to_ms).toLocaleDateString('zh-CN', { timeZone: 'Asia/Shanghai' })}
            </span>
            {isStrategiesFetching && (
              <span className="inline-flex items-center gap-1 text-[10px] text-brand animate-pulse font-medium ml-2">
                <RefreshCw className="h-3 w-3 animate-spin" />
                正在刷新该时间窗口表现...
              </span>
            )}
          </div>
          <span className="text-[10px] text-text-muted">
            自然退出指标、Tickets 与 Observations 均严格对齐
          </span>
        </div>
      )}

      {/* 3. Tab Contents (Scrollable) */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* TAB 1: PERFORMANCE */}
        {activeTab === 'performance' && (
          <div className="space-y-6 animate-in fade-in-50 duration-150">
            {/* Top Metrics Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {/* Card 1: Natural Net PnL */}
              <div className="rounded-lg border border-border bg-surface p-4 shadow-xs">
                <div className="flex items-center justify-between text-[11px] text-text-muted">
                  <span>所选范围已核实净收益</span>
                  <TrendingUp className="h-3.5 w-3.5 text-brand" />
                </div>
                <div
                  className={`mt-1 font-mono text-xl font-bold ${
                    strategy.netPnlIsPositive === true
                      ? 'text-emerald-600 dark:text-emerald-400'
                      : strategy.netPnlIsPositive === false
                      ? 'text-rose-600 dark:text-rose-400'
                      : 'text-text-muted'
                  }`}
                >
                  {strategy.netPnlFormatted}
                </div>
                <div className="text-[10px] text-text-muted mt-1 leading-normal">
                  仅计入已确认评审的自然终态交易 (排除受控退出与待评项)
                </div>
              </div>

              {/* Card 2: Natural Net R */}
              <div className="rounded-lg border border-border bg-surface p-4 shadow-xs">
                <div className="flex items-center justify-between text-[11px] text-text-muted">
                  <span>累计单笔净 R</span>
                  <Activity className="h-3.5 w-3.5 text-brand" />
                </div>
                <div
                  className={`mt-1 font-mono text-xl font-bold ${
                    strategy.netRIsPositive === true
                      ? 'text-emerald-600 dark:text-emerald-400'
                      : strategy.netRIsPositive === false
                      ? 'text-rose-600 dark:text-rose-400'
                      : 'text-text-muted'
                  }`}
                >
                  {strategy.netRFormatted}
                </div>
                <div className="text-[10px] text-text-muted mt-1 leading-normal">
                  以初始止损距离 (1R) 为单位风险基准
                </div>
              </div>

              {/* Card 3: Win Rate */}
              <div className="rounded-lg border border-border bg-surface p-4 shadow-xs">
                <div className="flex items-center justify-between text-[11px] text-text-muted">
                  <span>自然胜率</span>
                  <CheckCircle2 className="h-3.5 w-3.5 text-brand" />
                </div>
                <div className="mt-1 font-mono text-xl font-bold text-text-primary">
                  {strategy.winRatePercent != null ? `${strategy.winRatePercent}%` : '—'}
                </div>
                <div className="text-[10px] text-text-muted mt-1 leading-normal">
                  {strategy.winRateLabel}
                </div>
              </div>
            </div>

            {/* Exit Classification Breakdown */}
            <div className="rounded-lg border border-border bg-surface p-4 shadow-xs space-y-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-text-primary flex items-center justify-between">
                <span>终态路径物理隔离分解 (Exit Scope)</span>
                <span className="font-mono text-[11px] text-text-muted font-normal">
                  总 Ticket: {strategy.totalTickets} 笔
                </span>
              </h3>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
                <div className="rounded border border-border bg-surface-subtle p-3">
                  <span className="text-[10px] text-text-muted uppercase font-sans">自然终态 (Natural)</span>
                  <div className="text-base font-bold text-text-primary mt-1">
                    {strategy.naturalTerminals} 笔
                  </div>
                  <div className="text-[10px] text-text-muted mt-0.5">
                    策略信号自然退出
                  </div>
                </div>

                <div className="rounded border border-amber-500/20 bg-amber-500/5 p-3">
                  <span className="text-[10px] text-amber-700 dark:text-amber-400 uppercase font-sans">受控退出 (Controlled)</span>
                  <div className="text-base font-bold text-amber-600 dark:text-amber-400 mt-1">
                    {strategy.controlledExits} 笔
                  </div>
                  <div className="text-[10px] text-text-muted mt-0.5">
                    人工/管理干预平仓
                  </div>
                </div>

                <div className="rounded border border-emerald-500/20 bg-emerald-500/5 p-3">
                  <span className="text-[10px] text-emerald-700 dark:text-emerald-400 uppercase font-sans">达到 TP1 (Target)</span>
                  <div className="text-base font-bold text-emerald-600 dark:text-emerald-400 mt-1">
                    {strategy.tp1Reached} 笔
                  </div>
                  <div className="text-[10px] text-text-muted mt-0.5">
                    首要目标位达成
                  </div>
                </div>

                <div className="rounded border border-border bg-surface-subtle p-3">
                  <span className="text-[10px] text-text-muted uppercase font-sans">未达 TP1 (Missed)</span>
                  <div className="text-base font-bold text-text-primary mt-1">
                    {strategy.tp1NotReached} 笔
                  </div>
                  <div className="text-[10px] text-text-muted mt-0.5">
                    止损或平保先到达
                  </div>
                </div>
              </div>
            </div>

            {/* Review Completeness Breakdown */}
            <div className="rounded-lg border border-border bg-surface p-4 shadow-xs space-y-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-text-primary">
                事后复盘审查覆盖 (Review Completeness)
              </h3>
              <div className="grid grid-cols-2 gap-3 text-xs font-mono">
                <div className="rounded border border-emerald-500/20 bg-emerald-500/5 p-3">
                  <span className="text-[10px] text-emerald-700 dark:text-emerald-400 uppercase font-sans">已确认审查 (Confirmed Review)</span>
                  <div className="text-base font-bold text-emerald-600 dark:text-emerald-400 mt-1">
                    {strategy.confirmedReviews} 笔
                  </div>
                  <div className="text-[10px] text-text-muted mt-0.5">
                    已入账自然终态经济数据
                  </div>
                </div>

                <div className="rounded border border-amber-500/20 bg-amber-500/5 p-3">
                  <span className="text-[10px] text-amber-700 dark:text-amber-400 uppercase font-sans">待确认审查 (Pending Review)</span>
                  <div className="text-base font-bold text-amber-600 dark:text-amber-400 mt-1">
                    {strategy.pendingReviews} 笔
                  </div>
                  <div className="text-[10px] text-text-muted mt-0.5">
                    等待结算对账与复盘记录生成
                  </div>
                </div>
              </div>
            </div>

            {/* StrategyVersion Isolation Notice */}
            <div className="rounded-lg border border-border bg-surface-subtle p-3 text-[11px] text-text-secondary leading-relaxed">
              <strong className="text-text-primary">StrategyVersion 独立评估原则：</strong>
              本页面展示的各项数值由当前策略版本（<code>{summary.strategy_version_id}</code>）独立产出，
              严格排除历史已退役版本的样本污染，亦不把不同策略组的盈亏混合。
            </div>
          </div>
        )}

        {/* TAB 2: CONTROLS & RUNTIME */}
        {activeTab === 'runtime' && (
          <div className="space-y-6 animate-in fade-in-50 duration-150">
            {/* Status Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="rounded-lg border border-border bg-surface p-4 shadow-xs">
                <span className="text-[10px] text-text-muted uppercase">配置启停 (Configured)</span>
                <div className="mt-1 font-mono text-base font-bold text-text-primary">
                  {control?.configured_state === 'enabled'
                    ? '已配置启用'
                    : control?.configured_state === 'paused'
                    ? '已配置暂停'
                    : '事实不可用'}
                </div>
                <div className="text-[10px] text-text-muted mt-0.5">Owner 主控配置意图</div>
              </div>

              <div className="rounded-lg border border-border bg-surface p-4 shadow-xs">
                <span className="text-[10px] text-text-muted uppercase">有效状态 (Effective)</span>
                <div
                  className={`mt-1 font-mono text-base font-bold ${
                    control?.effective_state === 'enabled'
                      ? 'text-emerald-600 dark:text-emerald-400'
                      : control?.effective_state === 'paused' || control?.effective_state === 'paused_by_global'
                      ? 'text-amber-600 dark:text-amber-400'
                      : 'text-text-muted'
                  }`}
                >
                  {control?.effective_state === 'enabled'
                    ? '运行中 (Enabled)'
                    : control?.effective_state === 'paused'
                    ? '已暂停 (Paused)'
                    : control?.effective_state === 'paused_by_global'
                    ? '全局暂停生效中'
                    : '事实不可用'}
                </div>
                <div className="text-[10px] text-text-muted mt-0.5">综合全系统门禁实际判定</div>
              </div>

              <div className="rounded-lg border border-border bg-surface p-4 shadow-xs">
                <span className="text-[10px] text-text-muted uppercase">准入阻断因 (Blocker)</span>
                <div
                  className={`mt-1 font-mono text-base font-bold truncate ${
                    strategy.firstBlocker ? 'text-rose-600 dark:text-rose-400' : 'text-emerald-600 dark:text-emerald-400'
                  }`}
                  title={strategy.firstBlocker ?? '无阻断'}
                >
                  {strategy.firstBlocker ?? '准入畅通 (无阻断)'}
                </div>
                <div className="text-[10px] text-text-muted mt-0.5">当前首个阻断开仓原因</div>
              </div>
            </div>

            {/* Product Events Specs */}
            {summary.product_events && summary.product_events.length > 0 && (
              <div className="rounded-lg border border-border bg-surface p-4 shadow-xs space-y-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-text-primary">
                  产品标的与执行时段契约 (Product Events)
                </h3>
                <div className="space-y-2">
                  {summary.product_events.map((evt, idx) => (
                    <div key={idx} className="rounded border border-border bg-surface-subtle p-3 text-xs space-y-1.5 font-mono">
                      <div className="flex items-center justify-between font-sans">
                        <span className="font-bold text-text-primary">{evt.event_id}</span>
                        <span className="rounded bg-brand/10 px-2 py-0.5 text-[10px] font-bold text-brand uppercase">
                          {evt.product_family}
                        </span>
                      </div>
                      <div className="text-[11px] text-text-secondary">
                        交易所: <span className="text-text-primary font-bold">{evt.venue_id ?? 'OKX'}</span> ·
                        方向: <span className="text-text-primary font-bold">{evt.position_side === 'long' ? '做多 (Long)' : '做空 (Short)'}</span> ·
                        周期: <span className="text-text-primary font-bold">{evt.timeframe}</span>
                      </div>
                      <div className="text-[11px] text-text-muted">
                        活跃标的 ({evt.active_exchange_instrument_ids.length}):{' '}
                        <span className="text-text-secondary">{evt.active_exchange_instrument_ids.map(cleanSymbol).join(', ') || '无'}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB 3: SELECTION */}
        {activeTab === 'selection' && (
          <div className="space-y-6 animate-in fade-in-50 duration-150">
            {isSelectionLoading ? (
              <div className="py-16 text-center">
                <div className="inline-block h-6 w-6 border-2 border-brand/30 border-t-brand rounded-full animate-spin mb-2" />
                <p className="text-xs text-text-secondary">正在获取选币引擎权威事实...</p>
              </div>
            ) : selectionDiagnostic ? (
              <div className="space-y-4">
                {(() => {
                  const isOrb = selectionDiagnostic.kind === 'orb';
                  const authorityId = isOrb ? selectionDiagnostic.authority_id : selectionDiagnostic.current_authority_id;
                  const selectedCount = isOrb
                    ? selectionDiagnostic.selected_count
                    : (selectionDiagnostic.latest_selected_count ?? selectionDiagnostic.members.length);
                  const candidateCount = isOrb
                    ? selectionDiagnostic.candidate_count
                    : (selectionDiagnostic.latest_ready_count ?? selectionDiagnostic.members.length);

                  return (
                    <>
                      {/* Mode & Authority Cards */}
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <div className="rounded-lg border border-border bg-surface p-4 shadow-xs">
                          <span className="text-[10px] text-text-muted uppercase">选币工作模式</span>
                          <div className="mt-1 font-mono text-base font-bold text-brand">
                            {selectionDiagnostic.selection_mode === 'dynamic_selection'
                              ? '动态选币 (Dynamic)'
                              : '静态基线 (Static)'}
                          </div>
                          <div className="text-[10px] text-text-muted mt-0.5">
                            轮动周期: {selectionDiagnostic.cadence_hours}h
                          </div>
                        </div>

                        <div className="rounded-lg border border-border bg-surface p-4 shadow-xs">
                          <span className="text-[10px] text-text-muted uppercase">权威生效状态</span>
                          <div
                            className="mt-1 font-mono text-sm font-bold text-text-primary truncate"
                            title={selectionDiagnostic.authority_status_zh}
                          >
                            {selectionDiagnostic.authority_status_zh}
                          </div>
                          <div className="text-[10px] text-text-muted mt-0.5 truncate" title={authorityId ?? '无'}>
                            ID: {authorityId ?? '无'}
                          </div>
                        </div>

                        <div className="rounded-lg border border-border bg-surface p-4 shadow-xs">
                          <span className="text-[10px] text-text-muted uppercase">入选标的数量</span>
                          <div className="mt-1 font-mono text-base font-bold text-text-primary">
                            {selectedCount} 标的
                          </div>
                          <div className="text-[10px] text-text-muted mt-0.5">
                            候选池总数: {candidateCount}
                          </div>
                        </div>
                      </div>

                      {/* Selection Action Strip */}
                      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface-subtle p-3">
                        <div className="flex flex-wrap items-center gap-2 text-xs">
                          <span className="font-semibold text-text-primary">选币授权控制:</span>
                          {selectionDiagnostic.pending_selection_mode ? (
                            <span className="inline-flex items-center gap-1 rounded bg-status-blue-bg px-2 py-0.5 text-[11px] font-semibold text-status-blue border border-status-blue/30">
                              <span className="h-1.5 w-1.5 rounded-full bg-status-blue animate-pulse" />
                              等待 {selectionDiagnostic.pending_selection_mode === 'dynamic_selection' ? 'Dynamic' : 'Static'} 周期生效
                            </span>
                          ) : (
                            <span className="text-text-secondary">
                              当前模式稳定运行中 · 权限变更由 Worker 在周期边界物化
                            </span>
                          )}
                        </div>

                        <div className="flex items-center gap-2">
                          {selectionDiagnostic.selection_mode === 'dynamic_selection' ? (
                            <button
                              type="button"
                              disabled={
                                Boolean(selectionDiagnostic.pending_selection_mode) ||
                                !selectionDiagnostic.rollback_baseline_id ||
                                !selectionDiagnostic.selection_epoch_id
                              }
                              title={
                                !selectionDiagnostic.rollback_baseline_id || !selectionDiagnostic.selection_epoch_id
                                  ? '缺少服务端认证的静态回退基线或 Epoch'
                                  : selectionDiagnostic.pending_selection_mode
                                  ? `已有未生效变更 (${selectionDiagnostic.pending_selection_mode})`
                                  : '回退至认证静态基线'
                              }
                              onClick={() => openSelectionModal(strategyGroupId, 'static')}
                              className="inline-flex items-center gap-1 rounded border border-status-amber/40 bg-status-amber-bg px-2.5 py-1 text-xs font-semibold text-status-amber hover:bg-status-amber/20 transition-colors cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              <RotateCcw className="h-3.5 w-3.5" />
                              回退 Static 基线
                            </button>
                          ) : (
                            <button
                              type="button"
                              disabled={
                                Boolean(selectionDiagnostic.pending_selection_mode) ||
                                !selectionDiagnostic.installed
                              }
                              title={
                                !selectionDiagnostic.installed
                                  ? '选币 Spec 未安装或未认证'
                                  : selectionDiagnostic.pending_selection_mode
                                  ? `已有未生效变更 (${selectionDiagnostic.pending_selection_mode})`
                                  : '授权激活动态选币模式'
                              }
                              onClick={() => openSelectionModal(strategyGroupId, 'dynamic')}
                              className="inline-flex items-center gap-1 rounded border border-status-blue/40 bg-status-blue-bg px-2.5 py-1 text-xs font-semibold text-status-blue hover:bg-status-blue/20 transition-colors cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              <Compass className="h-3.5 w-3.5" />
                              启用 Dynamic 模式
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Selected Members Section */}
                      <div className="rounded-lg border border-border bg-surface p-4 shadow-xs space-y-3">
                        <h3 className="text-xs font-bold uppercase tracking-wider text-text-primary flex items-center justify-between">
                          <span>
                            当前入围标的清单 ({isOrb ? selectionDiagnostic.selected_members.length : selectionDiagnostic.members.length})
                          </span>
                          <span className="font-mono text-[11px] text-text-muted">
                            {selectionDiagnostic.vacuum_state}
                          </span>
                        </h3>
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 font-mono text-xs">
                          {isOrb
                            ? selectionDiagnostic.selected_members.map((symbol, idx) => (
                                <div
                                  key={idx}
                                  className="rounded border border-border bg-surface-subtle p-2 flex items-center justify-between"
                                >
                                  <span className="font-bold text-text-primary">{cleanSymbol(symbol)}</span>
                                  <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-semibold">
                                    入选
                                  </span>
                                </div>
                              ))
                            : selectionDiagnostic.members.map((m, idx) => (
                                <div
                                  key={idx}
                                  className="rounded border border-border bg-surface-subtle p-2 flex items-center justify-between"
                                >
                                  <span className="font-bold text-text-primary">
                                    {cleanSymbol(m.facts.exchange_instrument_id)}
                                  </span>
                                  <span
                                    className={`text-[10px] font-semibold ${
                                      m.first_blocker ? 'text-amber-600' : 'text-emerald-600 dark:text-emerald-400'
                                    }`}
                                  >
                                    {m.first_blocker ? '阻断' : '在役'}
                                  </span>
                                </div>
                              ))}
                        </div>
                      </div>
                    </>
                  );
                })()}
              </div>
            ) : isSelectionError ? (
              <div className="rounded-lg border border-border bg-surface p-8 text-center text-xs text-text-muted space-y-2">
                <Compass className="mx-auto h-8 w-8 text-text-muted/50 mb-2" />
                <p className="font-semibold text-text-secondary">该策略未配置动态选币引擎</p>
                <p className="text-[11px] text-text-muted">标的池遵循静态配置文件或策略独立指定标的。</p>
                <div className="mt-3 inline-flex items-center gap-1.5 rounded bg-surface-subtle border border-border px-3 py-1 font-mono text-[10px] text-text-secondary">
                  <span>服务端响应:</span>
                  <span className="font-semibold text-text-primary">
                    {selectionError instanceof Error ? selectionError.message : 'generic_strategy_not_supported'}
                  </span>
                </div>
              </div>
            ) : (
              <div className="rounded-lg border border-border bg-surface p-8 text-center text-xs text-text-muted">
                <Compass className="mx-auto h-8 w-8 text-text-muted/50 mb-2" />
                <p className="font-semibold text-text-secondary">该策略未配置动态选币引擎</p>
                <p className="mt-1 text-[11px]">标的池遵循静态配置文件或策略独立指定标的。</p>
              </div>
            )}
          </div>
        )}

        {/* TAB 4: TICKETS */}
        {activeTab === 'tickets' && (
          <div className="animate-in fade-in-50 duration-150">
            <StrategyTicketsTab
              strategyVersionId={summary.strategy_version_id}
              onSelectTicket={onSelectTicket}
              from_ms={from_ms}
              to_ms={to_ms}
              scope={scope ?? 'all'} exit_scope={exit_scope}
              exit_path={exit_path ?? null}
              onScopeChange={onScopeChange}
              onExitPathChange={onExitPathChange}
              onTicketFiltersChange={onTicketFiltersChange}
            />
          </div>
        )}

        {/* TAB 5: OBSERVATIONS */}
        {activeTab === 'observations' && (
          <div className="animate-in fade-in-50 duration-150">
            <StrategyObservationsTab
              strategyVersionId={summary.strategy_version_id}
              onSelectTicketId={onSelectTicketId}
              from_ms={from_ms}
              to_ms={to_ms}
              first_path={first_path ?? null}
              onFirstPathChange={onFirstPathChange}
            />
          </div>
        )}
      </div>

      {/* Toast Notification */}
      {toastMessage && (
        <div className="absolute bottom-4 left-6 right-6 z-50 flex items-center justify-between rounded border border-status-green/30 bg-surface-elevated px-4 py-2.5 text-xs font-semibold text-status-green shadow-xl">
          <span>{toastMessage}</span>
          <button type="button" onClick={clearToast} className="text-text-muted hover:text-text-primary cursor-pointer">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* Confirmation & Step-Up Modal */}
      <TotpActionModal {...modalProps} />

      {/* Selection Control Action Modal */}
      <SelectionActionModal {...selectionModalProps} />
    </div>
  );
};
