import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { useMemo, useState, type ChangeEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AppShell } from "../../app/AppShell";
import { CursorPagination } from "../../components/tables/CursorPagination";
import { DenseTable, type DenseTableColumnDef } from "../../components/tables/DenseTable";
import { InlineDetailRow } from "../../components/tables/InlineDetailRow";
import { DataAge } from "../../components/ui/DataAge";
import { ManualRefreshButton } from "../../components/ui/ManualRefreshButton";
import { PageHeader } from "../../components/ui/PageHeader";
import { StatusTag, type StatusTone } from "../../components/ui/StatusTag";
import { UnavailablePanel } from "../../components/ui/UnavailablePanel";
import { TimeRangeFilter } from "../../components/ui/TimeRangeFilter";
import { formatMoney, formatOwnerReason, formatOwnerStatus, formatTimestamp } from "../../components/ui/presentation";
import type { components } from "../../api/schema";
import { getTrades, tradesQueryKey } from "./api";
import {
  parseTradeSearchParams,
  tradeSearchParamsToString,
  type TradeSearchParams,
} from "./searchParams";

type TradeItem = components["schemas"]["TradeListItem"];
type Freshness = components["schemas"]["Freshness"];
type MoneyMetric = components["schemas"]["MoneyMetric"];

const TRADE_COLUMN_WIDTHS = ["16%", "11%", "15%", "11%", "11%", "10%", "8%", "8%", "10%"] as const;

function freshnessPresentation(freshness: Freshness) {
  if (freshness === "stale") return { label: "数据陈旧", tone: "attention" as const };
  if (freshness === "unavailable") return { label: "数据不可用", tone: "danger" as const };
  if (freshness === "contradictory") return { label: "事实矛盾", tone: "danger" as const };
  return { label: "数据正常", tone: "success" as const };
}

function metricLabel(metric: MoneyMetric): string {
  if (metric.value === null) return "—";
  return formatMoney(metric.value, metric.unit);
}

function sumDecimalStrings(values: string[]): string {
  const scale = values.reduce((largest, value) => {
    const unsigned = value.startsWith("-") ? value.slice(1) : value;
    if (!/^\d+(?:\.\d+)?$/.test(unsigned)) throw new Error("invalid decimal metric");
    return Math.max(largest, unsigned.split(".")[1]?.length ?? 0);
  }, 0);
  const total = values.reduce((sum, value) => {
    const negative = value.startsWith("-");
    const unsigned = negative ? value.slice(1) : value;
    const [whole, fraction = ""] = unsigned.split(".");
    const atomic = BigInt(`${whole}${fraction.padEnd(scale, "0")}`);
    return sum + (negative ? -atomic : atomic);
  }, 0n);
  if (total === 0n) return "0";
  const negative = total < 0n;
  const digits = (negative ? -total : total).toString().padStart(scale + 1, "0");
  if (scale === 0) return `${negative ? "-" : ""}${digits}`;
  const whole = digits.slice(0, -scale);
  const fraction = digits.slice(-scale).replace(/0+$/, "");
  return `${negative ? "-" : ""}${whole}${fraction ? `.${fraction}` : ""}`;
}

function sumMetric(items: TradeItem[], select: (item: TradeItem) => MoneyMetric, unit: "USDT" | "R"): string {
  const values = items.map(select).flatMap((metric) => metric.value === null ? [] : [metric.value]);
  if (values.length === 0) return "—";
  return formatMoney(sumDecimalStrings(values), unit);
}

