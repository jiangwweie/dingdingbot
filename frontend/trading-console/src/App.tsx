import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Bell,
  ChevronRight,
  FileText,
  Gauge,
  Grid2X2,
  Layers3,
  LockKeyhole,
  LogOut,
  Moon,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  Sun,
  WalletCards,
} from "lucide-react";
import { getSession, login, logout, readModel } from "./api";
import {
  toAccountRiskViewModel,
  toDashboardViewModel,
  toExceptionsViewModel,
  toOrderLedgerViewModel,
  toStrategyGroupsViewModel,
} from "./adapters";
import {
  dashboardMock,
  accountRiskMock,
  orderLedgerMock,
  strategyGroupsMock,
  exceptionsMock,
} from "./mock";
import type {
  AccountRiskViewModel,
  DashboardViewModel,
  ExceptionsViewModel,
  Health,
  Kpi,
  OrderLedgerViewModel,
  SessionResponse,
  StrategyGroupsViewModel,
  ThemeMode,
  TradingConsoleEnvelope,
} from "./types";

type RouteKey = "dashboard" | "account-risk" | "order-ledger" | "strategy-groups" | "exceptions";

const basePath = import.meta.env.BASE_URL.replace(/\/$/, "");

const routes: Array<{ key: RouteKey; label: string; path: string; icon: typeof Grid2X2 }> = [
  { key: "dashboard", label: "仪表盘", path: "/dashboard", icon: Grid2X2 },
  { key: "account-risk", label: "账户风险", path: "/account-risk", icon: WalletCards },
  { key: "order-ledger", label: "订单台账", path: "/order-ledger", icon: FileText },
  { key: "strategy-groups", label: "策略组", path: "/strategy-groups", icon: Layers3 },
  { key: "exceptions", label: "异常信息", path: "/exceptions", icon: AlertTriangle },
];

const endpointMap: Record<RouteKey, string> = {
  dashboard: "/api/trading-console/dashboard-state",
  "account-risk": "/api/trading-console/account-risk",
  "order-ledger": "/api/trading-console/order-ledger",
  "strategy-groups": "/api/trading-console/strategygroup-runtime-pilot-status",
  exceptions: "/api/trading-console/recovery-exception-state",
};

function routeFromPath(pathname: string): RouteKey {
  const normalized = basePath && pathname.startsWith(`${basePath}/`)
    ? pathname.slice(basePath.length)
    : pathname;
  return routes.find((route) => route.path === normalized)?.key || "dashboard";
}

function routePath(route: { path: string }): string {
  return `${basePath}${route.path}`;
}

function currentTheme(): ThemeMode {
  const stored = localStorage.getItem("brc-theme");
  if (stored === "dark" || stored === "light") return stored;
  return "dark";
}

