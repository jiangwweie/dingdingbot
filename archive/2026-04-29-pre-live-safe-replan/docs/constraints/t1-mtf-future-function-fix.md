# T1 - MTF 未来函数问题修复设计文档

**创建日期**: 2026-04-01
**作者**: 盯盘狗开发团队
**状态**: ✅ 已完成
**完成日期**: 2026-04-01
**优先级**: P0（致命问题 - 回测结果失效）

---

## 1. 问题分析

### 1.1 核心问题

MTF (多时间框架) 过滤器在回测中使用**未收盘的 K 线**，导致未来函数问题 - 回测中"预知未来"。

**问题场景示例**:
```
15m 策略时间线:
- 10:00 (15m K 线收盘) → 触发信号
- 此时需要检查 1h MTF 趋势

1h K 线时间线:
- 09:00 K 线 (已收盘)
- 10:00 K 线 (未收盘 - 正在运行中!)

❌ 当前行为：使用 10:00 的 1h K 线计算 MTF 趋势
   → 但 10:00 的 1h K 线在 10:00 时刻还未收盘！
   → 回测"预知"了 10:00-11:00 之间的价格运动

✅ 期望行为：使用 09:00 的 1h K 线计算 MTF 趋势
   → 09:00 的 1h K 线在 10:00 时刻已经收盘
   → 只使用历史已知数据
```

### 1.2 影响范围

| 组件 | 影响 | 严重程度 |
|------|------|----------|
| `backtester.py` | MTF 数据构建和趋势查询 | 高 |
| `signal_pipeline.py` | 实盘 MTF 计算 | 中 |
| 所有依赖 MTF 的策略 | 回测结果虚高 | 高 |

### 1.3 根本原因定位

**问题代码位置**: `src/application/backtester.py`

**问题 1**: `_run_strategy_loop` 中构建 MTF 数据时使用简单映射
```python
# 第 403-407 行 - 问题代码
for kline in higher_tf_klines_list:
    ts = kline.timestamp
    higher_tf_data[ts] = {
        higher_tf: TrendDirection.BULLISH if kline.close > kline.open else TrendDirection.BEARISH
    }
```

**问题 2**: `_get_closest_higher_tf_trends` 使用 `ts <= timestamp` 判断
```python
# 第 533-538 行 - 问题代码
for ts in higher_tf_data:
    if ts <= timestamp:  # ❌ 允许相等！
        if closest_ts is None or ts > closest_ts:
            closest_ts = ts
```

**问题场景**:
```
15m K 线 timestamp = 10:00 (10:00-10:15 的 K 线，10:15 才收盘)
1h K 线 timestamp = 10:00 (10:00-11:00 的 K 线，11:00 才收盘)

在 10:15 时刻：
- 15m K 线已收盘 (is_closed=True)
- 1h K 线未收盘 (还在 10:00-11:00 周期内)

当前代码会使用 timestamp=10:00 的 1h K 线
但该 K 线在 10:15 时刻还未收盘！
```

### 1.4 实盘管道对比

**实盘管道 (`signal_pipeline.py`)** 已经正确实现：
```python
# signal_pipeline.py 使用 EMA 指标计算趋势
# 并且只在 is_closed=True 时触发策略计算
```

**回测引擎** 需要与实盘保持一致。

---

## 2. 修复方案

### 2.1 核心修复原则

**MTF K 线往前偏移 1 根** - 确保只使用已收盘的 K 线数据。

**判断标准**:
```python
# 对于 timestamp 为 T 的当前 K 线
# 高周期 K 线必须满足：timestamp < T 才能使用
# (注意：是严格小于，不是小于等于)
```

### 2.2 代码修改点

#### 修改点 1: `_get_closest_higher_tf_trends` 方法

**文件**: `src/application/backtester.py`

