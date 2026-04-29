# Backtest.test.tsx 测试设计文档

**创建日期**: 2026-04-06  
**优先级**: P1  
**状态**: 设计中

---

## 1. 测试文件路径

```
gemimi-web-front/src/pages/__tests__/Backtest.test.tsx
```

---

## 2. 测试目标

验证经典回测页面 (`Backtest.tsx`) 的完整功能，包括：
- 表单配置 UI 渲染正确性
- 快速配置区与高级配置区的交互
- 表单验证逻辑
- 回测执行流程
- 结果展示与错误处理
- 边界条件处理

---

## 3. 测试用例清单 (10 个)

### 3.1 初始渲染测试

```typescript
it('should render all form elements on initial load', async () => {
  // 验证快速配置区
  - 渲染币种选择器 (8 个选项：BTC/ETH/SOL/BNB/XRP/ADA/DOGE/MATIC)
  - 渲染周期选择器 (7 个选项：1m/5m/15m/1h/4h/1d/1w)
  - 渲染日期范围选择器 (QuickDateRangePicker)
  - 渲染 [一键执行回测] 按钮 (初始禁用状态)
  
  // 验证高级配置区
  - 高级配置默认处于折叠状态
  - 展开按钮可见
  
  // 验证空状态
  - 显示"等待执行回测"提示
})
```

### 3.2 快速配置区交互测试

```typescript
it('should update state when selecting symbol/timeframe', async () => {
  // 选择币种
  - 用户选择 ETH/USDT:USDT
  - 验证 state 正确更新
  
  // 选择周期
  - 用户选择 4h
  - 验证 state 正确更新
  
  // 日期选择
  - QuickDateRangePicker 返回有效时间戳
  - startTime < endTime 时验证通过
})
```

### 3.3 高级配置折叠/展开测试

```typescript
it('should toggle advanced config panel on click', async () => {
  // 初始状态
  - 高级配置面板处于折叠状态
  - 看不到滑点/手续费输入框
  
  // 点击展开
  - 点击展开按钮
  - 显示策略组装工作台 (StrategyBuilder)
  - 显示风控参数覆写区域
  - 最大亏损比例输入框可见
  - 测试杠杆倍数输入框可见
  
  // 点击折叠
  - 再次点击折叠按钮
  - 高级配置区域隐藏
})
```

### 3.4 表单验证测试

```typescript
it('should show validation errors for invalid inputs', async () => {
  // 未选日期
  - 点击 [一键执行回测]
  - 显示错误："请选择起始和结束时间"
  
  // 起始时间 > 结束时间
  - 设置 startTime = 2026-04-06, endTime = 2026-04-01
  - 点击 [一键执行回测]
  - 显示错误："起始时间必须早于结束时间"
  
  // 未配置策略
  - 选择日期范围
  - 策略列表为空
  - 点击 [一键执行回测]
  - 显示错误："请至少配置一个策略"
})
```

### 3.5 回测执行流程测试

```typescript
it('should execute backtest and display results', async () => {
  // 准备有效表单
  - 选择 BTC/USDT:USDT
  - 选择 1h 周期
  - 选择有效日期范围
  - 配置 Pinbar 策略
  
  // 点击执行
  - 点击 [一键执行回测]
  - 按钮显示 loading 状态："回测引擎运行中..."
  - 按钮禁用
  
  // API 调用验证
  - 调用 runSignalBacktest(payload)
  - payload 包含正确的 symbol/timeframe/strategies
  
  // 成功响应
  - 显示回测报告看板
  - 显示 4 个指标卡片：
    * 符合策略信号数
    * 被拦截信号数
    * 分析 K 线数
    * 执行耗时
  - 显示过滤器拦截分布图
})
```

### 3.6 回测结果展示测试

```typescript
it('should display backtest report dashboard', async () => {
  // Mock 回测报告数据
  const mockReport: BacktestReport = {
    total_signals: 15,
    total_filtered: 42,
    filtered_by_filters: {
      ema_trend: 25,
      mtf_validation: 12,
      volume_surge: 5,
    },
    signal_logs: [...],
    execution_time_ms: 1250,
    klines_analyzed: 1000,
  };
  
  // 验证指标卡片
  - 显示"符合策略信号 15"
  - 显示"被拦截信号 42"
  - 显示"分析 K 线数 1,000"
  - 显示"执行耗时 1250ms"
  
  // 验证过滤器分布
  - 显示 EMA 趋势过滤：25 (59.5%)
  - 显示 MTF 验证过滤：12 (28.6%)
  - 显示成交量激增过滤：5 (11.9%)
})
```

### 3.7 日志视图切换测试

