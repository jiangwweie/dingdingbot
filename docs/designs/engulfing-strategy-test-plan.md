# 吞没形态策略测试方案设计

**创建日期**: 2026-04-01
**任务来源**: 用户头脑风暴需求
**关联任务**: #3 吞没形态策略 + 过滤器组合测试

---

## 一、测试目标

对 `EngulfingStrategy` 吞没形态策略进行全面的单元测试和集成测试，验证：
1. 形态检测逻辑正确性
2. 过滤器组合有效性
3. 评分逻辑合理性
4. 信号覆盖机制

---

## 二、测试范围与优先级

| 编号 | 测试模块 | 优先级 | 预计用例数 | 工时 |
|------|----------|--------|------------|------|
| T1 | 基础形态检测测试 | 🔴 最高 | 8 | 2h |
| T2 | ATR 过滤器测试 | 🔴 高 | 6 | 2h |
| T3 | EMA 趋势过滤器测试 | 🟠 中 | 4 | 1.5h |
| T4 | MTF 多周期过滤测试 | 🟠 中 | 6 | 2h |
| T5 | 过滤器组合测试 | 🟠 中 | 8 | 3h |
| T6 | 评分逻辑测试 | 🟡 低 | 4 | 1.5h |
| T7 | 端到端集成测试 | 🟡 低 | 4 | 2h |
| **合计** | - | - | **40** | **14h** |

---

## 三、测试用例详细设计

### T1: 基础形态检测测试 (8 用例)

**测试文件**: `tests/unit/test_engulfing_strategy.py`

| ID | 场景 | 输入 | 期望输出 |
|----|------|------|----------|
| T1-1 | 标准看涨吞没 | 前阴后阳，阳线包覆阴线 | `direction=LONG`, `score≥0.5` |
| T1-2 | 标准看跌吞没 | 前阳后阴，阴线包覆阴线 | `direction=SHORT`, `score≥0.5` |
| T1-3 | 非吞没 - 同向 K 线 | 两根阳线或两根阴线 | `None` |
| T1-4 | 非吞没 - 部分包覆 | 阳线未完全包覆阴线实体 | `None` |
| T1-5 | 边界 - 十字星 (当前) | 当前 K 线为十字星 | `None` |
| T1-6 | 边界 - 十字星 (前一根) | 前一根 K 线为十字星 | `None` |
| T1-7 | 边界 - 极小实体 | 实体<1% 但非零 | 正常检测 |
| T1-8 | engulfing_ratio 计算 | 当前实体=2×前实体 | `engulfing_ratio=2.0`, `score≈0.67` |

**关键测试代码示例**:
```python
def test_bullish_engulfing_standard():
    """T1-1: 标准看涨吞没"""
    prev = KlineData(
        symbol="BTC/USDT:USDT", timeframe="15m",
        open=Decimal("100"), high=Decimal("102"),
        low=Decimal("98"), close=Decimal("99"),  # 阴线
        timestamp=1000, is_closed=True
    )
    curr = KlineData(
        symbol="BTC/USDT:USDT", timeframe="15m",
        open=Decimal("98"), high=Decimal("103"),
        low=Decimal("97"), close=Decimal("102"),  # 阳线，包覆前一根
        timestamp=2000, is_closed=True
    )
    
    strategy = EngulfingStrategy()
    result = strategy.detect(curr, prev_kline=prev)
    
    assert result is not None
    assert result.direction == Direction.LONG
    assert result.strategy_name == "engulfing"
    assert 0.5 <= result.score <= 1.0
```

---

### T2: ATR 过滤器测试 (6 用例)

**测试文件**: `tests/unit/test_engulfing_atr_filter.py`

**配置**: `min_atr_ratio=0.5`, `min_absolute_range=0.1`

| ID | 场景 | ATR 值 | K 线波幅 | atr_ratio | 期望 |
|----|------|--------|----------|-----------|------|
| T2-1 | 高波动通过 | 400 | 500 | 1.25 | ✅ PASS |
| T2-2 | 临界通过 | 400 | 200 | 0.5 | ✅ PASS |
| T2-3 | 低波幅过滤 | 400 | 100 | 0.25 | ❌ FILTERED |
| T2-4 | 绝对波幅过滤 | - | 0.05 | - | ❌ FILTERED |
| T2-5 | ATR 数据未就绪 | None | - | - | ✅ PASS(降级) |
| T2-6 | 十字星 + 低波幅 | 400 | 50 | 0.125 | ❌ FILTERED |

