# 诊断报告：回测系统亏损问题根因分析

**报告编号**: DA-20260418-001
**优先级**: 🔴 P0
**诊断日期**: 2026-04-18
**诊断师**: Diagnostic Analyst

---

## 问题描述

| 字段 | 内容 |
|------|------|
| **用户报告** | 回测多笔交易，基本没有正收益 |
| **影响范围** | 所有回测报告（18个），特别是 BTC 15m 周期 |
| **出现频率** | 100%（所有回测报告） |
| **数据异常** | positions 表为空（0条），但 position_close_events 有 678 条 |

### 关键数据

**最差表现报告**（BTC 15m）:
- 总回报率: **-98.56%**（接近爆仓）
- 胜率: 35.3%（41胜 / 75负）
- 总交易: 116 笔
- 止损次数: 75 次（平均亏损 -182.4 USDT/笔）
- 止盈次数: 22 次（平均盈利 +205.1 USDT/笔）

**止盈止损统计**:
```
止损（SL）: 452 次（占总平仓的 66.7%）
止盈（TP1）: 226 次（占总平仓的 33.3%）
```

**盈亏比分析**:
- 平均止损亏损: -182.4 USDT
- 平均止盈盈利: +205.1 USDT
- **盈亏比**: 205.1 / 182.4 = **1.12**（严重偏低！）

---

## 排查过程

### 假设验证

| 假设 | 可能性 | 验证方法 | 结果 |
|------|--------|---------|------|
| 1. 止损距离过大 | 高 | 检查 RiskCalculator.calculate_stop_loss() | ✅ **确认** |
| 2. 止盈目标过小 | 高 | 检查默认 TP 配置 | ✅ **确认** |
| 3. 滑点/手续费过高 | 中 | 检查撮合引擎配置 | ❌ 正常 |
| 4. 策略信号质量差 | 中 | 检查 Pinbar 参数 | ⚠️ 部分影响 |
| 5. positions 表数据丢失 | 低 | 检查数据库写入逻辑 | ❌ 非问题根因 |

### 根因定位 (5 Why)

```
Why 1: 为什么回测严重亏损？
→ 止损次数远多于止盈次数（75 vs 22），且平均止损亏损过大（-182.4 USDT）

Why 2: 为什么止损次数远多于止盈？
→ 止损距离过小（Pinbar low/high），导致容易被触发

Why 3: 为什么止损距离过小？
→ RiskCalculator.calculate_stop_loss() 直接使用 Pinbar 的 low/high 作为止损价
   对于 15m 周期，Pinbar 的 low/high 距离 entry 很近（可能只有 0.5%-1%）

Why 4: 为什么止盈目标无法弥补止损亏损？
→ 默认止盈配置为 TP1=1.5R, TP2=3.0R，但实际止盈距离/止损距离 = 1.12
   说明止盈目标设置不合理，或者止盈被提前触发

Why 5: 为什么盈亏比只有 1.12？
→ 根本原因：
   ① 止损距离 = Pinbar low/high 距离 entry 的距离（15m 周期很小）
   ② 止盈目标 = Entry + 1.5 × 止损距离（理论值）
   ③ 实际止盈价格 = 止盈目标 × (1 - 0.05% 滑点)
   ④ 实际止损价格 = 止损价 × (1 - 0.1% 滑点)
   ⑤ 由于 15m 周期波动小，止盈目标经常无法触及，而止损容易被触发
```

**问题代码位置**:

1. **止损计算**: `src/domain/risk_calculator.py:60-88`
   ```python
   def calculate_stop_loss(self, kline: KlineData, direction: Direction) -> Decimal:
       if direction == Direction.LONG:
           stop_loss = kline.low  # ❌ 直接使用 Pinbar low，距离太近
       else:
           stop_loss = kline.high  # ❌ 直接使用 Pinbar high，距离太近
       return self._quantize_price(stop_loss, kline.close)
   ```

2. **默认止盈配置**: `src/domain/risk_calculator.py:215-223`
   ```python
   def _get_default_take_profit_config(self) -> TakeProfitConfig:
       return TakeProfitConfig(
           enabled=True,
           levels=[
               TakeProfitLevel(id="TP1", position_ratio=Decimal("0.5"), risk_reward=Decimal("1.5")),
               # ❌ 1.5R 对于 15m 周期可能不够，需要至少 2R-3R
               TakeProfitLevel(id="TP2", position_ratio=Decimal("0.5"), risk_reward=Decimal("3.0")),
           ]
       )
   ```