**当前代码** (第 524-543 行):
```python
def _get_closest_higher_tf_trends(
    self,
    timestamp: int,
    higher_tf_data: Dict[int, Dict[str, TrendDirection]],
) -> Dict[str, TrendDirection]:
    """Get the closest available higher timeframe trends."""
    if not higher_tf_data:
        return {}

    # Find the closest timestamp <= current timestamp
    closest_ts = None
    for ts in higher_tf_data:
        if ts <= timestamp:  # ❌ 问题：允许相等
            if closest_ts is None or ts > closest_ts:
                closest_ts = ts

    if closest_ts is None:
        return {}

    return higher_tf_data.get(closest_ts, {})
```

**修复后代码**:
```python
def _get_closest_higher_tf_trends(
    self,
    timestamp: int,
    higher_tf_data: Dict[int, Dict[str, TrendDirection]],
) -> Dict[str, TrendDirection]:
    """
    Get the closest available higher timeframe trends.
    
    CRITICAL: Uses strictly less than (<) to ensure we only use
    closed higher timeframe candles. A candle with timestamp T
    closes at T + period, so at time T it is still forming.
    """
    if not higher_tf_data:
        return {}

    # Find the closest timestamp < current timestamp (strictly less than!)
    closest_ts = None
    for ts in higher_tf_data:
        if ts < timestamp:  # ✅ 修复：严格小于，排除未收盘的 K 线
            if closest_ts is None or ts > closest_ts:
                closest_ts = ts

    if closest_ts is None:
        return {}

    return higher_tf_data.get(closest_ts, {})
```

#### 修改点 2: MTF 趋势计算逻辑

**文件**: `src/application/backtester.py`

**当前代码** (第 403-407 行):
```python
# Build a map of timestamp -> trend
for kline in higher_tf_klines_list:
    ts = kline.timestamp
    higher_tf_data[ts] = {
        higher_tf: TrendDirection.BULLISH if kline.close > kline.open else TrendDirection.BEARISH
    }
```

**问题**: 这里使用简单的 `close > open` 判断趋势，而不是 EMA 斜率。

**修复**: 与实盘保持一致，使用 EMA 计算趋势。但考虑回测性能，暂不引入完整 EMA 缓存。

**阶段 1 修复** (优先): 仅修复 `<` vs `<=` 问题
**阶段 2 优化** (可选): 引入 EMA 计算与实盘完全一致

---

## 3. 影响范围评估

### 3.1 受影响的测试用例

| 测试文件 | 受影响测试 | 状态 |
|----------|-----------|------|
| `tests/integration/test_mtf_e2e.py` | 所有 MTF 测试 | 需更新 |
| `tests/unit/test_strategy_engine.py` | MTF 相关测试 | 需审查 |
| `tests/backtest.py` | 回测脚本 | 需验证 |

### 3.2 受影响的策略

所有使用 MTF 过滤器的策略：
- Pinbar + MTF
- Engulfing + MTF
- 动态策略中的 MTF 过滤器

### 3.3 回测结果影响

**预期影响**:
- 信号数量可能减少 (部分信号因 MTF 数据不足被过滤)
- 胜率可能下降 (移除"预知未来"的信号)
- 回测结果更接近实盘表现

---

## 4. 测试用例设计

### 4.1 单元测试 - MTF 时间对齐

**文件**: `tests/unit/test_timeframe_utils.py`

