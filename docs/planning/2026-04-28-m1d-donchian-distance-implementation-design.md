# M1d Donchian Distance Filter — 实现设计

**日期**: 2026-04-28
**类型**: Design-only review（不涉及代码修改或 git 操作）
**前置**: M1/M1b/M1c 三重口径验证均 PASS（E4 Donchian Distance Toxic Filter）

---

## 设计背景

M1/M1b/M1c 已证明 `distance_to_donchian_20_high < -0.016809` 是跨口径稳定的 toxic-state filter。现在设计如何将 E4 从实验脚本中迁移到正式策略/回测系统。

**关键约束**:
- `FilterContext` 仅含当前 kline + 趋势方向，**无 N-bar 历史**
- 有状态过滤器（EMA、ATR）通过 `update_state(kline)` 逐根积累内部状态
- `kline_history` 在 `run_all()` 中存在，但只传给策略（如 Engulfing），不传给过滤器
- 过滤器链短路语义：第一个 FAIL 即停止

---

## A. 推荐实现方案

### 作为**有状态通用过滤器** `donchian_distance`

**设计要点**:
- 注册为 `FilterFactory._registry["donchian_distance"]`，通用（不限于 Pinbar）
- 继承 `FilterBase`，标记 `is_stateful = True`
- 通过 `update_state(kline)` 逐根积累 high/low，维护滚动窗口
- `check()` 时计算 Donchian 通道上轨（N 根最高价），然后判断 `close` 与上轨的距离

**状态管理**:
```python
class DonchianDistanceFilterDynamic(FilterBase):
    def __init__(self, lookback: int = 20, threshold: float = -0.016809,
                 direction_aware: bool = True, enabled: bool = False):
        self._lookback = lookback
        self._threshold = threshold      # 默认 M0 tercile boundary
        self._direction_aware = direction_aware
        self._enabled = enabled
        # Per-symbol:timeframe state
        self._state: Dict[str, List[Decimal]] = {}  # rolling high window

    def update_state(self, kline, symbol, timeframe):
        key = f"{symbol}:{timeframe}"
        if key not in self._state:
            self._state[key] = []
        self._state[key].append(kline.high)
        # 保留 lookback+1 根（current bar excluded from Donchian）
        if len(self._state[key]) > self._lookback + 1:
            self._state[key] = self._state[key][-(self._lookback + 1):]

    def check(self, pattern, context):
        # Donchian high = max(highs of PREVIOUS lookback bars, excluding current)
        # 用 lookback 根**历史** K 线的 high，不包含当前 K 线 → 防止未来函数
        key = f"{context.kline.symbol}:{context.current_timeframe}"
        window = self._state.get(key, [])
        if len(window) < self._lookback + 1:
            return TraceEvent(passed=True, reason="insufficient_data")  # 不够数据时不过滤

        # 排除最后一根（当前 K 线），取前 lookback 根
        historical_highs = window[-(self._lookback + 1):-1]
        dc_high = max(historical_highs)

        distance = (context.current_price - dc_high) / dc_high  # always ≤ 0

        if self._direction_aware and pattern.direction == Direction.SHORT:
            # SHORT 信号：检查 Donchian 下轨
            # （当前仅验证 LONG，SHORT 扩展待研究）
            return TraceEvent(passed=True, reason="short_not_filtered")

        if distance < self._threshold:
            return TraceEvent(passed=False, reason="too_close_to_donchian_high",
                              actual=f"{distance:.6f}", expected=f">= {self._threshold}")
        return TraceEvent(passed=True, reason="donchian_distance_ok")
```

**理由**:
1. 不修改 `FilterContext`，完全兼容现有架构
2. 有状态过滤器模式与 EMA/ATR 一致
3. 通用注册，任何策略（Pinbar、Engulfing、未来策略）均可使用
4. `default=False` 不影响现有 sim1_eth_runtime

---

## B. 备选方案

### B1. 无状态方案（修改 FilterContext 传入 kline_history）

- 修改 `FilterContext` 增加 `kline_history: List[KlineData]`
- `run_all()` 中将 `kline_history` 传入 `FilterContext`
- `check()` 内直接取历史窗口计算 Donchian

**问题**: 修改 `FilterContext` 影响所有已有过滤器的签名，且违反 "状态由 update_state 积累" 的架构约定。不推荐。

### B2. Pinbar 专用方案（在 Pinbar strategy 内部计算）

- 在 `PinbarStrategy.detect()` 中计算 Donchian distance
- 信号质量评分 `score` 中加入 distance 惩罚

**问题**: 将 filter 逻辑耦合到 strategy，无法复用于 Engulfing 等其他策略，违反关注点分离。不推荐。

### B3. 预计算指标方案（在 BacktestRunner 外部预计算 Donchian）

- 在 backtester 数据加载阶段预计算 Donchian 上轨序列
- 注入到 runner 或 filter 作为外部数据源

**问题**: 仅适用于回测，live 模式下无法预计算。架构不对称。不推荐。

---

## C. 需要修改的文件

