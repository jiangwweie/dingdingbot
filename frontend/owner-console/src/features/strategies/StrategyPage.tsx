import { useQuery } from "@tanstack/react-query";
import * as Dialog from "@radix-ui/react-dialog";
import { ChevronRight, Maximize2, X } from "lucide-react";
import { lazy, Suspense, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import type { components } from "../../api/schema";
import { AppShell } from "../../app/AppShell";
import type { ChartPriceLevel } from "../../components/charts/CausalityChart";
import { CursorPagination } from "../../components/tables/CursorPagination";
import { DenseTable, type DenseTableColumnDef } from "../../components/tables/DenseTable";
import { DataAge } from "../../components/ui/DataAge";
import { ManualRefreshButton } from "../../components/ui/ManualRefreshButton";
import { PageHeader } from "../../components/ui/PageHeader";
import { StatusTag, type StatusTone } from "../../components/ui/StatusTag";
import { TimeRangeFilter } from "../../components/ui/TimeRangeFilter";
import { UnavailablePanel } from "../../components/ui/UnavailablePanel";
import { formatMoney, formatTimestamp } from "../../components/ui/presentation";
import { candlesQueryKey, getCandles } from "../trades/api";
import {
  getStrategies,
  getStrategyObservations,
  getStrategyTickets,
  strategiesQueryKey,
  strategyObservationsQueryKey,
  strategyTicketsQueryKey,
} from "./api";
import {
  parseStrategySearchParams,
  strategySearchParamsToString,
  type StrategySearchParams,
} from "./searchParams";

const CausalityChart = lazy(() => import("../../components/charts/CausalityChart"));

type Strategy = components["schemas"]["StrategyVersionSummary"];
type StrategyTicket = components["schemas"]["StrategyTicketListItem"];
type Observation = components["schemas"]["StrategyObservationListItem"];
type Freshness = components["schemas"]["Freshness"];
type TicketPath = NonNullable<StrategySearchParams["exit_path"]>;
type ObservationPath = NonNullable<StrategySearchParams["observation_path"]>;

const STRATEGY_COLUMN_WIDTHS = ["23%", "12%", "11%", "11%", "10%", "16%", "17%"] as const;

function freshnessPresentation(freshness: Freshness) {
  if (freshness === "stale") return { label: "数据陈旧", tone: "attention" as const };
  if (freshness === "unavailable") return { label: "数据不可用", tone: "danger" as const };
  if (freshness === "contradictory") return { label: "事实矛盾", tone: "danger" as const };
  return { label: "数据正常", tone: "success" as const };
}

function Metric({ metric, sign = false }: { metric: components["schemas"]["MoneyMetric"]; sign?: boolean }) {
  if (metric.value === null) return <span className="text-[var(--color-text-secondary)]">—</span>;
  return <span className="tabular-number">{formatMoney(metric.value, metric.unit, { sign })}</span>;
}

function StrategyFilters({ filters, onChange }: { filters: StrategySearchParams; onChange: (filters: StrategySearchParams) => void }) {
  return (
    <form className="mb-2 grid grid-cols-1 gap-2 border border-[var(--color-divider)] bg-[var(--color-surface)] p-2 md:grid-cols-[220px_minmax(0,1fr)]" aria-label="策略统计筛选条件">
      <label className="grid content-start gap-1 text-[11px] text-[var(--color-text-secondary)]">策略视图
        <select className="h-[30px] border border-[var(--color-divider)] bg-[var(--color-background)] px-2 text-[12px] text-[var(--color-text-primary)] outline-none focus:border-[var(--color-emphasis)]" value={filters.view ?? "current"} onChange={(event) => onChange({ ...filters, view: event.target.value as "current" | "all", cursor: undefined, observation_cursor: undefined })}>
          <option value="current">当前活跃版本</option>
          <option value="all">全部历史版本</option>
        </select>
        <small className="text-[10px]">统计主键为 StrategyVersion，不合并版本</small>
      </label>
      <TimeRangeFilter value={filters} onChange={(range) => onChange({ ...filters, ...range, cursor: undefined, observation_cursor: undefined })} />
    </form>
  );
}

function ticketPathLabel(path: TicketPath): string {
  return { tp1_reached: "已达 TP1", tp1_not_reached: "未达 TP1", controlled_exit: "受控退出" }[path];
}

function ticketPathScope(path: TicketPath): "natural" | "all" {
  return path === "controlled_exit" ? "all" : "natural";
}

function observationPathLabel(path: ObservationPath | null): string {
  if (path === null) return "全部路径";
  return {
    tp1_first: "TP1 先到",
    initial_stop_first: "Stop 先到",
    ambiguous_same_bar: "同 Bar 歧义",
    opening_range_failure: "开盘区间失效",
    time_stop: "Time Stop",
    session_exit: "Session Exit",
    horizon_complete: "观察期完成",
  }[path];
}

function modalTitle(item: Strategy | undefined, path: TicketPath | undefined): string {
  if (!item || !path) return "Ticket 证据";
  return `${item.strategy_group_display_name} v${item.version} · ${ticketPathLabel(path)}`;
}

function productFamilyLabel(value: components["schemas"]["StrategyProductEventFacts"]["product_family"]): string {
  return value === "tradfi_equity_perpetual" ? "Equity Perp" : "Crypto Perp";
}

function entryWindowLabel(event: components["schemas"]["StrategyProductEventFacts"]): string {
  if (event.product_family === "tradfi_equity_perpetual" && event.event_id.startsWith("SOR-US-")) return "REGULAR +30m–+150m";
  if (event.product_family === "tradfi_equity_perpetual") return "REGULAR only";
  return `Continuous · ${event.timeframe} close`;
}

function formatDecimal(value: string | null, suffix = ""): string {
  if (value === null) return "—";
  return `${Number(value).toFixed(2)}${suffix}`;
}

function observationPriceLevels(observation: Observation): ChartPriceLevel[] {
  const levels: ChartPriceLevel[] = [];
  if (observation.entry_reference_price !== null) levels.push({ price: observation.entry_reference_price, color: "#F0B90B", label: `ENTRY · ${observation.entry_reference_price}` });
  if (observation.initial_stop_price !== null) levels.push({ price: observation.initial_stop_price, color: "#F6465D", label: `STOP · ${observation.initial_stop_price}` });
  if (observation.take_profit_price !== null) levels.push({ price: observation.take_profit_price, color: "#0ECB81", label: `TP1 · ${observation.take_profit_price}` });
  if (observation.opening_range_boundary_price !== null) levels.push({ price: observation.opening_range_boundary_price, color: "#5B8FF9", label: `OPENING RANGE · ${observation.opening_range_boundary_price}` });
  return levels;
}

function observationStatusTone(status: Observation["status"]): StatusTone {
  if (status === "completed") return "success";
  if (status === "unavailable") return "danger";
  if (status === "claimed") return "attention";
  return "neutral";
}

export function StrategyPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(() => parseStrategySearchParams(searchParams), [searchParams]);
  const [observationFullscreen, setObservationFullscreen] = useState(false);
  const summaryFilters = useMemo(() => ({ from_ms: filters.from_ms, to_ms: filters.to_ms, view: filters.view ?? "current" }), [filters.from_ms, filters.to_ms, filters.view]);
  const strategies = useQuery({ queryKey: strategiesQueryKey(summaryFilters), queryFn: () => getStrategies(summaryFilters) });
  const envelope = strategies.data;

  const selectedTicketVersionId = filters.ticket_modal === "1" ? filters.strategy_version_id : undefined;
  const selectedTicketPath = filters.ticket_modal === "1" ? filters.exit_path : undefined;
  const selectedTicketVersion = envelope?.data.items.find((item) => item.strategy_version_id === selectedTicketVersionId);
  const ticketFilters = useMemo(() => ({ strategy_version_id: selectedTicketVersionId, from_ms: filters.from_ms, to_ms: filters.to_ms, scope: filters.scope ?? (selectedTicketPath ? ticketPathScope(selectedTicketPath) : "natural"), exit_path: selectedTicketPath, cursor: filters.cursor }), [filters.cursor, filters.from_ms, filters.scope, filters.to_ms, selectedTicketPath, selectedTicketVersionId]);
  const tickets = useQuery({
    queryKey: strategyTicketsQueryKey(ticketFilters),
    queryFn: () => getStrategyTickets({ ...ticketFilters, strategy_version_id: ticketFilters.strategy_version_id! }),
    enabled: selectedTicketVersionId !== undefined && selectedTicketPath !== undefined,
  });

  const selectedObservationVersionId = filters.observation_modal === "1" ? filters.strategy_version_id : undefined;
  const selectedObservationVersion = envelope?.data.items.find((item) => item.strategy_version_id === selectedObservationVersionId);
  const observationFilters = useMemo(() => ({ strategy_version_id: selectedObservationVersionId, from_ms: filters.from_ms, to_ms: filters.to_ms, observation_path: filters.observation_path, observation_cursor: filters.observation_cursor }), [filters.from_ms, filters.observation_cursor, filters.observation_path, filters.to_ms, selectedObservationVersionId]);
  const observations = useQuery({
    queryKey: strategyObservationsQueryKey(observationFilters),
    queryFn: () => getStrategyObservations({ strategy_version_id: selectedObservationVersionId!, from_ms: filters.from_ms, to_ms: filters.to_ms, first_path: filters.observation_path, cursor: filters.observation_cursor }),
    enabled: selectedObservationVersionId !== undefined,
  });
  const observationItems = observations.data?.data.items ?? [];
  const selectedObservation = observationItems.find((item) => item.shadow_outcome_id === filters.observation_id) ?? observationItems[0];
  const observationChartWindow = selectedObservation ? { closedAtMs: selectedObservation.horizon_end_ms + 4 * 900_000, limit: 48 } : null;
  const observationCandles = useQuery({
    queryKey: selectedObservation && observationChartWindow ? candlesQueryKey(selectedObservation.shadow_outcome_id, "15m", observationChartWindow.closedAtMs, observationChartWindow.limit) : ["owner", "strategies", "observation-candles", "disabled"],
    queryFn: () => getCandles({ exchangeInstrumentId: selectedObservation!.exchange_instrument_id, timeframe: "15m", closedAtMs: observationChartWindow!.closedAtMs, limit: observationChartWindow!.limit }),
    enabled: selectedObservation !== undefined && selectedObservation.status !== "unavailable" && observationChartWindow !== null,
  });

  const shellStatus = envelope ? freshnessPresentation(envelope.freshness) : { label: strategies.isError ? "不可用" : "加载中", tone: "neutral" as StatusTone };
  const updateFilters = (next: StrategySearchParams) => setSearchParams(strategySearchParamsToString(next));
  const openTicketPath = (strategy: Strategy, path: TicketPath) => updateFilters({ ...filters, strategy_version_id: strategy.strategy_version_id, ticket_modal: "1", observation_modal: undefined, scope: ticketPathScope(path), exit_path: path, cursor: undefined, observation_path: undefined, observation_id: undefined, observation_cursor: undefined });
  const openObservationPath = (strategy: Strategy, path?: ObservationPath) => updateFilters({ ...filters, strategy_version_id: strategy.strategy_version_id, observation_modal: "1", ticket_modal: undefined, observation_path: path, observation_id: undefined, observation_cursor: undefined, exit_path: undefined, scope: undefined, cursor: undefined });
  const closeTicketModal = () => {
    const { strategy_version_id: _strategyVersionId, ticket_modal: _ticketModal, scope: _scope, exit_path: _exitPath, cursor: _cursor, ...rest } = filters;
    updateFilters(rest);
  };
  const closeObservationModal = () => {
    const { strategy_version_id: _strategyVersionId, observation_modal: _observationModal, observation_path: _observationPath, observation_id: _observationId, observation_cursor: _observationCursor, ...rest } = filters;
    setObservationFullscreen(false);
    updateFilters(rest);
  };
  const refreshPage = () => {
    void strategies.refetch();
    if (selectedTicketVersionId) void tickets.refetch();
    if (selectedObservationVersionId) void observations.refetch();
    if (selectedObservation) void observationCandles.refetch();
  };

  const pageHeader = <PageHeader title="策略" description="按 StrategyVersion 隔离实盘 Ticket 与 Observation 路径证据" actions={<ManualRefreshButton isRefreshing={strategies.isFetching || tickets.isFetching || observations.isFetching || observationCandles.isFetching} onRefresh={refreshPage} />} />;
  if (!envelope) {
    return <AppShell dataTime={<DataAge generatedAt={null} />} statusLabel={shellStatus.label} statusTone={shellStatus.tone}>{pageHeader}<UnavailablePanel title={strategies.isError ? "策略统计不可用" : "正在读取策略统计"} detail={strategies.isError ? "保留空状态，不将缺失数据解释为没有策略或没有交易。" : "仅读取一次 StrategyVersion 快照。"} /></AppShell>;
  }

  const data = envelope.data;
  const naturalCount = data.items.reduce((total, item) => total + item.natural_terminal_count, 0);
  const confirmedCount = data.items.reduce((total, item) => total + item.confirmed_natural_review_count, 0);
  const pendingCount = data.items.reduce((total, item) => total + item.pending_natural_review_count, 0);
  const observationCount = data.items.reduce((total, item) => total + item.observation_count, 0);
  const status = freshnessPresentation(envelope.freshness);
  const columns: DenseTableColumnDef<Strategy>[] = [
    { id: "version", header: "StrategyVersion / Product", cell: ({ row }) => { const product = row.original.product_events[0]; const activeCount = row.original.product_events.reduce((total, event) => total + event.active_exchange_instrument_ids.length, 0); const warmingCount = row.original.product_events.reduce((total, event) => total + event.warming_exchange_instrument_ids.length, 0); return <div className="grid min-w-0 gap-0.5 py-1"><strong className="truncate text-[12px]">{row.original.strategy_group_display_name} · v{row.original.version}</strong>{product ? <><span className="truncate text-[10px] text-[var(--color-text-secondary)]">{product.venue_id ?? "Venue 未绑定"} · {productFamilyLabel(product.product_family)} · {entryWindowLabel(product)}</span><span className="truncate text-[10px] text-[var(--color-text-secondary)]" title={product.runtime_profile_id ?? undefined}>{product.runtime_profile_id ?? "Runtime 未绑定"} · Active {activeCount} / Warming {warmingCount}</span></> : <span className="truncate text-[10px] text-[var(--color-text-secondary)]" title={row.original.strategy_version_id}>产品摘要不可用 · {row.original.strategy_version_id}</span>}</div>; } },
    { id: "samples", header: "实盘样本", cell: ({ row }) => <div className="grid gap-0.5 text-[11px]"><strong className="tabular-number">{row.original.natural_terminal_count} 自然终态</strong><span className="text-[var(--color-text-secondary)]">{row.original.ticket_count} Tickets</span></div> },
    { id: "reviews", header: "Review", cell: ({ row }) => <div className="grid gap-0.5 text-[11px]"><strong className="tabular-number">{row.original.confirmed_natural_review_count} 已确认</strong><span className="text-[var(--color-text-secondary)]">{row.original.pending_natural_review_count} 待确认</span></div> },
    { id: "pnl", header: "自然 Net PnL", cell: ({ row }) => <Metric metric={row.original.net_pnl} sign /> },
    { id: "r", header: "自然 Net R", cell: ({ row }) => <Metric metric={row.original.net_r} sign /> },
    { id: "ticket_paths", header: "Ticket 路径", cell: ({ row }) => <div className="flex flex-wrap gap-1"><button className="border border-[var(--color-divider)] bg-transparent px-1.5 py-1 text-[10px] text-[var(--color-emphasis)] hover:border-[var(--color-emphasis)] disabled:opacity-40" disabled={row.original.tp1_reached_count === 0} type="button" onClick={() => openTicketPath(row.original, "tp1_reached")}>TP1 {row.original.tp1_reached_count}</button><button className="border border-[var(--color-divider)] bg-transparent px-1.5 py-1 text-[10px] hover:border-[var(--color-emphasis)] disabled:opacity-40" disabled={row.original.tp1_not_reached_count === 0} type="button" onClick={() => openTicketPath(row.original, "tp1_not_reached")}>未达 {row.original.tp1_not_reached_count}</button><button className="border border-[var(--color-divider)] bg-transparent px-1.5 py-1 text-[10px] hover:border-[var(--color-emphasis)] disabled:opacity-40" disabled={row.original.controlled_exit_count === 0} type="button" onClick={() => openTicketPath(row.original, "controlled_exit")}>受控 {row.original.controlled_exit_count}</button></div> },
    { id: "observations", header: "Observation 路径", cell: ({ row }) => row.original.observation_count === 0 ? <span className="text-[var(--color-text-secondary)]">—</span> : <div className="grid gap-1"><button className="w-fit bg-transparent p-0 text-left text-[11px] text-[var(--color-emphasis)] hover:underline" type="button" onClick={() => openObservationPath(row.original)}>样本 {row.original.completed_observation_count}/{row.original.observation_count} · MFE {formatDecimal(row.original.median_mfe_r, "R")}</button><div className="flex flex-wrap gap-1"><button className="text-[10px] text-[var(--color-success)] hover:underline" type="button" onClick={() => openObservationPath(row.original, "tp1_first")}>TP1 {row.original.tp1_first_count}</button><button className="text-[10px] text-[var(--color-danger)] hover:underline" type="button" onClick={() => openObservationPath(row.original, "initial_stop_first")}>Stop {row.original.initial_stop_first_count}</button><button className="text-[10px] text-[var(--color-text-secondary)] hover:underline" type="button" onClick={() => openObservationPath(row.original, "opening_range_failure")}>OR Fail {row.original.opening_range_failure_count}</button><button className="text-[10px] text-[var(--color-text-secondary)] hover:underline" type="button" onClick={() => openObservationPath(row.original, "ambiguous_same_bar")}>歧义 {row.original.ambiguous_observation_count}</button></div></div> },
  ];

  const ticketItems = tickets.data?.data.items ?? [];
  const ticketDetailQuery = (ticketId: string, fromObservation = false) => {
    const detail = new URLSearchParams();
    detail.set("origin", "strategy");
    detail.set("view", filters.view ?? "current");
    if (filters.from_ms !== undefined) detail.set("from_ms", String(filters.from_ms));
    if (filters.to_ms !== undefined) detail.set("to_ms", String(filters.to_ms));
    if (filters.strategy_version_id) detail.set("strategy_version_id", filters.strategy_version_id);
    if (fromObservation) {
      detail.set("observation_modal", "1");
      if (filters.observation_path) detail.set("observation_path", filters.observation_path);
      if (selectedObservation) detail.set("observation_id", selectedObservation.shadow_outcome_id);
      if (filters.observation_cursor) detail.set("observation_cursor", filters.observation_cursor);
    } else {
      detail.set("ticket_modal", "1");
      if (selectedTicketPath) detail.set("exit_path", selectedTicketPath);
      detail.set("scope", ticketFilters.scope);
    }
    return `/trades/${encodeURIComponent(ticketId)}?${detail.toString()}`;
  };

  return (
    <AppShell dataTime={<DataAge generatedAt={envelope.generated_at} />} statusLabel={status.label} statusTone={status.tone}>
      {pageHeader}
      {strategies.isRefetchError ? <div className="refresh-error" role="status">刷新失败<span>继续显示上一次成功快照</span></div> : null}
      <StrategyFilters filters={filters} onChange={updateFilters} />
      <section className="mb-2 grid grid-cols-2 border border-[var(--color-divider)] bg-[var(--color-surface)] md:grid-cols-5" aria-label="策略统计摘要">
        {[["StrategyVersions", String(data.items.length)], ["自然终态", String(naturalCount)], ["已确认 Review", String(confirmedCount)], ["待确认 Review", String(pendingCount)], ["Observation", String(observationCount)]].map(([label, value], index) => <div className={`grid min-h-[48px] content-center gap-1 px-2 ${index > 0 ? "border-l border-[var(--color-divider)]" : ""}`} key={label}><span className="text-[10px] text-[var(--color-text-secondary)]">{label}</span><strong className="tabular-number text-[14px]">{value}</strong></div>)}
      </section>
      {data.items.length === 0 ? <div className="panel compact-empty px-2">当前范围内没有可展示的 StrategyVersion</div> : <DenseTable ariaLabel="StrategyVersion 统计列表" columnWidths={STRATEGY_COLUMN_WIDTHS} columns={columns} data={data.items} getRowId={(item) => item.strategy_version_id} />}

      <Dialog.Root open={selectedTicketVersionId !== undefined && selectedTicketPath !== undefined} onOpenChange={(open) => { if (!open) closeTicketModal(); }}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-black/75" />
          <Dialog.Content className="fixed inset-x-3 top-1/2 z-50 grid max-h-[calc(100vh-32px)] w-auto -translate-y-1/2 grid-rows-[auto_minmax(0,1fr)] border border-[var(--color-divider)] bg-[var(--color-background)] outline-none md:inset-x-[8vw] lg:inset-x-[14vw]">
            <div className="flex min-h-12 items-center justify-between gap-3 border-b border-[var(--color-divider)] bg-[var(--color-surface)] px-3"><div className="min-w-0"><Dialog.Title className="m-0 truncate text-[14px] font-semibold">{modalTitle(selectedTicketVersion, selectedTicketPath)}</Dialog.Title><Dialog.Description className="m-0 truncate text-[11px] text-[var(--color-text-secondary)]">点击 Ticket 进入完整生命周期与 K 线复盘；返回将恢复当前筛选和弹窗。</Dialog.Description></div><Dialog.Close asChild><button className="grid h-8 w-8 flex-none place-items-center bg-transparent text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]" type="button" aria-label="关闭 Ticket 证据"><X aria-hidden="true" className="h-4 w-4" /></button></Dialog.Close></div>
            <div className="min-h-0 overflow-y-auto p-2">
              {tickets.isError ? <UnavailablePanel title="Ticket 证据不可用" detail="保留 StrategyVersion 上下文，未将读取失败解释为无样本。" /> : tickets.isLoading ? <div className="grid min-h-40 place-content-center text-[12px] text-[var(--color-text-secondary)]">正在读取 Ticket 证据</div> : ticketItems.length === 0 ? <div className="grid min-h-40 place-content-center text-[12px] text-[var(--color-text-secondary)]">当前路径没有 Ticket</div> : <div className="grid gap-px border border-[var(--color-divider)] bg-[var(--color-divider)]">{ticketItems.map((ticket: StrategyTicket) => <Link className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-3 bg-[var(--color-surface)] px-3 py-2 text-left no-underline hover:bg-[var(--color-surface-secondary)]" key={ticket.ticket_id} state={{ ticketIds: ticketItems.map((item) => item.ticket_id) }} to={ticketDetailQuery(ticket.ticket_id)}><span className="min-w-0"><strong className="block truncate text-[12px] text-[var(--color-emphasis)]">{ticket.exchange_instrument_id} {ticket.position_side.toUpperCase()}</strong><small className="block truncate text-[10px] text-[var(--color-text-secondary)]">{ticket.ticket_id} · {formatTimestamp(ticket.issued_at_ms)}</small></span><span className="tabular-number text-[11px] text-[var(--color-text-primary)]"><Metric metric={ticket.net_pnl} sign /></span><ChevronRight aria-hidden="true" className="h-4 w-4 text-[var(--color-text-secondary)]" /></Link>)}</div>}
              <CursorPagination hasNextPage={tickets.data?.data.next_cursor !== null && tickets.data !== undefined} label="还有更多路径 Ticket" onNextPage={() => updateFilters({ ...filters, cursor: tickets.data?.data.next_cursor ?? undefined })} />
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <Dialog.Root open={selectedObservationVersionId !== undefined} onOpenChange={(open) => { if (!open) closeObservationModal(); }}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-black/80" />
          <Dialog.Content className="fixed inset-3 z-50 grid max-h-[calc(100vh-24px)] grid-rows-[auto_minmax(0,1fr)] border border-[var(--color-divider)] bg-[var(--color-background)] outline-none md:inset-6">
            <div className="flex min-h-12 items-center justify-between gap-3 border-b border-[var(--color-divider)] bg-[var(--color-surface)] px-3"><div className="min-w-0"><Dialog.Title className="m-0 truncate text-[14px] font-semibold">{selectedObservationVersion ? `${selectedObservationVersion.strategy_group_display_name} v${selectedObservationVersion.version}` : "StrategyVersion"} · Observation</Dialog.Title><Dialog.Description className="m-0 truncate text-[11px] text-[var(--color-text-secondary)]">{observationPathLabel(filters.observation_path ?? null)} · Signal 路径证据，不是模拟 Ticket 或模拟收益。</Dialog.Description></div><Dialog.Close asChild><button className="grid h-8 w-8 flex-none place-items-center bg-transparent text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]" type="button" aria-label="关闭 Observation"><X aria-hidden="true" className="h-4 w-4" /></button></Dialog.Close></div>
            <div className="grid min-h-0 lg:grid-cols-[minmax(280px,34%)_minmax(0,1fr)]">
              <aside className="min-h-0 overflow-y-auto border-b border-[var(--color-divider)] lg:border-b-0 lg:border-r" aria-label="Observation 样本列表">
                {observations.isError ? <UnavailablePanel title="Observation 不可用" detail="保留 StrategyVersion 与路径筛选。" /> : observations.isLoading ? <div className="grid min-h-40 place-content-center text-[12px] text-[var(--color-text-secondary)]">正在读取 Observation</div> : observationItems.length === 0 ? <div className="grid min-h-40 place-content-center text-[12px] text-[var(--color-text-secondary)]">当前路径没有 Observation</div> : <div className="grid">{observationItems.map((item) => <button className={`grid min-h-[68px] grid-cols-[minmax(0,1fr)_auto] items-center gap-2 border-b border-[var(--color-divider)] px-3 py-2 text-left hover:bg-[var(--color-surface-secondary)] ${selectedObservation?.shadow_outcome_id === item.shadow_outcome_id ? "bg-[var(--color-surface-secondary)]" : "bg-[var(--color-surface)]"}`} key={item.shadow_outcome_id} type="button" onClick={() => updateFilters({ ...filters, observation_id: item.shadow_outcome_id })}><span className="min-w-0"><strong className="block truncate text-[12px]">{item.exchange_instrument_id} · {item.position_side.toUpperCase()}</strong><small className="block truncate text-[10px] text-[var(--color-text-secondary)]">{formatTimestamp(item.occurred_at_ms)} · {item.first_path ? observationPathLabel(item.first_path) : item.completion_reason ?? "观察中"}</small><small className="block tabular-number text-[10px] text-[var(--color-text-secondary)]">MFE {formatDecimal(item.mfe_r, "R")} · MAE {formatDecimal(item.mae_r, "R")} · Spread {formatDecimal(item.spread_bps, " bps")}</small></span><StatusTag tone={observationStatusTone(item.status)}>{item.status === "completed" ? "已完成" : item.status === "unavailable" ? "不可用" : "观察中"}</StatusTag></button>)}</div>}
                <div className="p-2"><CursorPagination hasNextPage={observations.data?.data.next_cursor !== null && observations.data !== undefined} label="还有更多 Observation" onNextPage={() => updateFilters({ ...filters, observation_cursor: observations.data?.data.next_cursor ?? undefined, observation_id: undefined })} /></div>
              </aside>
              <section className="min-h-0 overflow-y-auto p-2" aria-label="Observation 路径详情">
                {!selectedObservation ? <div className="grid min-h-40 place-content-center text-[12px] text-[var(--color-text-secondary)]">选择一笔 Observation 查看价格计划与路径</div> : <div className="grid gap-2">
                  <div className="grid grid-cols-2 border border-[var(--color-divider)] bg-[var(--color-surface)] md:grid-cols-4">
                    {[["Entry", selectedObservation.entry_reference_price], ["Initial Stop", selectedObservation.initial_stop_price], ["TP1", selectedObservation.take_profit_price], ["Opening Range", selectedObservation.opening_range_boundary_price]].map(([label, value], index) => <div className={`grid min-h-[58px] content-center gap-1 px-2 ${index > 0 ? "border-l border-[var(--color-divider)]" : ""}`} key={label}><span className="text-[10px] text-[var(--color-text-secondary)]">{label}</span><strong className="tabular-number text-[14px]">{value ?? "—"}</strong></div>)}
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-2 border border-[var(--color-divider)] bg-[var(--color-surface-secondary)] px-2 py-1.5 text-[11px]"><span><strong>{observationPathLabel(selectedObservation.first_path)}</strong> · {selectedObservation.observed_bar_count ?? "—"} bars · Mark/Index {formatDecimal(selectedObservation.mark_index_deviation_bps, " bps")}</span><div className="flex items-center gap-3">{selectedObservation.ticket_id ? <Link className="text-[var(--color-emphasis)] hover:underline" to={ticketDetailQuery(selectedObservation.ticket_id, true)}>查看真实 Ticket</Link> : <StatusTag tone="neutral">Observation only</StatusTag>}<button className="inline-flex items-center gap-1 bg-transparent p-0 text-[var(--color-emphasis)] hover:underline disabled:opacity-40" disabled={!observationCandles.data} type="button" onClick={() => setObservationFullscreen(true)}><Maximize2 aria-hidden="true" className="h-3 w-3" />全屏</button></div></div>
                  <div className="min-h-[420px] border border-[var(--color-divider)] bg-[#11141A]">{selectedObservation.status === "unavailable" ? <div className="grid min-h-[420px] place-content-center gap-2 text-center"><strong>观察计划不可用</strong><span className="text-[12px] text-[var(--color-text-secondary)]">{selectedObservation.completion_reason ?? "缺少冻结价格事实"}</span></div> : observationCandles.isError ? <div className="grid min-h-[420px] place-content-center gap-2 text-center"><strong>公共 K 线不可用</strong><span className="text-[12px] text-[var(--color-text-secondary)]">冻结 Observation 价格和路径仍可阅读</span></div> : !observationCandles.data ? <div className="grid min-h-[420px] place-content-center text-[12px] text-[var(--color-text-secondary)]">正在读取 15m K 线</div> : <Suspense fallback={<div className="grid min-h-[420px] place-content-center text-[12px] text-[var(--color-text-secondary)]">正在加载图表组件</div>}><CausalityChart annotations={selectedObservation.annotations} candles={observationCandles.data.data.candles} priceLevels={observationPriceLevels(selectedObservation)} /></Suspense>}</div>
                </div>}
              </section>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <Dialog.Root open={observationFullscreen && selectedObservation !== undefined} onOpenChange={setObservationFullscreen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-[60] bg-black/85" />
          <Dialog.Content className="fixed inset-4 z-[70] grid max-h-[calc(100vh-32px)] grid-rows-[auto_minmax(0,1fr)] border border-[var(--color-divider)] bg-[var(--color-background)] outline-none md:inset-8">
            <div className="flex min-h-11 items-center justify-between gap-3 border-b border-[var(--color-divider)] bg-[var(--color-surface)] px-3"><div className="min-w-0"><Dialog.Title className="m-0 truncate text-[14px] font-semibold">{selectedObservation?.exchange_instrument_id} · Observation 15m</Dialog.Title><Dialog.Description className="m-0 truncate text-[11px] text-[var(--color-text-secondary)]">Entry、Stop、TP1 与 Opening Range 均为 Signal 时冻结计划</Dialog.Description></div><Dialog.Close asChild><button className="grid h-8 w-8 place-items-center bg-transparent text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]" type="button" aria-label="关闭 Observation 全屏"><X aria-hidden="true" className="h-4 w-4" /></button></Dialog.Close></div>
            {selectedObservation && observationCandles.data ? <Suspense fallback={<div className="grid place-content-center text-[12px] text-[var(--color-text-secondary)]">正在加载图表组件</div>}><CausalityChart annotations={selectedObservation.annotations} candles={observationCandles.data.data.candles} priceLevels={observationPriceLevels(selectedObservation)} fullscreen /></Suspense> : <div className="grid place-content-center text-[12px] text-[var(--color-text-secondary)]">K 线不可用</div>}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </AppShell>
  );
}
