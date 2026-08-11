import { useQuery } from "@tanstack/react-query";
import * as Dialog from "@radix-ui/react-dialog";
import { ChevronRight, X } from "lucide-react";
import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AppShell } from "../../app/AppShell";
import type { components } from "../../api/schema";
import { CursorPagination } from "../../components/tables/CursorPagination";
import { DenseTable, type DenseTableColumnDef } from "../../components/tables/DenseTable";
import { DataAge } from "../../components/ui/DataAge";
import { ManualRefreshButton } from "../../components/ui/ManualRefreshButton";
import { PageHeader } from "../../components/ui/PageHeader";
import { StatusTag, type StatusTone } from "../../components/ui/StatusTag";
import { TimeRangeFilter } from "../../components/ui/TimeRangeFilter";
import { UnavailablePanel } from "../../components/ui/UnavailablePanel";
import { formatMoney, formatOwnerReason, formatTimestamp } from "../../components/ui/presentation";
import { getStrategies, getStrategyTickets, strategiesQueryKey, strategyTicketsQueryKey } from "./api";
import { parseStrategySearchParams, strategySearchParamsToString, type StrategySearchParams } from "./searchParams";

type Strategy = components["schemas"]["StrategyVersionSummary"];
type StrategyTicket = components["schemas"]["StrategyTicketListItem"];
type Freshness = components["schemas"]["Freshness"];
type Path = NonNullable<StrategySearchParams["exit_path"]>;

const STRATEGY_COLUMN_WIDTHS = ["22%", "13%", "13%", "12%", "12%", "16%", "12%"] as const;

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
        <select className="h-[30px] border border-[var(--color-divider)] bg-[var(--color-background)] px-2 text-[12px] text-[var(--color-text-primary)] outline-none focus:border-[var(--color-emphasis)]" value={filters.view ?? "current"} onChange={(event) => onChange({ ...filters, view: event.target.value as "current" | "all", cursor: undefined })}>
          <option value="current">当前活跃版本</option>
          <option value="all">全部历史版本</option>
        </select>
        <small className="text-[10px]">统计主键为 StrategyVersion，不合并版本</small>
      </label>
      <TimeRangeFilter value={filters} onChange={(range) => onChange({ ...filters, ...range, cursor: undefined })} />
    </form>
  );
}

function pathLabel(path: Path): string {
  return { tp1_reached: "已达 TP1", tp1_not_reached: "未达 TP1", controlled_exit: "受控退出" }[path];
}

function pathScope(path: Path): "natural" | "all" {
  return path === "controlled_exit" ? "all" : "natural";
}

function modalTitle(item: Strategy | undefined, path: Path | undefined): string {
  if (!item || !path) return "Ticket 证据";
  return `${item.strategy_group_display_name} v${item.version} · ${pathLabel(path)}`;
}

function productFamilyLabel(value: components["schemas"]["StrategyProductEventFacts"]["product_family"]): string {
  return value === "tradfi_equity_perpetual" ? "Equity Perp" : "Crypto Perp";
}

function entryWindowLabel(event: components["schemas"]["StrategyProductEventFacts"]): string {
  if (event.product_family === "tradfi_equity_perpetual" && event.event_id.startsWith("SOR-US-")) return "REGULAR +30m–+150m";
  if (event.product_family === "tradfi_equity_perpetual") return "REGULAR only";
  return `Continuous · ${event.timeframe} close`;
}

