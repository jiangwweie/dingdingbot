import { Activity, AlertTriangle, CheckCircle2, Clock3, FileText, ListChecks, RefreshCw, ShieldCheck, Wallet } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { automationStateLabels, healthLabels } from "../data";
import type { OwnerProductProjection, StrategyGroupProductRow } from "../types";
import { PageShell } from "./chrome";
import { healthTone, homepageOperatingState, isBusinessDataUnavailable, noActionGuaranteeLabels, sourceKindLabels, sourceStatusTone, stateTone, toneClass, toneTextClass, type ConsoleContext, type NavigationKey } from "./model";
import { CascadePanel, ContextRow, CurrentStrategyPanel, FundMiniCard, FundsSafetyPanel, ImportantChanges, MetricTile, SafetyOverviewStrip, StatusBadge, StrategyAvatar, StrategyGroupList, StrategyRunSettings, SystemStateCard } from "./panels";

export function ConsoleContent({
  activeView,
  context,
  onSelect,
  projection,
  selectedStrategy,
}: {
  activeView: NavigationKey;
  context: ConsoleContext;
  onSelect: (id: string) => void;
  projection: OwnerProductProjection;
  selectedStrategy: StrategyGroupProductRow | null;
}) {
  if (activeView === "strategies") {
    return <StrategyGroupsPage onSelect={onSelect} projection={projection} selectedStrategy={selectedStrategy} />;
  }
  if (activeView === "funds") {
    return <FundsPage projection={projection} />;
  }
  if (activeView === "orders") {
    return <OrdersPositionsPage onSelect={onSelect} projection={projection} selectedStrategy={selectedStrategy} />;
  }
  if (activeView === "records") {
    return <RecordsPage projection={projection} />;
  }
  if (activeView === "system") {
    return <SystemPage context={context} projection={projection} />;
  }
  return <HomePage onSelect={onSelect} projection={projection} selectedStrategy={selectedStrategy} />;
}

function HomePage({
  projection,
  selectedStrategy,
  onSelect,
}: {
  projection: OwnerProductProjection;
  selectedStrategy: StrategyGroupProductRow | null;
  onSelect: (id: string) => void;
}) {
  return (
    <PageShell activeView="home">
      <SafetyOverviewStrip summary={projection.productSummary} />
      <OwnerProgressBanner projection={projection} />
      <OperationalAssuranceStrip projection={projection} />
      <RuntimeMetrics summary={projection.productSummary} />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="grid min-w-0 gap-4">
          <StrategyGroupList onSelect={onSelect} rows={projection.strategies} selectedId={selectedStrategy?.id ?? null} />
          <FundsSafetyPanel fundPool={projection.fundPool} />
        </div>
        <aside className="grid min-w-0 gap-4">
          <CurrentStrategyPanel strategy={selectedStrategy} />
          <RealOrderReadinessCard projection={projection} />
          <ImportantChanges changes={projection.importantChanges} />
        </aside>
      </div>
    </PageShell>
  );
}

function OwnerProgressBanner({ projection }: { projection: OwnerProductProjection }) {
  const state = homepageOperatingState(projection);
  return (
    <Card className="rounded-lg bg-[color:var(--background-card-raised)] shadow-[var(--shadow-card)]">
      <CardContent className="grid gap-3 p-4 lg:grid-cols-[180px_minmax(0,1fr)_180px] lg:items-center">
        <div>
          <div className="text-xs font-semibold text-muted-foreground">当前阶段</div>
          <div className="mt-1">
            <StatusBadge tone={state.tone}>{state.label}</StatusBadge>
          </div>
        </div>
        <div className="min-w-0">
          <div className="truncate text-base font-semibold">{state.detail}</div>
          <div className="mt-1 text-sm text-muted-foreground">{ownerProgressSupportText(state.label)}</div>
        </div>
        <ContextRow label="Owner" tone={state.tone} value={state.ownerAction} />
      </CardContent>
    </Card>
  );
}

function ownerProgressSupportText(label: string) {
  if (label === "安全边界阻断") return "真实订单路径保持关闭，等待安全状态恢复";
  if (label === "工程状态暂不可用") return "本地状态等待刷新，不触发额外服务器操作";
  if (label === "系统处理中") return "系统正在处理，Owner 暂无需操作";
  if (label === "需要介入") return "系统已收敛到需要处理的事项";
  return "真实订单路径保持关闭，系统继续观察市场";
}

