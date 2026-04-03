/**
 * Phase 5 实盘集成 - 订单与持仓类型定义
 *
 * SSOT: docs/designs/phase5-contract.md Section 12
 *
 * 注意：
 * - Decimal 类型序列化后使用 string 表示
 * - 时间戳使用 number (毫秒)
 * - 可选字段使用 null 联合类型
 */

/**
 * 交易方向
 */
export enum Direction {
  LONG = "LONG",
  SHORT = "SHORT",
}

/**
 * 订单类型
 */
export enum OrderType {
  /** 市价单 */
  MARKET = "MARKET",
  /** 限价单 */
  LIMIT = "LIMIT",
  /** 止损市价单 */
  STOP_MARKET = "STOP_MARKET",
  /** 止损限价单 */
  STOP_LIMIT = "STOP_LIMIT",
}

/**
 * 订单角色 - v3.0 PMS 精细定义
 *
 * 注意：与简化版 OPEN/CLOSE 分类不同，此枚举支持多级别止盈订单链管理
 */
export enum OrderRole {
  /** 入场开仓 */
  ENTRY = "ENTRY",
  /** 第一目标位止盈（首笔止盈） */
  TP1 = "TP1",
  /** 第二目标位止盈 */
  TP2 = "TP2",
  /** 第三目标位止盈 */
  TP3 = "TP3",
  /** 第四目标位止盈 */
  TP4 = "TP4",
  /** 第五目标位止盈 */
  TP5 = "TP5",
  /** 止损单 */
  SL = "SL",
}

/**
 * 订单状态 - 7 状态机
 */
export enum OrderStatus {
  /** 待处理 (已创建但未提交到交易所) */
  PENDING = "PENDING",
  /** 进行中 (已提交到交易所，等待成交) */
  OPEN = "OPEN",
  /** 已完全成交 */
  FILLED = "FILLED",
  /** 已取消 */
  CANCELED = "CANCELED",
  /** 被拒绝 */
  REJECTED = "REJECTED",
  /** 已过期 */
  EXPIRED = "EXPIRED",
  /** 部分成交 */
  PARTIALLY_FILLED = "PARTIALLY_FILLED",
}

/**
 * 标签接口 - 用于订单/持仓的动态标签
 */
export interface Tag {
  /** 标签名称 */
  name: string;
  /** 标签值 */
  value: string;
}

/**
 * 下单请求
 */
export interface OrderRequest {
  /** 交易对，如 "BTC/USDT:USDT" */
  symbol: string;
  /** 订单类型 */
  order_type: OrderType;
  /** 订单角色 (ENTRY/TP1-5/SL) */
  order_role: OrderRole;
  /** 交易方向 */
  direction: Direction;
  /** 订单数量 (Decimal string) */
  quantity: string;
  /** 订单价格 (限价单必填，Decimal string) */
  price?: string;
  /** 触发价格 (止损单必填，Decimal string) */
  trigger_price?: string;
  /** 是否仅减仓模式 */
  reduce_only: boolean;
  /** 客户端订单 ID (可选，用于幂等) */
  client_order_id?: string;
  /** 策略名称 (可选，用于追踪) */
  strategy_name?: string;
  /** 关联信号 ID (可选) */
  signal_id?: string;
  /** 止损价格 (Decimal string) */
  stop_loss?: string;
  /** 止盈价格 (Decimal string) */
  take_profit?: string;
}

/**
 * 订单响应
 */
