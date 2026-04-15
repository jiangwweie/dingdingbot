/**
 * Backtest Report Types
 *
 * 回测报告相关类型定义，与后端 /api/v3/backtest/reports 端点对齐
 */

/**
 * 回测报告摘要信息
 */
export interface BacktestReportSummary {
  /** 报告 ID */
  id: string;
  /** 策略 ID */
  strategy_id: string;
  /** 策略名称 */
  strategy_name: string;
  /** 策略版本 */
  strategy_version: string;
  /** 交易对 */
  symbol: string;
  /** 时间周期 */
  timeframe: string;
  /** 回测开始时间戳（毫秒） */
  backtest_start: number;
  /** 回测结束时间戳（毫秒） */
  backtest_end: number;
  /** 创建时间戳（毫秒） */
  created_at: number;
  /** 总收益率（Decimal 字符串，如 "0.0523" 表示 5.23%） */
  total_return: string;
  /** 总交易次数 */
  total_trades: number;
  /** 胜率（Decimal 字符串，如 "0.6500" 表示 65%） */
  win_rate: string;
  /** 总盈亏（USDT，Decimal 字符串） */
  total_pnl: string;
  /** 最大回撤（Decimal 字符串） */
  max_drawdown: string;
}

/**
 * 回测报告列表请求参数
 */
export interface ListBacktestReportsRequest {
  /** 策略 ID 筛选 */
  strategyId?: string;
  /** 交易对筛选 */
  symbol?: string;
  /** 开始时间戳（毫秒） */
  startDate?: number;
  /** 结束时间戳（毫秒） */
  endDate?: number;
  /** 页码（从 1 开始） */
  page?: number;
  /** 每页数量 */
  pageSize?: number;
  /** 排序字段 */
  sortBy?: 'total_return' | 'win_rate' | 'created_at';
  /** 排序方向 */
  sortOrder?: 'asc' | 'desc';
}

/**
 * 回测报告列表响应
 */
export interface ListBacktestReportsResponse {
  /** 回测报告列表 */
  reports: BacktestReportSummary[];
  /** 总记录数 */
  total: number;
  /** 当前页码 */
  page: number;
  /** 每页数量 */
  pageSize: number;
}

/**
 * 归因组件详情（单信号归因的每个组件）
 */
export interface AttributionComponent {
  /** 组件名称: "pattern" | "ema_trend" | "mtf" | "atr" */
  name: string;
  /** 组件评分 (0~1) */
  score: number;
  /** 预设权重 */
  weight: number;
  /** 贡献值 = score × weight */
  contribution: number;
  /** 贡献百分比 = contribution / final_score × 100 */
  percentage: number;
  /** 信心评分依据 */
  confidence_basis: string;
  /** 状态: "passed" | "rejected" */
  status: 'passed' | 'rejected';
}

/**
 * 单信号归因结果
 */
export interface SignalAttribution {
  /** 最终归因总分 */
  final_score: number;
  /** 归因组件列表 */
  components: AttributionComponent[];
  /** 各组件贡献百分比 {"pattern": 54.4, "ema_trend": 27.5, "mtf": 18.1} */
  percentages: Record<string, number>;
  /** 人类可读解释文本 */
  explanation: string;
}

/**
 * 聚合归因（报告摘要级别）
 */
export interface AggregateAttribution {
  /** 平均形态贡献 */
  avg_pattern_contribution: number;
  /** 平均过滤器贡献（按过滤器分组） */
  avg_filter_contributions: Record<string, number>;
  /** Top 表现最好的过滤器 */
  top_performing_filters: string[];
  /** Bottom 表现最差的过滤器 */
  worst_performing_filters: string[];
}

/**
 * 回测报告详情（完整报告）
 */
export interface BacktestReportDetail extends BacktestReportSummary {
  /** 初始资金（USDT） */
  initial_balance: string;
  /** 最终余额（USDT） */
  final_balance: string;
  /** 盈利交易次数 */
  winning_trades: number;
  /** 亏损交易次数 */
  losing_trades: number;
  /** 总手续费（USDT） */
  total_fees_paid: string;
  /** 总滑点成本（USDT） */
  total_slippage_cost: string;
  /** 总资金费用（USDT，BT-2）正数=支付，负数=收取 */
  total_funding_cost: string;
  /** 夏普比率（可选） */
  sharpe_ratio?: string | null;
  /** 仓位历史摘要列表 */
  positions: PositionSummary[];
  /** 单信号归因列表（可选，后端可能不返回） */
  signal_attributions?: SignalAttribution[] | null;
  /** 聚合归因（可选，后端可能不返回） */
  aggregate_attribution?: AggregateAttribution | null;
  /** 出场事件明细列表（报告级别，与 position.close_events 二选一或同时存在） */
  close_events?: PositionCloseEvent[];
}

/**
 * 仓位出场事件明细（分批止盈 TP1~TP5 + 止损 SL）
 */
export interface PositionCloseEvent {
  /** 仓位 ID */
  position_id: string;
  /** 订单 ID */
  order_id: string;
  /** 出场类型: TP1 | TP2 | TP3 | TP4 | TP5 | SL */
  event_type: string;
  /** 事件分类: "exit" */
  event_category: string;
  /** 成交价（Decimal 字符串） */
  close_price: string | null;
  /** 成交量（Decimal 字符串） */
  close_qty: string | null;
  /** 盈亏（USDT，Decimal 字符串） */
  close_pnl: string | null;
  /** 手续费（USDT，Decimal 字符串） */
  close_fee: string | null;
  /** 出场时间戳（毫秒） */
  close_time: number;
  /** 出场原因 */
  exit_reason: string | null;
}

/**
 * 仓位摘要信息
 */
export interface PositionSummary {
  /** 仓位 ID */
  position_id: string;
  /** 信号 ID */
  signal_id: string;
  /** 交易对 */
  symbol: string;
  /** 方向 */
  direction: 'LONG' | 'SHORT';
  /** 开仓价 */
  entry_price: string;
  /** 平仓价（可选，未平仓时为 null） */
  exit_price: string | null;
  /** 开仓时间戳（毫秒） */
  entry_time: number;
  /** 平仓时间戳（毫秒，可选） */
  exit_time: number | null;
  /** 已实现盈亏（USDT） */
  realized_pnl: string;
  /** 平仓原因（TP1/SL/TRAILING 等） */
  exit_reason: string | null;
  /** 该仓位的出场事件明细列表 */
  close_events?: PositionCloseEvent[];
}
