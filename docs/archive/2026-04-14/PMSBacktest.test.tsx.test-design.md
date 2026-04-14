# PMSBacktest.test.tsx 测试设计文档

**创建日期**: 2026-04-06  
**优先级**: P1  
**状态**: 设计中

---

## 1. 测试文件路径

```
web-front/src/pages/__tests__/PMSBacktest.test.tsx
```

---

## 2. 测试目标

验证 PMS 回测页面 (`PMSBacktest.tsx`) 的完整功能，包括：
- PMS 特定表单配置（初始资金）
- 策略组装工作台集成
- PMS 回测执行流程
- PMS 报告展示（仓位级追踪）
- 错误处理与边界条件

---

## 3. 测试用例清单 (8 个)

### 3.1 初始渲染测试

```typescript
it('should render all PMS-specific form elements', async () => {
  // 验证 PMS 特有字段
  - 渲染 initial_balance 输入框
  - 默认值为 10000 (USDT)
  - 渲染币种选择器 (8 个选项)
  - 渲染周期选择器 (5 个选项：15m/1h/4h/1d/1w)
  - 渲染日期范围选择器
  - 渲染 [执行 PMS 回测] 按钮
  
  // 验证信息横幅
  - 显示 "PMS 回测 vs 经典回测" 说明
  - 解释仓位级追踪与信号级统计的区别
})
```

### 3.2 初始资金配置测试

```typescript
it('should handle initial_balance input correctly', async () => {
  // 默认值验证
  - 输入框默认显示 "10000"
  
  // 修改值
  - 用户输入 "50000"
  - state 正确更新为 50000
  
  // 无效值验证
  - 输入 "0" 或负数
  - 输入框有 min="100" 限制
  - 超出范围无法提交
})
```

### 3.3 表单验证测试

```typescript
it('should validate PMS backtest form', async () => {
  // 未选日期
  - 点击 [执行 PMS 回测]
  - 显示错误："请选择起始和结束时间"
  
  // 起始时间 >= 结束时间
  - 设置无效日期范围
  - 显示错误："起始时间必须早于结束时间"
  
  // 未配置策略
  - 选择日期但未添加策略
  - 显示错误："请至少配置一个策略"
  
  // 初始资金无效
  - 输入负数或 0
  - HTML5 验证阻止提交
})
```

### 3.4 PMS 回测执行流程测试

```typescript
it('should execute PMS backtest with correct payload', async () => {
  // 准备有效表单
  - symbol: 'BTC/USDT:USDT'
  - timeframe: '1h'
  - start_time: 1700000000000
  - end_time: 1700086400000
  - strategies: [Pinbar 策略]
  - initial_balance: 50000
  
  // 点击执行
  - 点击 [执行 PMS 回测]
  - 按钮显示 loading: "PMS 回测引擎运行中..."
  
  // API 调用验证
  - 调用 runPMSBacktest(payload)
  - payload 结构验证:
    {
      symbol: 'BTC/USDT:USDT',
      timeframe: '1h',
      start_time: 1700000000000,
      end_time: 1700086400000,
      strategies: [...],
      risk_overrides: {...},
      initial_balance: 50000,  // PMS 特有字段
    }
})
```

### 3.5 PMS 报告展示测试

```typescript
it('should display PMS backtest report with position-level tracking', async () => {
  // Mock PMS 报告
  const mockPMSReport: PMSBacktestReport = {
    strategy_id: 'strat-001',
    strategy_name: 'Pinbar 保守策略',
    backtest_start: 1700000000000,
    backtest_end: 1700086400000,
    initial_balance: '50000.00',
    final_balance: '52500.00',
    total_return: '5.00',  // 5%
    total_trades: 20,
    winning_trades: 12,
    losing_trades: 8,
    win_rate: '60.00',
    total_pnl: '2500.00',
    total_fees_paid: '50.00',
    total_slippage_cost: '25.00',
    max_drawdown: '3.50',
    sharpe_ratio: '1.25',
    positions: [
      {
        position_id: 'pos-001',
        signal_id: 'sig-001',
        symbol: 'BTC/USDT:USDT',
        direction: 'LONG',
        entry_price: '50000.00',
        exit_price: '51500.00',
        entry_time: 1700000000000,
        exit_time: 1700010000000,
        realized_pnl: '1500.00',
        exit_reason: 'TP1',
      },
    ],
  };
  
  // 验证概览卡片
  - 显示初始余额：50,000 USDT
  - 显示最终余额：52,500 USDT
  - 显示总收益率：5.00%
  - 显示胜率：60.00%
  - 显示总盈亏：+2,500 USDT
  - 显示最大回撤：3.50%
  
  // 验证仓位列表
  - 显示仓位历史表格
  - 列：仓位 ID/信号 ID/方向/开仓价/平仓价/盈亏/平仓原因
})
```

### 3.6 错误处理测试