```typescript
it('should switch between dashboard and logs view', async () => {
  // 初始视图
  - 默认显示"指标看板"视图
  
  // 切换到日志视图
  - 点击 [日志流水] 标签
  - 显示信号日志表格
  
  // 验证表格列
  - 时间戳列
  - 策略列
  - 触发器列
  - 过滤器列
  - 结果列
  - 详情列
  
  // 切换回指标看板
  - 点击 [指标看板] 标签
  - 恢复显示指标卡片
})
```

### 3.8 错误处理测试

```typescript
it('should display error message on API failure', async () => {
  // Mock API 错误
  vi.mocked(runSignalBacktest).mockRejectedValue({
    info: {
      detail: [
        { loc: ['body', 'symbol'], msg: 'invalid symbol' }
      ]
    }
  });
  
  // 点击执行
  - 点击 [一键执行回测]
  
  // 错误展示
  - 显示红色错误卡片
  - 显示错误标题："回测失败"
  - 显示错误详情："body.symbol: invalid symbol"
})
```

### 3.9 策略模板导入测试

```typescript
it('should import strategy from template picker', async () => {
  // 点击导入按钮
  - 点击 [从策略工作台导入]
  - 显示 StrategyTemplatePicker 弹窗
  
  // 选择策略
  - 选择 "Pinbar 保守策略"
  - 点击确认
  
  // 验证导入
  - 弹窗关闭
  - StrategyBuilder 显示导入的策略
})
```

### 3.10 回测历史测试

```typescript
it('should fetch and display backtest signals history', async () => {
  // 点击历史按钮
  - 点击 [回测历史]
  - 显示抽屉式历史面板
  
  // 加载状态
  - 显示"加载中..."
  
  // 成功加载
  - 显示信号历史表格
  - 列：时间/币种/周期/方向/策略/入场价/止损价/操作
  
  // 空状态
  - 无数据时显示"暂无回测信号记录"
})
```

---

## 4. Fixtures 设计

```typescript
// ============================================================
// Mock 数据 Fixtures
// ============================================================

/**
 * 模拟策略列表
 */
const mockStrategies: StrategyDefinition[] = [
  {
    id: 'strat-001',
    name: 'Pinbar 保守策略',
    trigger_config: {
      type: 'pinbar',
      params: {
        min_wick_ratio: 0.6,
        max_body_ratio: 0.3,
        body_position_tolerance: 0.1,
      },
    },
    filter_configs: [
      {
        id: 'f1',
        type: 'ema',
        enabled: true,
        params: { period: 60, trend_direction: 'bullish' },
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
 * 模拟回测报告
 */
const mockBacktestReport: BacktestReport = {
  total_signals: 15,
  total_filtered: 42,
  filtered_by_filters: {
    ema_trend: 25,
    mtf_validation: 12,
    volume_surge: 5,
  },
  signal_logs: [
    {
      timestamp: 1700000000000,
      symbol: 'BTC/USDT:USDT',
      timeframe: '1h',
      strategy_name: 'Pinbar 保守策略',
      trigger_type: 'pinbar',
      trigger_passed: true,
      filters_passed: [
        { node_name: 'ema', passed: true },
        { node_name: 'mtf', passed: true },
      ],
      signal_fired: true,
      direction: 'long',
      entry_price: 52000,
      stop_loss: 51000,
    },
    {
      timestamp: 1700003600000,
      symbol: 'BTC/USDT:USDT',
      timeframe: '1h',
      trigger_type: 'pinbar',
      trigger_passed: false,
      filters_passed: [],
      signal_fired: false,
      filter_stage: 'ema_trend',
      filter_reason: 'EMA 趋势不符',
    },
  ],
  execution_time_ms: 1250,
  klines_analyzed: 1000,
  // Legacy field aliases
  signal_stats: {
    signals_fired: 15,
    filtered_by_filters: {
      ema_trend: 25,
      mtf_validation: 12,
      volume_surge: 5,
    },
  },
  attempts: [],
  candles_analyzed: 1000,
};

/**
 * 模拟回测历史信号
 */
const mockBacktestSignals: Signal[] = [
  {
    id: 'sig-001',
    created_at: '2026-04-01T10:00:00Z',
    symbol: 'BTC/USDT:USDT',
    timeframe: '1h',
    direction: 'long',
    entry_price: '52000.00',
    stop_loss: '51000.00',
    position_size: '0.1',
    leverage: 10,
    tags: [{ name: 'EMA', value: 'Bullish' }],
    status: 'OPEN',
    strategy_name: 'Pinbar 保守策略',
    score: 0.85,
  },
];

// ============================================================
// MSW Request Interceptors
// ============================================================

const mockApiHandlers = [
  // GET /api/strategies/templates
  http.get('/api/strategies/templates', () => {
    return HttpResponse.json({
      templates: [
        { id: 1, name: 'Pinbar 保守策略', description: '基于 Pinbar 形态' },
        { id: 2, name: 'Engulfing 激进策略', description: '吞没形态策略' },
      ],
    });
  }),
  
  // POST /api/backtest/signals
  http.post('/api/backtest/signals', async ({ request }) => {
    const payload = await request.json();
    // 验证 payload 结构
    expect(payload).toHaveProperty('symbol');
    expect(payload).toHaveProperty('timeframe');
    expect(payload).toHaveProperty('start_time');
    expect(payload).toHaveProperty('end_time');
    
    return HttpResponse.json(mockBacktestReport);
  }),
  
  // GET /api/backtest/signals/history
  http.get('/api/backtest/signals/history', () => {
    return HttpResponse.json({
      signals: mockBacktestSignals,
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

// 1. Mock window.matchMedia (Ant Design 需要)
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

// 2. Mock API 模块
vi.mock('../../../lib/api', () => ({
  runSignalBacktest: vi.fn(),
  fetchStrategyTemplates: vi.fn(),
  fetchBacktestSignals: vi.fn(),
}));

// 3. Mock 子组件 (简化测试)
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
      <button onClick={() => onStartChange(1700000000000)}>设置开始时间</button>
      <button onClick={() => onEndChange(1700086400000)}>设置结束时间</button>
    </div>
  ),
}));

vi.mock('../../../components/StrategyTemplatePicker', () => ({
  __esModule: true,
  default: ({ open, onClose, onSelect }) => open ? (
    <div data-testid="template-picker">
      <button onClick={() => onSelect(mockStrategies[0])}>选择 Pinbar 策略</button>
      <button onClick={onClose}>关闭</button>
    </div>
  ) : null,
}));
```

