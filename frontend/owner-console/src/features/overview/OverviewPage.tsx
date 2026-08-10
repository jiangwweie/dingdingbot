import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AppShell } from "../../app/AppShell";
import { DataAge } from "../../components/ui/DataAge";
import { ManualRefreshButton } from "../../components/ui/ManualRefreshButton";
import { PageHeader } from "../../components/ui/PageHeader";
import { Panel } from "../../components/ui/Panel";
import { StatusTag, type StatusTone } from "../../components/ui/StatusTag";
import { UnavailablePanel } from "../../components/ui/UnavailablePanel";
import { formatMoney } from "../../components/ui/presentation";
import type { components } from "../../api/schema";
import { getOverview, overviewQueryKey } from "./api";

type Freshness = components["schemas"]["Freshness"];
type MoneyMetric = components["schemas"]["MoneyMetric"];
type OwnerConclusion = components["schemas"]["OwnerConclusion"];

const conclusionPresentation: Record<
  OwnerConclusion["level"],
  { label: string; tone: StatusTone }
> = {
  intervention: { label: "需要介入", tone: "danger" },
  attention: { label: "值得关注", tone: "attention" },
  no_action: { label: "无需操作", tone: "success" },
};

function freshnessPresentation(freshness: Freshness, conclusion: OwnerConclusion) {
  if (freshness === "stale") return { label: "数据陈旧", tone: "attention" as const };
  if (freshness === "unavailable") return { label: "数据不可用", tone: "danger" as const };
  if (freshness === "contradictory") return { label: "事实矛盾", tone: "danger" as const };
  return conclusionPresentation[conclusion.level];
}

function formatMetric(metric: MoneyMetric): { text: string; reason: string | null } {
  if (metric.value === null) {
    return { text: "—", reason: metric.unavailable_reason ?? "Unavailable" };
  }
  return { text: formatMoney(metric.value, metric.unit), reason: null };
}

function metricTone(metric: MoneyMetric): string {
  if (metric.value === null || /^-?0(?:\.0+)?$/.test(metric.value)) return "neutral";
  return metric.value.startsWith("-") ? "negative" : "positive";
}