3. **撮合引擎悲观原则**: `src/domain/matching_engine.py:122-162`
   ```python
   # 按优先级排序订单：SL > TP > ENTRY
   sorted_orders = self._sort_orders_by_priority(active_orders)
   # ❌ 同一 K 线内，止损优先于止盈判定，导致假突破时更容易止损
   ```

---

## 核心问题总结

### 问题 1: 止损距离过小（🔴 P0）

**当前逻辑**:
- LONG 止损 = Pinbar low
- SHORT 止损 = Pinbar high

**问题**:
- 15m 周期 Pinbar 的 low/high 距离 entry 可能只有 0.5%-1%
- 正常市场波动即可触发止损
- 未考虑 Pinbar 形态质量（wick_ratio, body_ratio）

**影响**:
- 止损触发率高达 66.7%
- 平均止损亏损 -182.4 USDT/笔

### 问题 2: 止盈目标不合理（🟠 P1）

**当前配置**:
- TP1 = 1.5R（平仓 50%）
- TP2 = 3.0R（平仓 50%）

**问题**:
- 1.5R 对于 15m 周期偏小，但对于 4h 周期可能合适
- 未根据周期动态调整止盈目标
- 实际盈亏比只有 1.12，远低于理论值 1.5

**影响**:
- 即使触发止盈，盈利也无法弥补止损亏损
- 盈亏比失衡

### 问题 3: 撮合引擎悲观原则过强（🟡 P2）

**当前逻辑**:
- 同一 K 线内，止损优先级 > 止盈优先级
- 止损滑点 0.1%，止盈滑点 0.05%

**问题**:
- 假突破时，止损先于止盈判定
- 对于高频周期（15m），假突破概率高

**影响**:
- 增加了止损触发概率
- 降低了实际盈亏比

### 问题 4: positions 表为空（🟢 P3）

**现象**:
- positions 表: 0 条记录
- position_close_events: 678 条记录

**原因**:
- 回测引擎使用内存中的 `positions_map: Dict[str, Position]`
- 未持久化到数据库的 `positions` 表
- 仅持久化了 `position_close_events`（平仓事件）

**影响**:
- 无法查询历史持仓详情
- 不影响回测结果准确性（数据在内存中）

---

## 修复方案

### 方案 A: 动态止损距离（推荐 🔥）

**核心思路**: 根据 Pinbar 形态质量和周期动态调整止损距离

**修改内容**:

**文件**: `src/domain/risk_calculator.py`
**位置**: 第 60-88 行

**当前代码**:
```python
def calculate_stop_loss(self, kline: KlineData, direction: Direction) -> Decimal:
    if direction == Direction.LONG:
        stop_loss = kline.low
    else:
        stop_loss = kline.high
    return self._quantize_price(stop_loss, kline.close)
```

**修改为**:
```python
def calculate_stop_loss(
    self,
    kline: KlineData,
    direction: Direction,
    pattern_score: Optional[float] = None,  # 新增：形态质量评分
    timeframe: Optional[str] = None,  # 新增：周期
) -> Decimal:
    """
    动态止损距离计算

    核心逻辑:
    1. 基础止损 = Pinbar low/high
    2. 形态质量调整: score 越高，止损距离可以越小
    3. 周期调整: 周期越小，止损距离需要越大（波动相对大）

    Args:
        kline: K 线数据
        direction: 方向
        pattern_score: Pinbar 形态质量评分 (0-1)
        timeframe: 周期 ("15m", "1h", "4h", "1d")

    Returns:
        动态调整后的止损价格
    """
    # Step 1: 基础止损
    if direction == Direction.LONG:
        base_stop = kline.low
    else:
        base_stop = kline.high

    # Step 2: 计算止损距离
    stop_distance = abs(kline.close - base_stop)

    # Step 3: 动态调整系数
    # 3.1 形态质量调整 (score 越高，系数越小，止损越近)
    if pattern_score is not None:
        # score=0.6 → 系数=1.5, score=1.0 → 系数=1.0
        quality_factor = Decimal('2.0') - Decimal(str(pattern_score))
    else:
        quality_factor = Decimal('1.5')  # 默认扩大 1.5 倍

    # 3.2 周期调整 (周期越小，系数越大，止损越远)
    timeframe_factors = {
        '15m': Decimal('2.0'),  # 15m 扩大 2 倍
        '1h': Decimal('1.5'),   # 1h 扩大 1.5 倍
        '4h': Decimal('1.2'),   # 4h 扩大 1.2 倍
        '1d': Decimal('1.0'),   # 1d 不调整
    }
    timeframe_factor = timeframe_factors.get(timeframe, Decimal('1.5'))

    # Step 4: 计算调整后的止损距离
    adjusted_distance = stop_distance * quality_factor * timeframe_factor

    # Step 5: 计算最终止损价格
    if direction == Direction.LONG:
        stop_loss = kline.close - adjusted_distance
    else:
        stop_loss = kline.close + adjusted_distance

    return self._quantize_price(stop_loss, kline.close)
```

