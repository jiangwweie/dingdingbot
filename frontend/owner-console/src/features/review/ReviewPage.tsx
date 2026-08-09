import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { type ChangeEvent, type ReactNode, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import type { components } from "../../api/schema";
import { AppShell } from "../../app/AppShell";
import { CursorPagination } from "../../components/tables/CursorPagination";
import { DenseTable, type DenseTableColumnDef } from "../../components/tables/DenseTable";
import { InlineDetailRow } from "../../components/tables/InlineDetailRow";
import { DataAge } from "../../components/ui/DataAge";
import { ManualRefreshButton } from "../../components/ui/ManualRefreshButton";
import { PageHeader } from "../../components/ui/PageHeader";
import { StatusTag, type StatusTone } from "../../components/ui/StatusTag";
import { UnavailablePanel } from "../../components/ui/UnavailablePanel";
import { getReviewCenter, reviewQueryKey } from "./api";
import { parseReviewSearchParams, reviewSearchParamsToString, type ReviewSearchParams } from "./searchParams";

type Freshness = components["schemas"]["Freshness"];
type MoneyMetric = components["schemas"]["MoneyMetric"];
type ReviewItem = components["schemas"]["ReviewCenterItem"];
type Evidence = components["schemas"]["EvidenceRef"];

const REVIEW_COLUMN_WIDTHS = ["14%", "11%", "13%", "12%", "9%", "8%", "8%", "8%", "10%", "7%"] as const;

function freshnessPresentation(freshness: Freshness) {
  if (freshness === "stale") return { label: "数据陈旧", tone: "attention" as const };
  if (freshness === "unavailable") return { label: "数据不可用", tone: "danger" as const };
  if (freshness === "contradictory") return { label: "事实矛盾", tone: "danger" as const };
  return { label: "数据正常", tone: "success" as const };
}

function trimDecimal(value: string): string {
  if (!/^-?\d+(?:\.\d+)?$/.test(value)) return value;
  const [whole = value, fraction = ""] = value.split(".");
  const trimmed = fraction.replace(/0+$/, "");
  return trimmed ? `${whole}.${trimmed}` : whole;
}

function metricText(metric: MoneyMetric, sign = false): string {
  if (metric.value === null) return `— · ${metric.unavailable_reason ?? "unavailable"}`;
  const normalized = trimDecimal(metric.value);
  const prefix = sign && !normalized.startsWith("-") && normalized !== "0" ? "+" : "";
  return `${prefix}${normalized} ${metric.unit === "USDT" ? "U" : metric.unit}`;
}

function MetricValue({ metric, sign = false }: { metric: MoneyMetric; sign?: boolean }) {
  if (metric.value !== null) return <span className="tabular-number whitespace-nowrap">{metricText(metric, sign)}</span>;
  return <span className="grid min-w-0"><span>—</span><small className="truncate text-[9px] text-[var(--color-text-secondary)]" title={metric.unavailable_reason ?? "unavailable"}>{metric.unavailable_reason ?? "unavailable"}</small></span>;
}

function executionTone(value: ReviewItem["review"]["execution_classification"]): StatusTone {
  if (value === "complete") return "success";
  if (value === "recovered_incident") return "attention";
  if (value === "evidence_incomplete") return "danger";
  return "neutral";
}

function executionLabel(value: ReviewItem["review"]["execution_classification"]): string {
  if (value === "recovered_incident") return "recovered";
  if (value === "evidence_incomplete") return "incomplete";
  if (value === "waiting_review") return "waiting review";
  if (value === "in_progress") return "in progress";
  return value;
}

function evidenceStatusLabel(value: ReviewItem["review"]["review_status"]): string {
  if (value === "complete") return "完整";
  if (value === "incomplete_evidence") return "不完整";
  if (value === "waiting_review") return "等待 Review";
  return "进行中";
}

function EvidenceLinks({ evidence, ticketId }: { evidence: Evidence[]; ticketId: string }) {
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1">
      {evidence.map((item) => (
        <Link className="break-all text-[10px] text-[var(--color-emphasis)] hover:underline" key={`${item.kind}:${item.identity}:${item.occurred_at_ms}`} to={`/trades/${encodeURIComponent(ticketId)}`}>
          {item.identity}
        </Link>
      ))}
    </div>
  );
}

