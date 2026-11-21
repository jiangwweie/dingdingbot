import React, { useState } from 'react';
import { useControlsData } from '../hooks/useControlsData';
import { cleanSymbol } from '../hooks/useOverviewData';
import { CausalityDrawer } from './overview/CausalityDrawer';
import { TopStatusBar } from './TopStatusBar';
import { StrategyMatrix } from './StrategyMatrix';
import { SelectionSection } from './SelectionSection';
import { DangerZoneCard } from './DangerZoneCard';
import { ControlledFlattenModal } from './ControlledFlattenModal';
import { RiskBudgetCard } from './overview/RiskBudgetCard';
import { CapacitySection } from './CapacitySection';
import { RecentOperations } from './RecentOperations';
import { useFlattenControl } from '../hooks/useFlattenControl';
import { useGlobalEntryControl } from '../hooks/useGlobalEntryControl';
import { TotpActionModal } from './TotpActionModal';
import type { TradeEpisodeSummary } from '../types/overview';
import { RefreshCw, AlertCircle, Shield } from 'lucide-react';

export const ControlsPage: React.FC = () => {
  const [selectedTicketEpisode, setSelectedTicketEpisode] = useState<TradeEpisodeSummary | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  };

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

  const flattenControl = useFlattenControl({
    onSuccess: (op) => {
      showToast(`受控平仓指令已提交 (${op.state})，全局 ENTRY 已挂起。`);
    },
    onError: (msg) => {
      showToast(msg);
    },
  });

  const activeFlattenOperation = currentOperation ?? flattenControl.currentOperation;

  const globalControl = useGlobalEntryControl({
    onSuccess: (msg) => showToast(msg),
    activeFlattenOperation,
  });

  const activeStrategies = strategies.filter((s) => !s.is_retired && s.strategy_group_id !== 'SOR-001');
  const enabledCount = activeStrategies.filter((s) => s.configured_state === 'enabled').length;
  const pausedCount = activeStrategies.filter((s) => s.configured_state === 'paused').length;
  const unknownCount = activeStrategies.length - enabledCount - pausedCount;

  return (
    <div id="controls-page">
      {/* Controls Header & Refresh */}
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-base font-bold text-text-primary flex items-center gap-2">
            控制中心
          </h1>
          <p className="mt-0.5 text-xs text-text-secondary">
            全局开仓开关、各策略准入控制、动态选币授权、容量占用与最近操作。
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
            <span>{controlsFetching ? '刷新中...' : '刷新当前页'}</span>
          </button>
        </div>
      </div>

      {/* Control Posture Status Banner */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded border border-brand/30 bg-brand/5 px-3 py-1.5 text-xs">
        <span className="text-text-secondary">
          高风险控制操作均需 TOTP 签名与基线版本核验 · 单 Ticket 平仓保持禁用
        </span>
        <span className="font-mono text-[11px] text-text-muted">
          快照时间: {new Date(generatedAtMs).toLocaleTimeString('zh-CN', { hour12: false })}
        </span>
      </div>

      {controlsLoading ? (
        <div className="py-24 text-center">
          <div className="inline-block h-6 w-6 border-2 border-brand/30 border-t-brand rounded-full animate-spin mb-3" />
          <p className="text-xs text-text-secondary">正在读取控制中心快照...</p>
        </div>
      ) : controlsError ? (
        <div className="rounded-xl border border-danger/30 bg-surface p-8 text-center max-w-lg mx-auto my-8 shadow-sm">
          <div className="inline-flex items-center justify-center h-12 w-12 rounded-full bg-danger/10 text-danger mb-4">
            <AlertCircle className="h-6 w-6" />
          </div>
          <h3 className="text-base font-bold text-text-primary">控制状态暂时不可用</h3>
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
            enabledStrategyCount={enabledCount}
            pausedStrategyCount={pausedCount}
            unknownStrategyCount={unknownCount}
            totalActiveStrategies={activeStrategies.length}
            onRequestAction={globalControl.requestAction}
            isActionDisabled={Boolean(
              activeFlattenOperation &&
              activeFlattenOperation.state !== 'completed' &&
              activeFlattenOperation.state !== 'blocked'
            )}
            disabledReason={
              activeFlattenOperation &&
              activeFlattenOperation.state !== 'completed' &&
              activeFlattenOperation.state !== 'blocked'
                ? '受控平仓正在执行中，禁止操作全局新开仓准入'
                : undefined
            }
          />

          <RiskBudgetCard />

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
          <SelectionSection onSuccess={(msg) => showToast(msg)} />

          {/* Level 4: Capacity & High Risk Guardrail */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <CapacitySection
              capacity={capacity}
              activeTicketCount={globalEntry.active_ticket_count}
              policyVersion={globalEntry.policy_version}
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

      {/* Global Entry Control Modal */}
      <TotpActionModal {...globalControl.modalProps} />

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
