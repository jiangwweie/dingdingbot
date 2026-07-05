import type {
  AccountRiskViewModel,
  DashboardViewModel,
  ExceptionsViewModel,
  OrderLedgerViewModel,
  StrategyGroupsViewModel,
  TopStatus,
} from "./types";

export const topStatus: TopStatus = {
  system: "normal",
  account: "normal",
  execution: "normal",
  clock: "10:24:36 (UTC+8)",
  notificationCount: 3,
};

export const dashboardMock: DashboardViewModel = {
  topStatus,
  kpis: [
    { label: "生效策略", value: "12 个", sublabel: "运行中 12  暂停 0  停止 0", tone: "normal", trend: "+7.31%", sparkline: [42, 44, 47, 51, 49, 55, 58], source: "composed" },
    { label: "持仓订单数", value: "38 个", sublabel: "多 24  空 14  挂单 6", tone: "normal", sparkline: [30, 36, 34, 42, 46, 45, 52], source: "direct" },
    { label: "持仓盈亏", value: "+8,246.37 USDT", sublabel: "今日 +2.35%    累计 +18.72%", tone: "normal", sparkline: [22, 28, 31, 36, 34, 42, 49], source: "direct" },
    { label: "市场基本面", value: "52/100", sublabel: "资金费率 0.0100%  溢价 +0.32%", tone: "warning", sparkline: [50, 51, 48, 54, 55, 53, 52], source: "mock-required" },
  ],
  overview: [
    { label: "运行时长", value: "7 天 14:23:11", hint: "自 2025-05-06 19:01:25 启动", tone: "normal" },
    { label: "活跃承载", value: "4 / 4", hint: "Binance OKX Bybit Gate.io", tone: "normal" },
    { label: "策略组", value: "5 / 6", hint: "主力趋势、套利捕捉、高频择时", tone: "normal" },
    { label: "信号新鲜度", value: "1.2 秒", hint: "优秀", tone: "normal" },
  ],
  equity: [322, 326, 324, 331, 333, 330, 337, 339, 336, 342, 345, 348, 351, 350, 356, 359, 358, 362],
  recentActions: [
    { time: "10:23:41", symbol: "BTCUSDT 永续", action: "开多", result: "Binance", delta: "+0.48 BTC" },
    { time: "10:22:17", symbol: "ETHUSDT 永续", action: "减仓", result: "OKX", delta: "-2.00 ETH" },
    { time: "10:19:03", symbol: "SOLUSDT 永续", action: "平仓", result: "Bybit", delta: "+1.35 SOL" },
    { time: "10:15:44", symbol: "ARBUSDT 永续", action: "开空", result: "Gate.io", delta: "-5,000 ARB" },
  ],
  alerts: [
    { level: "高", text: "BTC 资金费率 0.020% 超阈值", time: "10:18:05" },
    { level: "中", text: "ETH 波动率 3H 异常上升", time: "10:12:44" },
    { level: "低", text: "API 延迟 Bybit 185ms", time: "10:02:31" },
  ],
  markets: [
    { symbol: "BTCUSDT", price: "65,218.4", change: "+1.28%", trend: [34, 35, 33, 39, 42, 40, 45] },
    { symbol: "ETHUSDT", price: "3,142.7", change: "+1.85%", trend: [26, 28, 30, 29, 34, 36, 41] },
    { symbol: "SOLUSDT", price: "152.36", change: "-0.72%", trend: [40, 37, 34, 31, 35, 32, 30] },
    { symbol: "BNBUSDT", price: "598.2", change: "+0.96%", trend: [30, 32, 31, 34, 37, 38, 42] },
  ],
  riskGauges: [
    { label: "预算使用率", value: 63, hint: "63,000 / 100,000", tone: "normal" },
    { label: "杠杆使用率", value: 42, hint: "4.2x / 10x", tone: "normal" },
    { label: "最大并发仓位", value: 38, hint: "38 / 100", tone: "warning" },
    { label: "保护覆盖率", value: 87, hint: "良好", tone: "warning" },
  ],
};