| 文件 | 修改类型 | 修改内容 |
|------|----------|----------|
| `src/domain/filter_factory.py` | **新增** class | 新增 `DonchianDistanceFilterDynamic` 类 |
| `src/domain/filter_factory.py` | 修改 registry | `_registry` 中添加 `"donchian_distance": DonchianDistanceFilterDynamic` |
| `src/domain/filter_factory.py` | 修改 `create()` | 添加 `elif filter_type == "donchian_distance":` 分支 |
| `tests/unit/test_donchian_distance_filter.py` | **新增** | 新增单元测试文件 |
| `src/domain/models.py` | 可选 | `FilterConfig` 文档中新增 donchian_distance 示例 |

**不需要修改的文件**:
- `FilterContext` — 不变
- `strategy_engine.py` — `run_all()` 逻辑不变（`update_state` + `check` 已覆盖新 filter）
- `backtester.py` — 无需修改（filter chain 创建和执行逻辑通用）
- Pinbar / Engulfing strategy — 策略代码不变

---

## D. 数据流设计

```
[Backtest / Live 循环]
    │
    ├─── 每根 K 线 ──→ runner.update_state(kline)
    │                       │
    │                       ├──→ EmaTrendFilter.update_state()
    │                       ├──→ AtrFilter.update_state()
    │                       └──→ DonchianDistanceFilter.update_state()  ← NEW
    │                               └── 累积 high 值，维护滚动窗口
    │
    └─── 形态检测后 ──→ runner.run_all(kline, trends, kline_history)
                            │
                            ├──→ strategy.detect(kline) → PatternResult?
                            │       (无 pattern → 跳过)
                            │
                            ├──→ FilterContext(kline, trends, ...)
                            │
                            └──→ filter_chain.check(pattern, context)
                                    ├──→ EmaTrendFilter.check()     → TraceEvent
                                    ├──→ AtrFilter.check()          → TraceEvent
                                    ├──→ DonchianDistanceFilter.check()  ← NEW
                                    │       ├── 内部取 state[lookback+1:-1] 计算 dc_high
                                    │       ├── distance = (close - dc_high) / dc_high
                                    │       └── distance < threshold → FAIL
                                    └──→ (短路: 任一 FAIL 即停止)
```

**关键**: Donchian 计算完全在 filter 内部完成，不依赖 `FilterContext` 扩展。

---

## E. 参数模型

```python
{
    "type": "donchian_distance",
    "enabled": false,              # 默认关闭，不影响现有 runtime
    "params": {
        "lookback": 20,            # Donchian 通道周期（默认 20）
        "threshold": -0.016809,    # 距离阈值（M0 tercile boundary）
        "direction_aware": true    # true = LONG 检查上轨，SHORT 检查下轨
    }
}
```

### 参数说明

| 参数 | 类型 | 默认值 | 来源 | 说明 |
|------|------|--------|------|------|
| `lookback` | int | 20 | M0 研究 (Donchian 20) | 回看周期 |
| `threshold` | float | -0.016809 | M0 tercile boundary | 距离阈值，`distance < threshold` 时过滤 |
| `direction_aware` | bool | true | — | LONG 信号检查上轨，SHORT 信号检查下轨 |
| `enabled` | bool | false | 安全默认 | 现有 runtime 默认不启用 |

### 距离公式

```python
# LONG 信号: 检查与 Donchian 上轨的距离
distance = (close - dc_high) / dc_high   # always ≤ 0

# SHORT 信号 (direction_aware=True): 检查与 Donchian 下轨的距离
distance = (dc_low - close) / dc_low     # always ≤ 0
```

### 阈值可调性

`threshold` 为 negative float。更负 = 更激进（只过滤极端接近通道边界的信号）；更接近 0 = 更保守（更多信号被过滤）。

| 阈值 | 含义 | 预期过滤率 |
|------|------|-----------|
| -0.005 | 价格距上轨 < 0.5% 即过滤 | 较高 |
| -0.016809 | M0 tercile boundary (研究默认) | ~5% |
| -0.03 | 价格距上轨 < 3% 才过滤 | 较低 |

---

## F. 未来函数防护

### 问题

Donchian 通道使用 N 根 K 线的 high/low。如果使用**当前 K 线**的 high 来计算通道上轨，再判断当前 close 是否接近上轨，存在轻微的"信息泄漏"（用到了当前 bar 的 high，而 close 可能在 high 之前被确定）。

### 防护策略

**排除当前 K 线，只用历史 K 线计算 Donchian**:

```python
# update_state() 累积所有 K 线（包含当前）
self._state[key].append(kline.high)

# check() 时排除最后一根（当前 K 线），取前 lookback 根
# window = [bar_{n-lookback}, ..., bar_{n-1}, bar_n]  ← bar_n = 当前
# historical_highs = window[-(lookback+1):-1]  ← 只取 bar_{n-lookback} 到 bar_{n-1}
dc_high = max(historical_highs)
```

**为什么这是保守的**:
- 用 `kline.high`（而非 `close`）作为 Donchian 上轨，已经避免了用 close 判断 close 的问题
- 排除当前 K 线后，Donchian 完全由**已完成的历史 K 线**决定，零未来函数风险