function OperationalAssuranceStrip({ projection }: { projection: OwnerProductProjection }) {
  const items = [
    {
      label: "监控方式",
      value: `${interactionPrefix(projection.runtimeInteraction.level)} ${projection.runtimeInteraction.ownerLabel}`,
      detail: projection.runtimeInteraction.detail,
      tone: "safe" as const,
      icon: <ShieldCheck />,
    },
    {
      label: "观察服务",
      value: projection.sourceHealth.watcher.label,
      detail: ownerSafeSourceDetail(projection.sourceHealth.watcher.detail, "正在观察市场，当前无需操作"),
      tone: sourceStatusTone[projection.sourceHealth.watcher.status],
      icon: <Activity />,
    },
    {
      label: "事实状态",
      value: projection.sourceHealth.liveFacts.label,
      detail: ownerSafeSourceDetail(projection.sourceHealth.liveFacts.detail, "账户、订单、持仓与保护只读确认"),
      tone: sourceStatusTone[projection.sourceHealth.liveFacts.status],
      icon: <ListChecks />,
    },
    {
      label: "链路演练",
      value: projection.sourceHealth.runtimeDryRunAudit.label,
      detail: ownerSafeSourceDetail(projection.sourceHealth.runtimeDryRunAudit.detail, "非执行演练正常"),
      tone: sourceStatusTone[projection.sourceHealth.runtimeDryRunAudit.status],
      icon: <RefreshCw />,
    },
    {
      label: "发布状态",
      value: projection.sourceHealth.deployChannel.label,
      detail: ownerSafeSourceDetail(projection.sourceHealth.deployChannel.detail, "首页静态资源已接入主线"),
      tone: sourceStatusTone[projection.sourceHealth.deployChannel.status],
      icon: <FileText />,
    },
  ];

  return (
    <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-5" aria-label="运行保障">
      {items.map((item) => (
        <div
          className="grid min-h-[116px] grid-rows-[auto_1fr] rounded-lg border bg-[color:var(--background-card-raised)] p-4 shadow-[var(--shadow-card)]"
          key={item.label}
        >
          <div className="flex items-center justify-between gap-3">
            <span className={cn("grid size-8 place-items-center rounded-lg border", toneClass(item.tone))}>{item.icon}</span>
            <StatusBadge tone={item.tone}>{item.label}</StatusBadge>
          </div>
          <div className="mt-4 min-w-0">
            <div className="truncate text-base font-semibold">{item.value}</div>
            <div className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">{item.detail}</div>
          </div>
        </div>
      ))}
    </section>
  );
}

function interactionPrefix(level: string) {
  return level.split("_", 1)[0] || "L1";
}

function ownerSafeSourceDetail(detail: string | null | undefined, fallback: string) {
  if (!detail) return fallback;
  if (detail.includes("_") || detail.includes(":") || detail.length > 34) return fallback;
  return detail;
}

function realOrderTone(projection: OwnerProductProjection) {
  const readiness = projection.realOrderReadiness;
  if (readiness.submitBlockerReview.required) return "danger" as const;
  if (readiness.blockedCount > 0 || projection.sourceHealth.realOrderReadiness.status === "unavailable") return "danger" as const;
  if (readiness.readyForRealOrderAction) return "safe" as const;
  if (readiness.waitingCount > 0) return "waiting" as const;
  return sourceStatusTone[projection.sourceHealth.realOrderReadiness.status];
}