export function StrategyPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(() => parseStrategySearchParams(searchParams), [searchParams]);
  const summaryFilters = useMemo(() => ({ from_ms: filters.from_ms, to_ms: filters.to_ms, view: filters.view ?? "current" }), [filters.from_ms, filters.to_ms, filters.view]);
  const strategies = useQuery({ queryKey: strategiesQueryKey(summaryFilters), queryFn: () => getStrategies(summaryFilters) });
  const envelope = strategies.data;
  const selectedId = filters.ticket_modal === "1" ? filters.strategy_version_id : undefined;
  const selectedPath = filters.ticket_modal === "1" ? filters.exit_path : undefined;
  const selectedVersion = envelope?.data.items.find((item) => item.strategy_version_id === selectedId);
  const ticketFilters = useMemo(() => ({ strategy_version_id: selectedId, from_ms: filters.from_ms, to_ms: filters.to_ms, scope: filters.scope ?? (selectedPath ? pathScope(selectedPath) : "natural"), exit_path: selectedPath, cursor: filters.cursor }), [filters.cursor, filters.from_ms, filters.scope, filters.to_ms, selectedId, selectedPath]);
  const tickets = useQuery({
    queryKey: strategyTicketsQueryKey(ticketFilters),
    queryFn: () => getStrategyTickets({ ...ticketFilters, strategy_version_id: ticketFilters.strategy_version_id! }),
    enabled: selectedId !== undefined && selectedPath !== undefined,
  });
  const shellStatus = envelope ? freshnessPresentation(envelope.freshness) : { label: strategies.isError ? "不可用" : "加载中", tone: "neutral" as StatusTone };

  const updateFilters = (next: StrategySearchParams) => setSearchParams(strategySearchParamsToString(next));
  const openPath = (strategy: Strategy, path: Path) => updateFilters({
    ...filters,
    strategy_version_id: strategy.strategy_version_id,
    ticket_modal: "1",
    scope: pathScope(path),
    exit_path: path,
    cursor: undefined,
  });
  const closeModal = () => {
    const { strategy_version_id: _strategyVersionId, ticket_modal: _ticketModal, scope: _scope, exit_path: _exitPath, cursor: _cursor, ...rest } = filters;
    updateFilters(rest);
  };

  const pageHeader = <PageHeader title="策略" description="按 StrategyVersion 隔离的自然样本、收益路径与 Ticket 证据" actions={<ManualRefreshButton isRefreshing={strategies.isFetching || tickets.isFetching} onRefresh={() => { void strategies.refetch(); if (selectedId) void tickets.refetch(); }} />} />;
  if (!envelope) {
    return <AppShell dataTime={<DataAge generatedAt={null} />} statusLabel={shellStatus.label} statusTone={shellStatus.tone}>{pageHeader}<UnavailablePanel title={strategies.isError ? "策略统计不可用" : "正在读取策略统计"} detail={strategies.isError ? "保留空状态，不将缺失数据解释为没有策略或没有交易。" : "仅读取一次 StrategyVersion 快照。"} /></AppShell>;
  }

  const data = envelope.data;
  const naturalCount = data.items.reduce((total, item) => total + item.natural_terminal_count, 0);
  const confirmedCount = data.items.reduce((total, item) => total + item.confirmed_natural_review_count, 0);
  const pendingCount = data.items.reduce((total, item) => total + item.pending_natural_review_count, 0);
  const status = freshnessPresentation(envelope.freshness);
  const columns: DenseTableColumnDef<Strategy>[] = [
    { id: "version", header: "StrategyVersion / Product", cell: ({ row }) => { const product = row.original.product_events[0]; const activeCount = row.original.product_events.reduce((total, event) => total + event.active_exchange_instrument_ids.length, 0); const warmingCount = row.original.product_events.reduce((total, event) => total + event.warming_exchange_instrument_ids.length, 0); return <div className="grid min-w-0 gap-0.5 py-1"><strong className="truncate text-[12px]">{row.original.strategy_group_display_name} · v{row.original.version}</strong>{product ? <><span className="truncate text-[10px] text-[var(--color-text-secondary)]">{product.venue_id ?? "Venue 未绑定"} · {productFamilyLabel(product.product_family)} · {entryWindowLabel(product)}</span><span className="truncate text-[10px] text-[var(--color-text-secondary)]" title={product.runtime_profile_id ?? undefined}>{product.runtime_profile_id ?? "Runtime 未绑定"} · Active {activeCount} / Warming {warmingCount}</span></> : <span className="truncate text-[10px] text-[var(--color-text-secondary)]" title={row.original.strategy_version_id}>产品摘要不可用 · {row.original.strategy_version_id}</span>}</div>; } },
    { id: "samples", header: "样本覆盖", cell: ({ row }) => <div className="grid gap-0.5 text-[11px]"><strong className="tabular-number">{row.original.natural_terminal_count} 自然终态</strong><span className="text-[var(--color-text-secondary)]">{row.original.ticket_count} Tickets</span></div> },
    { id: "reviews", header: "Review", cell: ({ row }) => <div className="grid gap-0.5 text-[11px]"><strong className="tabular-number">{row.original.confirmed_natural_review_count} 已确认</strong><span className="text-[var(--color-text-secondary)]">{row.original.pending_natural_review_count} 待确认</span></div> },
    { id: "pnl", header: "自然 Net PnL", cell: ({ row }) => <Metric metric={row.original.net_pnl} sign /> },
    { id: "r", header: "自然 Net R", cell: ({ row }) => <Metric metric={row.original.net_r} sign /> },
    { id: "paths", header: "路径归因", cell: ({ row }) => <div className="flex flex-wrap gap-1"><button className="border border-[var(--color-divider)] bg-transparent px-1.5 py-1 text-[10px] text-[var(--color-emphasis)] hover:border-[var(--color-emphasis)] disabled:cursor-not-allowed disabled:opacity-40" disabled={row.original.tp1_reached_count === 0} type="button" onClick={() => openPath(row.original, "tp1_reached")}>TP1 {row.original.tp1_reached_count}</button><button className="border border-[var(--color-divider)] bg-transparent px-1.5 py-1 text-[10px] text-[var(--color-text-primary)] hover:border-[var(--color-emphasis)] disabled:cursor-not-allowed disabled:opacity-40" disabled={row.original.tp1_not_reached_count === 0} type="button" onClick={() => openPath(row.original, "tp1_not_reached")}>未达 {row.original.tp1_not_reached_count}</button></div> },
    { id: "controlled", header: "受控退出", cell: ({ row }) => row.original.controlled_exit_count === 0 ? <span className="text-[var(--color-text-secondary)]">—</span> : <button className="text-[11px] text-[var(--color-emphasis)] hover:underline" type="button" onClick={() => openPath(row.original, "controlled_exit")}>查看 {row.original.controlled_exit_count} 笔</button> },
  ];
  const ticketItems = tickets.data?.data.items ?? [];
  const detailQuery = (ticketId: string) => {
    const detail = new URLSearchParams();
    detail.set("origin", "strategy");
    detail.set("view", filters.view ?? "current");
    if (filters.from_ms !== undefined) detail.set("from_ms", String(filters.from_ms));
    if (filters.to_ms !== undefined) detail.set("to_ms", String(filters.to_ms));
    if (selectedId) detail.set("strategy_version_id", selectedId);
    detail.set("ticket_modal", "1");
    if (selectedPath) detail.set("exit_path", selectedPath);
    detail.set("scope", ticketFilters.scope);
    return `/trades/${encodeURIComponent(ticketId)}?${detail.toString()}`;
  };

  return (
    <AppShell dataTime={<DataAge generatedAt={envelope.generated_at} />} statusLabel={status.label} statusTone={status.tone}>
      {pageHeader}
      {strategies.isRefetchError ? <div className="refresh-error" role="status">刷新失败<span>继续显示上一次成功快照</span></div> : null}
      <StrategyFilters filters={filters} onChange={updateFilters} />
      <section className="mb-2 grid grid-cols-2 border border-[var(--color-divider)] bg-[var(--color-surface)] md:grid-cols-4" aria-label="策略统计摘要">
        {[["StrategyVersions", String(data.items.length)], ["自然终态", String(naturalCount)], ["已确认 Review", String(confirmedCount)], ["待确认 Review", String(pendingCount)]].map(([label, value], index) => <div className={`grid min-h-[48px] content-center gap-1 px-2 ${index > 0 ? "border-l border-[var(--color-divider)]" : ""}`} key={label}><span className="text-[10px] text-[var(--color-text-secondary)]">{label}</span><strong className="tabular-number text-[14px]">{value}</strong></div>)}
      </section>
      {data.items.length === 0 ? <div className="panel compact-empty px-2">当前范围内没有可展示的 StrategyVersion</div> : <DenseTable ariaLabel="StrategyVersion 统计列表" columnWidths={STRATEGY_COLUMN_WIDTHS} columns={columns} data={data.items} getRowId={(item) => item.strategy_version_id} />}

      <Dialog.Root open={selectedId !== undefined && selectedPath !== undefined} onOpenChange={(open) => { if (!open) closeModal(); }}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-black/75" />
          <Dialog.Content className="fixed inset-x-3 top-1/2 z-50 grid max-h-[calc(100vh-32px)] w-auto -translate-y-1/2 grid-rows-[auto_minmax(0,1fr)] border border-[var(--color-divider)] bg-[var(--color-background)] outline-none md:inset-x-[8vw] lg:inset-x-[14vw]">
            <div className="flex min-h-12 items-center justify-between gap-3 border-b border-[var(--color-divider)] bg-[var(--color-surface)] px-3"><div className="min-w-0"><Dialog.Title className="m-0 truncate text-[14px] font-semibold">{modalTitle(selectedVersion, selectedPath)}</Dialog.Title><Dialog.Description className="m-0 truncate text-[11px] text-[var(--color-text-secondary)]">点击 Ticket 进入完整生命周期与 K 线复盘；返回将恢复当前筛选和弹窗。</Dialog.Description></div><Dialog.Close asChild><button className="grid h-8 w-8 flex-none place-items-center bg-transparent text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]" type="button" aria-label="关闭 Ticket 证据"><X aria-hidden="true" className="h-4 w-4" /></button></Dialog.Close></div>
            <div className="min-h-0 overflow-y-auto p-2">
              {tickets.isError ? <UnavailablePanel title="Ticket 证据不可用" detail="保留 StrategyVersion 上下文，未将读取失败解释为无样本。" /> : tickets.isLoading ? <div className="grid min-h-40 place-content-center text-[12px] text-[var(--color-text-secondary)]">正在读取 Ticket 证据</div> : ticketItems.length === 0 ? <div className="grid min-h-40 place-content-center text-[12px] text-[var(--color-text-secondary)]">当前路径没有 Ticket</div> : <div className="grid gap-px border border-[var(--color-divider)] bg-[var(--color-divider)]">{ticketItems.map((ticket) => <Link className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-3 bg-[var(--color-surface)] px-3 py-2 text-left no-underline hover:bg-[var(--color-surface-secondary)]" key={ticket.ticket_id} state={{ ticketIds: ticketItems.map((item) => item.ticket_id) }} to={detailQuery(ticket.ticket_id)}><span className="min-w-0"><strong className="block truncate text-[12px] text-[var(--color-emphasis)]">{ticket.exchange_instrument_id} {ticket.position_side.toUpperCase()}</strong><small className="block truncate text-[10px] text-[var(--color-text-secondary)]">{ticket.ticket_id} · {formatTimestamp(ticket.issued_at_ms)}</small></span><span className="tabular-number text-[11px] text-[var(--color-text-primary)]"><Metric metric={ticket.net_pnl} sign /></span><ChevronRight aria-hidden="true" className="h-4 w-4 text-[var(--color-text-secondary)]" /></Link>)}</div>}
              <CursorPagination hasNextPage={tickets.data?.data.next_cursor !== null && tickets.data !== undefined} label="还有更多路径 Ticket" onNextPage={() => updateFilters({ ...filters, cursor: tickets.data?.data.next_cursor ?? undefined })} />
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </AppShell>
  );
}
