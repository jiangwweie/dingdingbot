import React, { useState } from 'react';
import type { SelectionDiagnosticData, UniverseMemberItem } from '../types/controls';
import { useSelectionPreview } from '../hooks/useControlsData';
import { cleanSymbol } from '../hooks/useOverviewData';
import type { GenericSelectionPreview, OrbSelectionPreview } from '../api/controlsApi';
import { SelectionDrawer } from './SelectionDrawer';
import { RefreshCw, RotateCcw, ShieldCheck, ExternalLink, ShieldAlert, Loader2 } from 'lucide-react';

interface SelectionSectionProps {
  onTriggerFallback?: (groupId: string) => void;
  onTriggerReauthorize?: (groupId: string) => void;
  onRefreshData?: (groupId: string) => void;
}

const TABS = ['CPM-RO-001', 'BRF2-001', 'MI-001', 'MPG-001', 'SOR-1H-001'];

function mapPreviewToDiagnostic(
  strategyGroupId: string,
  preview: GenericSelectionPreview | OrbSelectionPreview | undefined
): SelectionDiagnosticData | null {
  if (!preview) return null;
  const isOrb = 'strategy_label' in preview || strategyGroupId === 'SOR-1H-001';
  const runtime = (preview as any).runtime ?? {};
  const control = (preview as any).control ?? {};

  if (isOrb) {
    const snapshotDisp = runtime.snapshot_disposition ?? {};
    const snapshot = snapshotDisp.snapshot ?? {};
    const currentAuth = runtime.current_authority?.authority ?? {};
    const selectedMembersRaw: string[] = snapshotDisp.selected_members ?? [];

    const candidateCount = snapshot.candidate_count ?? 24;
    const selectedCount = snapshot.selected_count ?? selectedMembersRaw.length;
    const readyCount = snapshot.ready_count ?? candidateCount;

    // Selected members list
    const members: UniverseMemberItem[] = selectedMembersRaw.map((m: string) => ({
      exchange_instrument_id: cleanSymbol(m),
      selected: true,
      first_blocker: null,
    }));

    const cadenceHours = 24; // SOR-1H ORB 日周期轮动 (24h)

    const outcome = currentAuth.authority_outcome ?? 'ACTIVE_NEW';
    const epochId = currentAuth.selection_epoch_id ?? null;
    const authorityStatusZh = `权威有效 · ${outcome}`;
    const completionAgeMs = snapshot.created_at_ms
      ? Math.max(0, Date.now() - snapshot.created_at_ms)
      : 0;

    return {
      strategy_group_id: strategyGroupId,
      installed: (preview as any).installed ?? true,
      cadence_hours: cadenceHours,
      selection_mode: (control.selection_mode as any) ?? 'dynamic_selection',
      pending_selection_mode: control.pending_selection_mode ?? null,
      pending_effective_period_anchor_ms: control.pending_effective_period_anchor_ms ?? null,
      rollback_baseline_id: control.rollback_baseline_id ?? null,
      selection_epoch_id: epochId,
      control_version: control.control_version ?? 1,
      current_authority_outcome: outcome,
      authority_status_zh: authorityStatusZh,
      membership_valid_until_ms: snapshot.expires_at_ms ?? 0,
      consecutive_missed_periods: 0,
      latest_ready_count: readyCount,
      latest_selected_count: selectedCount,
      materialization_state: runtime.materialization_generation ? 'active' : 'idle',
      materialization_deadline_ms: null,
      vacuum_state: (runtime.entry_vacuums?.length ?? 0) > 0 ? 'vacuum_active' : 'clear',
      vacuum_fenced_at_ms: null,
      latest_successful_completion_age_ms: completionAgeMs,
      latest_successful_cutoff_age_ms: completionAgeMs,
      membership_source_age_ms: completionAgeMs,
      members,
    };
  }

  // Generic Selection (CPM, BRF2, MI, MPG)
  const isGeneric = 'cadence_hours' in preview;
  const members: UniverseMemberItem[] = (runtime.members ?? []).map((m: any) => ({
    exchange_instrument_id: cleanSymbol(m.exchange_instrument_id),
    selected: Boolean(m.selected),
    first_blocker: m.first_blocker ?? null,
  }));

  const cadenceHours = isGeneric ? (preview as GenericSelectionPreview).cadence_hours : 4;
  const selectionMode = control.selection_mode ?? 'dynamic_selection';
  const selectedCount = runtime.latest_selected_count ?? members.filter((m) => m.selected).length;
  const readyCount = runtime.latest_ready_count ?? members.length;

  return {
    strategy_group_id: strategyGroupId,
    installed: runtime.installed ?? true,
    cadence_hours: cadenceHours,
    selection_mode: selectionMode,
    pending_selection_mode: control.pending_selection_mode ?? null,
    pending_effective_period_anchor_ms: control.pending_effective_period_anchor_ms ?? null,
    rollback_baseline_id: control.rollback_baseline_id ?? null,
    selection_epoch_id: runtime.selection_epoch_id ?? null,
    control_version: control.control_version ?? 1,
    current_authority_outcome: runtime.current_authority_outcome ?? '权威有效',
    authority_status_zh: runtime.current_authority_outcome
      ? `权威有效 · ${runtime.current_authority_outcome}`
      : '权威有效 · 承接上一周期连续性',
    membership_valid_until_ms: runtime.membership_valid_until_ms ?? 0,
    consecutive_missed_periods: runtime.consecutive_missed_periods ?? 0,
    latest_ready_count: readyCount,
    latest_selected_count: selectedCount,
    materialization_state: runtime.materialization_state ?? 'active',
    materialization_deadline_ms: runtime.materialization_deadline_ms ?? null,
    vacuum_state: runtime.vacuum_state ?? 'clear',
    vacuum_fenced_at_ms: runtime.vacuum_fenced_at_ms ?? null,
    latest_successful_completion_age_ms: runtime.latest_successful_completion_age_ms ?? 0,
    latest_successful_cutoff_age_ms: runtime.latest_successful_cutoff_age_ms ?? 0,
    membership_source_age_ms: runtime.membership_source_age_ms ?? 0,
    members,
  };
}