export interface OrderResponse {
  /** 系统内部订单 ID */
  order_id: string;
  /** 交易所订单 ID (可能为 null) */
  exchange_order_id: string | null;
  /** 交易对 */
  symbol: string;
  /** 订单类型 */
  order_type: OrderType;
  /** 订单角色 */
  order_role: OrderRole;
  /** 交易方向 */
  direction: Direction;
  /** 订单状态 */
  status: OrderStatus;
  /** 订单数量 (Decimal string) */
  quantity: string;
  /** 已成交数量 (Decimal string) */
  filled_qty: string;
  /** 剩余数量 (Decimal string) */
  remaining_qty: string;
  /** 订单价格 (Decimal string 或 null) */
  price: string | null;
  /** 触发价格 (Decimal string 或 null) */
  trigger_price: string | null;
  /** 平均成交价格 (Decimal string 或 null) */
  average_exec_price: string | null;
  /** 是否仅减仓模式 */
  reduce_only: boolean;
  /** 客户端订单 ID */
  client_order_id: string | null;
  /** 策略名称 */
  strategy_name: string | null;
  /** 关联信号 ID */
  signal_id: string | null;
  /** 止损价格 (Decimal string 或 null) */
  stop_loss: string | null;
  /** 止盈价格 (Decimal string 或 null) */
  take_profit: string | null;
  /** 创建时间戳 (毫秒) */
  created_at: number;
  /** 更新时间戳 (毫秒) */
  updated_at: number;
  /** 成交时间戳 (毫秒) */
  filled_at?: number;
  /** 已支付手续费 (Decimal string) */
  fee_paid: string;
  /** 手续费币种 */
  fee_currency: string | null;
  /** 订单标签列表 */
  tags: Tag[];
}

/**
 * 取消订单响应
 */
export interface OrderCancelResponse {
  /** 系统内部订单 ID */
  order_id: string;
  /** 交易所订单 ID */
  exchange_order_id: string | null;
  /** 交易对 */
  symbol: string;
  /** 取消后的订单状态 */
  status: OrderStatus;
  /** 取消时间戳 (毫秒) */
  canceled_at: number;
  /** 响应消息 */
  message: string;
}

/**
 * 持仓信息
 */
export interface PositionInfo {
  /** 持仓 ID */
  position_id: string;
  /** 交易对 */
  symbol: string;
  /** 交易方向 */
  direction: Direction;
  /** 当前持仓数量 (Decimal string) */
  current_qty: string;
  /** 原始数量 (Decimal string) */
  original_qty: string;
  /** 开仓均价 (Decimal string) */
  entry_price: string;
  /** 标记价格 (Decimal string 或 null) */
  mark_price: string | null;
  /** 未实现盈亏 (Decimal string) */
  unrealized_pnl: string;
  /** 已实现盈亏 (Decimal string) */
  realized_pnl: string;
  /** 强平价格 (Decimal string 或 null) */
  liquidation_price: string | null;
  /** 杠杆倍数 */
  leverage: number;
  /** 保证金模式 */
  margin_mode: "CROSS" | "ISOLATED";
  /** 是否已平仓 */
  is_closed: boolean;
  /** 开仓时间戳 (毫秒) */
  opened_at: number;
  /** 平仓时间戳 (毫秒 或 null) */
  closed_at: number | null;
  /** 累计手续费 (Decimal string) */
  total_fees_paid: string;
  /** 关联策略名称 */
  strategy_name: string | null;
  /** 关联信号 ID */
  signal_id: string | null;
  /** 止损价格 (Decimal string 或 null) */
  stop_loss: string | null;
  /** 止盈价格 (Decimal string 或 null) */
  take_profit: string | null;
  /** 止盈订单链 (TP1-TP5) */
  take_profit_orders: OrderResponse[];
  /** 止损订单 */
  stop_loss_order: OrderResponse | null;
  /** 持仓标签列表 */
  tags: Tag[];
}

/**
 * 持仓列表响应
 */
export interface PositionResponse {
  /** 持仓列表 */
  positions: PositionInfo[];
  /** 总未实现盈亏 (Decimal string) */
  total_unrealized_pnl: string;
  /** 总已实现盈亏 (Decimal string) */
  total_realized_pnl: string;
  /** 总保证金占用 (Decimal string) */
  total_margin_used: string;
  /** 账户权益 (Decimal string 或 null) */
  account_equity: string | null;
}

/**
 * 账户余额信息
 */
export interface AccountBalance {
  /** 币种 */
  currency: string;
  /** 总余额 (Decimal string) */
  total_balance: string;
  /** 可用余额 (Decimal string) */
  available_balance: string;
  /** 冻结余额 (Decimal string) */
  frozen_balance: string;
  /** 未实现盈亏 (Decimal string) */
  unrealized_pnl: string;
}

/**
 * 账户信息响应
 */