**测试代码示例**:
```python
def test_atr_filter_low_volatility():
    """T2-3: 低波幅被 ATR 过滤器拒绝"""
    atr_filter = AtrFilterDynamic(
        period=14,
        min_atr_ratio=Decimal("0.5"),
        min_absolute_range=Decimal("0.1"),
        enabled=True
    )
    
    # 模拟 ATR 状态
    atr_filter._atr_state["BTC/USDT:USDT:15m"] = {
        "tr_values": [Decimal("400")] * 14,
        "atr": Decimal("400"),
        "prev_close": Decimal("10000")
    }
    
    kline = KlineData(
        symbol="BTC/USDT:USDT", timeframe="15m",
        open=Decimal("10000"), high=Decimal("10050"),
        low=Decimal("9950"), close=Decimal("10020"),
        timestamp=1000, is_closed=True
    )
    # candle_range = 100, atr_ratio = 100/400 = 0.25 < 0.5
    
    pattern = PatternResult(
        strategy_name="engulfing",
        direction=Direction.LONG,
        score=0.6,
        details={}
    )
    context = FilterContext(kline=kline, current_timeframe="15m")
    
    event = atr_filter.check(pattern, context)
    
    assert event.passed == False
    assert event.reason == "insufficient_volatility"
    assert event.metadata["ratio"] == 0.25
```

---

### T3: EMA 趋势过滤器测试 (4 用例)

**测试文件**: `tests/unit/test_engulfing_ema_filter.py`

| ID | 场景 | EMA 趋势 | 信号方向 | 期望 |
|----|------|----------|----------|------|
| T3-1 | 趋势匹配 - 多头 | BULLISH | LONG | ✅ PASS |
| T3-2 | 趋势匹配 - 空头 | BEARISH | SHORT | ✅ PASS |
| T3-3 | 趋势冲突 - 多头 | BULLISH | SHORT | ❌ FILTERED |
| T3-4 | 趋势冲突 - 空头 | BEARISH | LONG | ❌ FILTERED |

---

### T4: MTF 多周期过滤测试 (6 用例)

**测试文件**: `tests/unit/test_engulfing_mtf_filter.py`

| ID | 场景 | 当前周期 | 高周期趋势 | 信号方向 | 期望 |
|----|------|----------|------------|----------|------|
| T4-1 | 15m 多头确认 | 15m | 1h BULLISH | LONG | ✅ PASS |
| T4-2 | 15m 空头确认 | 15m | 1h BEARISH | SHORT | ✅ PASS |
| T4-3 | 15m 多头冲突 | 15m | 1h BEARISH | LONG | ❌ FILTERED |
| T4-4 | 1h 多头确认 | 1h | 4h BULLISH | LONG | ✅ PASS |
| T4-5 | 4h 多头确认 | 4h | 1d BULLISH | LONG | ✅ PASS |
| T4-6 | 1w 无高周期 | 1w | None | LONG | ✅ PASS(自动通过) |

---

### T5: 过滤器组合测试 (8 用例)

**测试文件**: `tests/integration/test_engulfing_filters_integration.py`

**测试策略配置**:
```yaml
strategy: engulfing
filters:
  - type: atr
    enabled: true
    min_atr_ratio: 0.5
  - type: ema_trend
    enabled: true
    period: 60
  - type: mtf
    enabled: true
```

| ID | 场景 | ATR | EMA | MTF | 期望 |
|----|------|-----|-----|-----|------|
| T5-1 | 全部通过 | ✅ | ✅ | ✅ | ✅ 信号产生 |
| T5-2 | ATR 失败 | ❌ | ✅ | ✅ | ❌ 被过滤 |
| T5-3 | EMA 失败 | ✅ | ❌ | ✅ | ❌ 被过滤 |
| T5-4 | MTF 失败 | ✅ | ✅ | ❌ | ❌ 被过滤 |
| T5-5 | ATR+EMA 失败 | ❌ | ❌ | ✅ | ❌ 被过滤 |
| T5-6 | 全部失败 | ❌ | ❌ | ❌ | ❌ 被过滤 |
| T5-7 | 仅 ATR 启用 | ✅ | 关闭 | 关闭 | ✅ 信号产生 |
| T5-8 | 仅 MTF 启用 | ✅ | 关闭 | ✅ | ✅ 信号产生 |

**测试代码示例**:
```python
async def test_all_filters_pass():
    """T5-1: 所有过滤器通过"""
    # 准备数据：看涨吞没 + 高波动 + EMA 多头 + 1h 多头
    # ... 数据准备 ...
    
    pipeline = SignalPipeline(config_manager, risk_config)
    await pipeline.process_kline(curr_kline)
    
    # 验证信号产生
    signals = await repository.get_signals(limit=1)
    assert len(signals) == 1
    assert signals[0].direction == "long"
```

---

### T6: 评分逻辑测试 (4 用例)

**测试文件**: `tests/unit/test_engulfing_scoring.py`

| ID | 场景 | engulfing_ratio | ATR 有无 | 期望 Score |
|----|------|-----------------|----------|------------|
| T6-1 | 基础评分 | 1.0 | 无 | 0.5 |
| T6-2 | 高 engulfing_ratio | 3.0 | 无 | 0.75 |
| T6-3 | ATR 加分 | 1.0 | 有 (atr_ratio=1.0) | 0.5×0.7 + 1.0×0.3 = 0.65 |
| T6-4 | ATR 加分上限 | 1.0 | 有 (atr_ratio=2.0) | 0.5×0.7 + 2.0×0.3 = 0.95 |