function TradeFilters({ filters, onChange }: { filters: TradeSearchParams; onChange: (filters: TradeSearchParams) => void }) {
  const setTextFilter = (event: ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target;
    onChange({ ...filters, [name]: value.trim() || undefined, cursor: undefined } as TradeSearchParams);
  };
  const setSelectFilter = (event: ChangeEvent<HTMLSelectElement>) => {
    const { name, value } = event.target;
    onChange({ ...filters, [name]: value || undefined, cursor: undefined } as TradeSearchParams);
  };

  return <form className="mb-2 grid grid-cols-2 gap-2 border border-[var(--color-divider)] bg-[var(--color-surface)] p-2 md:grid-cols-4" aria-label="Ticket 筛选条件">
    <label className="grid gap-1 text-[11px] text-[var(--color-text-secondary)]">策略组<input className="h-[30px] min-w-0 border border-[var(--color-divider)] bg-[var(--color-background)] px-2 text-[12px] text-[var(--color-text-primary)] outline-none focus:border-[var(--color-emphasis)]" name="strategy_group_id" value={filters.strategy_group_id ?? ""} onChange={setTextFilter} /></label>
    <label className="grid gap-1 text-[11px] text-[var(--color-text-secondary)]">交易对<input className="h-[30px] min-w-0 border border-[var(--color-divider)] bg-[var(--color-background)] px-2 text-[12px] text-[var(--color-text-primary)] outline-none focus:border-[var(--color-emphasis)]" name="exchange_instrument_id" value={filters.exchange_instrument_id ?? ""} onChange={setTextFilter} /></label>
    <label className="grid gap-1 text-[11px] text-[var(--color-text-secondary)]">方向<select className="h-[30px] border border-[var(--color-divider)] bg-[var(--color-background)] px-2 text-[12px] text-[var(--color-text-primary)] outline-none focus:border-[var(--color-emphasis)]" name="position_side" value={filters.position_side ?? ""} onChange={setSelectFilter}><option value="">全部</option><option value="long">做多</option><option value="short">做空</option></select></label>
    <label className="grid gap-1 text-[11px] text-[var(--color-text-secondary)]">状态<input className="h-[30px] min-w-0 border border-[var(--color-divider)] bg-[var(--color-background)] px-2 text-[12px] text-[var(--color-text-primary)] outline-none focus:border-[var(--color-emphasis)]" name="aggregate_status" value={filters.aggregate_status ?? ""} onChange={setTextFilter} /></label>
    <TimeRangeFilter value={filters} onChange={(range) => onChange({ ...filters, ...range, cursor: undefined })} />
  </form>;
}

function TradeSummary({ trade }: { trade: TradeItem }) {
  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[12px] sm:grid-cols-4">
      <span><small className="block text-[11px] text-[var(--color-text-secondary)]">Ticket</small><strong className="break-all">{trade.ticket_id}</strong></span>
      <span><small className="block text-[11px] text-[var(--color-text-secondary)]">生命周期</small><strong className="tabular-number">{trade.completed_stage_count}/{trade.total_stage_count}</strong></span>
      <span><small className="block text-[11px] text-[var(--color-text-secondary)]">经济事实</small><strong>{formatOwnerStatus(trade.economics_completeness ?? "in_progress")}</strong></span>
      <span><small className="block text-[11px] text-[var(--color-text-secondary)]">关注</small><strong className="break-words">{trade.attention_items.join(" · ") || "无"}</strong></span>
    </div>
  );
}

