import React, { useState, useEffect } from 'react';
import { useAuth } from './hooks/useAuth';
import { useControlsData } from './hooks/useControlsData';
import { cleanSymbol } from './hooks/useOverviewData';
import { LoginPage } from './components/auth/LoginPage';
import { Navbar, type NavTabId } from './components/Navbar';
import { OverviewPage } from './components/overview/OverviewPage';
import { TradesPage } from './components/trades/TradesPage';
import { StrategiesPage } from './components/strategies/StrategiesPage';
import { ReviewPage } from './components/review/ReviewPage';
import { CausalityDrawer } from './components/overview/CausalityDrawer';
import { TopStatusBar } from './components/TopStatusBar';
import { StrategyMatrix } from './components/StrategyMatrix';
import { SelectionSection } from './components/SelectionSection';
import { DangerZoneCard } from './components/DangerZoneCard';
import { ControlledFlattenModal } from './components/ControlledFlattenModal';
import { CapacitySection } from './components/CapacitySection';
import { RecentOperations } from './components/RecentOperations';
import { useFlattenControl } from './hooks/useFlattenControl';
import type { TradeEpisodeSummary } from './types/overview';
import { RefreshCw, AlertCircle, Shield } from 'lucide-react';

const getInitialTab = (): NavTabId => {
  if (typeof window !== 'undefined') {
    const tab = new URLSearchParams(window.location.search).get('tab');
    if (tab === 'trades' || tab === 'strategies' || tab === 'controls' || tab === 'overview' || tab === 'review') {
      return tab;
    }
  }
  return 'overview';
};