---

## 6. 验收标准

### 6.1 功能验收

| 编号 | 验收项 | 预期结果 |
|------|--------|----------|
| F-1 | 页面初始加载 | 所有表单元素渲染正确 |
| F-2 | 币种选择器 | 8 个选项可选，选择后 state 更新 |
| F-3 | 周期选择器 | 7 个选项可选，选择后 state 更新 |
| F-4 | 日期选择器 | 返回有效时间戳，startTime < endTime |
| F-5 | 高级配置折叠 | 默认折叠，点击可展开/折叠 |
| F-6 | 表单验证 | 无效输入显示清晰错误提示 |
| F-7 | 回测执行 | 调用正确 API，显示 loading 状态 |
| F-8 | 结果展示 | 4 个指标卡片 + 过滤器分布图 |
| F-9 | 日志视图 | 可切换查看信号日志表格 |
| F-10 | 错误处理 | API 失败显示友好错误信息 |
| F-11 | 策略导入 | 可从模板导入策略 |
| F-12 | 回测历史 | 可查看历史信号列表 |

### 6.2 边界条件验收

| 编号 | 边界场景 | 预期行为 |
|------|----------|----------|
| B-1 | 空策略列表 | 按钮禁用，点击提示"请至少配置一个策略" |
| B-2 | API 超时 | 显示"请求超时，请重试" |
| B-3 | 网络错误 | 显示"网络连接失败" |
| B-4 | 日期范围无效 | startTime >= endTime 时显示错误 |
| B-5 | 回测无数据 | 显示"暂无数据"空状态 |

### 6.3 性能验收

| 编号 | 指标 | 目标值 |
|------|------|--------|
| P-1 | 初始渲染时间 | < 500ms |
| P-2 | 交互响应时间 | < 100ms |
| P-3 | 组件卸载 | 无内存泄漏 |

---

## 7. 依赖组件

- `StrategyBuilder` - 策略组装器
- `QuickDateRangePicker` - 快捷日期选择器
- `StrategyTemplatePicker` - 策略模板选择器
- `SignalDetailsDrawer` - 信号详情抽屉
- `BacktestOverviewCards` - 回测概览卡片
- `EquityComparisonChart` - 权益曲线对比图
- `TradeStatisticsTable` - 交易统计表
- `PnLDistributionHistogram` - 盈亏分布直方图
- `MonthlyReturnHeatmap` - 月度收益热力图

---

## 8. 参考文件

- 被测试组件：`gemimi-web-front/src/pages/Backtest.tsx`
- API 接口定义：`gemimi-web-front/src/lib/api.ts`
- 现有测试参考：`gemimi-web-front/src/pages/config/__tests__/StrategiesTab.test.tsx`