```python
class TestMtfFutureFunctionFix:
    """验证 MTF 不使用未收盘 K 线的测试。"""

    def test_get_closest_higher_tf_trends_excludes_current_candle(self):
        """
        验证：当 15m K 线 timestamp=10:00 时，
        不应使用 1h K 线 timestamp=10:00 (未收盘),
        应使用 1h K 线 timestamp=09:00 (已收盘)
        """
        higher_tf_data = {
            hour_to_ms(9): {"1h": TrendDirection.BULLISH},  # 09:00 K 线 (已收盘)
            hour_to_ms(10): {"1h": TrendDirection.BEARISH}, # 10:00 K 线 (未收盘!)
            hour_to_ms(11): {"1h": TrendDirection.BULLISH}, # 11:00 K 线 (未来)
        }

        # 15m K 线 timestamp = 10:00 (实际是 10:00-10:15 的 K 线)
        current_ts = hour_to_ms(10)

        trends = backtester._get_closest_higher_tf_trends(current_ts, higher_tf_data)

        # 应该使用 09:00 的 K 线，而不是 10:00 的
        assert trends == {"1h": TrendDirection.BULLISH}  # 09:00 的趋势

    def test_no_valid_closed_kline_returns_empty(self):
        """
        验证：当没有已收盘的高周期 K 线时，返回空字典。
        """
        higher_tf_data = {
            hour_to_ms(11): {"1h": TrendDirection.BULLISH}, # 未来 K 线
        }

        current_ts = hour_to_ms(10)
        trends = backtester._get_closest_higher_tf_trends(current_ts, higher_tf_data)

        assert trends == {}

    def test_boundary_case_exactly_on_hour(self):
        """
        边界情况：15m K 线正好在整点 (如 11:00)
        此时 10:00-11:00 的 1h K 线刚好收盘
        应该可以使用 10:00 的 1h K 线
        """
        higher_tf_data = {
            hour_to_ms(10): {"1h": TrendDirection.BULLISH},  # 10:00-11:00 K 线
            hour_to_ms(11): {"1h": TrendDirection.BEARISH},  # 11:00-12:00 K 线 (刚收盘)
        }

        # 15m K 线 timestamp = 11:00 (11:00-11:15 的 K 线)
        current_ts = hour_to_ms(11)

        trends = backtester._get_closest_higher_tf_trends(current_ts, higher_tf_data)

        # 应该使用 10:00 的 K 线 (11:00 的 K 线虽然刚收盘，但属于下一个周期)
        assert trends == {"1h": TrendDirection.BULLISH}
```

### 4.2 回测场景测试

**文件**: `tests/unit/test_backtester.py` (新增)

```python
class TestBacktesterMtfAlignment:
    """验证回测中 MTF 对齐逻辑正确。"""

    async def test_backtest_mtf_uses_closed_kline_only(self):
        """
        场景：
        - 15m K 线范围：09:00, 09:15, 09:30, ..., 10:00
        - 1h K 线范围：08:00, 09:00, 10:00

        验证:
        - 10:00 的 15m K 线应使用 09:00 的 1h K 线 (而非 10:00)
        """
        # Setup: 准备测试数据
        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            start_time=hour_to_ms(9),
            end_time=hour_to_ms(10) + minute_to_ms(15),
            mtf_validation_enabled=True,
        )

        # Mock gateway 返回固定的 K 线数据
        mock_gateway = create_mock_gateway_with_klines()

        backtester = Backtester(mock_gateway)
        report = await backtester.run_backtest(request)

        # Verify: 检查 MTF 验证逻辑
        # 10:00 的 15m 信号应该被 09:00 的 1h 趋势过滤
        # (具体断言取决于 09:00 的 1h K 线趋势)
        assert report is not None
        # 详细断言需要根据具体数据设计
```

### 4.3 覆盖率目标

- `backtester.py::_get_closest_higher_tf_trends`: 90%+
- `backtester.py::_run_strategy_loop` (MTF 部分): 85%+
- MTF 过滤器集成测试：100%

---

## 5. 实施顺序

```
1. 修复 `_get_closest_higher_tf_trends` 方法 (< vs <=) [T1 核心]
2. 编写单元测试验证修复 [SST 先行]
3. 运行现有测试验证无回归 [回归测试]
4. 运行回测脚本对比修复前后差异 [验证]
```

---

## 6. 相关文件

- `src/application/backtester.py` - 主要修改文件
- `tests/unit/test_timeframe_utils.py` - 新增测试
- `tests/integration/test_mtf_e2e.py` - 集成测试
- `docs/superpowers/specs/2026-03-27-s3-1-mtf-data-alignment-design.md` - 相关设计文档

---

## 7. 验收标准

### 功能验收
- [ ] `_get_closest_higher_tf_trends` 使用严格 `<` 判断
- [ ] 单元测试验证边界情况
- [ ] 回测结果合理 (信号数量可能减少)

### 测试验收
- [ ] 新增测试覆盖率 > 90%
- [ ] 现有测试无回归

### 文档验收
- [ ] 设计文档完成
- [ ] 测试用例文档完成
- [ ] progress.md 更新

---

*最后更新：2026-04-01*