```typescript
it('should display error message on PMS backtest failure', async () => {
  // Mock API 错误 (422 验证失败)
  vi.mocked(runPMSBacktest).mockRejectedValue({
    info: {
      detail: [
        { 
          loc: ['body', 'initial_balance'], 
          msg: 'Initial balance must be greater than 0' 
        }
      ]
    }
  });
  
  // 点击执行
  - 点击 [执行 PMS 回测]
  
  // 错误展示
  - 显示红色错误卡片
  - 标题："PMS 回测失败"
  - 详情："initial_balance: Initial balance must be greater than 0"
})
```

### 3.7 边界条件测试

```typescript
it('should handle edge cases correctly', async () => {
  // 初始资金超限
  - 输入 initial_balance = 1000000 (最大值)
  - 提交有效
  
  - 输入 initial_balance = 1000001 (超限)
  - HTML5 验证阻止 (max="1000000")
  
  // API 超时
  - Mock 超时错误
  - 显示"请求超时，请重试"
  
  // 空策略列表
  - strategies.length === 0
  - 按钮保持禁用状态
})
```

### 3.8 策略模板导入与历史测试

```typescript
it('should support strategy template import and history view', async () => {
  // 策略模板导入
  - 点击 [从策略工作台导入]
  - 显示模板选择器
  - 选择策略并导入
  - StrategyBuilder 显示导入的策略
  
  // 回测历史
  - 点击 [回测历史]
  - 显示 PMS 回测历史抽屉
  - 显示历史信号表格
  - 可点击查看详情
})
```

---

## 4. Fixtures 设计

```typescript
// ============================================================
// Mock 数据 Fixtures
// ============================================================

/**
 * 模拟 PMS 回测报告
 */
const mockPMSReport: PMSBacktestReport = {
  strategy_id: 'strat-001',
  strategy_name: 'Pinbar 保守策略',
  backtest_start: 1700000000000,
  backtest_end: 1700086400000,
  initial_balance: '50000.00',
  final_balance: '52500.00',
  total_return: '5.00',
  total_trades: 20,
  winning_trades: 12,
  losing_trades: 8,
  win_rate: '60.00',
  total_pnl: '2500.00',
  total_fees_paid: '50.00',
  total_slippage_cost: '25.00',
  max_drawdown: '3.50',
  sharpe_ratio: '1.25',
  positions: [
    {
      position_id: 'pos-001',
      signal_id: 'sig-001',
      symbol: 'BTC/USDT:USDT',
      direction: 'LONG',
      entry_price: '50000.00',
      exit_price: '51500.00',
      entry_time: 1700000000000,
      exit_time: 1700010000000,
      realized_pnl: '1500.00',
      exit_reason: 'TP1',
    },
    {
      position_id: 'pos-002',
      signal_id: 'sig-002',
      symbol: 'BTC/USDT:USDT',
      direction: 'SHORT',
      entry_price: '51000.00',
      exit_price: '50500.00',
      entry_time: 1700020000000,
      exit_time: 1700030000000,
      realized_pnl: '500.00',
      exit_reason: 'SL',
    },
  ],
};

/**
 * 模拟策略定义
 */
const mockStrategies: StrategyDefinition[] = [
  {
    id: 'strat-001',
    name: 'Pinbar + EMA + MTF',
    trigger_config: {
      type: 'pinbar',
      params: {
        min_wick_ratio: 0.6,
        max_body_ratio: 0.3,
      },
    },
    filter_configs: [
      {
        id: 'f1',
        type: 'ema',
        enabled: true,
        params: { period: 60 },
      },
      {
        id: 'f2',
        type: 'mtf',
        enabled: true,
        params: { require_confirmation: true },
      },
    ],
    filter_logic: 'AND',
    symbols: ['BTC/USDT:USDT'],
    timeframes: ['1h'],
  },
];

/**
 * 模拟 PMS 回测历史信号
 */
const mockPMSSignals: Signal[] = [
  {
    id: 'pms-sig-001',
    created_at: '2026-04-01T10:00:00Z',
    symbol: 'BTC/USDT:USDT',
    timeframe: '1h',
    direction: 'long',
    entry_price: '50000.00',
    stop_loss: '49000.00',
    position_size: '0.5',
    leverage: 10,
    status: 'CLOSED',
    pnl_ratio: '0.03',
    strategy_name: 'Pinbar 保守策略',
    source: 'backtest',
  },
];

// ============================================================
// MSW Request Interceptors
// ============================================================

const mockPMSApiHandlers = [
  // GET /api/strategies/templates
  http.get('/api/strategies/templates', () => {
    return HttpResponse.json({
      templates: [
        { id: 1, name: 'PMS Pinbar 策略', description: 'PMS 模式 Pinbar' },
        { id: 2, name: 'PMS Engulfing 策略', description: 'PMS 吞没形态' },
      ],
    });
  }),
  
  // POST /api/backtest/pms
  http.post('/api/backtest/pms', async ({ request }) => {
    const payload = await request.json();
    
    // 验证 PMS 特有字段
    expect(payload).toHaveProperty('initial_balance');
    expect(typeof payload.initial_balance).toBe('number');
    expect(payload.initial_balance).toBeGreaterThan(0);
    
    return HttpResponse.json(mockPMSReport);
  }),
  
  // GET /api/backtest/signals/history (PMS 复用经典回测历史接口)
  http.get('/api/backtest/signals/history', () => {
    return HttpResponse.json({
      signals: mockPMSSignals,
    });
  }),
];
```