export const SelectionSection: React.FC<SelectionSectionProps> = () => {
  const [activeTab, setActiveTab] = useState('CPM-RO-001');
  const [drawerOpen, setDrawerOpen] = useState(false);

  const { data: rawPreview, isLoading, isError, refetch } = useSelectionPreview(activeTab);
  const current = mapPreviewToDiagnostic(activeTab, rawPreview);

  const isDynamic = current ? current.selection_mode === 'dynamic_selection' : true;
  const selectedCount = current?.latest_selected_count ?? 0;
  const totalPool = current
    ? Math.max(current.latest_ready_count, current.members.length, 24)
    : 24;
  const filteredCount = Math.max(0, totalPool - selectedCount);

  return (
    <div className="rounded border border-border bg-surface shadow-xs">
      {/* Header & Tabs */}
      <div className="flex flex-col gap-3 border-b border-border px-5 py-3.5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-xs font-bold uppercase tracking-wider text-text-primary">
            动态选币与轮动治理 (Selection)
          </h2>
          <p className="mt-0.5 text-xs text-text-secondary">
            各策略独立的 4h / 24h 动态打分授权与 Static 基线回退；修改均需 Owner TOTP 签名。
          </p>
        </div>

        {/* Strategy Switcher Tabs */}
        <div className="flex items-center gap-1 rounded border border-border bg-surface-subtle p-1">
          {TABS.map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={`rounded px-3 py-1 font-mono text-xs font-medium transition-colors ${
                activeTab === tab
                  ? 'bg-surface text-brand font-bold shadow-xs border border-border'
                  : 'text-text-muted hover:text-text-primary'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>

      {/* Main Body for Active Strategy: Unified Single-Row Command Bar */}
      <div className="p-3.5">
        {isLoading ? (
          <div className="flex items-center justify-center py-6 gap-2 text-xs text-text-muted">
            <Loader2 className="h-4 w-4 animate-spin text-brand" />
            <span>正在读取 {activeTab} 选币真实快照...</span>
          </div>
        ) : isError || !current ? (
          <div className="flex items-center justify-between rounded border border-border bg-surface-subtle px-4 py-3 text-xs text-text-muted">
            <span>该策略当前暂无可用的选币事实或尚未安装。</span>
            <button
              type="button"
              onClick={() => refetch()}
              className="inline-flex items-center gap-1 rounded border border-border px-2.5 py-1 text-xs font-medium text-text-primary hover:bg-surface-elevated"
            >
              <RefreshCw className="h-3 w-3" />
              重试
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-2 rounded border border-border bg-surface-subtle px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
            {/* Left: Mode, Authority, Counts & Freshness */}
            <div className="flex flex-wrap items-center gap-2.5">
              {/* Mode badge */}
              <span
                className={`inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-xs font-semibold ${
                  isDynamic
                    ? 'border border-status-blue/30 bg-status-blue-bg text-status-blue'
                    : 'border border-status-amber/30 bg-status-amber-bg text-status-amber'
                }`}
              >
                <span
                  className={`h-2 w-2 rounded-full ${
                    isDynamic ? 'bg-status-blue' : 'bg-status-amber'
                  }`}
                />
                {isDynamic
                  ? current.cadence_hours === 24
                    ? 'DYNAMIC (24h 日周期)'
                    : `DYNAMIC (${current.cadence_hours}h)`
                  : 'STATIC 基线'}
              </span>

              {/* Authority Status */}
              <div className="flex items-center gap-1 text-xs">
                <ShieldCheck className="h-4 w-4 text-status-green flex-none" />
                <span className="font-semibold text-text-primary">
                  {current.authority_status_zh}
                </span>
              </div>

              <span className="text-text-muted opacity-30">·</span>

              {/* Candidates Counts */}
              <div className="flex items-center gap-1 text-xs font-medium text-text-secondary">
                <span className="text-status-green font-semibold">{selectedCount}</span> 入围 /{' '}
                <span className="text-text-muted">{filteredCount}</span> 过滤
              </div>

              <span className="text-text-muted opacity-30">·</span>

              {/* Freshness / Age */}
              <span className="font-mono text-xs text-text-muted">
                年龄:{' '}
                {current.latest_successful_completion_age_ms > 0
                  ? `${Math.round(current.latest_successful_completion_age_ms / 3600000)}h 前`
                  : '近期生成'}
              </span>
            </div>

            {/* Right: Actions & Drawer Trigger */}
            <div className="flex items-center gap-2">
              {isDynamic ? (
                <button
                  type="button"
                  disabled
                  title="Phase 1 · 只读模式 (选币模式切换写操作未开放)"
                  className="inline-flex items-center gap-1 rounded border border-border bg-surface px-2.5 py-1 text-xs font-medium text-text-muted opacity-60 cursor-not-allowed shadow-none"
                >
                  <RotateCcw className="h-3.5 w-3.5 text-text-muted" />
                  回退 Static (只读)
                </button>
              ) : (
                <button
                  type="button"
                  disabled
                  title="Phase 1 · 只读模式 (选币模式切换写操作未开放)"
                  className="inline-flex items-center gap-1 rounded border border-border bg-surface px-2.5 py-1 text-xs font-medium text-text-muted opacity-60 cursor-not-allowed shadow-none"
                >
                  <ShieldAlert className="h-3.5 w-3.5 text-text-muted" />
                  授权 Dynamic (只读)
                </button>
              )}

              <button
                type="button"
                onClick={() => refetch()}
                className="inline-flex items-center gap-1 rounded border border-border-strong bg-surface px-2.5 py-1 text-xs font-medium text-text-primary hover:bg-surface-elevated transition-colors shadow-xs"
                title="重新读取该策略选币快照"
              >
                <RefreshCw className="h-3.5 w-3.5 text-text-muted" />
                刷新
              </button>

              <button
                type="button"
                onClick={() => setDrawerOpen(true)}
                className="inline-flex items-center gap-1 rounded border border-border-strong bg-surface px-2.5 py-1 text-xs font-semibold text-brand hover:bg-surface-elevated transition-colors shadow-xs"
              >
                <span>标的明细与诊断</span>
                <ExternalLink className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Drawer */}
      {current && (
        <SelectionDrawer
          open={drawerOpen}
          onOpenChange={setDrawerOpen}
          data={current}
        />
      )}
    </div>
  );
};