function RealOrderReadinessCard({ projection }: { projection: OwnerProductProjection }) {
  const readiness = projection.realOrderReadiness;
  const tone = realOrderTone(projection);
  const actionText = readiness.readyForRealOrderAction
    ? "路径已就绪，系统自动处理"
    : readiness.submitBlockerReview.required
      ? "已记录阻断，真实订单关闭"
    : readiness.blockedCount > 0
      ? "路径未就绪，系统保持关闭"
      : "路径健康，等待市场机会";
  const blockerLabels = submitBlockerLabels(readiness.submitBlockerReview.blockerKeys);

  return (
    <Card className="rounded-lg shadow-[var(--shadow-panel)]">
      <CardHeader>
        <CardTitle>实盘边界</CardTitle>
        <CardDescription>系统自动判断是否可以靠近真实订单</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        <div className="flex items-center justify-between gap-3">
          <StatusBadge tone={tone}>{readiness.ownerLabel}</StatusBadge>
          <span className={cn("text-sm font-semibold", toneTextClass(tone))}>{actionText}</span>
        </div>
        <div className="rounded-lg border bg-[color:var(--background-card-raised)] p-4">
          <div className="text-lg font-semibold">
            {readiness.passCount} 项正常 / {readiness.waitingCount} 项等待 / {readiness.blockedCount} 项不可用
          </div>
          <div className="mt-1 text-sm text-muted-foreground">
            {readiness.submitBlockerReview.required
              ? "系统已记录审查，继续修复或观察，真实订单不会提交"
              : readiness.blockedCount > 0
                ? "系统会保持关闭，直到状态恢复"
                : "市场没有机会时，系统继续观察"}
          </div>
        </div>
        {readiness.submitBlockerReview.required ? (
          <div className="rounded-lg border border-[color:var(--status-danger-border)] bg-[color:var(--status-danger-bg)] p-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-[color:var(--status-danger)]">
              <AlertTriangle className="size-4" />
              系统审查已记录
            </div>
            <div className="mt-2 text-sm text-muted-foreground">
              {blockerLabels.length > 0 ? blockerLabels.join("、") : "提交前状态需要系统处理"}
            </div>
          </div>
        ) : null}
        <ContextRow label="真实订单" tone={tone} value={readiness.readyForRealOrderAction ? "路径就绪" : "保持关闭"} />
      </CardContent>
    </Card>
  );
}

function submitBlockerLabels(keys: string[]) {
  const labels: Record<string, string> = {
    active_position_open_order: "有持仓或订单处理中",
    protection: "保护未就绪",
    budget: "预算未就绪",
    duplicate_submit: "重复提交风险",
    symbol_side_notional_leverage_scope: "交易边界不匹配",
    selected_strategygroup_scope: "策略组范围不匹配",
    hard_safety: "安全边界阻断",
    required_facts: "事实状态不可用",
  };
  return keys.map((key) => labels[key]).filter((label): label is string => Boolean(label));
}

function RuntimeMetrics({ summary }: { summary: OwnerProductProjection["productSummary"] }) {
  const metrics = [
    { label: "已启用", value: summary.enabledCount, tone: "safe" as const, icon: <CheckCircle2 /> },
    { label: "运行中", value: summary.runningCount, tone: "safe" as const, icon: <Activity /> },
    { label: "等待机会", value: summary.waitingCount, tone: "waiting" as const, icon: <Clock3 /> },
    { label: "处理中", value: summary.processingCount, tone: "processing" as const, icon: <RefreshCw /> },
    { label: "需要介入", value: summary.ownerAttentionCount, tone: "danger" as const, icon: <AlertTriangle /> },
  ];

  return (
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5" aria-label="今日概览">
      {metrics.map((metric) => (
        <MetricTile key={metric.label} {...metric} />
      ))}
    </section>
  );
}

function StrategyGroupsPage({
  projection,
  selectedStrategy,
  onSelect,
}: {
  projection: OwnerProductProjection;
  selectedStrategy: StrategyGroupProductRow | null;
  onSelect: (id: string) => void;
}) {
  return (
    <PageShell activeView="strategies">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
        <StrategyGroupList onSelect={onSelect} rows={projection.strategies} selectedId={selectedStrategy?.id ?? null} />
        <aside className="grid gap-4">
          <Card className="rounded-lg shadow-[var(--shadow-panel)]">
            <CardHeader>
              <CardTitle>策略组已接入</CardTitle>
              <CardDescription>当前只显示 Owner 能理解和处理的产品状态</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3">
              <ContextRow label="已启用" tone="safe" value={`${projection.productSummary.enabledCount} 个策略组`} />
              <ContextRow label="运行中" tone="safe" value={`${projection.productSummary.runningCount} 个`} />
              <ContextRow label="等待机会" tone="waiting" value={`${projection.productSummary.waitingCount} 个`} />
              <ContextRow label="处理中" tone="processing" value={`${projection.productSummary.processingCount} 个`} />
              <ContextRow label="需要介入" tone="danger" value={`${projection.productSummary.ownerAttentionCount} 个`} />
            </CardContent>
          </Card>
          <StrategyRunSettings strategy={selectedStrategy} />
          <CurrentStrategyPanel strategy={selectedStrategy} />
        </aside>
      </div>
    </PageShell>
  );
}

