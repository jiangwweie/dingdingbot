import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, X } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { components } from "../../api/schema";
import { AppShell } from "../../app/AppShell";
import { DenseTable, type DenseTableColumnDef } from "../../components/tables/DenseTable";
import { InlineDetailRow } from "../../components/tables/InlineDetailRow";
import { Button } from "../../components/ui/Button";
import { DataAge } from "../../components/ui/DataAge";
import { ManualRefreshButton } from "../../components/ui/ManualRefreshButton";
import { PageHeader } from "../../components/ui/PageHeader";
import { StatusTag, type StatusTone } from "../../components/ui/StatusTag";
import { UnavailablePanel } from "../../components/ui/UnavailablePanel";
import { formatTimestamp } from "../../components/ui/presentation";
import {
  applyUniverse,
  getInstruments,
  instrumentsQueryKey,
  previewUniverse,
  refreshInstruments,
  type InstrumentFilters,
} from "./api";

type Instrument = components["schemas"]["InstrumentCenterItem"];
type Universe = components["schemas"]["InstrumentUniverseView"];
type Freshness = components["schemas"]["Freshness"];
type ProductFamily = NonNullable<InstrumentFilters["product_family"]>;
type SessionState = NonNullable<InstrumentFilters["session_state"]>;

const COLUMN_WIDTHS = ["17%", "12%", "15%", "15%", "13%", "20%", "8%"] as const;

function freshnessPresentation(freshness: Freshness) {
  if (freshness === "stale") return { label: "数据陈旧", tone: "attention" as const };
  if (freshness === "unavailable") return { label: "数据不可用", tone: "danger" as const };
  if (freshness === "contradictory") return { label: "事实矛盾", tone: "danger" as const };
  return { label: "数据正常", tone: "success" as const };
}

function statusTone(value: string | null): StatusTone {
  if (value === "active" || value === "regular" || value === "clear") return "success";
  if (value === "blocked" || value === "inactive") return "danger";
  if (value === "temporarily_unavailable" || value === "unavailable" || value === "no_trading") return "attention";
  return "neutral";
}

function sessionLabel(value: Instrument["session_state"]): string {
  return value === null ? "UNAVAILABLE" : value.toUpperCase();
}

function productLabel(item: Instrument): string {
  return item.product_family === "tradfi_equity_perpetual" ? "Equity Perp" : "Crypto Perp";
}

function exactPrice(value: string | null): string {
  if (value === null) return "—";
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString("en-US", { maximumFractionDigits: 4 }) : value;
}

function spreadLabel(item: Instrument): string {
  const current = spreadBps(item);
  if (current === null) return "—";
  const threshold = item.max_entry_spread_bps;
  return threshold === null ? `${current.toFixed(1)} bps` : `${current.toFixed(1)} / ${Number(threshold).toFixed(0)} bps`;
}

function spreadBps(item: Instrument): number | null {
  if (item.best_bid === null || item.best_ask === null) return null;
  const bid = Number(item.best_bid);
  const ask = Number(item.best_ask);
  const midpoint = (bid + ask) / 2;
  if (!Number.isFinite(midpoint) || midpoint <= 0 || ask < bid) return null;
  return ((ask - bid) / midpoint) * 10_000;
}

function markIndexDeviationBps(item: Instrument): number | null {
  if (item.mark_price === null || item.index_price === null) return null;
  const mark = Number(item.mark_price);
  const index = Number(item.index_price);
  if (!Number.isFinite(mark) || !Number.isFinite(index) || index <= 0) return null;
  return Math.abs(mark - index) / index * 10_000;
}

function thresholdTone(value: number | null, threshold: string | null): StatusTone {
  if (value === null || threshold === null) return "neutral";
  const ratio = value / Number(threshold);
  if (ratio > 1) return "danger";
  if (ratio >= 0.8) return "attention";
  return "success";
}

function fundingLabel(value: string | null): string {
  if (value === null) return "—";
  const number = Number(value);
  return Number.isFinite(number) ? `${(number * 100).toFixed(4)}%` : value;
}