export const accountRiskMock: AccountRiskViewModel = {
  topStatus,
  kpis: [
    { label: "账户净值 (USDT)", value: "358,246.37", sublabel: "今日 +2.35%    累计 +18.72%", tone: "normal", sparkline: [36, 38, 37, 42, 43, 46, 49], source: "direct" },
    { label: "可用保证金 (USDT)", value: "126,842.19", sublabel: "占净值 35.41%", tone: "normal", source: "direct" },
    { label: "风险率", value: "42%", sublabel: "等级 正常", tone: "normal", source: "derived" },
    { label: "保护覆盖率", value: "87%", sublabel: "等级 良好", tone: "warning", source: "derived" },
  ],
  equity: dashboardMock.equity,
  drawdown: [5, 8, 9, 14, 18, 20, 23, 25, 24, 25, 26, 26],
  positions: [
    { symbol: "BTC/USDT", direction: "多", exposure: "265,218.4", leverage: "3.12x", concentration: "38.5%", tone: "danger" },
    { symbol: "ETH/USDT", direction: "多", exposure: "89,672.1", leverage: "2.34x", concentration: "13.0%", tone: "danger" },
    { symbol: "SOL/USDT", direction: "空", exposure: "32,450.6", leverage: "1.85x", concentration: "4.7%", tone: "warning" },
    { symbol: "BNB/USDT", direction: "多", exposure: "21,880.2", leverage: "1.92x", concentration: "3.2%", tone: "normal" },
    { symbol: "ARB/USDT", direction: "多", exposure: "12,304.5", leverage: "1.41x", concentration: "1.8%", tone: "normal" },
  ],
  budgetRows: [
    { label: "总预算 (USDT)", value: "500,000.00" },
    { label: "已预留预算", value: "60,000.00", hint: "12.0%" },
    { label: "已使用预算", value: "421,525.80", hint: "84.3%" },
    { label: "最大杠杆 (全局)", value: "5.00x" },
    { label: "最大同时持仓数", value: "20" },
    { label: "当前余量", value: "78,474.20", hint: "15.7%" },
  ],
  protectionRows: [
    { label: "TP/SL 覆盖率", value: "98 / 100 (98%)", tone: "normal" },
    { label: "孤儿单检查", value: "0", tone: "normal" },
    { label: "保护延迟 (中位数)", value: "183ms", tone: "normal" },
    { label: "最后对账结果", value: "成功", tone: "normal" },
    { label: "最后对账时间", value: "2025-05-16 10:22:44", tone: "normal" },
  ],
  alerts: [
    { level: "中", text: "ETH/USDT 杠杆接近上限 (2.34x / 3.00x)", time: "10:23:41" },
    { level: "高", text: "BTC/USDT 集中度偏高 (38.5% > 35%)", time: "10:22:17" },
    { level: "中", text: "SOL/USDT 回撤接近阈值", time: "10:21:05" },
    { level: "低", text: "保护延迟轻微上升", time: "10:18:32" },
  ],
};

export const orderLedgerMock: OrderLedgerViewModel = {
  topStatus,
  kpis: [
    { label: "今日订单", value: "1,248", sublabel: "昨日 1,163    +7.31%", tone: "normal", source: "direct" },
    { label: "成交率", value: "93.42%", sublabel: "昨日 91.18%    +2.24pp", tone: "normal", source: "derived" },
    { label: "挂单数", value: "186", sublabel: "昨日 172    +14", tone: "normal", source: "direct" },
    { label: "异常订单", value: "7", sublabel: "昨日 5    +2", tone: "danger", source: "composed" },
  ],
  orders: [
    { id: "OID-20250506-102231-001", time: "10:22:31", symbol: "BTCUSDT", side: "买入", type: "开仓限价", price: "65,218.4", qty: "0.200", notional: "13,043.68", status: "完全成交", protected: true, strategy: "趋势突破_01", venue: "Binance" },
    { id: "OID-20250506-102109-015", time: "10:21:09", symbol: "ETHUSDT", side: "卖出", type: "平仓限价", price: "3,142.7", qty: "1.600", notional: "5,028.32", status: "完全成交", protected: true, strategy: "均值回归_02", venue: "OKX" },
    { id: "OID-20250506-102054-008", time: "10:20:54", symbol: "SOLUSDT", side: "买入", type: "保护止损", price: "152.36", qty: "50.00", notional: "7,618.00", status: "已触发", protected: true, strategy: "动量追踪_03", venue: "Bybit" },
    { id: "OID-20250506-101933-003", time: "10:19:33", symbol: "ETHUSDT", side: "买入", type: "开仓限价", price: "3,138.2", qty: "0.800", notional: "2,510.56", status: "部分成交", protected: false, strategy: "趋势突破_01", venue: "Binance" },
    { id: "OID-20250506-101758-011", time: "10:17:58", symbol: "BTCUSDT", side: "卖出", type: "平仓市价", price: "-", qty: "0.150", notional: "9,782.15", status: "拒单", protected: false, strategy: "波段择时_01", venue: "Binance" },
  ],
  selected: {} as never,
  timeline: [
    { title: "信号事件", time: "10:21:45", meta: "趋势突破_01 SIG-20250506-102145-887 强度 82/100", tone: "normal" },
    { title: "候选提升", time: "10:21:46", meta: "突破确认 & 量能放大，预期胜率 63%", tone: "normal" },
    { title: "动作票据", time: "10:21:47", meta: "买入 / 开仓限价，有效期 GTC", tone: "normal" },
    { title: "最终闸口结果", time: "10:22:20", meta: "风控评估、风险敞口、限额校验通过", tone: "normal" },
    { title: "执行结果", time: "10:22:31", meta: "完全成交 0.200 BTC，Binance", tone: "normal" },
    { title: "保护单状态", time: "10:22:32", meta: "止损 / 止盈 OCO 已创建", tone: "warning" },
  ],
  executionCharts: [
    { label: "执行延迟 (p50)", value: "186ms", series: [180, 220, 360, 420, 390, 510, 830, 610], tone: "normal" },
    { label: "成交质量", value: "-1.7 bps", series: [2, -1, 1, -2, -1, 0, 3, -2], tone: "normal" },
    { label: "成功率", value: "96.32%", series: [94, 95, 96, 97, 96, 96, 97, 96], tone: "normal" },
  ],
  statusDistribution: [
    { label: "完全成交", value: 1002, pct: "80.4%", tone: "normal" },
    { label: "部分成交", value: 112, pct: "8.97%", tone: "warning" },
    { label: "挂单中", value: 86, pct: "6.90%", tone: "muted" },
    { label: "拒单", value: 13, pct: "1.04%", tone: "danger" },
  ],
};
orderLedgerMock.selected = orderLedgerMock.orders[0];