function FundsPage({ projection }: { projection: OwnerProductProjection }) {
  const fundPool = projection.fundPool;
  return (
    <PageShell activeView="funds">
      <FundsSafetyPanel fundPool={fundPool} />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="rounded-lg shadow-[var(--shadow-panel)]">
          <CardHeader>
            <CardTitle>账户只读</CardTitle>
            <CardDescription>本地只读 key 用于读取资金状态，不承担交易动作</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3">
            <ContextRow label="账户" tone="safe" value={fundPool.code} />
            <ContextRow label="资金" tone={sourceStatusTone[projection.sourceHealth.accountFunds.status]} value={fundPool.accountLabel} />
            <ContextRow label="保护" tone={healthTone[projection.strategies[0]?.protection ?? "unknown"]} value={fundPool.protectionLabel} />
          </CardContent>
        </Card>
        <Card className="rounded-lg shadow-[var(--shadow-panel)] lg:col-span-2">
          <CardHeader>
            <CardTitle>资金分配</CardTitle>
            <CardDescription>只展示资金池状态，不提供划转、扩额或改仓入口</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-3">
            <FundMiniCard label="预算" value={fundPool.budget} />
            <FundMiniCard label="已占用" value={fundPool.reserved} tone="processing" />
            <FundMiniCard label="可用" value={fundPool.available} tone="safe" />
          </CardContent>
        </Card>
      </div>
    </PageShell>
  );
}

function OrdersPositionsPage({
  projection,
  selectedStrategy,
  onSelect,
}: {
  projection: OwnerProductProjection;
  selectedStrategy: StrategyGroupProductRow | null;
  onSelect: (id: string) => void;
}) {
  return (
    <PageShell activeView="orders">
      <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
        <Card className="rounded-lg shadow-[var(--shadow-panel)]">
          <CardHeader>
            <CardTitle>策略组</CardTitle>
            <CardDescription>选择后查看对应订单和持仓级联</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-2">
            {projection.strategies.length === 0 ? (
              <div className="grid min-h-[140px] place-items-center rounded-lg border border-dashed text-sm text-muted-foreground">
                暂无已启用策略组
              </div>
            ) : (
              projection.strategies.map((strategy) => (
                <button
                  className={cn(
                    "flex cursor-pointer items-center justify-between rounded-lg border bg-[color:var(--background-row)] p-3 text-left transition hover:border-[color:var(--border-strong)]",
                    selectedStrategy?.id === strategy.id && "border-[color:var(--border-strong)] shadow-[inset_4px_0_0_var(--accent-primary)]",
                  )}
                  key={strategy.id}
                  onClick={() => onSelect(strategy.id)}
                  type="button"
                >
                  <span className="flex items-center gap-3">
                    <StrategyAvatar code={strategy.code} />
                    <span>
                      <span className="block font-semibold">{strategy.name}</span>
                      <span className="block text-xs text-muted-foreground">{strategy.description}</span>
                    </span>
                  </span>
                  <StatusBadge tone={stateTone[strategy.automationState]}>
                    {strategy.automationLabel || automationStateLabels[strategy.automationState]}
                  </StatusBadge>
                </button>
              ))
            )}
          </CardContent>
        </Card>
        <Card className="rounded-lg shadow-[var(--shadow-panel)]">
          <CardHeader>
            <CardTitle>级联视图</CardTitle>
            <CardDescription>持仓、成交单、保护单和对账状态保持同屏可见</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 lg:grid-cols-4">
            <CascadePanel
              detail={selectedStrategy ? `${selectedStrategy.name} ${healthLabels[selectedStrategy.position]}` : "暂无持仓"}
              icon={<Wallet />}
              label="持仓"
              tone={sourceStatusTone[projection.sourceHealth.positions.status]}
              value={projection.fundPool.positionsLabel}
            />
            <CascadePanel
              detail={selectedStrategy ? `${selectedStrategy.name} ${healthLabels[selectedStrategy.orders]}` : projection.fundPool.ordersLabel}
              icon={<ListChecks />}
              label="成交单"
              tone={sourceStatusTone[projection.sourceHealth.orders.status]}
              value={projection.fundPool.ordersLabel}
            />
            <CascadePanel
              detail={selectedStrategy ? `${selectedStrategy.name} ${healthLabels[selectedStrategy.protection]}` : "暂无保护单"}
              icon={<ShieldCheck />}
              label="保护单"
              tone={healthTone[selectedStrategy?.protection ?? "unknown"]}
              value={projection.fundPool.protectionLabel}
            />
            <CascadePanel
              detail={selectedStrategy ? `${selectedStrategy.name} ${healthLabels[selectedStrategy.reconciliation]}` : "暂无对账"}
              icon={<RefreshCw />}
              label="对账"
              tone={sourceStatusTone[projection.sourceHealth.reconciliation.status]}
              value={projection.fundPool.reconciliationLabel}
            />
          </CardContent>
        </Card>
      </div>
    </PageShell>
  );
}