### 数据需求

`update_state()` 需要积累 `lookback + 1` 根 K 线后才能开始过滤（前 lookback 根不够时，`check()` 返回 `passed=True`，不过滤 — 安全降级）。

---

## G. 测试计划

### 单元测试矩阵

| 测试 | 输入 | 预期 |
|------|------|------|
| `test_warmup_insufficient_data` | < lookback+1 根 K 线 | `passed=True`（不过滤） |
| `test_distance_below_threshold` | close 远低于 dc_high（distance < threshold） | `passed=True` |
| `test_distance_above_threshold_filtered` | close 接近 dc_high（distance >= threshold） | `passed=False` |
| `test_distance_exact_threshold` | distance == threshold | `passed=True`（`<` 不含等于） |
| `test_current_bar_excluded` | 构造当前 bar high = 新高，但前 N 根 dc_high 较低 | 用前 N 根计算，不受当前 bar 影响 |
| `test_disabled_filter` | `enabled=False` | `passed=True` |
| `test_short_direction_aware` | SHORT signal + `direction_aware=True` | 检查下轨，不检查上轨 |
| `test_short_direction_not_aware` | SHORT signal + `direction_aware=False` | 检查上轨（同 LONG） |
| `test_multiple_symbols` | 两个 symbol 各自维护独立状态 | 各自 Donchian 不互相干扰 |
| `test_window_rolling` | 累积 > lookback+1 根 K 线 | 只保留最近 lookback+1 根 |

### 集成测试

| 测试 | 场景 | 预期 |
|------|------|------|
| `test_factory_creates_donchian_filter` | `FilterFactory.create({"type":"donchian_distance",...})` | 返回 `DonchianDistanceFilterDynamic` 实例 |
| `test_filter_chain_with_donchian` | EMA + MTF + Donchian 串联 | 短路语义正确 |
| `test_register_custom_filter` | `FilterFactory.register_filter("donchian_distance", cls)` | 成功注册 |

### 回归测试

| 测试 | 场景 | 预期 |
|------|------|------|
| `test_no_donchian_default` | 现有 sim1_eth_runtime 配置（无 donchian filter） | 行为不变 |
| `test_existing_filters_unaffected` | 添加 donchian filter 后 EMA/ATR/MTF 行为 | 行为不变 |

### 回测对齐测试

| 测试 | 场景 | 预期 |
|------|------|------|
| `test_m1c_parity` | 用正式 filter 复现 M1c E4 实验 | PnL 差异 < 1%（脚本 vs 系统） |

---

## H. 是否建议现在实现

### 建议：**现在实现，分两步**

#### 第一步（当前）：Research/Backtest 可用
- 在 `filter_factory.py` 中新增 `DonchianDistanceFilterDynamic` class
- 注册到 `_registry["donchian_distance"]`
- 添加 `create()` 分支处理
- 编写单元测试
- **工作量**: ~2h

**此时**:
- 研究脚本可以改用正式 filter 替代手写 lambda
- Backtester 可通过配置启用 donchian_distance filter
- sim1_eth_runtime 不受影响（`enabled: false`）

#### 第二步（未来）：Pinbar(E4) + T1 组合验证
- 在 official backtester 中用 `donchian_distance` filter 跑 Pinbar(E4) continuous baseline
- 如果 official E4 continuous PnL > 0，做 Pinbar(E4) + T1 组合验证
- 验证 "移除 T1 Top 3 后组合不崩" 是否改善

#### 不建议推迟的理由
1. M1/M1b/M1c 三重验证均 PASS，风险低
2. 实现简单（单文件修改，不涉及架构变更）
3. `enabled=False` 安全默认，零影响
4. 为 C2 报告指出的 "Pinbar continuous PnL 太低" 问题提供基础设施支撑

---

## 附录：与 M1c 脚本的对照

| 维度 | M1c 脚本（手写） | 正式实现 |
|------|-----------------|---------|
| Donchian 计算 | `FeatureComputer` 类内部 `deque(maxlen=20)` | `DonchianDistanceFilterDynamic.update_state()` 滚动窗口 |
| 阈值判断 | `lambda s: s.distance_to_donchian_20_high < -0.016809` | `DonchianDistanceFilterDynamic.check()` |
| 预热处理 | 跳过前 N 根 | `check()` 返回 `passed=True`（安全降级） |
| 当前 K 线排除 | 脚本中未排除（使用当前 bar 的 high） | **正式实现排除**（更保守） |
| LONG/SHORT | 仅 LONG | `direction_aware=True` 支持双向 |

**注意**: M1c 脚本中 Donchian 使用了当前 bar 的 high（`deque` 在信号判断前 append），正式实现排除当前 bar，可能导致正式实现过滤率略低。这是有意为之 — 正式实现更保守，防止未来函数。

---

## 产出文件

| 文件 | 说明 |
|------|------|
| `docs/planning/2026-04-28-m1d-donchian-distance-implementation-design.md` | 本设计文档 |