export const strategyGroupsMock: StrategyGroupsViewModel = {
  topStatus,
  kpis: [
    { label: "策略组总数", value: "5", sublabel: "较昨日 +1", tone: "normal", source: "direct" },
    { label: "运行中", value: "3", sublabel: "60%", tone: "normal", source: "derived" },
    { label: "观察中", value: "1", sublabel: "20%", tone: "muted", source: "derived" },
    { label: "暂停中", value: "1", sublabel: "20%", tone: "warning", source: "derived" },
  ],
  strategies: [
    { id: "CPM-RO-001", state: "运行中", actionability: "可执行", purpose: "趋势跟随 / 突破动量", direction: "仅做多", symbols: "BTCUSDT, ETHUSDT", fresh: "2 分钟前", health: "98 / 100", actionsToday: 8, tone: "normal" },
    { id: "MPG-001", state: "运行中", actionability: "可执行", purpose: "均值回归 / 价格偏离修复", direction: "双向", symbols: "BTCUSDT, ETHUSDT, SOLUSDT", fresh: "5 分钟前", health: "94 / 100", actionsToday: 12, tone: "normal" },
    { id: "MI-001", state: "观察中", actionability: "观察", purpose: "微结构不平衡捕捉", direction: "双向", symbols: "BTCUSDT, SOLUSDT", fresh: "8 分钟前", health: "79 / 100", actionsToday: 0, tone: "muted" },
    { id: "SOR-001", state: "运行中", actionability: "可执行", purpose: "智能委托路由 / 最优成交", direction: "双向", symbols: "BTCUSDT, ETHUSDT, SOLUSDT", fresh: "1 分钟前", health: "96 / 100", actionsToday: 236, tone: "normal" },
    { id: "BRF2-001", state: "暂停中", actionability: "暂停", purpose: "事件驱动 / 基本面催化", direction: "仅做多", symbols: "BTCUSDT", fresh: "-", health: "-", actionsToday: 0, tone: "warning" },
  ],
  selected: {} as never,
  candidatePool: [
    { event: "突破上轨 + 量能放大", age: "2 分钟前", symbol: "BTCUSDT", strategy: "CPM-RO-001", strength: 0.87, action: "晋升为动作" },
    { event: "均值偏离 -1.8σ", age: "4 分钟前", symbol: "ETHUSDT", strategy: "MPG-001", strength: 0.63, action: "晋升为动作" },
    { event: "资金费率突变", age: "7 分钟前", symbol: "SOLUSDT", strategy: "MI-001", strength: 0.58, action: "加入观察" },
  ],
  eventStatus: [
    { label: "Fresh Signal", count: 7, tone: "normal" },
    { label: "动作进行中", count: 18, tone: "muted" },
    { label: "冷却中", count: 4, tone: "warning" },
    { label: "今日已完成", count: 56, tone: "normal" },
  ],
  recentActions: [
    { time: "10:21:14", symbol: "BTCUSDT", direction: "做多", action: "开仓", strength: "0.89", result: "已成交" },
    { time: "10:17:03", symbol: "ETHUSDT", direction: "做多", action: "加仓", strength: "0.76", result: "已成交" },
    { time: "10:13:28", symbol: "BTCUSDT", direction: "做多", action: "止盈", strength: "0.72", result: "已成交" },
  ],
  healthDistribution: [
    { label: "优秀 (90-100)", count: 2, pct: "40%", tone: "normal" },
    { label: "良好 (70-90)", count: 2, pct: "40%", tone: "muted" },
    { label: "一般 (50-70)", count: 1, pct: "20%", tone: "warning" },
    { label: "较差 (<50)", count: 0, pct: "0%", tone: "danger" },
  ],
};
strategyGroupsMock.selected = strategyGroupsMock.strategies[0];