function RecordsPage({ projection }: { projection: OwnerProductProjection }) {
  return (
    <PageShell activeView="records">
      <ImportantChanges changes={projection.importantChanges} />
      <Card className="rounded-lg shadow-[var(--shadow-panel)]">
        <CardHeader>
          <CardTitle>最近记录</CardTitle>
          <CardDescription>Web 只保留重要变化入口，深度复盘交给记录和 AI 解读</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          {projection.importantChanges.map((change) => (
            <div className="flex items-center gap-3 rounded-lg border bg-[color:var(--background-row)] p-4" key={change.id}>
              <span className={cn("grid size-10 shrink-0 place-items-center rounded-xl border", toneClass(change.tone))}>
                {change.tone === "processing" ? <RefreshCw /> : change.tone === "danger" ? <AlertTriangle /> : <FileText />}
              </span>
              <div className="min-w-0 flex-1">
                <div className="font-semibold">{change.title}</div>
                <div className="text-sm text-muted-foreground">{change.detail}</div>
              </div>
              <Badge variant="outline">{sourceKindLabels[change.sourceKind]}</Badge>
            </div>
          ))}
        </CardContent>
      </Card>
    </PageShell>
  );
}

function SystemPage({ context, projection }: { context: ConsoleContext; projection: OwnerProductProjection }) {
  const connected = context.connectionState === "connected";
  const businessDataUnavailable = isBusinessDataUnavailable(projection.productSummary);
  const dryRunSummary = projection.sourceHealth.runtimeDryRunAudit.summary;
  const dryRunRows = buildDryRunSummaryRows(dryRunSummary);
  const guaranteeRows = Object.entries(projection.noActionGuarantee)
    .filter(([, value]) => value === false)
    .map(([key]) => noActionGuaranteeLabels[key] ?? key);
  const sourceRows = [
    { label: "策略目录", item: projection.sourceHealth.catalog },
    { label: "运行状态", item: projection.sourceHealth.runtime },
    { label: "观察服务", item: projection.sourceHealth.watcher },
    { label: "事实状态", item: projection.sourceHealth.liveFacts },
    { label: "账户资金", item: projection.sourceHealth.accountFunds },
    { label: "订单", item: projection.sourceHealth.orders },
    { label: "持仓", item: projection.sourceHealth.positions },
    { label: "保护", item: projection.sourceHealth.protection },
    { label: "对账", item: projection.sourceHealth.reconciliation },
    { label: "审计记录", item: projection.sourceHealth.operationAudit },
    { label: "审计演练", item: projection.sourceHealth.runtimeDryRunAudit },
    { label: "实盘边界", item: projection.sourceHealth.realOrderReadiness },
    { label: "部署通道", item: projection.sourceHealth.deployChannel },
  ];

  return (
    <PageShell activeView="system">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Card className="rounded-lg shadow-[var(--shadow-panel)]">
          <CardHeader>
            <CardTitle>数据状态</CardTitle>
            <CardDescription>后端连接与业务状态分开显示</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-3">
            <SystemStateCard label="后端连接" tone={connected ? "safe" : "danger"} value={connected ? "已连接" : "不可用"} />
            <SystemStateCard label="业务数据" tone={businessDataUnavailable ? "danger" : "safe"} value={businessDataUnavailable ? "状态证据待刷新" : "正常"} />
            <SystemStateCard label="刷新时间" tone="neutral" value={context.refreshedAt ? new Date(context.refreshedAt).toLocaleTimeString("zh-CN", { hour12: false }) : "加载中"} />
            {sourceRows.map(({ label, item }) => (
              <SystemStateCard key={label} label={label} tone={sourceStatusTone[item.status]} value={item.label} />
            ))}
          </CardContent>
        </Card>
        <Card className="rounded-lg shadow-[var(--shadow-panel)]">
          <CardHeader>
            <CardTitle>只读保证</CardTitle>
            <CardDescription>当前前端只读取状态，不触发交易动作</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-2">
            {guaranteeRows.map((label) => (
              <div className="flex items-center gap-2 text-sm text-[color:var(--status-safe)]" key={label}>
                <CheckCircle2 className="size-4" />
                {label}
              </div>
            ))}
            {dryRunRows.length > 0 ? (
              <>
                <Separator className="my-2" />
                <div className="space-y-3">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="font-semibold">审计演练摘要</div>
                      <div className="text-xs text-muted-foreground">共性执行管道已通过只读演练</div>
                    </div>
                    <StatusBadge tone="safe">无需操作</StatusBadge>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
                    {dryRunRows.map((row) => (
                      <div className="flex items-center gap-2 text-sm" key={row.label}>
                        <CheckCircle2 className="size-4 text-[color:var(--status-safe)]" />
                        <span className="text-muted-foreground">{row.label}</span>
                        <span className="font-semibold">{row.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            ) : null}
            <Separator className="my-2" />
            <div className="text-xs text-muted-foreground">来源：{context.sourceLabel ?? projection.source}</div>
          </CardContent>
        </Card>
      </div>
    </PageShell>
  );
}

function buildDryRunSummaryRows(summary: Record<string, unknown> | undefined) {
  if (!summary) return [];
  const scenarioCount = typeof summary.scenario_count === "number" ? summary.scenario_count : null;
  const rows = [
    scenarioCount !== null ? { label: "演练场景", value: `${scenarioCount} 项通过` } : null,
    summary.shared_runtime_pipeline_checked === true ? { label: "共性管道", value: "已覆盖" } : null,
    summary.common_execution_chain_reuse_checked === true ? { label: "执行复用", value: "已验证" } : null,
    summary.strategygroup_adapter_boundary_checked === true ? { label: "策略适配", value: "边界清晰" } : null,
    summary.strategy_handoff_no_execution_pipeline_fields_checked === true ? { label: "策略输入", value: "未越界" } : null,
    summary.selected_strategygroup_dispatch_guard_checked === true ? { label: "选中范围", value: "已校验" } : null,
    summary.all_selected_strategygroups_reach_finalgate_dispatch_checked === true ? { label: "五组策略", value: "已覆盖" } : null,
    summary.operation_layer_hard_safety_blocker_matrix_checked === true ? { label: "安全矩阵", value: "已覆盖" } : null,
    summary.non_executing_prepare_auto_bridge_checked === true ? { label: "准备链路", value: "已演练" } : null,
    summary.expanded_watcher_scope_execution_guard_checked === true ? { label: "观察范围", value: "已隔离" } : null,
    summary.operation_layer_authorization_chain_guard_checked === true ? { label: "证据接力", value: "已校验" } : null,
    summary.post_submit_closed_loop_evidence_guard_checked === true ? { label: "闭环证据", value: "已校验" } : null,
    summary.operation_layer_submit_result_identity_guard_checked === true ? { label: "提交回执", value: "已校验" } : null,
    summary.post_submit_finalize_result_identity_guard_checked === true ? { label: "收尾回执", value: "已校验" } : null,
    summary.dangerous_effects_absent === true && summary.disabled_smoke_is_real_execution_proof === false
      ? { label: "危险动作", value: "未发生" }
      : null,
  ];
  return rows.filter((row): row is { label: string; value: string } => row !== null);
}
