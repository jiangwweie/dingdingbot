import React, { useState } from 'react';
import { Navbar } from './components/Navbar';
import { TopStatusBar } from './components/TopStatusBar';
import { StrategyMatrix } from './components/StrategyMatrix';
import { SelectionSection } from './components/SelectionSection';
import { DangerZoneCard } from './components/DangerZoneCard';
import { CapacitySection } from './components/CapacitySection';
import { RecentOperations } from './components/RecentOperations';
import { ControlledFlattenModal } from './components/ControlledFlattenModal';
import { TotpActionModal } from './components/TotpActionModal';
import { OverviewPage } from './components/overview/OverviewPage';
import { mockFlattenPreview } from './mock/controlsData';
import type { NavTabId } from './components/Navbar';
import type { StrategyControlItem, SelectionDiagnosticData, RecentOperationItem } from './types/controls';
import { useControlsData } from './hooks/useControlsData';
import { RefreshCw, CheckCircle2 } from 'lucide-react';

export const App: React.FC = () => {
  // Navigation State
  const [activeTab, setActiveTab] = useState<NavTabId>('overview');

  // Controls Real API Integration (Phase 1A: Read-Only GET)
  const {
    isRealData,
    isFetching: controlsFetching,
    globalEntry: remoteGlobalEntry,
    strategies: remoteStrategies,
    capacity,
    operations: remoteOperations,
    selectionMap: remoteSelectionMap,
    refetch: refetchControls,
    generatedAtMs,
  } = useControlsData();

  // Local interaction overrides for Phase 1A UI safety
  const [globalEntryOverride, setGlobalEntryOverride] = useState<typeof remoteGlobalEntry | null>(null);
  const [strategiesOverride, setStrategiesOverride] = useState<StrategyControlItem[] | null>(null);
  const [operationsOverride, setOperationsOverride] = useState<RecentOperationItem[] | null>(null);
  const [selectionMap, setSelectionMap] = useState<Record<string, SelectionDiagnosticData>>(remoteSelectionMap);
  const [flattenPreview] = useState(mockFlattenPreview);

  const globalEntry = globalEntryOverride ?? remoteGlobalEntry;
  const strategies = strategiesOverride ?? remoteStrategies;
  const operations = operationsOverride ?? remoteOperations;

  // Modal States
  const [flattenModalOpen, setFlattenModalOpen] = useState(false);
  const [totpModal, setTotpModal] = useState<{
    open: boolean;
    title: string;
    description: string;
    confirmLabel: string;
    requireTotp: boolean;
    onConfirm: (code: string) => void;
  }>({
    open: false,
    title: '',
    description: '',
    confirmLabel: '',
    requireTotp: true,
    onConfirm: () => {},
  });

  // Toast indicator
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  };

  // 1. Toggle Global Entry
  const handleToggleGlobalEntry = () => {
    if (globalEntry.configured_state === 'enabled') {
      // Pause does NOT require TOTP per code facts
      setGlobalEntryOverride({
        ...globalEntry,
        configured_state: 'paused',
        effective_state: 'paused',
      });
      showToast('全局新开仓已暂停 (存量持仓保护不受影响)');
    } else {
      // Resume REQUIRES TOTP
      setTotpModal({
        open: true,
        title: '确认恢复全局 ENTRY 新开仓',
        description: '恢复全局新准入后，所有处于启用状态的策略在新信号生成时均可创建新 Ticket 并入场。',
        confirmLabel: '确认恢复新准入',
        requireTotp: true,
        onConfirm: () => {
          setGlobalEntryOverride({
            ...globalEntry,
            configured_state: 'enabled',
            effective_state: 'enabled',
          });
          showToast('全局新开仓已恢复运行');
        },
      });
    }
  };

  // 2. Toggle Strategy
  const handleToggleStrategy = (strategy: StrategyControlItem) => {
    if (strategy.is_retired) return;

    if (strategy.configured_state === 'enabled') {
      // Pause
      setStrategiesOverride(
        strategies.map((s) =>
          s.strategy_group_id === strategy.strategy_group_id
            ? { ...s, configured_state: 'paused', effective_state: 'paused' }
            : s
        )
      );
      showToast(`策略 ${strategy.strategy_group_id} 已暂停`);
    } else {
      // Resume requires TOTP
      setTotpModal({
        open: true,
        title: `确认恢复策略 ${strategy.strategy_group_id}`,
        description: `恢复后，${strategy.name_zh} 将重新接收并消费行情事实，生成有效信号时可申请车道准入。`,
        confirmLabel: '确认恢复策略',
        requireTotp: true,
        onConfirm: () => {
          setStrategiesOverride(
            strategies.map((s) =>
              s.strategy_group_id === strategy.strategy_group_id
                ? { ...s, configured_state: 'enabled', effective_state: 'enabled' }
                : s
            )
          );
          showToast(`策略 ${strategy.strategy_group_id} 已恢复运行`);
        },
      });
    }
  };

  // 3. Fallback Selection to Static
  const handleTriggerFallback = (groupId: string) => {
    setTotpModal({
      open: true,
      title: `确认 ${groupId} 回退至 Static 基线`,
      description: `将锁定当前 16 个选入标的为固定交易名单，停止 4 小时动态轮动，直到 Owner 重新授权。需 TOTP 验证码。`,
      confirmLabel: '确认回退至 Static',
      requireTotp: true,
      onConfirm: () => {
        setSelectionMap((prev) => {
          const item = prev[groupId];
          if (!item) return prev;
          const updated: SelectionDiagnosticData = {
            ...item,
            selection_mode: 'static_baseline',
            authority_status_zh: 'Static 固化模式 · 由 Owner 手动锁定',
          };
          return { ...prev, [groupId]: updated };
        });
        showToast(`${groupId} 已回退至 Static 固化名单`);
      },
    });
  };

  // 4. Reauthorize Dynamic Selection
  const handleTriggerReauthorize = (groupId: string) => {
    setTotpModal({
      open: true,
      title: `重新授权 ${groupId} Dynamic 选币轮动`,
      description: `系统将在下一轮合法锚点执行算法选币与物化交接；已有 Ticket 继续原退出规则。需 TOTP 验证码。`,
      confirmLabel: '确认授权 Dynamic',
      requireTotp: true,
      onConfirm: () => {
        setSelectionMap((prev) => {
          const item = prev[groupId];
          if (!item) return prev;
          const updated: SelectionDiagnosticData = {
            ...item,
            selection_mode: 'dynamic_selection',
            authority_status_zh: '权威有效 · 承接上一周期连续性',
          };
          return { ...prev, [groupId]: updated };
        });
        showToast(`${groupId} 动态选币授权已更新`);
      },
    });
  };

  // 5. Refresh Selection
  const handleRefreshData = (groupId: string) => {
    showToast(`已刷新 ${groupId} 选币快照与准入数据`);
  };

  // 6. Confirm Controlled Flatten
  const handleConfirmFlatten = async () => {
    // Simulate async execution
    await new Promise((r) => setTimeout(r, 1200));

    // After flatten, Global ENTRY is paused, tickets are closed
    setGlobalEntryOverride({
      ...globalEntry,
      configured_state: 'paused',
      effective_state: 'paused',
      active_ticket_count: 0,
    });

    setStrategiesOverride(
      strategies.map((s) => ({
        ...s,
        active_tickets: [],
        admission_health: {
          ...s.admission_health,
          status: s.is_retired ? 'blocked' : 'cleared',
          summary: s.is_retired
            ? '已永久退役'
            : '准入畅通 · 待机中 (持仓已受控出场)',
        },
      }))
    );

    // Prepend to audit log
    setOperationsOverride([
      {
        authorization_id: `auth:flatten:${Date.now()}`,
        name: '受控平仓全部仓位',
        state: 'completed',
        ticket_count: 3,
        updated_at_ms: Date.now(),
        first_blocker: null,
      },
      ...operations,
    ]);

    showToast('受控平仓执行完毕 · 全部持仓已由 Lifecycle 退出，全局 ENTRY 已挂起');
  };

  const handleRefreshControls = async () => {
    setGlobalEntryOverride(null);
    setStrategiesOverride(null);
    await refetchControls();
    showToast('已从 PostgreSQL / API 刷新当前事实');
  };

  const pausedCount = strategies.filter((s) => s.configured_state === 'paused' && !s.is_retired).length;

  return (
    <div className="min-h-screen bg-background text-text-primary">
      <Navbar activeTab={activeTab} onSelectTab={setActiveTab} isRealData={isRealData} />

      <main className="mx-auto max-w-[1520px] px-4 py-4 sm:px-6">
        {activeTab === 'overview' ? (
          <div>
            {/* Page Title & Manual Refresh */}
            <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h1 className="text-base font-bold text-text-primary flex items-center gap-2">
                  总览态势
                  <span className="font-mono text-xs font-normal text-text-muted">
                    (System Pulse & Performance)
                  </span>
                </h1>
                <p className="text-xs text-text-secondary mt-0.5">
                  快速掌握系统运行脉搏、今日不对称收益与在管交易；0 关注项即代表一切平稳。
                </p>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => showToast('已刷新总览数据快照')}
                  className="inline-flex items-center gap-1.5 rounded border border-border-strong bg-surface px-3.5 py-1.5 text-xs font-medium text-text-primary hover:bg-surface-elevated transition-colors shadow-xs"
                >
                  <RefreshCw className="h-3.5 w-3.5 text-text-muted" />
                  刷新快照
                </button>
              </div>
            </div>

            <OverviewPage onNavigateToControls={() => setActiveTab('controls')} />
          </div>
        ) : (
          <div>
            {/* Page Title & Manual Refresh */}
            <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h1 className="text-base font-bold text-text-primary flex items-center gap-2">
                  控制中心
                  <span className="font-mono text-xs font-normal text-text-muted">
                    (Owner Controls Console)
                  </span>
                </h1>
                <p className="text-xs text-text-secondary mt-0.5">
                  统一调度全局准入、策略启停、动态选币授权与紧急生命周期干预；任何操作均具备真实不可逆防御。
                </p>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleRefreshControls}
                  disabled={controlsFetching}
                  className="inline-flex items-center gap-1.5 rounded border border-border-strong bg-surface px-3.5 py-1.5 text-xs font-medium text-text-primary hover:bg-surface-elevated transition-colors shadow-xs disabled:opacity-60"
                >
                  <RefreshCw className={`h-3.5 w-3.5 text-text-muted ${controlsFetching ? 'animate-spin text-brand' : ''}`} />
                  <span>{controlsFetching ? '正在读取真实 facts...' : '刷新当前页'}</span>
                </button>
              </div>
            </div>

            {/* Phase 1A: Integration Status Banner */}
            <div className="mb-3 flex items-center justify-between rounded border border-brand/30 bg-brand/5 px-3 py-1.5 text-xs">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[10px] font-bold uppercase rounded bg-brand/10 text-brand px-1.5 py-0.2">
                  Phase 1A: Read-Only
                </span>
                <span className="text-text-secondary">
                  {isRealData
                    ? '已成功接入真实 GET /api/owner/v1/controls 接口与 PostgreSQL 事实'
                    : '已建立真实 API 映射契约 (当前处于离线/原型基线模式，接口就绪后自动热加载)'}
                </span>
              </div>
              <span className="font-mono text-[11px] text-text-muted">
                快照时间: {new Date(generatedAtMs).toLocaleTimeString('zh-CN', { hour12: false })}
              </span>
            </div>

            {/* Level 1: System Status Ribbon */}
            <TopStatusBar
              globalEntry={globalEntry}
              pausedStrategyCount={pausedCount}
              totalActiveStrategies={5}
              onToggleGlobalEntry={handleToggleGlobalEntry}
            />

            {/* Main Workstation 2-Column Split */}
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
              {/* Left Column (8 of 12 cols): Operations & Governance */}
              <div className="space-y-4 lg:col-span-8">
                {/* Strategy Matrix */}
                <StrategyMatrix
                  strategies={strategies}
                  onToggleStrategy={handleToggleStrategy}
                />

                {/* Selection Governance & Fallback */}
                <SelectionSection
                  selectionMap={selectionMap}
                  onTriggerFallback={handleTriggerFallback}
                  onTriggerReauthorize={handleTriggerReauthorize}
                  onRefreshData={handleRefreshData}
                />
              </div>

              {/* Right Column (4 of 12 cols): Safety Guard, Quotas & Audit */}
              <div className="space-y-4 lg:col-span-4">
                {/* High-risk Emergency Flatten Card */}
                <DangerZoneCard
                  onTriggerFlatten={() => setFlattenModalOpen(true)}
                  activeTicketCount={globalEntry.active_ticket_count}
                />

                {/* Capacity & Quotas (Concise, no 0s clutter) */}
                <CapacitySection
                  capacity={capacity}
                  activeTicketCount={globalEntry.active_ticket_count}
                />

                {/* Recent Operations */}
                <RecentOperations operations={operations} />
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Controlled Flatten Modal */}
      <ControlledFlattenModal
        open={flattenModalOpen}
        onOpenChange={setFlattenModalOpen}
        preview={flattenPreview}
        onConfirmFlatten={handleConfirmFlatten}
      />

      {/* TOTP Confirmation Modal */}
      <TotpActionModal
        open={totpModal.open}
        onOpenChange={(open) => setTotpModal((prev) => ({ ...prev, open }))}
        title={totpModal.title}
        description={totpModal.description}
        confirmLabel={totpModal.confirmLabel}
        requireTotp={totpModal.requireTotp}
        onConfirm={totpModal.onConfirm}
      />

      {/* Toast Feedback */}
      {toastMessage && (
        <div className="fixed bottom-5 right-5 z-50 flex items-center gap-2 rounded border border-status-green/40 bg-surface px-4 py-2.5 text-xs font-semibold text-text-primary shadow-xl animate-in fade-in slide-in-from-bottom-2">
          <CheckCircle2 className="h-4 w-4 text-status-green" />
          {toastMessage}
        </div>
      )}
    </div>
  );
};