export interface AccountResponse {
  /** 交易所名称 */
  exchange: string;
  /** 账户类型 */
  account_type: "FUTURES" | "SPOT" | "MARGIN";
  /** 余额列表 */
  balances: AccountBalance[];
  /** 总权益 (Decimal string) */
  total_equity: string;
  /** 总保证金余额 (Decimal string) */
  total_margin_balance: string;
  /** 总钱包余额 (Decimal string) */
  total_wallet_balance: string;
  /** 总未实现盈亏 (Decimal string) */
  total_unrealized_pnl: string;
  /** 可用余额 (Decimal string) */
  available_balance: string;
  /** 总保证金占用 (Decimal string) */
  total_margin_used: string;
  /** 账户杠杆倍数 */
  account_leverage: number;
  /** 最后更新时间戳 (毫秒) */
  last_updated: number;
}

/**
 * 对账请求
 */
export interface ReconciliationRequest {
  /** 交易对 */
  symbol: string;
  /** 是否完整检查 (包括订单) */
  full_check?: boolean;
}

/**
 * 仓位不匹配记录
 */
export interface PositionMismatch {
  /** 交易对 */
  symbol: string;
  /** 本地系统记录的数量 (Decimal string) */
  local_qty: string;
  /** 交易所记录的数量 (Decimal string) */
  exchange_qty: string;
  /** 差异值 (Decimal string) */
  discrepancy: string;
}

/**
 * 订单不匹配记录
 */
export interface OrderMismatch {
  /** 订单 ID */
  order_id: string;
  /** 本地系统记录的状态 */
  local_status: OrderStatus;
  /** 交易所记录的状态 */
  exchange_status: string;
}

/**
 * 对账报告
 */
export interface ReconciliationReport {
  /** 交易对 */
  symbol: string;
  /** 对账时间戳 (毫秒) */
  reconciliation_time: number;
  /** 宽限期秒数 */
  grace_period_seconds: number;
  /** 仓位不匹配列表 */
  position_mismatches: PositionMismatch[];
  /** 缺失的持仓列表 */
  missing_positions: PositionInfo[];
  /** 订单不匹配列表 */
  order_mismatches: OrderMismatch[];
  /** 孤立订单列表 (本地不存在但交易所有) */
  orphan_orders: OrderResponse[];
  /** 是否一致 */
  is_consistent: boolean;
  /** 总差异数 */
  total_discrepancies: number;
  /** 是否需要关注 */
  requires_attention: boolean;
  /** 摘要说明 */
  summary: string;
}

/**
 * 资金保护检查结果
 */
export interface CapitalProtectionCheckResult {
  /** 是否允许执行 */
  allowed: boolean;
  /** 拒绝原因代码 */
  reason: string | null;
  /** 拒绝原因人类可读消息 */
  reason_message: string | null;
  /** 单笔损失检查是否通过 */
  single_trade_check: boolean | null;
  /** 仓位限制检查是否通过 */
  position_limit_check: boolean | null;
  /** 每日损失检查是否通过 */
  daily_loss_check: boolean | null;
  /** 每日交易次数检查是否通过 */
  daily_count_check: boolean | null;
  /** 余额检查是否通过 */
  balance_check: boolean | null;
  /** 预估损失 (Decimal string) */
  estimated_loss: string | null;
  /** 最大允许损失 (Decimal string) */
  max_allowed_loss: string | null;
  /** 仓位价值 (Decimal string) */
  position_value: string | null;
  /** 最大允许仓位 (Decimal string) */
  max_allowed_position: string | null;
  /** 每日盈亏 (Decimal string) */
  daily_pnl: string | null;
  /** 每日交易次数 */
  daily_trade_count: number | null;
  /** 可用余额 (Decimal string) */
  available_balance: string | null;
  /** 最小要求余额 (Decimal string) */
  min_required_balance: string | null;
}

/**
 * 订单列表响应
 */
export interface OrdersResponse {
  items: OrderResponse[];
  total: number;
  limit: number;
  offset: number;
}

/**
 * 持仓列表响应（与 PositionResponse 对齐）
 */