export function TradeListPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(() => parseTradeSearchParams(searchParams), [searchParams]);
  const [expandedTicketId, setExpandedTicketId] = useState<string | null>(null);
  const trades = useQuery({ queryKey: tradesQueryKey(filters), queryFn: () => getTrades(filters) });
  const envelope = trades.data;
  const shellStatus = envelope
    ? freshnessPresentation(envelope.freshness)
    : { label: trades.isError ? "不可用" : "加载中", tone: "neutral" as StatusTone };

  const updateFilters = (nextFilters: TradeSearchParams) => {
    setExpandedTicketId(null);
    setSearchParams(tradeSearchParamsToString(nextFilters));
  };
  const currentListPath = `/trades${searchParams.size > 0 ? `?${searchParams.toString()}` : ""}`;

  const pageHeader = <PageHeader title="交易" description="多 Ticket 生命周期、经济事实与精确因果入口" actions={<ManualRefreshButton isRefreshing={trades.isFetching} onRefresh={() => void trades.refetch()} />} />;

  if (!envelope) {
    return (
      <AppShell dataTime={<DataAge generatedAt={null} />} statusLabel={shellStatus.label} statusTone={shellStatus.tone}>
        {pageHeader}
        <UnavailablePanel title={trades.isError ? "交易不可用" : "正在读取 Ticket"} detail={trades.isError ? "保留页面，不把缺失事实解释为空仓。" : "仅读取一次页面快照。"} />
      </AppShell>
    );
  }

  const items = envelope.data.items;
  const activeCount = items.filter((item) => item.terminal_at_ms === null).length;
  const status = freshnessPresentation(envelope.freshness);
  const columns: DenseTableColumnDef<TradeItem>[] = [
    {
      id: "instrument",
      header: "Instrument / Side",
      cell: ({ row }) => {
        const trade = row.original;
        const isExpanded = expandedTicketId === trade.ticket_id;
        const returnParams = new URLSearchParams({ return: currentListPath });
        return (
          <div className="flex min-w-0 items-center gap-1">
            <button className="grid h-5 w-5 flex-none place-items-center bg-transparent p-0 text-[var(--color-text-secondary)]" type="button" aria-expanded={isExpanded} aria-label={`${isExpanded ? "收起" : "展开"} ${trade.exchange_instrument_id} ${trade.position_side.toUpperCase()} 概要`} onClick={() => setExpandedTicketId(isExpanded ? null : trade.ticket_id)}>
              <ChevronRight aria-hidden="true" className={`h-3.5 w-3.5 transition-transform ${isExpanded ? "rotate-90" : ""}`} strokeWidth={1.8} />
            </button>
            <Link className="min-w-0 truncate text-[var(--color-emphasis)] hover:underline" state={{ returnPath: currentListPath, ticketIds: items.map((item) => item.ticket_id) }} to={`/trades/${encodeURIComponent(trade.ticket_id)}?${returnParams.toString()}`}>{trade.exchange_instrument_id} {trade.position_side.toUpperCase()}</Link>
          </div>
        );
      },
    },
    { accessorKey: "strategy_group_id", header: "策略组", cell: ({ getValue }) => <span className="block truncate">{String(getValue())}</span> },
    { accessorKey: "aggregate_status", header: "状态", cell: ({ row }) => <StatusTag tone={row.original.terminal_at_ms === null ? "attention" : "success"}>{formatOwnerStatus(row.original.aggregate_status)}</StatusTag> },
    { accessorKey: "lifecycle_stage", header: "生命周期", cell: ({ row }) => <span className="tabular-number">{formatOwnerStatus(row.original.lifecycle_stage)} {row.original.completed_stage_count}/{row.original.total_stage_count}</span> },
    { accessorKey: "exit_reason", header: "退出原因", cell: ({ row }) => { const reason = row.original.exit_reason ?? row.original.exit_reason_unavailable_reason; return <span className="block truncate" title={reason ?? undefined}>{reason ? formatOwnerReason(reason).label : "—"}</span>; } },
    { accessorKey: "net_pnl", header: "净盈亏", cell: ({ row }) => <span className="tabular-number whitespace-nowrap">{metricLabel(row.original.net_pnl)}</span> },
    { accessorKey: "net_r", header: "净 R", cell: ({ row }) => <span className="tabular-number whitespace-nowrap">{metricLabel(row.original.net_r)}</span> },
    { accessorKey: "attention_items", header: "关注项", cell: ({ row }) => <span className="block truncate text-[var(--color-text-secondary)]" title={row.original.attention_items.join(" · ")}>{row.original.attention_items.length > 0 ? row.original.attention_items.length : "—"}</span> },
    { accessorKey: "issued_at_ms", header: "创建时间", cell: ({ getValue }) => <span className="tabular-number whitespace-nowrap">{formatTimestamp(Number(getValue()))}</span> },
  ];

  const summary = [
    ["本页 Tickets", String(items.length)],
    ["Active", String(activeCount)],
    ["Net PnL", sumMetric(items, (item) => item.net_pnl, "USDT")],
    ["Net R", sumMetric(items, (item) => item.net_r, "R")],
    ["Fees", sumMetric(items, (item) => item.fees, "USDT")],
    ["Funding", sumMetric(items, (item) => item.funding, "USDT")],
  ];

  return (
    <AppShell dataTime={<DataAge generatedAt={envelope.generated_at} />} statusLabel={status.label} statusTone={status.tone}>
      {pageHeader}
      {trades.isRefetchError ? <div className="refresh-error" role="status">刷新失败 · {new Date(trades.errorUpdatedAt).toLocaleTimeString("zh-CN", { hour12: false })}<span>继续显示上一次成功快照</span></div> : null}
      <TradeFilters filters={filters} onChange={updateFilters} />
      <section className="mb-2 grid grid-cols-3 border border-[var(--color-divider)] bg-[var(--color-surface)] md:grid-cols-6" aria-label="交易摘要">
        {summary.map(([label, value], index) => <div className={`grid min-h-[48px] content-center gap-1 px-2 ${index > 0 ? "border-l border-[var(--color-divider)]" : ""}`} key={label}><span className="text-[11px] text-[var(--color-text-secondary)]">{label}</span><strong className="tabular-number truncate text-[15px]" title={value}>{value}</strong></div>)}
      </section>
      {items.length === 0 ? <div className="panel compact-empty px-2">当前筛选范围内没有 Ticket</div> : <DenseTable ariaLabel="Ticket 交易列表" columnWidths={TRADE_COLUMN_WIDTHS} columns={columns} data={items} getRowId={(item) => item.ticket_id} expandedRowId={expandedTicketId} renderExpandedRow={(item, columnCount) => <InlineDetailRow colSpan={columnCount}><TradeSummary trade={item} /></InlineDetailRow>} />}
      <CursorPagination hasNextPage={envelope.data.next_cursor !== null} onNextPage={() => updateFilters({ ...filters, cursor: envelope.data.next_cursor ?? undefined })} />
    </AppShell>
  );
}
