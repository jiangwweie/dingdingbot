/**
 * 测试数据工厂
 *
 * 提供用于 E2E 测试的 mock 数据生成
 */

/**
 * 用户数据工厂
 */
export interface UserData {
  id: string;
  email: string;
  name: string;
  role?: 'admin' | 'user';
  createdAt?: string;
}

export function createUser(overrides?: Partial<UserData>): UserData {
  const timestamp = Date.now();
  return {
    id: `user-${timestamp}`,
    email: `test${timestamp}@example.com`,
    name: `Test User ${timestamp}`,
    role: 'user',
    createdAt: new Date().toISOString(),
    ...overrides
  };
}

/**
 * 策略配置数据工厂
 */
export interface StrategyConfig {
  id: string;
  name: string;
  description?: string;
  enabled: boolean;
  symbols: string[];
  timeframes: string[];
  triggers: TriggerConfig[];
  filters: FilterConfig[];
  riskConfig: RiskConfig;
}

export interface TriggerConfig {
  type: 'pinbar' | 'engulfing' | 'doji' | 'hammer';
  params: Record<string, unknown>;
}

export interface FilterConfig {
  type: 'ema' | 'mtf' | 'atr' | 'volume';
  params: Record<string, unknown>;
}

export interface RiskConfig {
  maxLossPercent: string;
  defaultLeverage: number;
  maxPositionSize: string;
}

export function createStrategyConfig(overrides?: Partial<StrategyConfig>): StrategyConfig {
  const timestamp = Date.now();
  return {
    id: `strategy-${timestamp}`,
    name: `Test Strategy ${timestamp}`,
    description: 'Auto-generated test strategy',
    enabled: true,
    symbols: ['BTC/USDT:USDT', 'ETH/USDT:USDT'],
    timeframes: ['15m', '1h'],
    triggers: [
      {
        type: 'pinbar',
        params: {
          min_wick_ratio: 0.6,
          max_body_ratio: 0.3
        }
      }
    ],
    filters: [
      {
        type: 'ema',
        params: {
          period: 20,
          trend: 'bullish'
        }
      },
      {
        type: 'mtf',
        params: {
          higher_timeframe: '1h'
        }
      }
    ],
    riskConfig: {
      maxLossPercent: '0.01',
      defaultLeverage: 10,
      maxPositionSize: '1000'
    },
    ...overrides
  };
}

/**
 * K 线数据工厂
 */
export interface KlineData {
  timestamp: number;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
}

export function createKline(overrides?: Partial<KlineData>): KlineData {
  const basePrice = 50000;
  const timestamp = Date.now();

  return {
    timestamp,
    open: basePrice.toString(),
    high: (basePrice * 1.02).toString(),
    low: (basePrice * 0.98).toString(),
    close: (basePrice * 1.01).toString(),
    volume: '1000.5',
    ...overrides
  };
}

/**
 * 创建看涨 Pinbar K 线
 */
export function createBullishPinbar(overrides?: Partial<KlineData>): KlineData {
  const basePrice = 50000;
  return {
    timestamp: Date.now(),
    open: (basePrice * 1.005).toString(),
    high: (basePrice * 1.01).toString(),
    low: (basePrice * 0.97).toString(),
    close: (basePrice * 1.02).toString(),
    volume: '1500.0',
    ...overrides
  };
}

/**
 * 创建看跌 Pinbar K 线
 */
export function createBearishPinbar(overrides?: Partial<KlineData>): KlineData {
  const basePrice = 50000;
  return {
    timestamp: Date.now(),
    open: (basePrice * 0.995).toString(),
    high: (basePrice * 1.03).toString(),
    low: (basePrice * 0.99).toString(),
    close: (basePrice * 0.98).toString(),
    volume: '1500.0',
    ...overrides
  };
}

/**
 * 创建吞没形态 K 线组合
 */
export function createEngulfingPattern(): { previous: KlineData; current: KlineData } {
  const basePrice = 50000;
  const timestamp = Date.now();

  // 看涨吞没：前一根阴线，当前阳线实体完全包裹前一根
  return {
    previous: {
      timestamp: timestamp - 900000, // 15 分钟前
      open: (basePrice * 1.01).toString(),
      high: (basePrice * 1.015).toString(),
      low: (basePrice * 0.995).toString(),
      close: (basePrice * 0.99).toString(),
      volume: '800.0'
    },
    current: {
      timestamp,
      open: (basePrice * 0.985).toString(),
      high: (basePrice * 1.02).toString(),
      low: (basePrice * 0.98).toString(),
      close: (basePrice * 1.015).toString(),
      volume: '2000.0'
    }
  };
}