**优点**:
- ✅ 根据形态质量动态调整，高质量形态止损更近
- ✅ 根据周期动态调整，小周期止损更远
- ✅ 理论基础扎实（Pinbar 形态学）

**缺点**:
- ⚠️ 需要传递 pattern_score 和 timeframe 参数
- ⚠️ 可能需要回测验证最优参数

**风险**:
- ⚠️ 调整系数可能需要微调
- ⚠️ 可能导致某些形态止损过远，降低盈亏比

**预估工作量**: 4 小时（修改 + 测试）

---

### 方案 B: 提高止盈目标（备选）

**核心思路**: 提高默认止盈目标，确保盈亏比 ≥ 2.0

**修改内容**:

**文件**: `src/domain/risk_calculator.py`
**位置**: 第 215-223 行

**当前代码**:
```python
def _get_default_take_profit_config(self) -> TakeProfitConfig:
    return TakeProfitConfig(
        enabled=True,
        levels=[
            TakeProfitLevel(id="TP1", position_ratio=Decimal("0.5"), risk_reward=Decimal("1.5")),
            TakeProfitLevel(id="TP2", position_ratio=Decimal("0.5"), risk_reward=Decimal("3.0")),
        ]
    )
```

**修改为**:
```python
def _get_default_take_profit_config(self) -> TakeProfitConfig:
    return TakeProfitConfig(
        enabled=True,
        levels=[
            TakeProfitLevel(id="TP1", position_ratio=Decimal("0.3"), risk_reward=Decimal("2.0")),  # 1.5 → 2.0
            TakeProfitLevel(id="TP2", position_ratio=Decimal("0.4"), risk_reward=Decimal("3.5")),  # 3.0 → 3.5
            TakeProfitLevel(id="TP3", position_ratio=Decimal("0.3"), risk_reward=Decimal("5.0")),  # 新增 TP3
        ]
    )
```

**优点**:
- ✅ 提高盈亏比，确保单笔止盈能覆盖 2 笔止损
- ✅ 修改简单，风险低

**缺点**:
- ⚠️ 止盈目标提高，触发概率降低
- ⚠️ 可能导致更多持仓无法止盈

**风险**:
- ⚠️ 可能降低胜率
- ⚠️ 需要回测验证

**预估工作量**: 1 小时

---

### 方案 C: 降低撮合引擎悲观程度（备选）

**核心思路**: 调整止损/止盈判定顺序，减少假突破止损

**修改内容**:

**文件**: `src/domain/matching_engine.py`
**位置**: 第 122-162 行

**当前逻辑**:
```python
# 按优先级排序订单：SL > TP > ENTRY
sorted_orders = self._sort_orders_by_priority(active_orders)
```

**修改为**:
```python
# 方案 C1: 根据 K 线实体大小动态调整优先级
kline_body = kline.high - kline.low
avg_body = ...  # 计算平均实体大小（需要传入历史数据）

if kline_body > avg_body * Decimal('1.5'):
    # 大实体 K 线（趋势明确），止损优先
    sorted_orders = self._sort_orders_by_priority(active_orders)
else:
    # 小实体 K 线（震荡），止盈优先（减少假突破止损）
    sorted_orders = self._sort_orders_by_priority_reversed(active_orders)
```

**优点**:
- ✅ 减少假突破止损
- ✅ 提高实际盈亏比