export const exceptionsMock: ExceptionsViewModel = {
  topStatus,
  kpis: [
    { label: "当前异常", value: "7", sublabel: "较昨日 +2", tone: "warning", sparkline: [4, 4, 5, 5, 6, 6, 7], source: "direct" },
    { label: "高优先级", value: "2", sublabel: "占比 28.6%", tone: "danger", sparkline: [1, 1, 2, 2, 2, 2, 2], source: "derived" },
    { label: "待恢复项", value: "4", sublabel: "较昨日 -1", tone: "muted", sparkline: [6, 5, 5, 4, 5, 4, 4], source: "direct" },
    { label: "最近 24H 事件", value: "23", sublabel: "较昨日 +5", tone: "normal", sparkline: [16, 17, 18, 17, 20, 21, 23], source: "composed" },
  ],
  exceptions: [
    { id: "EX-2025-05-16-001", priority: "高", title: "保护缺失：BTCUSDT 多单无止损", target: "BTCUSDT", time: "10:24:12", state: "待恢复", tone: "danger" },
    { id: "EX-2025-05-16-002", priority: "高", title: "对账不一致：ETHUSDT 持仓差异", target: "ETHUSDT", time: "10:21:03", state: "待处理", tone: "danger" },
    { id: "EX-2025-05-16-003", priority: "中", title: "信号陈旧：SOLUSDT 信号延迟", target: "SOLUSDT", time: "10:18:55", state: "处理中", tone: "warning" },
    { id: "EX-2025-05-16-004", priority: "中", title: "API 延迟尖峰：Binance 期货", target: "Binance", time: "10:16:37", state: "待处理", tone: "warning" },
    { id: "EX-2025-05-16-005", priority: "低", title: "订单状态不一致：ARBUSDT", target: "ARBUSDT", time: "10:12:41", state: "待确认", tone: "muted" },
  ],
  selected: {} as never,
  steps: [
    { label: "检测", state: "active" },
    { label: "诊断", state: "pending" },
    { label: "确认", state: "pending" },
    { label: "恢复", state: "pending" },
    { label: "复盘", state: "pending" },
  ],
  impact: [
    { label: "风险敞口 (USDT)", value: "42,816.37", tone: "danger" },
    { label: "潜在最大亏损 (USDT)", value: "8,372.11", tone: "danger" },
    { label: "影响账户", value: "趋势跟踪_01", tone: "muted" },
    { label: "影响账长", value: "主账户", tone: "muted" },
    { label: "持续时间", value: "00:05:23", tone: "warning" },
  ],
  health: [
    { label: "对账状态", value: "部分不一致", tone: "warning" },
    { label: "孤儿保护检查", value: "未发现孤儿保护", tone: "normal" },
    { label: "未匹配订单数", value: "3", tone: "warning" },
    { label: "上次成功恢复", value: "今天 09:41:18", tone: "normal" },
  ],
  audit: [
    { time: "10:24:12", text: "系统检测到保护缺失", author: "系统" },
    { time: "10:24:13", text: "触发告警，优先级设为高", author: "系统" },
    { time: "10:24:20", text: "通知渠道推送完成", author: "系统" },
    { time: "10:24:30", text: "量化团队已确认，准备诊断", author: "quant_master" },
  ],
};
exceptionsMock.selected = exceptionsMock.exceptions[0];