function ReviewFilters({ filters, onChange }: { filters: ReviewSearchParams; onChange: (filters: ReviewSearchParams) => void }) {
  const setText = (event: ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target;
    onChange({ ...filters, [name]: value.trim() || undefined, cursor: undefined } as ReviewSearchParams);
  };
  const setStatus = (event: ChangeEvent<HTMLSelectElement>) => {
    onChange({ ...filters, review_status: event.target.value ? event.target.value as ReviewSearchParams["review_status"] : undefined, cursor: undefined });
  };
  return (
    <form className="mb-2 grid grid-cols-2 gap-2 border border-[var(--color-divider)] bg-[var(--color-surface)] p-2 md:grid-cols-4" aria-label="复盘筛选条件">
      <label className="grid gap-1 text-[11px] text-[var(--color-text-secondary)]">StrategyGroup<input className="h-[30px] min-w-0 border border-[var(--color-divider)] bg-[var(--color-background)] px-2 text-[12px] text-[var(--color-text-primary)] outline-none focus:border-[var(--color-emphasis)]" name="strategy_group_id" value={filters.strategy_group_id ?? ""} onChange={setText} /></label>
      <label className="grid gap-1 text-[11px] text-[var(--color-text-secondary)]">Review Status<select className="h-[30px] border border-[var(--color-divider)] bg-[var(--color-background)] px-2 text-[12px] text-[var(--color-text-primary)] outline-none focus:border-[var(--color-emphasis)]" value={filters.review_status ?? ""} onChange={setStatus}><option value="">全部</option><option value="complete">Complete</option><option value="incomplete_evidence">Incomplete Evidence</option><option value="waiting_for_review">Waiting Review</option><option value="waiting_for_settlement">Waiting Settlement</option></select></label>
      <label className="grid gap-1 text-[11px] text-[var(--color-text-secondary)]">From (ms)<input className="h-[30px] min-w-0 border border-[var(--color-divider)] bg-[var(--color-background)] px-2 text-[12px] text-[var(--color-text-primary)] outline-none focus:border-[var(--color-emphasis)]" inputMode="numeric" name="from_ms" value={filters.from_ms ?? ""} onChange={setText} /></label>
      <label className="grid gap-1 text-[11px] text-[var(--color-text-secondary)]">To (ms)<input className="h-[30px] min-w-0 border border-[var(--color-divider)] bg-[var(--color-background)] px-2 text-[12px] text-[var(--color-text-primary)] outline-none focus:border-[var(--color-emphasis)]" inputMode="numeric" name="to_ms" value={filters.to_ms ?? ""} onChange={setText} /></label>
    </form>
  );
}

function ReviewDetail({ item }: { item: ReviewItem }) {
  return (
    <div className="grid gap-3">
      {item.review.sentences.map((sentence) => (
        <article className="grid gap-1" key={sentence.template_id}>
          <p className="m-0 text-[12px] leading-5 text-[var(--color-text-primary)]">{sentence.text}</p>
          <EvidenceLinks evidence={sentence.evidence} ticketId={item.ticket_id} />
        </article>
      ))}
      {item.review.attention_items.length > 0 ? <div className="border-t border-[var(--color-divider)] pt-2 text-[11px] text-[var(--color-danger)]">{item.review.attention_items.join(" · ")}</div> : null}
    </div>
  );
}

