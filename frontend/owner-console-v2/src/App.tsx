import React, { useState } from 'react';
import { useAuth } from './hooks/useAuth';
import { useControlsData } from './hooks/useControlsData';
import { cleanSymbol } from './hooks/useOverviewData';
import { LoginPage } from './components/auth/LoginPage';
import { Navbar, type NavTabId } from './components/Navbar';
import { OverviewPage } from './components/overview/OverviewPage';
import { CausalityDrawer } from './components/overview/CausalityDrawer';
import { TopStatusBar } from './components/TopStatusBar';
import { StrategyMatrix } from './components/StrategyMatrix';
import { SelectionSection } from './components/SelectionSection';
import { DangerZoneCard } from './components/DangerZoneCard';
import { CapacitySection } from './components/CapacitySection';
import { RecentOperations } from './components/RecentOperations';
import type { TradeEpisodeSummary } from './types/overview';
import { RefreshCw, AlertCircle, Shield } from 'lucide-react';

export const App: React.FC = () => {
  const {
    isAuthenticated,
    isLoading: isCheckingSession,
    login,
    isLoggingIn,
    loginError,
    logout,
  } = useAuth();

  const [activeTab, setActiveTab] = useState<NavTabId>('overview');
  const [selectedTicketEpisode, setSelectedTicketEpisode] = useState<TradeEpisodeSummary | null>(null);

  // Controls Data
  const {
    globalEntry,
    strategies,
    capacity,
    operations,
    rawTickets,
    isLoading: controlsLoading,
    isFetching: controlsFetching,
    isError: controlsError,
    error: controlsErrorObj,
    generatedAtMs,
    refetch: refetchControls,
  } = useControlsData();

  // Toast indicator
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  };

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

  // 2. Unauthenticated -> Show Login Page
  if (!isAuthenticated) {
    return <LoginPage onLogin={login} isLoading={isLoggingIn} error={loginError} />;
  }

  // 3. Authenticated Console
  const pausedCount = strategies.filter((s) => s.configured_state === 'paused' && !s.is_retired).length;

  return (
    <div className="min-h-screen bg-background text-text-primary">
      <Navbar
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        isRealData={true}
        onLogout={logout}
      />

      <main className="mx-auto max-w-[1520px] px-4 py-4 sm:px-6">
        {activeTab === 'overview' ? (
          <OverviewPage onNavigateToControls={() => setActiveTab('controls')} />
        ) : (
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

            {/* Phase 1 Read-Only Status Banner */}
            <div className="mb-4 flex items-center justify-between rounded border border-brand/30 bg-brand/5 px-3 py-1.5 text-xs">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[10px] font-bold uppercase rounded bg-brand/10 text-brand px-1.5 py-0.5 border border-brand/20">
                  Phase 1: Real Read-Only
                </span>
                <span className="text-text-secondary">
                  已连接生产 API · 只读模式 (写操作保持安全禁用，绝无假交互)
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
                  onToggleStrategy={() =>
                    showToast('Phase 1 · 只读模式 (策略启停写操作未开放)')
                  }
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
                  />
                </div>

                {/* Level 5: Audit Log */}
                <RecentOperations operations={operations} />
              </div>
            ) : null}
          </div>
        )}
      </main>

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