export function App() {
  const [theme, setTheme] = useState<ThemeMode>(() => currentTheme());
  const [session, setSession] = useState<SessionResponse | null>(null);
  const [route, setRoute] = useState<RouteKey>(() => routeFromPath(window.location.pathname));
  const [loading, setLoading] = useState(true);
  const [apiNotice, setApiNotice] = useState<string>("");
  const [payloads, setPayloads] = useState<Partial<Record<RouteKey, TradingConsoleEnvelope>>>({});

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("brc-theme", theme);
  }, [theme]);

  useEffect(() => {
    const onPop = () => setRoute(routeFromPath(window.location.pathname));
    window.addEventListener("popstate", onPop);
    if (import.meta.env.DEV) {
      setSession({
        authenticated: false,
        username: null,
        expires_at_ms: null,
        current_stage: "local frontend preview",
        next_recommended_step: "Login against backend or use local visual preview.",
        global_planning_stage: "frontend development",
        live_ready: false,
      });
      setLoading(false);
      return () => window.removeEventListener("popstate", onPop);
    }
    void getSession().then((value) => {
      setSession(value);
      setLoading(false);
    });
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  useEffect(() => {
    if (!session?.authenticated) return;
    if (import.meta.env.DEV && session.current_stage === "local frontend preview") {
      setApiNotice("本地视觉预览：页面使用已登记 mock 数据，真实联调与服务器验收将请求后端 API。");
      setPayloads({});
      return;
    }
    let cancelled = false;
    const keys = Object.keys(endpointMap) as RouteKey[];
    Promise.allSettled(keys.map((key) => readModel(endpointMap[key]).then((value) => [key, value] as const)))
      .then((results) => {
        if (cancelled) return;
        const next: Partial<Record<RouteKey, TradingConsoleEnvelope>> = {};
        const failures: string[] = [];
        results.forEach((result) => {
          if (result.status === "fulfilled") {
            next[result.value[0]] = result.value[1];
          } else {
            failures.push(result.reason instanceof Error ? result.reason.message : "read model unavailable");
          }
        });
        setPayloads(next);
        setApiNotice(failures.length ? "部分接口不可用，页面正在使用已登记 mock 字段补足。" : "");
      });
    return () => {
      cancelled = true;
    };
  }, [session?.authenticated]);

  const models = useMemo(() => ({
    dashboard: toDashboardViewModel(payloads.dashboard) || dashboardMock,
    accountRisk: toAccountRiskViewModel(payloads["account-risk"]) || accountRiskMock,
    orderLedger: toOrderLedgerViewModel(payloads["order-ledger"]) || orderLedgerMock,
    strategyGroups: toStrategyGroupsViewModel(payloads["strategy-groups"]) || strategyGroupsMock,
    exceptions: toExceptionsViewModel(payloads.exceptions) || exceptionsMock,
  }), [payloads]);

  const navigate = (next: RouteKey) => {
    const target = routes.find((item) => item.key === next);
    if (!target) return;
    window.history.pushState({}, "", routePath(target));
    setRoute(next);
  };

  if (loading) return <div className="boot-screen">正在装载交易控制台</div>;

  if (!session?.authenticated) {
    return (
      <LoginPage
        theme={theme}
        onThemeChange={() => setTheme(theme === "dark" ? "light" : "dark")}
        onLoggedIn={setSession}
      />
    );
  }

  return (
    <div className="app-shell">
      <Sidebar
        active={route}
        username={session.username || "quant_master"}
        theme={theme}
        onThemeChange={() => setTheme(theme === "dark" ? "light" : "dark")}
        onNavigate={navigate}
        onLogout={async () => setSession(await logout())}
      />
      <main className="workspace">
        <Header topStatus={models.dashboard.topStatus} title={pageTitle(route)} subtitle={pageSubtitle(route)} />
        {apiNotice ? <div className="notice">{apiNotice}</div> : null}
        {route === "dashboard" ? <DashboardPage model={models.dashboard} /> : null}
        {route === "account-risk" ? <AccountRiskPage model={models.accountRisk} /> : null}
        {route === "order-ledger" ? <OrderLedgerPage model={models.orderLedger} /> : null}
        {route === "strategy-groups" ? <StrategyGroupsPage model={models.strategyGroups} /> : null}
        {route === "exceptions" ? <ExceptionsPage model={models.exceptions} /> : null}
      </main>
    </div>
  );
}

function pageTitle(route: RouteKey): string {
  if (route === "account-risk") return "账户风险";
  if (route === "order-ledger") return "订单台账";
  if (route === "strategy-groups") return "策略组";
  if (route === "exceptions") return "异常信息";
  return "交易控制台";
}

function pageSubtitle(route: RouteKey): string {
  if (route === "account-risk") return "资金、仓位、杠杆与保护的全局视图";
  if (route === "order-ledger") return "订单、保护单与执行结果的审计视图";
  if (route === "strategy-groups") return "策略语义、支持范围与运行状态";
  if (route === "exceptions") return "告警、恢复、对账与待处理事项";
  return "有界实盘 · 风险可视 · 审计友好";
}

function LoginPage({
  theme,
  onThemeChange,
  onLoggedIn,
}: {
  theme: ThemeMode;
  onThemeChange: () => void;
  onLoggedIn: (session: SessionResponse) => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const next = await login(username, password, totpCode);
      onLoggedIn(next);
      window.history.replaceState({}, "", routePath(routes[0]));
    } catch {
      setError("登录失败：用户名、密码或认证器验证码无效。");
    } finally {
      setBusy(false);
    }
  };

  const useDevPreview = () => {
    if (!import.meta.env.DEV) return;
    onLoggedIn({
      authenticated: true,
      username: "quant_master",
      expires_at_ms: Date.now() + 3600_000,
      current_stage: "local frontend preview",
      next_recommended_step: "Visual verification only.",
      global_planning_stage: "frontend development",
      live_ready: false,
    });
  };

  return (
    <div className="login-shell">
      <button className="theme-float" type="button" onClick={onThemeChange} aria-label="切换主题">
        {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
      </button>
      <section className="login-panel">
        <div className="brand-mark"><Layers3 size={34} /></div>
        <div>
          <h1>交易控制台</h1>
          <p>使用操作员账号与 Google Authenticator 动态验证码登录。</p>
        </div>
        <form onSubmit={submit} className="login-form">
          <label>
            <span>用户名</span>
            <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
          </label>
          <label>
            <span>密码</span>
            <input value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete="current-password" />
          </label>
          <label>
            <span>认证器验证码</span>
            <input
              value={totpCode}
              onChange={(event) => setTotpCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="6 位数字"
            />
          </label>
          {error ? <div className="login-error">{error}</div> : null}
          <button className="primary-button" disabled={busy || !username || !password || totpCode.length !== 6} type="submit">
            <LockKeyhole size={16} /> {busy ? "验证中" : "安全登录"}
          </button>
          {import.meta.env.DEV ? (
            <button className="ghost-button" type="button" onClick={useDevPreview}>
              本地视觉预览
            </button>
          ) : null}
        </form>
      </section>
    </div>
  );
}

function Sidebar({
  active,
  username,
  theme,
  onThemeChange,
  onNavigate,
  onLogout,
}: {
  active: RouteKey;
  username: string;
  theme: ThemeMode;
  onThemeChange: () => void;
  onNavigate: (route: RouteKey) => void;
  onLogout: () => void;
}) {
  return (
    <aside className="sidebar">
      <div className="logo"><Layers3 /></div>
      <nav className="nav-list">
        {routes.map((route) => {
          const Icon = route.icon;
          return (
            <button className={route.key === active ? "nav-item active" : "nav-item"} key={route.key} onClick={() => onNavigate(route.key)}>
              <Icon size={19} />
              <span>{route.label}</span>
            </button>
          );
        })}
      </nav>
      <div className="sidebar-footer">
        <div className="account-chip">
          <div className="avatar" />
          <div><strong>{username}</strong><span>主账户</span></div>
        </div>
        <div className="footer-actions">
          <button onClick={onThemeChange} aria-label="切换主题">{theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}</button>
          <button aria-label="设置"><Settings size={18} /></button>
          <button onClick={onLogout} aria-label="退出"><LogOut size={18} /></button>
        </div>
      </div>
    </aside>
  );
}

function Header({ topStatus, title, subtitle }: { topStatus: DashboardViewModel["topStatus"]; title: string; subtitle: string }) {
  return (
    <header className="topbar">
      <div>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      <div className="topbar-actions">
        <StatusPill label="系统正常" tone={topStatus.system} icon={<RefreshCw size={15} />} />
        <StatusPill label="账户正常" tone={topStatus.account} icon={<Gauge size={15} />} />
        <StatusPill label="执行权限开启" tone={topStatus.execution} icon={<ShieldCheck size={15} />} />
        <span className="clock">{topStatus.clock}</span>
        <span className="bell"><Bell size={20} /><b>{topStatus.notificationCount}</b></span>
      </div>
    </header>
  );
}

function StatusPill({ label, tone, icon }: { label: string; tone: Health; icon: React.ReactNode }) {
  return <span className={`status-pill ${tone}`}>{icon}{label}</span>;
}

function KpiGrid({ items }: { items: Kpi[] }) {
  return (
    <div className="kpi-grid">
      {items.map((item) => (
        <article className={`panel kpi ${item.tone}`} key={item.label}>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
          <small>{item.sublabel}</small>
          {item.sparkline ? <Sparkline values={item.sparkline} tone={item.tone} /> : <div className="kpi-orb" />}
        </article>
      ))}
    </div>
  );
}

function Sparkline({ values, tone = "normal" }: { values: number[]; tone?: Health }) {
  const width = 120;
  const height = 42;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const points = values.map((value, index) => {
    const x = (index / Math.max(values.length - 1, 1)) * width;
    const y = height - ((value - min) / Math.max(max - min, 1)) * (height - 6) - 3;
    return `${x},${y}`;
  }).join(" ");
  return (
    <svg className={`sparkline ${tone}`} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
      <polyline points={points} fill="none" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function AreaChart({ values }: { values: number[] }) {
  const width = 900;
  const height = 230;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const points = values.map((value, index) => {
    const x = (index / Math.max(values.length - 1, 1)) * width;
    const y = height - ((value - min) / Math.max(max - min, 1)) * (height - 18) - 10;
    return `${x},${y}`;
  }).join(" ");
  return (
    <svg className="area-chart" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
      <defs>
        <linearGradient id="chartFill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0.42" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0.04" />
        </linearGradient>
      </defs>
      <polygon points={`0,${height} ${points} ${width},${height}`} fill="url(#chartFill)" />
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="3" />
    </svg>
  );
}

function GaugeRing({ value, tone = "normal" }: { value: number; tone?: Health }) {
  return (
    <div className={`gauge-ring ${tone}`} style={{ "--value": `${value * 3.6}deg` } as React.CSSProperties}>
      <strong>{value}%</strong>
    </div>
  );
}

function DashboardPage({ model }: { model: DashboardViewModel }) {
  return (
    <div className="page-grid">
      <KpiGrid items={model.kpis} />
      <section className="panel wide">
        <h2>系统总览</h2>
        <div className="overview-row">
          {model.overview.map((item) => <MetricBlock key={item.label} {...item} />)}
        </div>
        <div className="chart-title"><span>账户权益曲线 (USDT)</span><b>358,246.37</b><em>今日 +2.35%</em></div>
        <AreaChart values={model.equity} />
      </section>
      <section className="panel side-list">
        <PanelHeader title="最近实盘行动" />
        {model.recentActions.map((item) => (
          <div className="action-row" key={`${item.time}${item.symbol}`}>
            <span>{item.time}</span><strong>{item.symbol}</strong><b>{item.action}</b><em>{item.delta}</em>
          </div>
        ))}
      </section>
      <section className="panel"><PanelHeader title="操作驾驶舱" /><div className="control-strip"><MetricBlock label="自主状态" value="全自治运行中" hint="人工干预：关闭" tone="normal" /><MetricBlock label="最终门控" value="就绪" hint="所有检查通过" tone="normal" /><MetricBlock label="复核 backlog" value="23" hint="待复核项" tone="warning" /></div></section>
      <section className="panel"><PanelHeader title="风险边界" /><div className="gauge-grid">{model.riskGauges.map((g) => <div key={g.label}><GaugeRing value={g.value} tone={g.tone} /><span>{g.label}</span><small>{g.hint}</small></div>)}</div></section>
      <section className="panel side-list"><PanelHeader title="告警摘要" />{model.alerts.map((alert) => <div className="alert-row" key={alert.text}><b className={`level ${alert.level}`}>{alert.level}</b><span>{alert.text}</span><time>{alert.time}</time></div>)}</section>
      <section className="panel side-list"><PanelHeader title="市场观察" />{model.markets.map((market) => <div className="market-row" key={market.symbol}><strong>{market.symbol}</strong><span>{market.price}</span><b className={market.change.startsWith("+") ? "positive" : "negative"}>{market.change}</b><Sparkline values={market.trend} tone={market.change.startsWith("+") ? "normal" : "danger"} /></div>)}</section>
    </div>
  );
}

function AccountRiskPage({ model }: { model: AccountRiskViewModel }) {
  return (
    <div className="page-grid">
      <KpiGrid items={model.kpis} />
      <section className="panel wide"><PanelHeader title="风险概览" /><div className="split-charts"><div><div className="chart-title"><span>账户净值趋势 (USDT)</span><em>今日 +2.35%</em></div><AreaChart values={model.equity} /></div><div><div className="chart-title"><span>回撤与敞口趋势</span></div><AreaChart values={model.drawdown} /></div></div></section>
      <section className="panel side-list"><PanelHeader title="仓位风险分布" />{model.positions.map((item) => <div className="risk-row" key={item.symbol}><strong>{item.symbol}</strong><b className={item.direction === "多" ? "positive" : "negative"}>{item.direction}</b><span>{item.exposure}</span><span>{item.leverage}</span><Progress value={Number.parseFloat(item.concentration)} tone={item.tone} /></div>)}</section>
      <section className="panel"><PanelHeader title="边界与预算" />{model.budgetRows.map((row) => <div className="kv-row" key={row.label}><span>{row.label}</span><strong>{row.value}</strong><em>{row.hint}</em></div>)}</section>
      <section className="panel"><PanelHeader title="保护健康" />{model.protectionRows.map((row) => <div className="kv-row" key={row.label}><span>{row.label}</span><strong className={row.tone}>{row.value}</strong></div>)}</section>
      <section className="panel side-list"><PanelHeader title="风险告警" />{model.alerts.map((alert) => <div className="alert-row" key={alert.text}><b className={`level ${alert.level}`}>{alert.level}</b><span>{alert.text}</span><time>{alert.time}</time></div>)}</section>
    </div>
  );
}

function OrderLedgerPage({ model }: { model: OrderLedgerViewModel }) {
  return (
    <div className="ledger-layout">
      <div className="ledger-main">
        <KpiGrid items={model.kpis} />
        <section className="panel table-panel">
          <div className="tabs"><b>全部</b><span>开仓</span><span>平仓</span><span>保护单</span><span>异常</span></div>
          <div className="filters"><Search size={16} /><span>搜索 订单ID / 交易对 / 策略组</span><button>导出</button><button>刷新</button></div>
          <table>
            <thead><tr><th>时间</th><th>订单ID</th><th>交易对</th><th>方向</th><th>类型</th><th>价格</th><th>数量</th><th>名义价值</th><th>状态</th><th>保护</th><th>策略组</th><th>执行通道</th></tr></thead>
            <tbody>{model.orders.map((order, index) => <tr className={index === 0 ? "selected" : ""} key={order.id}><td>{order.time}</td><td>{order.id}</td><td>{order.symbol}</td><td className={order.side === "买入" ? "positive" : "negative"}>{order.side}</td><td>{order.type}</td><td>{order.price}</td><td>{order.qty}</td><td>{order.notional}</td><td><Badge tone={order.status.includes("拒") ? "danger" : "normal"}>{order.status}</Badge></td><td>{order.protected ? "是" : "否"}</td><td>{order.strategy}</td><td>{order.venue}</td></tr>)}</tbody>
          </table>
        </section>
        <section className="panel"><PanelHeader title="执行概览" /><div className="mini-chart-grid">{model.executionCharts.map((chart) => <div key={chart.label}><span>{chart.label}</span><strong>{chart.value}</strong><Sparkline values={chart.series} tone={chart.tone} /></div>)}<div>{model.statusDistribution.map((item) => <div className="distribution" key={item.label}><Badge tone={item.tone}>{item.label}</Badge><span>{item.value}</span><em>{item.pct}</em></div>)}</div></div></section>
      </div>
      <aside className="panel detail-panel"><PanelHeader title="订单详情" /><strong>{model.selected.id}</strong><p>{model.selected.symbol} · {model.selected.side} · {model.selected.venue}</p><div className="timeline">{model.timeline.map((item) => <div className={`timeline-item ${item.tone}`} key={item.title}><b>{item.title}</b><time>{item.time}</time><span>{item.meta}</span></div>)}</div></aside>
    </div>
  );
}

function StrategyGroupsPage({ model }: { model: StrategyGroupsViewModel }) {
  return (
    <div className="strategy-layout">
      <div className="strategy-main">
        <KpiGrid items={model.kpis} />
        <div className="strategy-card-grid">{model.strategies.map((item) => <article className={`panel strategy-card ${item.id === model.selected.id ? "selected-card" : ""}`} key={item.id}><div className="card-title"><strong>{item.id}</strong><Badge tone={item.tone}>{item.state}</Badge><Badge tone={item.tone}>{item.actionability}</Badge></div><div className="field-grid"><span>目的</span><b>{item.purpose}</b><span>方向</span><b>{item.direction}</b><span>支持标的</span><b>{item.symbols}</b></div><div className="card-foot"><span>Fresh 事件 <b>{item.fresh}</b></span><span>运行健康 <b>{item.health}</b></span><span>今日动作 <b>{item.actionsToday}</b></span></div></article>)}</div>
        <section className="panel"><PanelHeader title="候选池 / Candidate Pool" /><table><thead><tr><th>机会</th><th>触发时间</th><th>标的</th><th>策略建议</th><th>强度</th><th>晋升路径</th></tr></thead><tbody>{model.candidatePool.map((row) => <tr key={row.event}><td>{row.event}</td><td>{row.age}</td><td>{row.symbol}</td><td>{row.strategy}</td><td><Progress value={row.strength * 100} tone="normal" /></td><td><button className="small-action">{row.action}</button></td></tr>)}</tbody></table></section>
      </div>
      <aside className="strategy-side">
        <section className="panel detail-panel"><PanelHeader title={model.selected.id} /><div className="field-grid"><span>方向立场</span><b>{model.selected.direction}</b><span>支持标的</span><b>{model.selected.symbols}</b><span>时间框架</span><b>5m / 15m / 1h</b><span>适用市场</span><b>现货，永续合约</b></div><PanelHeader title="Fresh Signal 事件" /><div className="signal-line">突破上轨 + 量能放大 <b>BTCUSDT · 5m</b><em>强度 0.87</em></div></section>
        <section className="panel"><PanelHeader title="最近动作" />{model.recentActions.map((row) => <div className="action-row" key={`${row.time}${row.symbol}`}><span>{row.time}</span><strong>{row.symbol}</strong><b>{row.action}</b><em>{row.result}</em></div>)}</section>
        <section className="panel"><PanelHeader title="策略组健康分布" />{model.healthDistribution.map((item) => <div className="distribution" key={item.label}><Badge tone={item.tone}>{item.label}</Badge><span>{item.count}</span><em>{item.pct}</em></div>)}</section>
      </aside>
    </div>
  );
}

function ExceptionsPage({ model }: { model: ExceptionsViewModel }) {
  return (
    <div className="exceptions-layout">
      <div className="exceptions-main">
        <KpiGrid items={model.kpis} />
        <section className="panel exception-list"><PanelHeader title="异常列表" />{model.exceptions.map((item) => <div className={`exception-row ${item.id === model.selected.id ? "selected" : ""}`} key={item.id}><Badge tone={item.tone}>{item.priority}</Badge><strong>{item.title}<span>ID: {item.id}</span></strong><b>{item.target}</b><time>{item.time}</time><em>{item.state}</em></div>)}</section>
      </div>
      <div className="exceptions-detail">
        <section className="panel"><PanelHeader title="恢复工作台" /><h3>{model.selected.id} {model.selected.title}</h3><div className="stepper">{model.steps.map((step, index) => <div className={`step ${step.state}`} key={step.label}><b>{index + 1}</b><span>{step.label}</span></div>)}</div><div className="warning-box">系统检测到持仓未配置止损保护，存在潜在亏损扩大风险。</div><button className="primary-button">开始诊断</button></section>
        <section className="panel"><PanelHeader title="异常影响评估" />{model.impact.map((item) => <div className="kv-row" key={item.label}><span>{item.label}</span><strong className={item.tone}>{item.value}</strong></div>)}</section>
      </div>
      <aside className="exceptions-side"><section className="panel"><PanelHeader title="对账与保护健康" />{model.health.map((item) => <div className="kv-row" key={item.label}><span>{item.label}</span><strong className={item.tone}>{item.value}</strong></div>)}</section><section className="panel"><PanelHeader title="审计与备注" />{model.audit.map((row) => <div className="audit-row" key={`${row.time}${row.text}`}><time>{row.time}</time><span>{row.text}</span><em>{row.author}</em></div>)}</section></aside>
    </div>
  );
}

function PanelHeader({ title }: { title: string }) {
  return <div className="panel-header"><h2>{title}</h2><button>更多 <ChevronRight size={14} /></button></div>;
}

function MetricBlock({ label, value, hint, tone }: { label: string; value: string; hint: string; tone: Health }) {
  return <div className={`metric ${tone}`}><span>{label}</span><strong>{value}</strong><small>{hint}</small></div>;
}

function Badge({ children, tone }: { children: React.ReactNode; tone: Health }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

function Progress({ value, tone }: { value: number; tone: Health }) {
  return <span className="progress"><i className={tone} style={{ width: `${Math.min(100, Math.max(4, value))}%` }} /></span>;
}