function formatTimestamp(value: number | null): string {
  if (value === null) return "Unavailable";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function MetricValue({ label, metric }: { label: string; metric: MoneyMetric }) {
  const formatted = formatMetric(metric);
  return (
    <div className="metric-cell">
      <span className="metric-cell__label">{label}</span>
      <strong className="metric-cell__value tabular-number" data-value-tone={metricTone(metric)}>
        {formatted.text}
      </strong>
      {formatted.reason ? <span className="metric-cell__reason">{formatted.reason}</span> : null}
    </div>
  );
}

export function OverviewPage() {
  const overview = useQuery({ queryKey: overviewQueryKey, queryFn: getOverview });
  const envelope = overview.data;
  const shellStatus = envelope
    ? freshnessPresentation(envelope.freshness, envelope.data.conclusion)
    : { label: overview.isError ? "不可用" : "加载中", tone: "neutral" as const };

  const pageHeader = (
    <PageHeader
      title="总览"
      description="运行结论、准入快照与需要关注的交易事实"
      actions={
        <ManualRefreshButton
          isRefreshing={overview.isFetching}
          onRefresh={() => void overview.refetch()}
        />
      }
    />
  );

  if (!envelope) {
    return (
      <AppShell
        dataTime={<DataAge generatedAt={null} />}
        statusLabel={shellStatus.label}
        statusTone={shellStatus.tone}
      >
        {pageHeader}
        <UnavailablePanel
          title={overview.isError ? "总览不可用" : "正在读取总览"}
          detail={overview.isError ? "保留当前页面，不把缺失数据解释为系统正常。" : "仅读取一次页面快照。"}
        />
      </AppShell>
    );
  }

  const { data } = envelope;
  const conclusion = conclusionPresentation[data.conclusion.level];
  const wallet = formatMetric(data.account_snapshot.wallet_balance);
  const margin = formatMetric(data.account_snapshot.available_margin);
  const activeCount = data.active_ticket_count;
  const capacity = data.ticket_capacity;

  return (
    <AppShell
      dataTime={<DataAge generatedAt={envelope.generated_at} />}
      statusLabel={shellStatus.label}
      statusTone={shellStatus.tone}
    >
      {pageHeader}

      {overview.isRefetchError ? (
        <div className="refresh-error" role="status">
          刷新失败 · {new Date(overview.errorUpdatedAt).toLocaleTimeString("zh-CN", { hour12: false })}
          <span>继续显示上一次成功快照</span>
        </div>
      ) : null}

      <section className="overview-conclusion panel" data-level={data.conclusion.level}>
        <div className="overview-conclusion__status">
          <StatusTag tone={conclusion.tone}>{conclusion.label}</StatusTag>
          <strong>{data.conclusion.summary}</strong>
        </div>
        <div className="overview-conclusion__action">
          <span>Owner Action</span>
          <strong>{data.conclusion.owner_action ?? "无需 Owner 操作"}</strong>
        </div>
      </section>

      <div className="overview-primary-grid">
        <Panel title={data.account_snapshot.label}>
          <div className="snapshot-grid">
            <div className="fact-cell">
              <span>账户权益</span>
              <strong className="tabular-number">{wallet.text}</strong>
              {wallet.reason ? <small>{wallet.reason}</small> : null}
            </div>
            <div className="fact-cell">
              <span>可用保证金</span>
              <strong className="tabular-number">{margin.text}</strong>
              {margin.reason ? <small>{margin.reason}</small> : null}
            </div>
            <div className="fact-cell">
              <span>快照时间</span>
              <strong className="tabular-number">{formatTimestamp(data.account_snapshot.captured_at_ms)}</strong>
              <small>非实时账户余额</small>
            </div>
          </div>
        </Panel>

        <Panel title="Ticket 当前容量">
          <div className="capacity-row">
            <div className="capacity-row__main">
              <strong className="tabular-number">
                {activeCount ?? "—"} / {capacity ?? "—"}
              </strong>
              <span>当前占用 / 策略容量</span>
            </div>
            <StatusTag tone={activeCount === null || capacity === null ? "neutral" : "success"}>
              {activeCount === null || capacity === null ? "Unavailable" : "容量可读"}
            </StatusTag>
          </div>
        </Panel>
      </div>

      <Panel title="今日结果">
        <div className="daily-metrics">
          <MetricValue label="Net PnL" metric={data.today_net_pnl} />
          <MetricValue label="Net R" metric={data.today_net_r} />
          <div className="metric-cell">
            <span className="metric-cell__label">Signals</span>
            <strong className="metric-cell__value tabular-number">{data.today_signal_count}</strong>
            <span className="metric-cell__reason">今日已持久化 Signal</span>
          </div>
        </div>
      </Panel>

      <Panel title="活动 Ticket">
        {data.active_ticket_ids.length > 0 ? (
          <div className="active-ticket-list">
            {data.active_ticket_ids.map((ticketId) => (
              <Link className="active-ticket-row" to={`/trades/${encodeURIComponent(ticketId)}`} key={ticketId}>
                <span className="tabular-number">{ticketId}</span>
                <span>查看因果详情 →</span>
              </Link>
            ))}
          </div>
        ) : (
          <div className="compact-empty">当前没有活动 Ticket</div>
        )}
      </Panel>

      <div className="overview-secondary-grid">
        <Panel title="机会与准入">
          <div className="compact-stat-grid">
            <div><span>Signals</span><strong className="tabular-number">{data.today_signal_count}</strong></div>
            <div><span>Admitted</span><strong className="tabular-number positive-text">{data.admitted_signal_count}</strong></div>
            <div><span>Rejected</span><strong className="tabular-number">{data.rejected_signal_count}</strong></div>
          </div>
        </Panel>
        <Panel title="执行质量">
          <div className="execution-summary">
            <div>
              <span>运行 Incident</span>
              <strong className="tabular-number">{data.execution_incident_count ?? "—"}</strong>
            </div>
            <StatusTag
              tone={
                data.execution_incident_count === null
                  ? "neutral"
                  : data.execution_incident_count > 0
                    ? "danger"
                    : "success"
              }
            >
              {data.execution_incident_count === null
                ? "Unavailable"
                : data.execution_incident_count > 0
                  ? "需要检查"
                  : "执行链正常"}
            </StatusTag>
          </div>
        </Panel>
      </div>

      <Panel title="自动关注摘要">
        {data.attention_summary.length > 0 ? (
          <ul className="attention-list">
            {data.attention_summary.map((item) => <li key={item}>{item}</li>)}
          </ul>
        ) : (
          <div className="compact-empty">当前没有自动关注项</div>
        )}
      </Panel>
    </AppShell>
  );
}
