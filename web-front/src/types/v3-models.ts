/**
 * v3.0 核心模型 - TypeScript 类型定义
 *
 * @fileoverview 定义 v3.0 迁移 Phase 1 的核心数据模型
 * 与后端 src/domain/models.py 保持类型对齐
 * @see docs/designs/v3-phase1-models-contract.md
 * @version 1.0
 * @since 2026-03-30
 */

// ============================================================
// 枚举类型定义
// ============================================================

/**
 * 交易方向
 *
 * 用于标识信号、订单、仓位的多空方向
 */
export type Direction = 'LONG' | 'SHORT';

/**
 * 订单状态
 *
 * 与 CCXT 订单状态映射关系：
 * - OPEN → open (挂单中)
 * - PARTIALLY_FILLED → partially_filled (部分成交)
 * - FILLED → closed (完全成交)
 * - CANCELED → canceled (已撤销)
 * - REJECTED → rejected (交易所拒单)
 */
export type OrderStatus =
  | 'PENDING'        // 尚未发送到交易所
  | 'OPEN'           // 挂单中
  | 'PARTIALLY_FILLED' // 部分成交
  | 'FILLED'         // 完全成交
  | 'CANCELED'       // 已撤销
  | 'REJECTED';      // 交易所拒单

/**
 * 订单类型
 *
 * 各类型使用场景：
 * - MARKET: 市价单，用于快速入场
 * - LIMIT: 限价单，用于 TP1 止盈
 * - STOP_MARKET: 条件市价单，用于初始止损
 * - TRAILING_STOP: 移动止损单，用于追踪止盈
 */
export type OrderType =
  | 'MARKET'         // 市价单
  | 'LIMIT'          // 限价单
  | 'STOP_MARKET'    // 条件市价单
  | 'TRAILING_STOP'; // 移动止损单

/**
 * 订单角色
 *
 * 标识订单在策略中的用途
 */
export type OrderRole =
  | 'ENTRY'  // 入场开仓
  | 'TP1'    // 第一目标位止盈（50%）
  | 'SL';    // 止损单（初始/移动）

// ============================================================
// 核心模型定义
// ============================================================

/**
 * 资产账户
 *
 * 代表用户的钱包账户，包含总余额、冻结保证金等信息
 * available_balance 为计算属性：total_balance - frozen_margin
 */
export interface Account {
  /** 账户 ID，默认为 "default_wallet" */
  account_id: string;

  /** 钱包总余额（Decimal 序列化后为 string） */
  total_balance: string;

  /** 冻结保证金（Decimal 序列化后为 string） */
  frozen_margin: string;

  /** 可用余额（计算属性：total_balance - frozen_margin） */
  available_balance: string;
}

/**
 * 策略信号
 *
 * 由策略引擎生成的交易信号，包含入场、止损等关键信息
 */
export interface Signal {
  /** 信号唯一标识 ID */
  id: string;

  /** 触发该信号的策略名称/ID */
  strategy_id: string;

  /** 交易对，如 "BTC/USDT:USDT" */
  symbol: string;

  /** 信号方向（做多/做空） */
  direction: Direction;

  /** 信号生成时间戳（毫秒） */
  timestamp: number;

  /** 预期入场价格（Decimal 序列化后为 string） */
  expected_entry: string;

  /** 预期止损价格（Decimal 序列化后为 string） */
  expected_sl: string;

  /** 形态质量评分，范围 0-1 */
  pattern_score: number;

  /** 信号是否处于活跃状态（未被撤销或执行完毕） */
  is_active: boolean;
}

/**
 * 交易订单
 *
 * 代表一笔具体的交易委托，包含订单详情、执行状态等
 */
export interface Order {
  /** 订单唯一标识 ID */
  id: string;

  /** 所属信号 ID，关联到具体的 Signal */
  signal_id: string;

  /** 交易所返回的订单 ID（如有） */
  exchange_order_id: string | null;

  /** 交易对，如 "BTC/USDT:USDT" */
  symbol: string;

  /** 订单方向（做多/做空） */
  direction: Direction;

  /** 订单类型（市价/限价/条件单等） */
  order_type: OrderType;

  /** 订单角色（入场/止盈/止损） */
  order_role: OrderRole;

  /** 限价单价格（仅 LIMIT 订单有效，Decimal 序列化后为 string） */
  price: string | null;

  /** 条件单触发价格（Decimal 序列化后为 string） */
  trigger_price: string | null;

  /** 委托数量（Decimal 序列化后为 string） */
  requested_qty: string;

  /** 已成交数量（Decimal 序列化后为 string） */
  filled_qty: string;

  /** 成交均价（Decimal 序列化后为 string） */
  average_exec_price: string | null;

  /** 当前订单状态 */
  status: OrderStatus;

  /** 订单创建时间戳（毫秒） */
  created_at: number;

  /** 订单更新时间戳（毫秒） */
  updated_at: number;

  /** 出局原因（如适用） */
  exit_reason: string | null;
}

/**
 * 核心仓位
 *
 * 代表一个持仓仓位，包含入场价格、当前数量、最高价等信息
 */
export interface Position {
  /** 仓位唯一标识 ID */
  id: string;

  /** 所属信号 ID，关联到具体的 Signal */
  signal_id: string;

  /** 交易对，如 "BTC/USDT:USDT" */
  symbol: string;

  /** 仓位方向（做多/做空） */
  direction: Direction;

  /** 开仓均价（固定不变，Decimal 序列化后为 string） */
  entry_price: string;

  /** 当前持仓数量（Decimal 序列化后为 string） */
  current_qty: string;

  /** 入场后最高价格（用于追踪止损计算，Decimal 序列化后为 string） */
  highest_price_since_entry: string;

  /** 已实现盈亏（Decimal 序列化后为 string） */
  realized_pnl: string;

  /** 累计手续费（Decimal 序列化后为 string） */
  total_fees_paid: string;

  /** 仓位是否已平仓 */
  is_closed: boolean;
}

// ============================================================
// 联合类型（方便使用）
// ============================================================

/**
 * 多态实体类型
 * 用于需要同时处理多种实体类型的场景
 */
export type V3Entity = Account | Signal | Order | Position;