/**
 * 信号数据工厂
 */
export interface SignalData {
  id: string;
  symbol: string;
  timeframe: string;
  direction: 'LONG' | 'SHORT';
  entryPrice: string;
  stopLoss: string;
  positionSize: string;
  leverage: number;
  tags: Array<{ name: string; value: string }>;
  strategyName: string;
  score: number;
  createdAt: string;
}

export function createSignal(overrides?: Partial<SignalData>): SignalData {
  const timestamp = Date.now();
  const entryPrice = '50000';

  return {
    id: `signal-${timestamp}`,
    symbol: 'BTC/USDT:USDT',
    timeframe: '15m',
    direction: 'LONG',
    entryPrice,
    stopLoss: '49000',
    positionSize: '0.1',
    leverage: 10,
    tags: [
      { name: 'EMA', value: 'Bullish' },
      { name: 'MTF', value: 'Aligned' }
    ],
    strategyName: 'Pinbar + EMA',
    score: 0.85,
    createdAt: new Date().toISOString(),
    ...overrides
  };
}

/**
 * 账户数据工厂
 */
export interface AccountData {
  totalBalance: string;
  availableBalance: string;
  unrealizedPnl: string;
  equity: string;
  marginRatio: string;
  positions: PositionData[];
}

export interface PositionData {
  symbol: string;
  side: 'LONG' | 'SHORT';
  size: string;
  entryPrice: string;
  markPrice: string;
  unrealizedPnl: string;
  leverage: number;
  margin: string;
}

export function createAccount(overrides?: Partial<AccountData>): AccountData {
  return {
    totalBalance: '10000.00',
    availableBalance: '8000.00',
    unrealizedPnl: '150.00',
    equity: '10150.00',
    marginRatio: '0.15',
    positions: [],
    ...overrides
  };
}

export function createPosition(overrides?: Partial<PositionData>): PositionData {
  return {
    symbol: 'BTC/USDT:USDT',
    side: 'LONG',
    size: '0.1',
    entryPrice: '50000.00',
    markPrice: '50500.00',
    unrealizedPnl: '50.00',
    leverage: 10,
    margin: '500.00',
    ...overrides
  };
}

/**
 * 订单数据工厂
 */
export interface OrderData {
  id: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  type: 'LIMIT' | 'MARKET';
  price?: string;
  quantity: string;
  status: 'NEW' | 'FILLED' | 'CANCELED' | 'REJECTED';
  filledQuantity: string;
  avgPrice: string;
  createdAt: string;
  updatedAt: string;
}

export function createOrder(overrides?: Partial<OrderData>): OrderData {
  const timestamp = Date.now();
  const now = new Date().toISOString();

  return {
    id: `order-${timestamp}`,
    symbol: 'BTC/USDT:USDT',
    side: 'BUY',
    type: 'LIMIT',
    price: '50000.00',
    quantity: '0.1',
    status: 'NEW',
    filledQuantity: '0',
    avgPrice: '0',
    createdAt: now,
    updatedAt: now,
    ...overrides
  };
}

/**
 * 通知数据工厂
 */
export interface NotificationData {
  id: string;
  type: 'signal' | 'order' | 'alert' | 'error';
  title: string;
  message: string;
  level: 'info' | 'success' | 'warning' | 'error';
  read: boolean;
  createdAt: string;
}

export function createNotification(overrides?: Partial<NotificationData>): NotificationData {
  const timestamp = Date.now();

  return {
    id: `notification-${timestamp}`,
    type: 'signal',
    title: '新信号',
    message: 'BTC/USDT:USDT 15m 出现看涨信号',
    level: 'info',
    read: false,
    createdAt: new Date().toISOString(),
    ...overrides
  };
}

/**
 * 错误响应工厂
 */
export interface ErrorResponse {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export function createErrorResponse(
  code: string,
  message: string,
  details?: Record<string, unknown>
): ErrorResponse {
  return {
    code,
    message,
    details
  };
}