**缺点**:
- ⚠️ 逻辑复杂，需要历史数据
- ⚠️ 可能错过真实突破的止损

**风险**:
- ⚠️ 可能导致真实亏损扩大
- ⚠️ 需要大量回测验证

**预估工作量**: 8 小时（高风险）

---

### 方案 D: 持久化 positions 表（数据完整性）

**核心思路**: 回测时持久化 positions 数据到数据库

**修改内容**:

**文件**: `src/application/backtester.py`
**位置**: `_run_v3_pms_backtest()` 方法

**当前逻辑**:
```python
# 仅在内存中维护 positions_map
positions_map: Dict[str, Position] = {}
```

**修改为**:
```python
# 在回测循环中定期持久化 positions
for kline in klines:
    # ... 撮合逻辑 ...

    # 每 100 根 K 线持久化一次
    if len(klines_processed) % 100 == 0:
        await self._persist_positions(positions_map, position_repository)
```

**优点**:
- ✅ 数据完整性
- ✅ 可查询历史持仓

**缺点**:
- ⚠️ 增加数据库写入开销
- ⚠️ 不影响回测结果准确性

**风险**:
- ⚠️ 性能影响（可接受）

**预估工作量**: 2 小时

---

## 建议

### 立即修复（推荐顺序）

1. **方案 A（动态止损距离）** - 🔴 P0
   - 根本解决问题
   - 理论基础扎实
   - 预估收益：止损触发率降低 30%，盈亏比提升至 2.0+

2. **方案 B（提高止盈目标）** - 🟠 P1
   - 快速改善盈亏比
   - 风险低
   - 预估收益：盈亏比从 1.12 提升至 1.5+

3. **方案 D（持久化 positions）** - 🟢 P3
   - 数据完整性
   - 不影响回测结果
   - 预估收益：可查询历史持仓

### 后续优化

1. **回测验证**:
   - 使用方案 A + B 重新回测
   - 对比修改前后的胜率、盈亏比、总回报

2. **参数调优**:
   - 使用 Optuna 优化止损距离系数
   - 优化止盈目标配置

3. **策略改进**:
   - 增加 Pinbar 形态质量过滤（score > 0.7）
   - 增加趋势强度过滤（ADX > 25）

### 预防措施

1. **回测报告增加盈亏比指标**:
   - 在 BacktestReport 中增加 `avg_profit_per_win` 和 `avg_loss_per_loss`
   - 自动计算盈亏比并预警（< 1.5 时警告）

2. **止损距离合理性检查**:
   - 在 RiskCalculator 中增加止损距离检查
   - 止损距离 < 0.5% 时警告

3. **回测报告自动诊断**:
   - 回测完成后自动生成诊断报告
   - 检测常见问题（盈亏比失衡、止损过频等）

---

## 附录：数据验证

### 止损距离验证（BTC 15m）

假设：
- Entry Price = 50000 USDT
- Pinbar Low = 49750 USDT
- 止损距离 = 50000 - 49750 = 250 USDT = 0.5%

当前逻辑：
- 止损价 = 49750 USDT
- 止损距离 = 0.5%（极易触发）

方案 A 后（quality_factor=1.5, timeframe_factor=2.0）：
- 调整后止损距离 = 250 × 1.5 × 2.0 = 750 USDT
- 止损价 = 50000 - 750 = 49250 USDT
- 止损距离 = 1.5%（更合理）

### 盈亏比验证

当前：
- 平均止损亏损: -182.4 USDT
- 平均止盈盈利: +205.1 USDT
- 盈亏比: 1.12

方案 B 后（TP1=2.0R）：
- 理论止盈盈利: 182.4 × 2.0 = 364.8 USDT
- 理论盈亏比: 2.0

实际效果（考虑触发率）：
- 假设止盈触发率从 33.3% 降至 25%
- 止损触发率从 66.7% 升至 75%
- 平均盈利: 364.8 × 0.25 = 91.2 USDT
- 平均亏损: -182.4 × 0.75 = -136.8 USDT
- 净盈亏: 91.2 - 136.8 = -45.6 USDT（仍为负）

**结论**: 方案 A + B 必须组合使用，单独使用效果有限

---

**诊断完成时间**: 2026-04-18 00:15
**诊断师签名**: Diagnostic Analyst

---

*我是医生，不是药剂师 — 我诊断，别人配药。*