function membershipLabel(item: Instrument): string {
  if (item.memberships.length === 0) return "未加入策略池";
  return item.memberships.map((membership) => `${membership.event_id} · ${membership.lifecycle_state}`).join(" / ");
}

function UniverseEditor({
  instruments,
  universes,
  open,
  onOpenChange,
  onApplied,
}: {
  instruments: Instrument[];
  universes: Universe[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onApplied: () => void;
}) {
  const [selectedEventSpecId, setSelectedEventSpecId] = useState(universes[0]?.event_spec_id ?? "");
  const selectedUniverse = universes.find((item) => item.event_spec_id === selectedEventSpecId) ?? universes[0];
  const [members, setMembers] = useState<string[]>(selectedUniverse?.exchange_instrument_ids ?? []);
  const [reason, setReason] = useState("调整观察标的池");
  const [totpCode, setTotpCode] = useState("");
  const preview = useMutation({ mutationFn: previewUniverse });
  const apply = useMutation({ mutationFn: applyUniverse });

  const selectUniverse = (eventSpecId: string) => {
    const next = universes.find((item) => item.event_spec_id === eventSpecId);
    setSelectedEventSpecId(eventSpecId);
    setMembers(next?.exchange_instrument_ids ?? []);
    setTotpCode("");
    preview.reset();
    apply.reset();
  };
  const toggleMember = (instrumentId: string) => {
    setMembers((current) => current.includes(instrumentId)
      ? current.filter((item) => item !== instrumentId)
      : [...current, instrumentId].sort());
    preview.reset();
    apply.reset();
  };
  const runPreview = () => {
    if (!selectedUniverse) return;
    preview.mutate({
      runtime_profile_id: selectedUniverse.runtime_profile_id,
      event_id: selectedUniverse.event_id,
      exchange_instrument_ids: members,
    });
  };
  const runApply = () => {
    if (!selectedUniverse || !preview.data?.can_apply) return;
    apply.mutate({
      runtime_profile_id: selectedUniverse.runtime_profile_id,
      event_id: selectedUniverse.event_id,
      exchange_instrument_ids: members,
      expected_base_universe_version_id: preview.data.base_universe_version_id,
      reason,
      idempotency_key: `owner-request:universe:${crypto.randomUUID()}`,
      totp_code: totpCode,
    }, {
      onSuccess: () => {
        onApplied();
        setTotpCode("");
      },
    });
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/80 backdrop-blur-sm" />
        <Dialog.Content className="fixed inset-x-3 top-1/2 z-50 grid max-h-[calc(100vh-32px)] -translate-y-1/2 grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden rounded-[6px] border border-[var(--color-divider)] bg-[var(--color-surface)] shadow-2xl outline-none md:inset-x-[12vw] lg:inset-x-[22vw]">
          <div className="flex min-h-12 items-center justify-between border-b border-[var(--color-divider)] bg-[var(--color-surface-secondary)] px-4 py-2.5">
            <div>
              <Dialog.Title className="m-0 text-[14px] font-bold text-[var(--color-text-primary)]">Universe 成员</Dialog.Title>
              <Dialog.Description className="m-0 mt-0.5 text-[11px] text-[var(--color-text-secondary)]">Preview 差异后通过 TOTP 创建 Warming；不会直接替换 Active Universe。</Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <button className="grid h-7 w-7 place-items-center rounded text-[var(--color-text-secondary)] transition-colors hover:bg-white/[0.06] hover:text-[var(--color-text-primary)]" type="button" aria-label="关闭 Universe 编辑">
                <X className="h-4 w-4" />
              </button>
            </Dialog.Close>
          </div>
          <div className="min-h-0 overflow-y-auto p-4">
            {selectedUniverse ? (
              <div className="grid gap-3.5">
                <label className="grid gap-1 text-[11px] font-medium text-[var(--color-text-secondary)]">
                  Event
                  <select
                    className="h-8 rounded border border-[var(--color-divider)] bg-[var(--color-background)] px-2.5 text-[12px] text-[var(--color-text-primary)] outline-none transition-colors focus:border-[var(--color-emphasis)] focus:ring-1 focus:ring-[var(--color-emphasis)]"
                    value={selectedUniverse.event_spec_id}
                    onChange={(event) => selectUniverse(event.target.value)}
                  >
                    {universes.map((universe) => (
                      <option key={universe.event_spec_id} value={universe.event_spec_id}>
                        {universe.event_id} · {universe.position_side.toUpperCase()}
                      </option>
                    ))}
                  </select>
                </label>

                <div className="overflow-hidden rounded border border-[var(--color-divider)] bg-[var(--color-divider)]">
                  <div className="grid grid-cols-1 gap-px sm:grid-cols-2">
                    {instruments.map((instrument) => {
                      const disabled = instrument.entry_session_policy === "reference_only" || instrument.profile_status === "retired";
                      const checked = members.includes(instrument.exchange_instrument_id);
                      return (
                        <label
                          className={`flex min-h-11 items-center gap-2.5 px-3 py-2 transition-colors ${
                            checked
                              ? "bg-[var(--color-surface)] text-[var(--color-text-primary)]"
                              : "bg-[var(--color-surface)] text-[var(--color-text-secondary)]"
                          } ${disabled ? "opacity-50" : "cursor-pointer hover:bg-white/[0.03]"}`}
                          key={instrument.exchange_instrument_id}
                        >
                          <input
                            aria-label={`${instrument.venue_symbol} ${disabled ? "参考标的" : "候选标的"}`}
                            checked={checked}
                            disabled={disabled}
                            type="checkbox"
                            className="rounded border-[var(--color-divider)] accent-[var(--color-emphasis)]"
                            onChange={() => toggleMember(instrument.exchange_instrument_id)}
                          />
                          <span className="min-w-0">
                            <strong className="block text-[12px] font-semibold text-[var(--color-text-primary)]">{instrument.venue_symbol}</strong>
                            <small className="block text-[10px] text-[var(--color-text-secondary)]">
                              {disabled ? "Reference · 不可进入 Entry Universe" : instrument.profile_status}
                            </small>
                          </span>
                        </label>
                      );
                    })}
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2 text-[11px] md:grid-cols-4">
                  <div className="rounded border border-[var(--color-divider)] bg-[var(--color-surface-secondary)] p-2">
                    <span className="text-[var(--color-text-secondary)]">当前</span>
                    <strong className="mt-0.5 block tabular-number text-[13px] font-bold text-[var(--color-text-primary)]">{selectedUniverse.exchange_instrument_ids.length}</strong>
                  </div>
                  <div className="rounded border border-[var(--color-divider)] bg-[var(--color-surface-secondary)] p-2">
                    <span className="text-[var(--color-text-secondary)]">拟议</span>
                    <strong className="mt-0.5 block tabular-number text-[13px] font-bold text-[var(--color-emphasis)]">{members.length}</strong>
                  </div>
                  <div className="rounded border border-[var(--color-divider)] bg-[var(--color-surface-secondary)] p-2">
                    <span className="text-[var(--color-text-secondary)]">Lifecycle</span>
                    <strong className="mt-0.5 block text-[12px] text-[var(--color-text-primary)]">{selectedUniverse.lifecycle_state ?? "未安装"}</strong>
                  </div>
                  <div className="rounded border border-[var(--color-divider)] bg-[var(--color-surface-secondary)] p-2">
                    <span className="text-[var(--color-text-secondary)]">Runtime</span>
                    <strong className="mt-0.5 block truncate text-[12px] text-[var(--color-text-primary)]" title={selectedUniverse.runtime_profile_id}>{selectedUniverse.runtime_profile_id}</strong>
                  </div>
                </div>

                {preview.data ? (
                  <div className="grid gap-2 rounded border border-[var(--color-divider)] bg-[var(--color-surface-secondary)] p-3 text-[11px]">
                    <strong className="text-[12px] font-semibold text-[var(--color-text-primary)]">Diff Preview</strong>
                    <div className="grid grid-cols-3 gap-2">
                      <div className="rounded bg-[var(--color-background)] p-2">
                        <span className="text-[var(--color-text-secondary)]">加入</span>
                        <strong className="mt-0.5 block text-[13px] font-bold text-[var(--color-success)]">{preview.data.added_exchange_instrument_ids.length}</strong>
                      </div>
                      <div className="rounded bg-[var(--color-background)] p-2">
                        <span className="text-[var(--color-text-secondary)]">移出</span>
                        <strong className="mt-0.5 block text-[13px] font-bold text-[var(--color-danger)]">{preview.data.removed_exchange_instrument_ids.length}</strong>
                      </div>
                      <div className="rounded bg-[var(--color-background)] p-2">
                        <span className="text-[var(--color-text-secondary)]">保留</span>
                        <strong className="mt-0.5 block text-[13px] font-bold text-[var(--color-text-primary)]">{preview.data.unchanged_exchange_instrument_ids.length}</strong>
                      </div>
                    </div>
                    <small className="break-all text-[10px] text-[var(--color-text-secondary)]">Base · {preview.data.base_universe_version_id ?? "首次安装"}</small>
                  </div>
                ) : null}

                {preview.isError || apply.isError ? (
                  <div className="rounded border border-[var(--color-danger)]/50 bg-[var(--color-danger)]/10 p-2.5 text-[11px] text-[var(--color-danger)]">
                    Universe 操作失败，当前 Active Universe 未改变。
                  </div>
                ) : null}

                {apply.data ? (
                  <div className="rounded border border-[var(--color-success)]/50 bg-[var(--color-success)]/10 p-2.5 text-[11px] text-[var(--color-success)]">
                    结果 · {apply.data.status} · {apply.data.lifecycle_state ?? "未创建"}
                  </div>
                ) : null}

                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  <label className="grid gap-1 text-[11px] font-medium text-[var(--color-text-secondary)]">
                    变更原因
                    <input
                      className="h-8 rounded border border-[var(--color-divider)] bg-[var(--color-background)] px-2.5 text-[12px] text-[var(--color-text-primary)] outline-none transition-colors focus:border-[var(--color-emphasis)] focus:ring-1 focus:ring-[var(--color-emphasis)]"
                      value={reason}
                      onChange={(event) => setReason(event.target.value)}
                    />
                  </label>
                  <label className="grid gap-1 text-[11px] font-medium text-[var(--color-text-secondary)]">
                    Google Authenticator
                    <input
                      autoComplete="one-time-code"
                      className="h-8 rounded border border-[var(--color-divider)] bg-[var(--color-background)] px-2.5 tabular-nums text-[12px] text-[var(--color-text-primary)] outline-none transition-colors focus:border-[var(--color-emphasis)] focus:ring-1 focus:ring-[var(--color-emphasis)]"
                      inputMode="numeric"
                      maxLength={8}
                      placeholder="仅 Apply 时填写"
                      value={totpCode}
                      onChange={(event) => setTotpCode(event.target.value.replace(/\D/g, ""))}
                    />
                  </label>
                </div>
              </div>
            ) : (
              <UnavailablePanel title="没有可编辑的 Universe" detail="当前 Owner Policy 没有暴露可管理的 Event。" />
            )}
          </div>
          <div className="flex items-center justify-end gap-2.5 border-t border-[var(--color-divider)] bg-[var(--color-surface-secondary)] px-4 py-3">
            <Button disabled={!selectedUniverse || members.length === 0 || preview.isPending} onClick={runPreview}>
              {preview.isPending ? "预览中" : "Preview Diff"}
            </Button>
            <Button
              className="bg-[var(--color-emphasis)] text-[#181a20] font-semibold hover:bg-[var(--color-emphasis-hover)]"
              disabled={!preview.data?.can_apply || totpCode.length < 6 || reason.trim().length === 0 || apply.isPending}
              onClick={runApply}
            >
              {apply.isPending ? "创建中" : "创建 Warming"}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function InstrumentPage() {
  const [productFamily, setProductFamily] = useState<ProductFamily>("tradfi_equity_perpetual");
  const [sessionState, setSessionState] = useState<SessionState>();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const filters = useMemo<InstrumentFilters>(() => ({
    product_family: productFamily,
    limit: 100,
    ...(sessionState ? { session_state: sessionState } : {}),
  }), [productFamily, sessionState]);
  const query = useQuery({ queryKey: instrumentsQueryKey(filters), queryFn: () => getInstruments(filters) });
  const refresh = useMutation({
    mutationFn: refreshInstruments,
    onSuccess: () => void query.refetch(),
  });
  const envelope = query.data;
  const shellStatus = envelope ? freshnessPresentation(envelope.freshness) : { label: query.isError ? "不可用" : "加载中", tone: "neutral" as StatusTone };
  const handleRefresh = () => {
    if (productFamily === "tradfi_equity_perpetual") refresh.mutate();
    else void query.refetch();
  };
  const header = (
    <PageHeader
      title="标的"
      description="Product、Session 与 StrategyUniverse 的单一管理入口"
      actions={
        <div className="flex items-center gap-2">
          <Button disabled={!envelope || envelope.data.universes.length === 0} onClick={() => setEditorOpen(true)}>
            编辑 Universe
          </Button>
          <ManualRefreshButton isRefreshing={query.isFetching || refresh.isPending} onRefresh={handleRefresh} />
        </div>
      }
    />
  );

  if (!envelope) {
    return (
      <AppShell dataTime={<DataAge generatedAt={null} />} statusLabel={shellStatus.label} statusTone={shellStatus.tone}>
        {header}
        <UnavailablePanel
          title={query.isError ? "标的中心不可用" : "正在读取标的中心"}
          detail="保留空状态，不将读取失败解释为没有候选标的。"
        />
      </AppShell>
    );
  }

  const data = envelope.data;
  const columns: DenseTableColumnDef<Instrument>[] = [
    {
      id: "instrument",
      header: "标的 / Product",
      cell: ({ row }) => (
        <button
          className="flex w-full items-center gap-1.5 text-left transition-colors hover:text-[var(--color-emphasis)]"
          type="button"
          onClick={() => setExpandedId((current) => current === row.original.exchange_instrument_id ? null : row.original.exchange_instrument_id)}
        >
          {expandedId === row.original.exchange_instrument_id ? (
            <ChevronDown className="h-3.5 w-3.5 flex-none text-[var(--color-text-secondary)]" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 flex-none text-[var(--color-text-secondary)]" />
          )}
          <span className="min-w-0">
            <strong className="block truncate text-[12px] font-bold text-[var(--color-text-primary)]">{row.original.venue_symbol}</strong>
            <small className="block truncate text-[10px] text-[var(--color-text-secondary)]">
              {productLabel(row.original)} · {row.original.profile_status}
            </small>
          </span>
        </button>
      ),
    },
    {
      id: "session",
      header: "Session",
      cell: ({ row }) => (
        <div className="grid gap-0.5">
          <StatusTag tone={statusTone(row.original.session_state)}>{sessionLabel(row.original.session_state)}</StatusTag>
          <small className="text-[10px] text-[var(--color-text-secondary)]">{row.original.entry_session_policy}</small>
        </div>
      ),
    },
    {
      id: "price",
      header: "Mark / Index 门禁",
      cell: ({ row }) => {
        const deviation = markIndexDeviationBps(row.original);
        const threshold = row.original.max_mark_index_deviation_bps;
        return (
          <div className="grid gap-0.5 tabular-number">
            <div className="flex items-center gap-1.5">
              <strong className="font-semibold text-[var(--color-text-primary)]">{exactPrice(row.original.mark_price)}</strong>
              <StatusTag tone={thresholdTone(deviation, threshold)}>
                {deviation === null || threshold === null ? "—" : `${deviation.toFixed(1)} / ${Number(threshold).toFixed(0)} bps`}
              </StatusTag>
            </div>
            <small className="text-[10px] text-[var(--color-text-secondary)]">Index {exactPrice(row.original.index_price)}</small>
          </div>
        );
      },
    },
    {
      id: "micro",
      header: "Spread 门禁 / Funding",
      cell: ({ row }) => (
        <div className="grid gap-0.5 tabular-number">
          <StatusTag tone={thresholdTone(spreadBps(row.original), row.original.max_entry_spread_bps)}>
            {spreadLabel(row.original)}
          </StatusTag>
          <small className="text-[10px] text-[var(--color-text-secondary)]">Funding {fundingLabel(row.original.funding_rate)}</small>
        </div>
      ),
    },
    {
      id: "product",
      header: "Product / Event",
      cell: ({ row }) => (
        <div className="grid gap-0.5">
          <StatusTag tone={statusTone(row.original.product_status)}>{row.original.product_status ?? "unavailable"}</StatusTag>
          <small className="text-[10px] text-[var(--color-text-secondary)]">Corporate {row.original.corporate_event_status ?? "unavailable"}</small>
        </div>
      ),
    },
    {
      id: "universe",
      header: "Universe 归属",
      cell: ({ row }) => (
        <div className="grid gap-0.5">
          <strong className="truncate text-[11px] font-medium text-[var(--color-text-primary)]" title={membershipLabel(row.original)}>
            {membershipLabel(row.original)}
          </strong>
          <small className="text-[10px] text-[var(--color-text-secondary)]">{row.original.memberships.length} memberships</small>
        </div>
      ),
    },
    {
      id: "route",
      header: "路由",
      cell: () => (
        <Link className="inline-flex items-center text-[11px] font-medium text-[var(--color-emphasis)] transition-colors hover:underline hover:text-[var(--color-emphasis-hover)]" to="/strategies">
          策略页 →
        </Link>
      ),
    },
  ];
  const status = freshnessPresentation(envelope.freshness);

  return (
    <AppShell dataTime={<DataAge generatedAt={envelope.generated_at} />} statusLabel={status.label} statusTone={status.tone}>
      {header}
      {query.isRefetchError ? (
        <div className="refresh-error" role="status">
          刷新失败<span>继续显示上一次成功快照</span>
        </div>
      ) : null}
      {refresh.isError ? (
        <div className="refresh-error" role="status">
          Binance 公开事实刷新失败<span>PostgreSQL 保留上一次成功快照</span>
        </div>
      ) : null}
      {refresh.data ? (
        <div className="mb-2.5 flex min-h-8 items-center justify-between rounded border border-[var(--color-success)]/40 bg-[var(--color-success)]/10 px-3 text-[11px] text-[var(--color-success)]">
          <span>手动刷新完成 · {refresh.data.updated_count}/{refresh.data.attempted_count} 标的</span>
          <span>{refresh.data.unavailable_count} 个仍不可用</span>
        </div>
      ) : null}

      <section
        className="mb-3 grid grid-cols-2 overflow-hidden rounded border border-[var(--color-divider)] bg-[var(--color-surface)] shadow-sm md:grid-cols-4"
        aria-label="标的中心摘要"
      >
        {[
          ["候选", data.candidate_count],
          ["Reference", data.reference_count],
          ["Regular", data.regular_session_count],
          ["不可用", data.unavailable_count],
        ].map(([label, value], index) => (
          <div
            className={`grid min-h-[52px] content-center gap-0.5 px-3 py-1.5 transition-colors hover:bg-white/[0.02] ${
              index > 0 ? "border-l border-[var(--color-divider)]" : ""
            }`}
            key={label}
          >
            <span className="text-[11px] font-medium text-[var(--color-text-secondary)]">{label}</span>
            <strong className="tabular-number text-[15px] font-bold text-[var(--color-text-primary)]">{value}</strong>
          </div>
        ))}
      </section>

      <form
        className="mb-3 grid grid-cols-1 gap-3 rounded border border-[var(--color-divider)] bg-[var(--color-surface)] p-3 shadow-sm sm:grid-cols-2"
        aria-label="标的筛选"
      >
        <label className="grid gap-1 text-[11px] font-medium text-[var(--color-text-secondary)]">
          Product Family
          <select
            className="h-8 rounded border border-[var(--color-divider)] bg-[var(--color-background)] px-2.5 text-[12px] text-[var(--color-text-primary)] outline-none transition-colors focus:border-[var(--color-emphasis)] focus:ring-1 focus:ring-[var(--color-emphasis)]"
            value={productFamily}
            onChange={(event) => setProductFamily(event.target.value as ProductFamily)}
          >
            <option value="tradfi_equity_perpetual">TradFi Equity Perpetual</option>
            <option value="crypto_perpetual">Crypto Perpetual</option>
          </select>
        </label>
        <label className="grid gap-1 text-[11px] font-medium text-[var(--color-text-secondary)]">
          Session
          <select
            className="h-8 rounded border border-[var(--color-divider)] bg-[var(--color-background)] px-2.5 text-[12px] text-[var(--color-text-primary)] outline-none transition-colors focus:border-[var(--color-emphasis)] focus:ring-1 focus:ring-[var(--color-emphasis)]"
            value={sessionState ?? ""}
            onChange={(event) => setSessionState(event.target.value ? (event.target.value as SessionState) : undefined)}
          >
            <option value="">全部 Session</option>
            <option value="regular">REGULAR</option>
            <option value="pre_market">PRE_MARKET</option>
            <option value="after_market">AFTER_MARKET</option>
            <option value="overnight">OVERNIGHT</option>
            <option value="no_trading">NO_TRADING</option>
            <option value="unavailable">UNAVAILABLE</option>
          </select>
        </label>
      </form>

      {data.items.length === 0 ? (
        <UnavailablePanel title="当前筛选没有标的" detail="调整 Product 或 Session 筛选后手动刷新。" />
      ) : (
        <DenseTable
          ariaLabel="标的中心列表"
          columnWidths={COLUMN_WIDTHS}
          columns={columns}
          data={data.items}
          expandedRowId={expandedId}
          getRowId={(item) => item.exchange_instrument_id}
          renderExpandedRow={(item, count) => (
            <InlineDetailRow colSpan={count}>
              <div className="grid grid-cols-2 gap-3 text-[11px] md:grid-cols-4">
                <div className="rounded bg-[var(--color-surface)] p-2 border border-[var(--color-divider)]">
                  <span className="text-[var(--color-text-secondary)]">Regular Window</span>
                  <strong className="mt-0.5 block text-[var(--color-text-primary)]">
                    {formatTimestamp(item.regular_session_open_ms)} → {formatTimestamp(item.regular_session_close_ms)}
                  </strong>
                </div>
                <div className="rounded bg-[var(--color-surface)] p-2 border border-[var(--color-divider)]">
                  <span className="text-[var(--color-text-secondary)]">Bid / Ask</span>
                  <strong className="mt-0.5 block tabular-number text-[var(--color-text-primary)]">
                    {exactPrice(item.best_bid)} / {exactPrice(item.best_ask)}
                  </strong>
                </div>
                <div className="rounded bg-[var(--color-surface)] p-2 border border-[var(--color-divider)]">
                  <span className="text-[var(--color-text-secondary)]">事实有效期</span>
                  <strong className="mt-0.5 block text-[var(--color-text-primary)]">{formatTimestamp(item.valid_until_ms)}</strong>
                </div>
                <div className="rounded bg-[var(--color-surface)] p-2 border border-[var(--color-divider)]">
                  <span className="text-[var(--color-text-secondary)]">Source</span>
                  <strong className="mt-0.5 block truncate text-[var(--color-text-primary)]" title={item.source_ref ?? ""}>
                    {item.source_ref ?? "—"}
                  </strong>
                </div>
              </div>
            </InlineDetailRow>
          )}
        />
      )}
      <UniverseEditor
        key={productFamily}
        instruments={data.items}
        universes={data.universes}
        open={editorOpen}
        onOpenChange={setEditorOpen}
        onApplied={() => void query.refetch()}
      />
    </AppShell>
  );
}