export interface PositionsResponse {
  positions: PositionInfo[];
  total_unrealized_pnl: string;
  total_realized_pnl: string;
  total_margin_used: string;
  account_equity: string | null;
}

/**
 * 平仓请求
 */
export interface ClosePositionRequest {
  /** 平仓比例 (0.0-1.0)，默认 1.0 表示全部平仓 */
  close_ratio?: number;
  /** 平仓价格（市价单留空） */
  price?: string;
  /** 订单类型，默认 MARKET */
  order_type?: OrderType;
}

/**
 * 下单前资金保护检查请求
 */
export interface OrderCheckRequest {
  /** 交易对 */
  symbol: string;
  /** 订单类型 */
  order_type: OrderType;
  /** 订单角色 */
  order_role: OrderRole;
  /** 方向 */
  direction: Direction;
  /** 数量 (Decimal string) */
  quantity: string;
  /** 限价单价格 (可选) */
  price?: string;
  /** 触发价格 (可选) */
  trigger_price?: string;
  /** 止损价格 (可选) */
  stop_loss?: string;
}

/**
 * 账户快照（与后端 AccountResponse 对齐）
 */
export interface AccountSnapshot {
  /** 交易所名称 */
  exchange: string;
  /** 账户类型 */
  account_type: "FUTURES" | "SPOT" | "MARGIN";
  /** 余额列表 */
  balances: AccountBalance[];
  /** 总权益 (Decimal string) */
  total_equity: string;
  /** 总保证金余额 (Decimal string) */
  total_margin_balance: string;
  /** 总钱包余额 (Decimal string) */
  total_wallet_balance: string;
  /** 总未实现盈亏 (Decimal string) */
  total_unrealized_pnl: string;
  /** 可用余额 (Decimal string) */
  available_balance: string;
  /** 总保证金占用 (Decimal string) */
  total_margin_used: string;
  /** 账户杠杆倍数 */
  account_leverage: number;
  /** 最后更新时间戳 (毫秒) */
  last_updated: number;
}

/**
 * API 错误响应
 */
export interface ApiResponseError {
  /** 错误代码 */
  error_code: string;
  /** 错误消息 */
  message: string;
}

/**
 * 订单树节点 - 用于树形表格展示
 */
export interface OrderTreeNode {
  /** 订单详情 */
  order: OrderResponse;
  /** 子订单列表（TP1-5, SL） */
  children: OrderTreeNode[];
  /** 层级深度（0=根节点，1=子订单） */
  level: number;
  /** 是否有子订单（用于 UI 展示展开图标） */
  has_children: boolean;
}

/**
 * 订单树 API 响应
 */
export interface OrderTreeResponse {
  /** 树形节点列表 */
  items: OrderTreeNode[];
  /** 总根订单数（当前页） */
  total: number;
  /** 总记录数（用于分页） */
  total_count: number;
  /** 当前页码 */
  page: number;
  /** 每页数量 */
  page_size: number;
  /** 元数据 */
  metadata?: {
    /** 币种过滤 */
    symbol_filter?: string;
    /** 天数过滤 */
    days_filter?: number;
    /** 加载时间戳 */
    loaded_at?: number;
  };
}

/**
 * 批量删除请求
 */
export interface OrderBatchDeleteRequest {
  /** 订单 ID 列表 */
  order_ids: string[];
  /** 是否调用交易所取消接口 */
  cancel_on_exchange?: boolean;
  /** 审计信息 */
  audit_info?: {
    /** 操作人 ID */
    operator_id?: string;
    /** 操作 IP */
    ip_address?: string;
    /** 用户代理 */
    user_agent?: string;
  };
}

/**
 * 批量删除响应
 */
export interface OrderBatchDeleteResponse {
  /** 删除总数 */
  deleted_count: number;
  /** 交易所取消成功的订单 ID 列表 */
  cancelled_on_exchange: string[];
  /** 取消失败的订单列表 */
  failed_to_cancel: Array<{ order_id: string; reason: string }>;
  /** 数据库删除的订单 ID 列表 */
  deleted_from_db: string[];
  /** 删除失败的订单列表 */
  failed_to_delete: Array<{ order_id: string; reason: string }>;
  /** 审计日志 ID */
  audit_log_id?: string;
}