**评分公式**:
```python
score = engulfing_ratio_base × 0.7 + min(atr_ratio, 2.0) × 0.3
# engulfing_ratio_base = 1 - 1/(engulfing_ratio + 1)
```

---

### T7: 端到端集成测试 (4 用例)

**测试文件**: `tests/e2e/test_engulfing_e2e.py`

**使用真实 K 线数据**（从交易所获取或固定数据集）

| ID | 场景 | 数据源 | 验证点 |
|----|------|--------|--------|
| T7-1 | 实盘数据回测 | BTC 15m × 1000 根 | 信号数量、胜率、盈亏比 |
| T7-2 | 与 Pinbar 对比 | 同一数据源 | 信号频率、质量对比 |
| T7-3 | 参数敏感性 | 调整 min_atr_ratio | 信号数量变化曲线 |
| T7-4 | 极端行情 | 暴涨暴跌期间 K 线 | 策略稳定性 |

---

## 四、测试数据准备

### 标准 K 线数据集

```python
# 看涨吞没问题
BULLISH_ENGULFING_CASE = {
    "prev": KlineData(
        open=Decimal("100"), high=Decimal("102"),
        low=Decimal("98"), close=Decimal("99"),  # 阴线
    ),
    "curr": KlineData(
        open=Decimal("98"), high=Decimal("103"),
        low=Decimal("97"), close=Decimal("102"),  # 阳线包覆
    ),
}

# 看跌吞没问题
BEARISH_ENGULFING_CASE = {
    "prev": KlineData(
        open=Decimal("99"), high=Decimal("102"),
        low=Decimal("98"), close=Decimal("100"),  # 阳线
    ),
    "curr": KlineData(
        open=Decimal("101"), high=Decimal("102"),
        low=Decimal("97"), close=Decimal("98"),  # 阴线包覆
    ),
}

# 十字星
DOJI_CASE = {
    "prev": KlineData(...),
    "curr": KlineData(
        open=Decimal("100"), high=Decimal("101"),
        low=Decimal("99"), close=Decimal("100.01"),  # 十字星
    ),
}
```

---

## 五、验收标准

| 模块 | 通过率 | 覆盖率 | 关键指标 |
|------|--------|--------|----------|
| T1 基础检测 | 100% | 95%+ | 8/8 用例通过 |
| T2 ATR 过滤 | 100% | 90%+ | 6/6 用例通过 |
| T3 EMA 过滤 | 100% | 90%+ | 4/4 用例通过 |
| T4 MTF 过滤 | 100% | 90%+ | 6/6 用例通过 |
| T5 组合测试 | 100% | 85%+ | 8/8 用例通过 |
| T6 评分逻辑 | 100% | 95%+ | 4/4 用例通过 |
| T7 集成测试 | 100% | - | 4/4 用例通过 |

---

## 六、依赖与前提

| 依赖项 | 状态 | 备注 |
|--------|------|------|
| EngulfingStrategy 实现 | ✅ 已完成 | `src/domain/strategies/engulfing_strategy.py` |
| AtrFilterDynamic 实现 | ✅ 已完成 | `src/domain/filter_factory.py` |
| 递归逻辑树引擎 | ✅ 已完成 | `src/domain/recursive_engine.py` |
| SignalPipeline 覆盖逻辑 | ⚠️ 待实现 | S6-2-4 子任务 |
| 测试框架 | ✅ 已完成 | pytest + pytest-asyncio |

---

## 七、执行顺序

```
【阶段 1】T1 基础检测测试 (2h)
    ↓
【阶段 2】T2 ATR 过滤 + T6 评分 (3.5h)
    ↓
【阶段 3】T3 EMA + T4 MTF (3.5h)
    ↓
【阶段 4】T5 过滤器组合 (3h)
    ↓
【阶段 5】T7 端到端集成 (2h)
```

**总预计**: 14 小时

---

## 八、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| ATR 计算逻辑不一致 | 测试失败 | 对照 TradingView 验证 ATR 值 |
| MTF 数据对齐问题 | 集成测试失败 | 使用 `timeframe_utils.py` 工具函数 |
| 并发竞争条件 | 集成测试不稳定 | 使用 asyncio.Lock 保护 |
| 测试数据不足 | 覆盖率不达标 | 使用参数化测试生成边界值 |

---

## 九、相关文件

- `src/domain/strategies/engulfing_strategy.py` - 吞没策略实现
- `src/domain/filter_factory.py` - 过滤器工厂
- `src/application/signal_pipeline.py` - 信号处理管道
- `tests/unit/test_strategy_engine.py` - Pinbar 测试参考
- `tests/integration/test_risk_headroom.py` - 集成测试参考

---

*文档结束*
