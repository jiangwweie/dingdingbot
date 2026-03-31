# 回测信号 ATR 过滤器失效问题分析报告

**分析时间**: 2026-03-31
**问题报告**: 回测生成的信号 293 和 294 (ETH/USDT 1h SHORT) 波动率分别为 0.234% 和 0.256%，低于 ATR 过滤器要求的 0.5%，但仍然被生成。

---

## 📋 执行摘要

通过代码审查和配置分析，发现 **回测时使用的策略配置可能未包含 ATR 过滤器**。

**核心发现**:
1. 服务器 `user-prod.yaml` 配置中包含 ATR 过滤器（`logic_tree.children` 第 4 个节点）
2. 本地 `user.yaml` 配置中**没有**ATR 过滤器
3. 前端回测功能使用用户手动组装的策略配置，而非服务器配置
4. 回测日志中**未发现** ATR 过滤器拒绝记录

---

## 🔍 配置对比分析

### 服务器配置 (`/usr/local/monitorDog/config/user-prod.yaml`)

```yaml
active_strategies:
  - id: 1774704112251-34o2n0880
    name: 01pinbar-ema60
    logic_tree:
      gate: AND
      children:
        - type: trigger          # 1. Pinbar 触发器
          config:
            type: pinbar
            params:
              min_wick_ratio: 0.5
              max_body_ratio: 0.35
              body_position_tolerance: 0.3
        - type: filter           # 2. MTF 过滤器
          config:
            type: mtf
            enabled: true
        - type: filter           # 3. EMA 过滤器
          config:
            type: ema
            enabled: true
        - type: filter           # 4. ATR 过滤器 ✅
          config:
            type: atr
            enabled: true
            params: {}
```

### 本地配置 (`/Users/jiangwei/Documents/v2/config/user.yaml`)

```yaml
active_strategies:
  - id: 1774704112251-34o2n0880
    name: 01pinbar-ema60
    logic_tree:
      gate: AND
      children:
        - type: trigger          # 1. Pinbar 触发器
          config:
            type: pinbar
        - type: filter           # 2. MTF 过滤器
          config:
            type: mtf
        - type: filter           # 3. EMA 过滤器
          config:
            type: ema
        # ⚠️ 缺少 ATR 过滤器节点！
```

**差异**: 本地配置缺少 ATR 过滤器节点。

---

## 🧪 回测流程分析

### 回测请求处理流程

```
前端 Backtest.tsx
    ↓
构建 BacktestRequest { strategies: [...] }
    ↓
POST /api/backtest
    ↓
Backtester.run_backtest(request)
    ↓
_build_dynamic_runner(request.strategies)
    ↓
create_dynamic_runner(strategy_definitions)
    ↓
FilterFactory.create_chain(filters_config)
    ↓
DynamicStrategyRunner
```

### 关键代码路径

1. **前端构建策略配置** (`web-front/src/pages/Backtest.tsx:143-150`):
   ```typescript
   const payload: BacktestRequest = {
     symbol,
     timeframe,
     start_time: startTime!,
     end_time: endTime!,
     strategies,  // ← 用户在策略组装器中手动配置的策略
     risk_overrides: riskOverrides,
   };
   ```

2. **后端接收并反序列化** (`src/application/backtester.py:231-249`):
   ```python
   def _build_dynamic_runner(self, strategy_definitions: List[StrategyDefinition]):
       strategies = []
       for strat_def in strategy_definitions:
           if isinstance(strat_def, StrategyDefinition):
               strategies.append(strat_def)
           else:
               strategies.append(StrategyDefinition(**strat_def))
       return create_dynamic_runner(strategies)
   ```

3. **过滤器链创建** (`src/domain/strategy_engine.py:1094-1095`):
   ```python
   # Create filter chain from config
   filters = FilterFactory.create_chain(filters_config)
   ```

4. **ATR 过滤器实例化** (`src/domain/filter_factory.py:575-581`):
   ```python
   elif filter_type == "atr":
       return filter_class(
           period=params.get('period', 14),
           min_atr_ratio=params.get('min_atr_ratio', Decimal("0.001")),
           min_absolute_range=params.get('min_absolute_range', Decimal("0.1")),
           enabled=enabled
       )
   ```

---

## 📊 问题信号详细分析

### 信号 294: ETH/USDT 1h SHORT @ 2026-03-29 17:00

```
K 线数据:
  O:1783.6  H:1787.8  L:1779.5  C:1781.7

波动率分析:
  Candle Range: 1787.8 - 1779.5 = 8.3
  Range %: (8.3 / 1783.6) × 100 = 0.465%

ATR 过滤器要求:
  - 最小波幅比率：≥0.5%
  - 最小绝对波幅：≥0.1 USDT

判定:
  ❌ 0.465% < 0.5%  (波幅不足)
  ✅ 8.3 > 0.1      (绝对波幅达标)

预期结果：ATR 过滤器应拒绝
实际结果：信号被生成，tags 中无 ATR 标记
```

### 信号 293: ETH/USDT 1h SHORT @ 2026-03-29 16:00

```
K 线数据:
  O:1788.0  H:1792.1  L:1783.4  C:1791.0

波动率分析:
  Candle Range: 1792.1 - 1783.4 = 8.7
  Range %: (8.7 / 1788.0) × 100 = 0.487%

ATR 过滤器要求:
  - 最小波幅比率：≥0.5%
  - 最小绝对波幅：≥0.1 USDT

判定:
  ❌ 0.487% < 0.5%  (波幅不足)
  ✅ 8.7 > 0.1      (绝对波幅达标)

预期结果：ATR 过滤器应拒绝
实际结果：信号被生成，tags 中无 ATR 标记
```

