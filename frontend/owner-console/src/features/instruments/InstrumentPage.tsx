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
  if (item.best_bid === null || item.best_ask === null) return "—";
  const bid = Number(item.best_bid);
  const ask = Number(item.best_ask);
  const midpoint = (bid + ask) / 2;
  if (!Number.isFinite(midpoint) || midpoint <= 0 || ask < bid) return "—";
  return `${(((ask - bid) / midpoint) * 10_000).toFixed(1)} bp`;
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
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/75" />
        <Dialog.Content className="fixed inset-x-3 top-1/2 z-50 grid max-h-[calc(100vh-32px)] -translate-y-1/2 grid-rows-[auto_minmax(0,1fr)_auto] border border-[var(--color-divider)] bg-[var(--color-background)] outline-none md:inset-x-[12vw] lg:inset-x-[22vw]">
          <div className="flex min-h-12 items-center justify-between border-b border-[var(--color-divider)] bg-[var(--color-surface)] px-3">
            <div><Dialog.Title className="m-0 text-[14px] font-semibold">Universe 成员</Dialog.Title><Dialog.Description className="m-0 text-[11px] text-[var(--color-text-secondary)]">Preview 差异后通过 TOTP 创建 Warming；不会直接替换 Active Universe。</Dialog.Description></div>
            <Dialog.Close asChild><button className="grid h-8 w-8 place-items-center text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]" type="button" aria-label="关闭 Universe 编辑"><X className="h-4 w-4" /></button></Dialog.Close>
          </div>
          <div className="min-h-0 overflow-y-auto p-3">
            {selectedUniverse ? <div className="grid gap-3">
              <label className="grid gap-1 text-[11px] text-[var(--color-text-secondary)]">Event
                <select className="h-8 border border-[var(--color-divider)] bg-[var(--color-surface)] px-2 text-[12px] text-[var(--color-text-primary)]" value={selectedUniverse.event_spec_id} onChange={(event) => selectUniverse(event.target.value)}>{universes.map((universe) => <option key={universe.event_spec_id} value={universe.event_spec_id}>{universe.event_id} · {universe.position_side.toUpperCase()}</option>)}</select>
              </label>
              <div className="grid grid-cols-1 gap-px border border-[var(--color-divider)] bg-[var(--color-divider)] sm:grid-cols-2">
                {instruments.map((instrument) => {
                  const disabled = instrument.entry_session_policy === "reference_only" || instrument.profile_status === "retired";
                  return <label className={`flex min-h-11 items-center gap-2 bg-[var(--color-surface)] px-2 ${disabled ? "opacity-55" : "cursor-pointer"}`} key={instrument.exchange_instrument_id}><input aria-label={`${instrument.venue_symbol} ${disabled ? "参考标的" : "候选标的"}`} checked={members.includes(instrument.exchange_instrument_id)} disabled={disabled} type="checkbox" onChange={() => toggleMember(instrument.exchange_instrument_id)} /><span className="min-w-0"><strong className="block text-[12px]">{instrument.venue_symbol}</strong><small className="block text-[10px] text-[var(--color-text-secondary)]">{disabled ? "Reference · 不可进入 Entry Universe" : instrument.profile_status}</small></span></label>;
                })}
              </div>
              <div className="grid grid-cols-2 gap-2 text-[11px] md:grid-cols-4"><div><span className="text-[var(--color-text-secondary)]">当前</span><strong className="block tabular-number">{selectedUniverse.exchange_instrument_ids.length}</strong></div><div><span className="text-[var(--color-text-secondary)]">拟议</span><strong className="block tabular-number">{members.length}</strong></div><div><span className="text-[var(--color-text-secondary)]">Lifecycle</span><strong className="block">{selectedUniverse.lifecycle_state ?? "未安装"}</strong></div><div><span className="text-[var(--color-text-secondary)]">Runtime</span><strong className="block truncate" title={selectedUniverse.runtime_profile_id}>{selectedUniverse.runtime_profile_id}</strong></div></div>
              {preview.data ? <div className="grid gap-2 border border-[var(--color-divider)] bg-[var(--color-surface-secondary)] p-2 text-[11px]"><strong>Diff Preview</strong><div className="grid grid-cols-3 gap-2"><div><span className="text-[var(--color-text-secondary)]">加入</span><strong className="block text-[var(--color-success)]">{preview.data.added_exchange_instrument_ids.length}</strong></div><div><span className="text-[var(--color-text-secondary)]">移出</span><strong className="block text-[var(--color-danger)]">{preview.data.removed_exchange_instrument_ids.length}</strong></div><div><span className="text-[var(--color-text-secondary)]">保留</span><strong className="block">{preview.data.unchanged_exchange_instrument_ids.length}</strong></div></div><small className="break-all text-[var(--color-text-secondary)]">Base · {preview.data.base_universe_version_id ?? "首次安装"}</small></div> : null}
              {preview.isError || apply.isError ? <div className="border border-[var(--color-danger)] p-2 text-[11px] text-[var(--color-danger)]">Universe 操作失败，当前 Active Universe 未改变。</div> : null}
              {apply.data ? <div className="border border-[var(--color-success)] p-2 text-[11px] text-[var(--color-success)]">结果 · {apply.data.status} · {apply.data.lifecycle_state ?? "未创建"}</div> : null}
              <div className="grid grid-cols-1 gap-2 md:grid-cols-2"><label className="grid gap-1 text-[11px] text-[var(--color-text-secondary)]">变更原因<input className="h-8 border border-[var(--color-divider)] bg-[var(--color-surface)] px-2 text-[var(--color-text-primary)]" value={reason} onChange={(event) => setReason(event.target.value)} /></label><label className="grid gap-1 text-[11px] text-[var(--color-text-secondary)]">Google Authenticator<input autoComplete="one-time-code" className="h-8 border border-[var(--color-divider)] bg-[var(--color-surface)] px-2 tabular-nums text-[var(--color-text-primary)]" inputMode="numeric" maxLength={8} placeholder="仅 Apply 时填写" value={totpCode} onChange={(event) => setTotpCode(event.target.value.replace(/\D/g, ""))} /></label></div>
            </div> : <UnavailablePanel title="没有可编辑的 Universe" detail="当前 Owner Policy 没有暴露可管理的 Event。" />}
          </div>
          <div className="flex items-center justify-end gap-2 border-t border-[var(--color-divider)] bg-[var(--color-surface)] p-2"><Button disabled={!selectedUniverse || members.length === 0 || preview.isPending} onClick={runPreview}>{preview.isPending ? "预览中" : "Preview Diff"}</Button><Button className="border-[var(--color-emphasis)] text-[var(--color-emphasis)]" disabled={!preview.data?.can_apply || totpCode.length < 6 || reason.trim().length === 0 || apply.isPending} onClick={runApply}>{apply.isPending ? "创建中" : "创建 Warming"}</Button></div>
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
  const header = <PageHeader title="标的" description="Product、Session 与 StrategyUniverse 的单一管理入口" actions={<div className="flex gap-2"><Button disabled={!envelope || envelope.data.universes.length === 0} onClick={() => setEditorOpen(true)}>编辑 Universe</Button><ManualRefreshButton isRefreshing={query.isFetching || refresh.isPending} onRefresh={handleRefresh} /></div>} />;

  if (!envelope) {
    return <AppShell dataTime={<DataAge generatedAt={null} />} statusLabel={shellStatus.label} statusTone={shellStatus.tone}>{header}<UnavailablePanel title={query.isError ? "标的中心不可用" : "正在读取标的中心"} detail="保留空状态，不将读取失败解释为没有候选标的。" /></AppShell>;
  }

  const data = envelope.data;
  const columns: DenseTableColumnDef<Instrument>[] = [
    { id: "instrument", header: "标的 / Product", cell: ({ row }) => <button className="flex w-full items-center gap-1 text-left" type="button" onClick={() => setExpandedId((current) => current === row.original.exchange_instrument_id ? null : row.original.exchange_instrument_id)}>{expandedId === row.original.exchange_instrument_id ? <ChevronDown className="h-3.5 w-3.5 text-[var(--color-text-secondary)]" /> : <ChevronRight className="h-3.5 w-3.5 text-[var(--color-text-secondary)]" />}<span className="min-w-0"><strong className="block truncate text-[12px]">{row.original.venue_symbol}</strong><small className="block truncate text-[10px] text-[var(--color-text-secondary)]">{productLabel(row.original)} · {row.original.profile_status}</small></span></button> },
    { id: "session", header: "Session", cell: ({ row }) => <div className="grid gap-0.5"><StatusTag tone={statusTone(row.original.session_state)}>{sessionLabel(row.original.session_state)}</StatusTag><small className="text-[10px] text-[var(--color-text-secondary)]">{row.original.entry_session_policy}</small></div> },
    { id: "price", header: "Mark / Index", cell: ({ row }) => <div className="grid gap-0.5 tabular-number"><strong>{exactPrice(row.original.mark_price)}</strong><small className="text-[10px] text-[var(--color-text-secondary)]">Index {exactPrice(row.original.index_price)}</small></div> },
    { id: "micro", header: "Spread / Funding", cell: ({ row }) => <div className="grid gap-0.5 tabular-number"><strong>{spreadLabel(row.original)}</strong><small className="text-[10px] text-[var(--color-text-secondary)]">Funding {fundingLabel(row.original.funding_rate)}</small></div> },
    { id: "product", header: "Product / Event", cell: ({ row }) => <div className="grid gap-0.5"><StatusTag tone={statusTone(row.original.product_status)}>{row.original.product_status ?? "unavailable"}</StatusTag><small className="text-[10px] text-[var(--color-text-secondary)]">Corporate {row.original.corporate_event_status ?? "unavailable"}</small></div> },
    { id: "universe", header: "Universe 归属", cell: ({ row }) => <div className="grid gap-0.5"><strong className="truncate text-[11px]" title={membershipLabel(row.original)}>{membershipLabel(row.original)}</strong><small className="text-[10px] text-[var(--color-text-secondary)]">{row.original.memberships.length} memberships</small></div> },
    { id: "route", header: "路由", cell: () => <Link className="text-[11px] text-[var(--color-emphasis)] hover:underline" to="/strategies">策略页</Link> },
  ];
  const status = freshnessPresentation(envelope.freshness);

  return <AppShell dataTime={<DataAge generatedAt={envelope.generated_at} />} statusLabel={status.label} statusTone={status.tone}>
    {header}
    {query.isRefetchError ? <div className="refresh-error" role="status">刷新失败<span>继续显示上一次成功快照</span></div> : null}
    {refresh.isError ? <div className="refresh-error" role="status">Binance 公开事实刷新失败<span>PostgreSQL 保留上一次成功快照</span></div> : null}
    {refresh.data ? <div className="mb-2 flex min-h-8 items-center justify-between border border-[var(--color-success)] px-2 text-[11px] text-[var(--color-success)]"><span>手动刷新完成 · {refresh.data.updated_count}/{refresh.data.attempted_count} 标的</span><span>{refresh.data.unavailable_count} 个仍不可用</span></div> : null}
    <section className="mb-2 grid grid-cols-2 border border-[var(--color-divider)] bg-[var(--color-surface)] md:grid-cols-4" aria-label="标的中心摘要">{[["候选", data.candidate_count], ["Reference", data.reference_count], ["Regular", data.regular_session_count], ["不可用", data.unavailable_count]].map(([label, value], index) => <div className={`grid min-h-[48px] content-center gap-1 px-2 ${index > 0 ? "border-l border-[var(--color-divider)]" : ""}`} key={label}><span className="text-[10px] text-[var(--color-text-secondary)]">{label}</span><strong className="tabular-number text-[14px]">{value}</strong></div>)}</section>
    <form className="mb-2 grid grid-cols-1 gap-2 border border-[var(--color-divider)] bg-[var(--color-surface)] p-2 sm:grid-cols-2" aria-label="标的筛选"><label className="grid gap-1 text-[11px] text-[var(--color-text-secondary)]">Product Family<select className="h-8 border border-[var(--color-divider)] bg-[var(--color-background)] px-2 text-[12px] text-[var(--color-text-primary)]" value={productFamily} onChange={(event) => setProductFamily(event.target.value as ProductFamily)}><option value="tradfi_equity_perpetual">TradFi Equity Perpetual</option><option value="crypto_perpetual">Crypto Perpetual</option></select></label><label className="grid gap-1 text-[11px] text-[var(--color-text-secondary)]">Session<select className="h-8 border border-[var(--color-divider)] bg-[var(--color-background)] px-2 text-[12px] text-[var(--color-text-primary)]" value={sessionState ?? ""} onChange={(event) => setSessionState(event.target.value ? event.target.value as SessionState : undefined)}><option value="">全部 Session</option><option value="regular">REGULAR</option><option value="pre_market">PRE_MARKET</option><option value="after_market">AFTER_MARKET</option><option value="overnight">OVERNIGHT</option><option value="no_trading">NO_TRADING</option><option value="unavailable">UNAVAILABLE</option></select></label></form>
    {data.items.length === 0 ? <UnavailablePanel title="当前筛选没有标的" detail="调整 Product 或 Session 筛选后手动刷新。" /> : <DenseTable ariaLabel="标的中心列表" columnWidths={COLUMN_WIDTHS} columns={columns} data={data.items} expandedRowId={expandedId} getRowId={(item) => item.exchange_instrument_id} renderExpandedRow={(item, count) => <InlineDetailRow colSpan={count}><div className="grid grid-cols-2 gap-2 text-[11px] md:grid-cols-4"><div><span className="text-[var(--color-text-secondary)]">Regular Window</span><strong className="block">{formatTimestamp(item.regular_session_open_ms)} → {formatTimestamp(item.regular_session_close_ms)}</strong></div><div><span className="text-[var(--color-text-secondary)]">Bid / Ask</span><strong className="block tabular-number">{exactPrice(item.best_bid)} / {exactPrice(item.best_ask)}</strong></div><div><span className="text-[var(--color-text-secondary)]">事实有效期</span><strong className="block">{formatTimestamp(item.valid_until_ms)}</strong></div><div><span className="text-[var(--color-text-secondary)]">Source</span><strong className="block truncate" title={item.source_ref ?? ""}>{item.source_ref ?? "—"}</strong></div></div></InlineDetailRow>} />}
    <UniverseEditor key={productFamily} instruments={data.items} universes={data.universes} open={editorOpen} onOpenChange={setEditorOpen} onApplied={() => void query.refetch()} />
  </AppShell>;
}