export const App: React.FC = () => {
  const {
    isAuthenticated,
    isLoading: isCheckingSession,
    login,
    isLoggingIn,
    loginError,
    logout,
    isLoggingOut,
    logoutError,
    isLogoutUnconfirmed,
    acknowledgeUnconfirmedSession,
  } = useAuth();

  const [activeTab, setActiveTab] = useState<NavTabId>(getInitialTab);
  const [selectedTicketEpisode, setSelectedTicketEpisode] = useState<TradeEpisodeSummary | null>(null);

  // Synchronize activeTab with browser URL search params on popstate
  useEffect(() => {
    if (typeof window === 'undefined') return;

    const onPopState = () => {
      const tab = new URLSearchParams(window.location.search).get('tab');
      if (tab === 'trades' || tab === 'strategies' || tab === 'controls' || tab === 'overview' || tab === 'review') {
        setActiveTab(tab);
      } else {
        setActiveTab('overview');
      }
    };

    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  const handleSelectTab = (tab: NavTabId) => {
    setActiveTab(tab);
    if (typeof window !== 'undefined') {
      const sp = new URLSearchParams(window.location.search);
      if (sp.get('tab') !== tab) {
        const newSp = new URLSearchParams();
        newSp.set('tab', tab);
        window.history.pushState(null, '', `${window.location.pathname}?${newSp.toString()}`);
      }
    }
  };

  // Controls Data
  const {
    globalEntry,
    strategies,
    capacity,
    operations,
    currentOperation,
    rawTickets,
    isLoading: controlsLoading,
    isFetching: controlsFetching,
    isError: controlsError,
    error: controlsErrorObj,
    generatedAtMs,
    refetch: refetchControls,
  } = useControlsData();

  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  };

  const flattenControl = useFlattenControl({
    onSuccess: (op) => {
      showToast(`受控平仓指令已提交 (${op.state})，全局 ENTRY 已挂起。`);
    },
    onError: (msg) => {
      showToast(msg);
    },
  });

  const activeFlattenOperation = currentOperation ?? flattenControl.currentOperation;

  // 1. Session Verification View
  if (isCheckingSession) {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center p-4">
        <div className="h-8 w-8 border-2 border-brand/30 border-t-brand rounded-full animate-spin mb-3" />
        <p className="text-xs font-semibold text-text-primary">正在验证 Owner 会话...</p>
        <span className="text-[11px] text-text-muted mt-1">GET /api/owner/v1/auth/session</span>
      </div>
    );
  }

  // 2. Unconfirmed Logout Screen
  if (isLogoutUnconfirmed) {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center p-4">
        <div className="max-w-md w-full rounded-lg border border-danger/40 bg-surface p-6 shadow-xl text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-danger/10 text-danger mb-4 border border-danger/20">
            <AlertCircle className="h-6 w-6" />
          </div>
          <h2 className="text-base font-bold text-text-primary">
            服务端退出未确认
          </h2>
          <p className="mt-2 text-xs text-text-secondary leading-relaxed">
            {logoutError ?? '此前退出请求未获得服务端有效性注销确认。为保障交易安全，当前页面已进行隐私遮蔽。'}
          </p>
          <div className="mt-6 flex flex-col gap-2.5">
            <button
              type="button"
              disabled={isLoggingOut}
              onClick={() => logout()}
              className="w-full rounded bg-danger px-4 py-2 text-xs font-bold text-white hover:bg-danger/90 transition-colors shadow-xs cursor-pointer flex items-center justify-center gap-2"
            >
              {isLoggingOut ? '正在重试注销...' : '重试退出服务端会话 (POST /auth/logout)'}
            </button>
            <button
              type="button"
              onClick={acknowledgeUnconfirmedSession}
              className="w-full rounded border border-border bg-surface-subtle px-4 py-2 text-xs font-semibold text-text-muted hover:text-text-primary hover:bg-surface-elevated transition-colors cursor-pointer"
            >
              忽略警告并进入控制台
            </button>
          </div>
        </div>
      </div>
    );
  }

  // 3. Unauthenticated -> Show Login Page
  if (!isAuthenticated) {
    return <LoginPage onLogin={login} isLoading={isLoggingIn} error={loginError} />;
  }

  // 3. Authenticated Console
  const pausedCount = strategies.filter((s) => s.configured_state === 'paused' && !s.is_retired).length;

  return (
    <div className="min-h-screen bg-background text-text-primary">
      <Navbar
        activeTab={activeTab}
        onSelectTab={handleSelectTab}
        isRealData={true}
        onLogout={logout}
        isLoggingOut={isLoggingOut}
      />

      <main className="mx-auto max-w-[1520px] px-4 py-4 sm:px-6">
        {activeTab === 'overview' && (
          <OverviewPage onNavigateToControls={() => handleSelectTab('controls')} />
        )}

        {activeTab === 'trades' && (
          <TradesPage />
        )}

        {activeTab === 'strategies' && (
          <StrategiesPage />
        )}

        {activeTab === 'review' && (
          <ReviewPage />
        )}

        {activeTab === 'controls' && (
          <div>
            {/* Controls Header & Refresh */}
            <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h1 className="text-base font-bold text-text-primary flex items-center gap-2">
                  控制中心
                  <span className="rounded bg-brand/10 text-brand text-[10px] font-mono px-2 py-0.5 border border-brand/20">
                    CONTROLS
                  </span>
                </h1>
                <p className="mt-0.5 text-xs text-text-secondary">
                  全局开仓开关、各策略准入控制、动态选币授权、容量占用与审计流水。
                </p>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => refetchControls()}
                  disabled={controlsFetching}
                  className="inline-flex items-center gap-1.5 rounded border border-border-strong bg-surface px-3.5 py-1.5 text-xs font-medium text-text-primary hover:bg-surface-elevated transition-colors shadow-xs disabled:opacity-60"
                >
                  <RefreshCw
                    className={`h-3.5 w-3.5 text-text-muted ${
                      controlsFetching ? 'animate-spin text-brand' : ''
                    }`}
                  />
                  <span>{controlsFetching ? '正在读取真实 facts...' : '刷新当前页'}</span>
                </button>
              </div>
            </div>

            {/* Control Posture Status Banner */}
            <div className="mb-4 flex items-center justify-between rounded border border-brand/30 bg-brand/5 px-3 py-1.5 text-xs">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[10px] font-bold uppercase rounded bg-brand/10 text-brand px-1.5 py-0.5 border border-brand/20">
                  Phase B: Guarded Strategy & Global Flatten Controls Active
                </span>
                <span className="text-text-secondary">
                  单策略启停与全局受控平仓已接通权威写操作 (强制 TOTP + 文本确认) · 单 Ticket 平仓与选币授权保持安全禁用
                </span>
              </div>
              <span className="font-mono text-[11px] text-text-muted">
                快照时间: {new Date(generatedAtMs).toLocaleTimeString('zh-CN', { hour12: false })}
              </span>
            </div>

            {controlsLoading ? (
              <div className="py-24 text-center">
                <div className="inline-block h-6 w-6 border-2 border-brand/30 border-t-brand rounded-full animate-spin mb-3" />
                <p className="text-xs text-text-secondary">正在读取 /controls 控制台事实...</p>
              </div>
            ) : controlsError ? (
              <div className="rounded-xl border border-danger/30 bg-surface p-8 text-center max-w-lg mx-auto my-8 shadow-sm">
                <div className="inline-flex items-center justify-center h-12 w-12 rounded-full bg-danger/10 text-danger mb-4">
                  <AlertCircle className="h-6 w-6" />
                </div>
                <h3 className="text-base font-bold text-text-primary">Controls API 暂时不可用</h3>
                <p className="mt-1.5 text-xs text-text-secondary leading-relaxed">
                  {controlsErrorObj instanceof Error
                    ? controlsErrorObj.message
                    : '未能成功获取真实控制状态。'}
                </p>
                <div className="mt-5">
                  <button
                    type="button"
                    onClick={() => refetchControls()}
                    className="inline-flex items-center gap-1.5 rounded bg-brand px-4 py-2 text-xs font-semibold text-white hover:bg-brand/90 transition-colors"
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                    <span>重试</span>
                  </button>
                </div>
              </div>
            ) : globalEntry && capacity ? (
              <div className="space-y-4">
                {/* Level 1: System Status Ribbon */}
                <TopStatusBar
                  globalEntry={globalEntry}
                  pausedStrategyCount={pausedCount}
                  totalActiveStrategies={strategies.length}
                  onToggleGlobalEntry={() =>
                    showToast('Phase 1 · 只读模式 (全局开仓写操作未开放)')
                  }
                />

                {/* Level 2: Strategy Control Matrix */}
                <StrategyMatrix
                  strategies={strategies}
                  onSuccess={(msg) => showToast(msg)}
                  onSelectTicket={(ticketId) => {
                    const matching = rawTickets.find((t) => t.ticket_id === ticketId);
                    if (matching) {
                      setSelectedTicketEpisode({
                        ticket_id: matching.ticket_id,
                        strategy_id: matching.strategy_group_id,
                        strategy_name_zh: matching.strategy_group_id,
                        symbol: cleanSymbol(matching.exchange_instrument_id),
                        side: matching.position_side,
                        lifecycle_stage: matching.lifecycle_stage,
                        lifecycle_stage_zh: matching.lifecycle_stage,
                        completed_stage_count: matching.completed_stage_count,
                        total_stage_count: matching.total_stage_count,
                        ticket_status: matching.ticket_status,
                        issued_at_ms: matching.issued_at_ms,
                        issued_at_formatted: new Date(matching.issued_at_ms).toLocaleTimeString(
                          'zh-CN',
                          { hour12: false }
                        ),
                        attention_items: matching.attention_items ?? [],
                        net_pnl_formatted: '--',
                        net_r_formatted: '--',
                      });
                    }
                  }}
                />

                {/* Level 3: Dynamic Selection Governance */}
                <SelectionSection />

                {/* Level 4: Capacity & High Risk Guardrail */}
                <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <CapacitySection
                    capacity={capacity}
                    activeTicketCount={globalEntry.active_ticket_count}
                  />
                  <DangerZoneCard
                    activeTicketCount={globalEntry.active_ticket_count}
                    onTriggerFlatten={flattenControl.requestPreview}
                    isLoading={flattenControl.isLoadingPreview}
                    currentOperation={activeFlattenOperation}
                  />
                </div>

                {/* Level 5: Audit Log */}
                <RecentOperations operations={operations} />
              </div>
            ) : null}
          </div>
        )}
      </main>

      {/* Controlled Flatten Modal */}
      <ControlledFlattenModal
        open={flattenControl.isModalOpen}
        onClose={flattenControl.closeModal}
        preview={flattenControl.preview}
        isSubmitting={flattenControl.isSubmitting}
        isVerifying={flattenControl.isVerifying}
        errorMessage={flattenControl.errorMessage}
        isUnknownResult={flattenControl.isUnknownResult}
        isRetryFrozen={flattenControl.isRetryFrozen}
        currentOperation={activeFlattenOperation}
        inFlightOperation={flattenControl.inFlight}
        onConfirm={flattenControl.handleConfirm}
        onVerifyStatus={flattenControl.handleVerifyStatus}
        onRefreshPreview={flattenControl.requestPreview}
      />

      {/* Causality Drawer triggered from Controls Strategy Matrix */}
      <CausalityDrawer
        episode={selectedTicketEpisode}
        onClose={() => setSelectedTicketEpisode(null)}
      />

      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded border border-border-strong bg-surface-elevated px-4 py-2.5 text-xs font-semibold text-text-primary shadow-xl animate-in fade-in-50 slide-in-from-bottom-2">
          <Shield className="h-4 w-4 text-brand" />
          <span>{toastMessage}</span>
        </div>
      )}
    </div>
  );
};