---

## 🚨 根因分析

### 问题 1: 前端策略配置未包含 ATR 过滤器

**现象**: 用户在回测页面组装策略时，只添加了 3 个过滤器（MTF、EMA），未添加 ATR 过滤器。

**原因**:
- 前端 StrategyBuilder 组件默认创建的策略模板只包含 Pinbar 触发器
- 用户需要手动点击"添加过滤器"按钮并选择"ATR 波动率"
- 回测界面未默认加载服务器当前生效的配置

**证据**:
- 回测信号 tags 中包含 MTF 和 EMA，但无 ATR
- 日志中无 ATR 过滤器拒绝记录

### 问题 2: ATR 过滤器参数默认值过低

**代码位置**: `src/domain/filter_factory.py:576-580`

```python
elif filter_type == "atr":
    return filter_class(
        period=params.get('period', 14),
        min_atr_ratio=params.get('min_atr_ratio', Decimal("0.001")),  # ← 默认 0.1%
        min_absolute_range=params.get('min_absolute_range', Decimal("0.1")),
        enabled=enabled
    )
```

**问题**:
- `min_atr_ratio` 默认值为 `0.001` (0.1%)，而非配置的 `0.005` (0.5%)
- 当 `params` 为空 dict 时，使用默认值 0.1%，导致过滤器阈值过低

**服务器配置**: `user-prod.yaml` 中 `params: {}`（空对象）

### 问题 3: 回测与实盘配置不同步

**现象**: 服务器实盘配置包含 ATR 过滤器，但回测时使用的配置由前端手动组装。

**原因**:
- 回测功能设计为"策略沙箱"，允许用户自由组装策略
- 未提供"使用当前实盘配置"的快捷选项
- 用户可能 unaware 回测配置与实盘配置不同

---

## 🔧 修复建议

### 1. 🔴 高优先级：修复 ATR 过滤器默认参数

**问题**: `min_atr_ratio` 默认值 0.1% 过低

**修复**: 将默认值提升至 0.5%

```python
# src/domain/filter_factory.py:576-580
elif filter_type == "atr":
    return filter_class(
        period=params.get('period', 14),
        min_atr_ratio=params.get('min_atr_ratio', Decimal("0.005")),  # 修改为 0.5%
        min_absolute_range=params.get('min_absolute_range', Decimal("0.1")),
        enabled=enabled
    )
```

**或** 在配置中明确指定参数：

```yaml
# user-prod.yaml
- type: filter
  config:
    type: atr
    enabled: true
    params:
      min_atr_ratio: 0.005  # 明确指定 0.5%
      period: 14
```

### 2. 🟡 中优先级：前端默认策略包含 ATR 过滤器

**修改位置**: `web-front/src/components/StrategyBuilder.tsx`

默认创建策略时，自动添加 ATR 过滤器：

```typescript
const newStrategy: StrategyDefinition = {
  // ...
  filters: [
    {
      id: generateId(),
      type: 'mtf',
      enabled: true,
      params: {}
    },
    {
      id: generateId(),
      type: 'ema',
      enabled: true,
      params: {}
    },
    {
      id: generateId(),
      type: 'atr',
      enabled: true,
      params: { min_atr_ratio: 0.005, period: 14 }
    }
  ],
  // ...
};
```

### 3. 🟢 低优先级：添加"使用实盘配置"按钮

**修改位置**: `web-front/src/pages/Backtest.tsx`

在回测页面添加按钮，一键加载服务器当前生效的策略配置：

```typescript
const loadActiveStrategy = useCallback(async () => {
  const res = await fetch('/api/config');
  const config = await res.json();
  if (config.active_strategies) {
    setStrategies(config.active_strategies);
  }
}, []);
```

---

## 📝 验证步骤

### 验证修复 1: ATR 过滤器默认参数

1. 修改 `src/domain/filter_factory.py` 中的默认值
2. 运行回测，创建不包含 `params` 的 ATR 过滤器配置
3. 检查日志中 ATR 过滤器的阈值是否为 0.5%

### 验证修复 2: 前端默认配置

1. 打开回测页面
2. 点击"添加策略"
3. 展开策略，确认默认包含 ATR 过滤器
4. 运行回测，检查信号 tags 是否包含 ATR

### 验证修复 3: 信号标签生成

1. 运行回测，触发 ATR 过滤器拒绝
2. 检查 `signal_logs` 中 `filter_results` 是否包含 ATR 记录
3. 检查数据库中信号 `tags_json` 字段

---

## 📌 结论

**问题根因**: 前端回测使用的策略配置由用户手动组装，未包含 ATR 过滤器，导致低波动率信号未被过滤。

**次要问题**: ATR 过滤器默认参数 `min_atr_ratio` 为 0.1%，即使配置中包含 ATR 过滤器，阈值也过低。

**影响范围**:
- 回测功能生成的历史信号
- 不影响实盘信号（实盘配置正确包含 ATR 过滤器）

**修复优先级**:
1. 🔴 高：修复 ATR 过滤器默认参数（5 分钟）
2. 🟡 中：前端默认策略包含 ATR 过滤器（30 分钟）
3. 🟢 低：添加"使用实盘配置"按钮（1 小时）

---

**报告完成时间**: 2026-03-31 12:30