export function ReviewPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(() => parseReviewSearchParams(searchParams), [searchParams]);
  const [expandedTicketId, setExpandedTicketId] = useState<string | null>(null);
  const reviews = useQuery({ queryKey: reviewQueryKey(filters), queryFn: () => getReviewCenter(filters) });
  const envelope = reviews.data;
  const shellStatus = envelope ? freshnessPresentation(envelope.freshness) : { label: reviews.isError ? "不可用" : "加载中", tone: "neutral" as StatusTone };
  const updateFilters = (next: ReviewSearchParams) => {
    setExpandedTicketId(null);
    setSearchParams(reviewSearchParamsToString(next));
  };
  const pageHeader = <PageHeader title="复盘" description="逐笔执行质量、经济事实与可追溯证据" actions={<ManualRefreshButton isRefreshing={reviews.isFetching} onRefresh={() => void reviews.refetch()} />} />;

  if (!envelope) {
    return <AppShell dataTime={<DataAge generatedAt={null} />} statusLabel={shellStatus.label} statusTone={shellStatus.tone}>{pageHeader}<UnavailablePanel title={reviews.isError ? "复盘不可用" : "正在读取复盘"} detail={reviews.isError ? "保留页面，不把缺失 Review 解释为零结果。" : "仅读取一次有界页面快照。"} /></AppShell>;
  }

  const data = envelope.data;
  const status = freshnessPresentation(envelope.freshness);
  const columns: DenseTableColumnDef<ReviewItem>[] = [
    { id: "instrument", header: "Instrument / Side", cell: ({ row }) => { const item = row.original; const expanded = expandedTicketId === item.ticket_id; return <div className="flex min-w-0 items-center gap-1"><button className="grid h-5 w-5 flex-none place-items-center bg-transparent p-0 text-[var(--color-text-secondary)]" type="button" aria-expanded={expanded} aria-label={`${expanded ? "收起" : "展开"} ${item.exchange_instrument_id} ${item.position_side.toUpperCase()} 复盘`} onClick={() => setExpandedTicketId(expanded ? null : item.ticket_id)}><ChevronRight aria-hidden="true" className={`h-3.5 w-3.5 transition-transform ${expanded ? "rotate-90" : ""}`} /></button><Link className="min-w-0 truncate text-[var(--color-emphasis)] hover:underline" to={`/trades/${encodeURIComponent(item.ticket_id)}`}>{item.exchange_instrument_id} {item.position_side.toUpperCase()}</Link></div>; } },
    { accessorKey: "strategy_group_id", header: "StrategyGroup", cell: ({ getValue }) => <span className="block truncate">{String(getValue())}</span> },
    { id: "execution", header: "Execution", cell: ({ row }) => <span title={row.original.review.execution_classification}><StatusTag tone={executionTone(row.original.review.execution_classification)}>{executionLabel(row.original.review.execution_classification)}</StatusTag></span> },
    { id: "exit", header: "Exit Reason", cell: ({ row }) => <span className="block truncate" title={row.original.review.exit_reason ?? "exit_reason_unavailable"}>{row.original.review.exit_reason ?? "—"}</span> },
    { id: "net_pnl", header: "Net PnL", cell: ({ row }) => <MetricValue metric={row.original.review.economic_summary.net_pnl} sign /> },
    { id: "net_r", header: "Net R", cell: ({ row }) => <MetricValue metric={row.original.review.economic_summary.net_r} /> },
    { id: "fees", header: "Fees", cell: ({ row }) => <MetricValue metric={row.original.review.economic_summary.fees} /> },
    { id: "funding", header: "Funding", cell: ({ row }) => <MetricValue metric={row.original.review.economic_summary.funding} /> },
    { id: "evidence", header: "Evidence", cell: ({ row }) => <StatusTag tone={row.original.review.review_status === "complete" ? "success" : row.original.review.review_status === "incomplete_evidence" ? "danger" : "neutral"}>{evidenceStatusLabel(row.original.review.review_status)}</StatusTag> },
    { id: "attention", header: "Attention", cell: ({ row }) => <span className="tabular-number text-[var(--color-text-secondary)]">{row.original.review.attention_items.length || "—"}</span> },
  ];
  const summary: { label: string; value: ReactNode }[] = [
    { label: "Completed Tickets", value: String(data.sample_count) },
    { label: "Net PnL", value: <MetricValue metric={data.net_pnl} sign /> },
    { label: "Net R", value: <MetricValue metric={data.net_r} /> },
    { label: "Fees", value: <MetricValue metric={data.fees} /> },
    { label: "Funding", value: <MetricValue metric={data.funding} /> },
    { label: "证据完整", value: String(data.complete_review_count) },
    { label: "Attention", value: String(data.incomplete_review_count) },
  ];

  return (
    <AppShell dataTime={<DataAge generatedAt={envelope.generated_at} />} statusLabel={status.label} statusTone={status.tone}>
      {pageHeader}
      {reviews.isRefetchError ? <div className="refresh-error" role="status">刷新失败<span>继续显示上一次成功快照</span></div> : null}
      <ReviewFilters filters={filters} onChange={updateFilters} />
      <section className="mb-2 grid grid-cols-2 border border-[var(--color-divider)] bg-[var(--color-surface)] sm:grid-cols-4 xl:grid-cols-7" aria-label="复盘摘要">{summary.map((item, index) => <div className={`grid min-h-[48px] content-center gap-1 px-2 ${index > 0 ? "border-l border-[var(--color-divider)]" : ""}`} key={item.label}><span className="text-[10px] text-[var(--color-text-secondary)]">{item.label}</span><strong className="min-w-0 text-[14px] tabular-number">{item.value}</strong></div>)}</section>
      {data.items.length === 0 ? <div className="panel compact-empty px-2">当前筛选范围内没有完成 Ticket</div> : <DenseTable ariaLabel="完成 Ticket 复盘列表" columnWidths={REVIEW_COLUMN_WIDTHS} columns={columns} data={data.items} getRowId={(item) => item.ticket_id} expandedRowId={expandedTicketId} renderExpandedRow={(item, columnCount) => <InlineDetailRow colSpan={columnCount}><ReviewDetail item={item} /></InlineDetailRow>} />}
      <CursorPagination hasNextPage={data.next_cursor !== null} label="还有更多终态 Review" onNextPage={() => updateFilters({ ...filters, cursor: data.next_cursor ?? undefined })} />
      <div className="mt-2 grid gap-2 lg:grid-cols-3">
        <section className="border border-[var(--color-divider)] bg-[var(--color-surface)]"><h2 className="m-0 flex min-h-[30px] items-center border-b border-[var(--color-divider)] bg-[var(--color-surface-secondary)] px-2 text-[11px] font-medium text-[var(--color-text-secondary)]">StrategyGroup Evidence</h2><div className="grid">{data.strategy_group_samples.map((item) => <div className="grid min-h-[42px] grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-2 border-b border-[var(--color-divider)] px-2 last:border-b-0" key={item.strategy_group_id}><strong className="truncate text-[12px]">{item.strategy_group_id}</strong><span className="tabular-number text-[11px] text-[var(--color-text-secondary)]">{item.sample_count}</span><StatusTag tone={item.evidence_state === "observe_only" ? "attention" : "neutral"}>{item.evidence_state === "observe_only" ? "Observe Only" : "No Evidence"}</StatusTag></div>)}</div></section>
        <section className="border border-[var(--color-divider)] bg-[var(--color-surface)]"><h2 className="m-0 flex min-h-[30px] items-center border-b border-[var(--color-divider)] bg-[var(--color-surface-secondary)] px-2 text-[11px] font-medium text-[var(--color-text-secondary)]">Execution Classification</h2><div className="grid">{data.execution_quality_breakdown.map((item) => <div className="flex min-h-[42px] items-center justify-between gap-2 border-b border-[var(--color-divider)] px-2 last:border-b-0" key={item.label}><span className="truncate text-[12px]">{item.label}</span><strong className="tabular-number text-[12px]">{item.ticket_count}</strong></div>)}</div></section>
        <section className="border border-[var(--color-divider)] bg-[var(--color-surface)]"><h2 className="m-0 flex min-h-[30px] items-center border-b border-[var(--color-divider)] bg-[var(--color-surface-secondary)] px-2 text-[11px] font-medium text-[var(--color-text-secondary)]">Exit Reason</h2><div className="grid">{data.exit_reason_breakdown.map((item) => <div className="flex min-h-[42px] items-center justify-between gap-2 border-b border-[var(--color-divider)] px-2 last:border-b-0" key={item.label}><span className="truncate text-[12px]" title={item.label}>{item.label}</span><strong className="tabular-number text-[12px]">{item.ticket_count}</strong></div>)}</div></section>
      </div>
    </AppShell>
  );
}