---

## 5. Mock 策略

```typescript
// ============================================================
// 模块级 Mock 配置
// ============================================================

// 1. Mock window.matchMedia
beforeEach(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().matchMedia.mockImplementation((query) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

// 2. Mock PMS API
vi.mock('../../../lib/api', () => ({
  runPMSBacktest: vi.fn(),
  fetchStrategyTemplates: vi.fn(),
  fetchBacktestSignals: vi.fn(),
}));

// 3. Mock 子组件
vi.mock('../../../components/StrategyBuilder', () => ({
  __esModule: true,
  default: ({ strategies, onChange }) => (
    <div data-testid="strategy-builder">
      <span>策略数量：{strategies.length}</span>
      <button onClick={() => onChange([...strategies, {}])}>添加策略</button>
    </div>
  ),
}));

vi.mock('../../../components/QuickDateRangePicker', () => ({
  __esModule: true,
  default: ({ onStartChange, onEndChange }) => (
    <div data-testid="date-picker">
      <button onClick={() => onStartChange(1700000000000)}>设置开始</button>
      <button onClick={() => onEndChange(1700086400000)}>设置结束</button>
    </div>
  ),
}));

// 4. Mock v3 回测组件
vi.mock('../../../components/v3/backtest', () => ({
  BacktestOverviewCards: ({ report }) => (
    <div data-testid="overview-cards">
      <span>初始余额：{report.initial_balance}</span>
      <span>最终余额：{report.final_balance}</span>
    </div>
  ),
  EquityComparisonChart: ({ report }) => (
    <div data-testid="equity-chart">权益曲线图</div>
  ),
  TradeStatisticsTable: ({ report }) => (
    <div data-testid="trade-stats">交易统计表</div>
  ),
  PnLDistributionHistogram: ({ report }) => (
    <div data-testid="pnl-distribution">盈亏分布</div>
  ),
  MonthlyReturnHeatmap: ({ report }) => (
    <div data-testid="monthly-heatmap">月度热力图</div>
  ),
}));
```

---

## 6. 验收标准

### 6.1 功能验收

| 编号 | 验收项 | 预期结果 |
|------|--------|----------|
| F-1 | PMS 页面初始加载 | 所有 PMS 特有元素渲染正确 |
| F-2 | initial_balance 输入框 | 默认值 10000，可修改 |
| F-3 | 币种选择器 | 8 个选项，选择后 state 更新 |
| F-4 | 周期选择器 | 5 个选项 (15m/1h/4h/1d/1w) |
| F-5 | 表单验证 | 无效输入显示错误提示 |
| F-6 | PMS 回测执行 | 调用正确 API，payload 包含 initial_balance |
| F-7 | PMS 报告展示 | 显示仓位级追踪数据 |
| F-8 | 错误处理 | API 失败显示友好错误 |
| F-9 | 策略导入 | 可从模板导入策略 |
| F-10 | 回测历史 | 可查看 PMS 历史信号 |

### 6.2 PMS 特有验收

| 编号 | 验收项 | 预期结果 |
|------|--------|----------|
| P-1 | 初始资金范围 | min=100, max=1000000 |
| P-2 | PMS 报告字段 | 显示 initial_balance/final_balance/total_return |
| P-3 | 仓位列表 | 显示仓位级详细信息 |
| P-4 | 止盈止损追踪 | 显示 exit_reason (TP1/SL/TRAILING) |
| P-5 | 夏普比率 | 显示风险调整收益指标 |

### 6.3 边界条件验收

| 编号 | 边界场景 | 预期行为 |
|------|----------|----------|
| B-1 | initial_balance = 0 | HTML5 验证阻止 |
| B-2 | initial_balance > 1000000 | HTML5 验证阻止 |
| B-3 | 空策略列表 | 按钮禁用 |
| B-4 | API 超时 | 显示超时错误 |
| B-5 | 网络错误 | 显示连接失败 |

---

## 7. 与经典回测测试的区别

| 测试项 | 经典回测 (Backtest.test.tsx) | PMS 回测 (PMSBacktest.test.tsx) |
|--------|------------------------------|---------------------------------|
| API 端点 | `/api/backtest/signals` | `/api/backtest/pms` |
| 请求参数 | 无 initial_balance | 必须包含 initial_balance |
| 周期选项 | 7 个 (含 1m/5m) | 5 个 (15m 起) |
| 报告类型 | BacktestReport (信号级) | PMSBacktestReport (仓位级) |
| 核心指标 | 信号数/过滤数 | 收益率/胜率/回撤 |
| 展示组件 | 过滤器分布图 | 权益曲线/仓位列表 |

---

## 8. 参考文件

- 被测试组件：`web-front/src/pages/PMSBacktest.tsx`
- API 接口定义：`web-front/src/lib/api.ts` (PMSBacktestRequest/PMSBacktestReport)
- 现有测试参考：`web-front/src/pages/config/__tests__/StrategiesTab.test.tsx`
