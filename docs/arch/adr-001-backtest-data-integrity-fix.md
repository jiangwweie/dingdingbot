# ADR-001: 回测数据完整性修复设计

> **架构决策记录 (Architecture Decision Record)**
> **文档级别**: P8 架构师评审级
> **创建日期**: 2026-04-06
> **状态**: 待评审 (Pending Review)
> **影响范围**: MockMatchingEngine, FilterResult, Backtester._attempt_to_dict
> **关联任务**: BT-4 策略归因分析

---

## 1. 问题分析

### 1.1 背景

BT-4 策略归因分析需要完整的回测数据支撑，用于追踪每笔信号的完整生命周期和过滤链决策过程。当前回测链路存在 3 个数据缺失问题，导致无法准确进行策略归因分析。

### 1.2 问题详情

#### P0: `MockMatchingEngine._execute_fill()` 未设置 `order.filled_at` 字段

**位置**: `src/domain/matching_engine.py` 第 231-352 行

**具体表现**:
```python
def _execute_fill(
    self,
    order: Order,
    exec_price: Decimal,
    position: Optional[Position],
    account: Account,
    positions_map: Dict[str, Position],
    timestamp: int,  # ← 已接收 timestamp 参数
) -> None:
    # 1. 翻转订单状态
    order.status = OrderStatus.FILLED
    order.filled_qty = order.requested_qty
    order.average_exec_price = exec_price
    # ❌ 缺失：order.filled_at = timestamp  # 未设置成交时间戳
```

**影响**:
- 回测报告中无法追踪订单成交时间
- 无法计算持仓时长（entry_time → exit_time）
- 无法进行时间序列分析（如按时段统计胜率）

---

#### P1: 各过滤器的 `FilterResult.metadata` 结构不标准，可能为空

**位置**: `src/domain/models.py` 第 473-481 行（FilterResult 定义）
         `src/domain/filter_factory.py` 各过滤器实现

**具体表现**:
```python
@dc_dataclass
class FilterResult:
    """单个过滤器的判断结果"""
    passed: bool
    reason: str
    metadata: Dict[str, Any] = None  # ❌ 可能为 None，结构不统一
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}  # 仅初始化空字典，无标准字段
```

**当前各过滤器 metadata 结构差异**:

| 过滤器 | metadata 字段 | 问题 |
|--------|--------------|------|
| EmaTrendFilter | `{}` (空) | 缺少 trend 值、EMA 值 |
| MtfFilter | `{"higher_timeframe": "1h", "higher_trend": "bearish"}` | 部分字段缺失 |
| AtrFilter | `{"candle_range": 70.0, "atr": 50.0, "ratio": 1.4}` | 字段完整但类型不统一 |

**影响**:
- 归因分析无法统一解析 metadata
- 前端无法展示过滤链详细决策依据
- 无法进行过滤效果统计分析

---

#### P2: `Backtester._attempt_to_dict()` 缺少 `pnl_ratio` 和 `exit_reason` 字段

**位置**: `src/application/backtester.py` 第 874-886 行

**具体表现**:
```python
def _attempt_to_dict(self, attempt: SignalAttempt) -> Dict[str, Any]:
    """Convert SignalAttempt to dictionary for JSON serialization."""
    return {
        "strategy_name": attempt.strategy_name,
        "final_result": attempt.final_result,
        "direction": attempt.direction.value if attempt.direction else None,
        "kline_timestamp": attempt.kline_timestamp,
        "pattern_score": attempt.pattern.score if attempt.pattern else None,
        "filter_results": [
            {"filter": name, "passed": r.passed, "reason": r.reason}
            for name, r in attempt.filter_results
        ],
        # ❌ 缺失：pnl_ratio (盈亏比)
        # ❌ 缺失：exit_reason (出场原因)
    }
```

**影响**:
- 回测报告无法展示盈亏比数据
- 无法区分出场原因（止损/止盈/时间退出）
- 策略归因分析缺少关键统计维度

---

## 2. 修复方案设计

### 2.1 任务 3: `filled_at` 设置的具体代码位置和时序

**修改文件**: `src/domain/matching_engine.py`

**修改位置**: `_execute_fill()` 方法第 286-289 行

**修复代码**:
```python
def _execute_fill(
    self,
    order: Order,
    exec_price: Decimal,
    position: Optional[Position],
    account: Account,
    positions_map: Dict[str, Position],
    timestamp: int,
) -> None:
    """
    执行订单结算与仓位/账户同步
    
    副作用:
        - order.status = FILLED
        - order.filled_qty = requested_qty
        - order.average_exec_price = exec_price
        - order.filled_at = timestamp  # ← 新增
    """
    # 1. 翻转订单状态
    order.status = OrderStatus.FILLED
    order.filled_qty = order.requested_qty
    order.average_exec_price = exec_price
    order.filled_at = timestamp  # ← 新增：设置成交时间戳
    order.updated_at = timestamp  # ← 建议同步更新 updated_at
    
    # 2. 区分入场单 vs 平仓单
    # ... 后续逻辑不变
```

**时序说明**:
```
K-line 级撮合流程:
┌─────────────────────────────────────────────────────────┐
│ 1. match_orders_for_kline(kline, ...)                   │
│    │                                                     │
│    ├─► 2. 检查止损单触发条件 (kline.low/high)           │
│    │   └─► 若触发 → _execute_fill(..., kline.timestamp) │
│    │                                                     │
│    ├─► 3. 检查止盈单触发条件 (kline.high/low)           │
│    │   └─► 若触发 → _execute_fill(..., kline.timestamp) │
│    │                                                     │
│    └─► 4. 检查入场单 (kline.open)                       │
│        └─► 若触发 → _execute_fill(..., kline.timestamp) │
└─────────────────────────────────────────────────────────┘

filled_at 设置时机：
- 所有订单的 filled_at = kline.timestamp (毫秒级时间戳)
- 同一 K 线内成交的订单具有相同的 filled_at
```

**调用点确认** (共 4 处):
1. 第 149 行：止损单触发 `_execute_fill(order, exec_price, position, account, positions_map, kline.timestamp)`
2. 第 174 行：止盈单触发 `_execute_fill(order, exec_price, position, account, positions_map, kline.timestamp)`
3. 第 193 行：入场单触发 `_execute_fill(order, exec_price, position, account, positions_map, kline.timestamp)`

---

### 2.2 任务 4: `FilterResult.metadata` 标准化结构定义

**修改文件**: `src/domain/models.py`, `src/domain/filter_factory.py`

#### 2.2.1 FilterResult 元数据标准结构

```python
@dc_dataclass
class FilterResult:
    """单个过滤器的判断结果"""
    passed: bool
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 标准 metadata 字段定义:
    # {
    #     # 通用字段 (所有过滤器)
    #     "filter_name": str,           # 过滤器名称
    #     "filter_type": str,           # 过滤器类型 (ema_trend/mtf/atr_volatility)
    #     "timestamp": int,             # 判断时间戳
    #     
    #     # 条件字段 (根据过滤器类型)
    #     # EMA Trend Filter:
    #     "ema_value": Optional[float],
    #     "trend_direction": Optional[str],  # "bullish" | "bearish"
    #     "period": int,
    #     
    #     # MTF Filter:
    #     "higher_timeframe": Optional[str],
    #     "higher_trend": Optional[str],
    #     "current_timeframe": str,
    #     
    #     # ATR Filter:
    #     "atr_value": Optional[float],
    #     "candle_range": Optional[float],
    #     "min_required": Optional[float],
    #     "volatility_ratio": Optional[float],
    # }
```

#### 2.2.2 各过滤器 metadata 标准化实现

**EmaTrendFilterDynamic** (第 164-216 行):
```python
def check(self, pattern: PatternResult, context: FilterContext) -> TraceEvent:
    if not self._enabled:
        return TraceEvent(
            node_name=self.name,
            passed=True,
            reason="filter_disabled",
            metadata={
                "filter_name": "ema_trend",
                "filter_type": "ema_trend",
                "period": self._period,
                "enabled": False,
            }
        )

    current_trend = context.current_trend
    if current_trend is None:
        return TraceEvent(
            node_name=self.name,
            passed=False,
            reason="ema_data_not_ready",
            expected="valid_ema_trend",
            actual="no_data",
            metadata={
                "filter_name": "ema_trend",
                "filter_type": "ema_trend",
                "period": self._period,
                "ema_value": None,
                "trend_direction": None,
            }
        )

    # 获取 EMA 值用于 metadata
    ema_value = None
    if context.kline and context.current_timeframe:
        # 从 EMA 计算器获取当前值 (需要扩展 get_current_trend 返回值)
        key = f"{context.kline.symbol}:{context.current_timeframe}"
        if key in self._ema_calculators:
            ema_value = float(self._ema_calculators[key].value) if self._ema_calculators[key].value else None

    if pattern.direction == Direction.LONG:
        if current_trend == TrendDirection.BULLISH:
            return TraceEvent(
                node_name=self.name,
                passed=True,
                reason="trend_match",
                expected="bullish",
                actual="bullish",
                metadata={
                    "filter_name": "ema_trend",
                    "filter_type": "ema_trend",
                    "period": self._period,
                    "ema_value": ema_value,
                    "trend_direction": current_trend.value,
                    "pattern_direction": pattern.direction.value,
                }
            )
        else:
            return TraceEvent(
                node_name=self.name,
                passed=False,
                reason="bearish_trend_blocks_long",
                expected="bullish",
                actual="bearish",
                metadata={
                    "filter_name": "ema_trend",
                    "filter_type": "ema_trend",
                    "period": self._period,
                    "ema_value": ema_value,
                    "trend_direction": current_trend.value,
                    "pattern_direction": pattern.direction.value,
                }
            )
    # ... SHORT 逻辑类似
```

**MtfFilterDynamic** (第 257-326 行):
```python
def check(self, pattern: PatternResult, context: FilterContext) -> TraceEvent:
    if not self._enabled:
        return TraceEvent(
            node_name=self.name,
            passed=True,
            reason="filter_disabled",
            metadata={
                "filter_name": "mtf",
                "filter_type": "mtf",
                "enabled": False,
            }
        )

    current_tf = context.current_timeframe
    higher_tf = self._timeframe_map.get(current_tf)

    if higher_tf is None:
        return TraceEvent(
            node_name=self.name,
            passed=True,
            reason="no_higher_timeframe",
            metadata={
                "filter_name": "mtf",
                "filter_type": "mtf",
                "current_timeframe": current_tf,
                "higher_timeframe": None,
                "higher_trend": None,
            }
        )

    higher_tf_trend = context.higher_tf_trends.get(higher_tf)
    if higher_tf_trend is None:
        return TraceEvent(
            node_name=self.name,
            passed=False,
            reason="higher_tf_data_unavailable",
            expected=f"trend_data_for_{higher_tf}",
            actual="no_data",
            metadata={
                "filter_name": "mtf",
                "filter_type": "mtf",
                "current_timeframe": current_tf,
                "higher_timeframe": higher_tf,
                "higher_trend": None,
            }
        )

    # 正常判断逻辑...
    if pattern.direction == Direction.LONG:
        if higher_tf_trend == TrendDirection.BULLISH:
            return TraceEvent(
                node_name=self.name,
                passed=True,
                reason="mtf_confirmed_bullish",
                expected="bullish",
                actual="bullish",
                metadata={
                    "filter_name": "mtf",
                    "filter_type": "mtf",
                    "current_timeframe": current_tf,
                    "higher_timeframe": higher_tf,
                    "higher_trend": higher_tf_trend.value,
                    "pattern_direction": pattern.direction.value,
                }
            )
        # ... 拒绝逻辑类似
```

**AtrFilterDynamic** (第 413-470 行):
```python
def check(self, pattern: PatternResult, context: FilterContext) -> TraceEvent:
    if not self._enabled:
        return TraceEvent(
            node_name=self.name,
            passed=True,
            reason="filter_disabled",
            metadata={
                "filter_name": "atr_volatility",
                "filter_type": "atr_volatility",
                "enabled": False,
            }
        )

    kline = context.kline
    if kline is None:
        return TraceEvent(
            node_name=self.name,
            passed=False,
            reason="kline_data_missing",
            metadata={
                "filter_name": "atr_volatility",
                "filter_type": "atr_volatility",
                "error": "kline is None",
            }
        )

    atr = self._get_atr(kline.symbol, kline.timeframe)

    if atr is None:
        return TraceEvent(
            node_name=self.name,
            passed=False,
            reason="atr_data_not_ready",
            metadata={
                "filter_name": "atr_volatility",
                "filter_type": "atr_volatility",
                "symbol": kline.symbol,
                "timeframe": kline.timeframe,
                "required_period": self._period,
                "atr_value": None,
            }
        )

    candle_range = kline.high - kline.low
    min_range = atr * self._min_atr_ratio

    if candle_range < min_range:
        return TraceEvent(
            node_name=self.name,
            passed=False,
            reason="insufficient_volatility",
            metadata={
                "filter_name": "atr_volatility",
                "filter_type": "atr_volatility",
                "candle_range": float(candle_range),
                "atr_value": float(atr),
                "min_required": float(min_range),
                "volatility_ratio": float(candle_range / atr),
                "min_atr_ratio": float(self._min_atr_ratio),
            }
        )

    return TraceEvent(
        node_name=self.name,
        passed=True,
        reason="volatility_sufficient",
        metadata={
            "filter_name": "atr_volatility",
            "filter_type": "atr_volatility",
            "candle_range": float(candle_range),
            "atr_value": float(atr),
            "volatility_ratio": float(candle_range / atr),
            "min_atr_ratio": float(self._min_atr_ratio),
        }
    )
```

---

### 2.3 任务 5: `_attempt_to_dict` 扩展字段设计

**修改文件**: `src/application/backtester.py`

**修改位置**: 第 874-886 行

#### 2.3.1 当前结构分析

当前 `_attempt_to_dict` 仅返回基础信息，缺少 BT-4 归因分析所需的关键字段：

```python
def _attempt_to_dict(self, attempt: SignalAttempt) -> Dict[str, Any]:
    return {
        "strategy_name": attempt.strategy_name,
        "final_result": attempt.final_result,
        "direction": attempt.direction.value if attempt.direction else None,
        "kline_timestamp": attempt.kline_timestamp,
        "pattern_score": attempt.pattern.score if attempt.pattern else None,
        "filter_results": [...],
        # 缺失 pnl_ratio 和 exit_reason
    }
```

#### 2.3.2 扩展后结构

```python
def _attempt_to_dict(self, attempt: SignalAttempt) -> Dict[str, Any]:
    """Convert SignalAttempt to dictionary for JSON serialization.
    
    BT-4 归因分析扩展字段:
    - pnl_ratio: 盈亏比 (仅 SIGNAL_FIRED 信号)
    - exit_reason: 出场原因 (仅 SIGNAL_FIRED 信号)
    - metadata: 标准化元数据
    """
    result = {
        "strategy_name": attempt.strategy_name,
        "final_result": attempt.final_result,
        "direction": attempt.direction.value if attempt.direction else None,
        "kline_timestamp": attempt.kline_timestamp,
        "pattern_score": attempt.pattern.score if attempt.pattern else None,
        "filter_results": [
            {
                "filter": name,
                "passed": r.passed,
                "reason": r.reason,
                "metadata": r.metadata,  # ← 标准化 metadata
            }
            for name, r in attempt.filter_results
        ],
        # BT-4 新增字段
        "pnl_ratio": None,       # 由后续 _simulate_win_rate 填充
        "exit_reason": None,     # 由后续 _simulate_win_rate 填充
    }
    
    # 为 SIGNAL_FIRED 信号计算 pnl_ratio 和 exit_reason
    if attempt.final_result == "SIGNAL_FIRED" and attempt.pattern:
        # 注意：实际计算需要在 _simulate_win_rate 中进行
        # 这里预留字段，由后处理填充
        pass
    
    return result
```

#### 2.3.3 新增辅助方法

在 `Backtester` 类中新增方法，用于计算 pnl_ratio 和 exit_reason：

```python
def _calculate_attempt_outcome(
    self,
    attempt: SignalAttempt,
    klines: List[KlineData],
    risk_config: RiskConfig,
) -> Tuple[Optional[float], Optional[str]]:
    """
    Calculate pnl_ratio and exit_reason for a fired signal.
    
    Args:
        attempt: Signal attempt with SIGNAL_FIRED result
        klines: Historical K-line data
        risk_config: Risk configuration for stop-loss calculation
        
    Returns:
        Tuple of (pnl_ratio, exit_reason)
        - pnl_ratio: float or None (e.g., 2.0 for 2R gain, -1.0 for 1R loss)
        - exit_reason: str or None (e.g., "STOP_LOSS", "TAKE_PROFIT", "TIME_EXIT")
    """
    if attempt.final_result != "SIGNAL_FIRED" or not attempt.pattern:
        return None, None
    
    # Find entry kline
    entry_kline = None
    for k in klines:
        if k.timestamp == attempt.kline_timestamp:
            entry_kline = k
            break
    
    if not entry_kline:
        return None, None
    
    # Calculate stop-loss level
    if attempt.direction == Direction.LONG:
        stop_loss = entry_kline.low
        take_profit_target = entry_kline.close + (entry_kline.close - stop_loss) * 2
    else:  # SHORT
        stop_loss = entry_kline.high
        take_profit_target = entry_kline.close - (stop_loss - entry_kline.close) * 2
    
    # Determine outcome using existing logic
    outcome = self._determine_trade_outcome(
        klines,
        attempt.kline_timestamp,
        entry_kline,
        stop_loss,
        take_profit_target,
        attempt.direction,
    )
    
    if outcome == "WIN":
        return 2.0, "TAKE_PROFIT"  # 2R gain
    elif outcome == "LOSS":
        return -1.0, "STOP_LOSS"   # 1R loss
    else:
        return 0.0, "TIME_EXIT"    # No clear outcome
```

修改 `_simulate_win_rate` 方法返回更详细的结果：

```python
async def _simulate_win_rate(
    self,
    attempts: List[SignalAttempt],
    klines: List[KlineData],
    request: BacktestRequest,
    risk_config: RiskConfig,
) -> Tuple[float, float, float]:
    """
    Simulate win rate based on stop-loss distance.
    
    Returns:
        Tuple of (win_rate, avg_gain, avg_loss)
    """
    # ... 现有逻辑保持不变 ...
    # 但内部调用 _calculate_attempt_outcome 来填充每个 attempt 的结果
```

修改 `_run_backtest` 方法中的处理：

```python
# Step 5.5: 计算每个 attempt 的 pnl_ratio 和 exit_reason
risk_config = RiskConfig(max_loss_percent=Decimal("0.01"), max_leverage=20)
for attempt in attempts:
    pnl_ratio, exit_reason = self._calculate_attempt_outcome(
        attempt, klines, risk_config
    )
    # 这些字段将在 _attempt_to_dict 中被序列化
    attempt._pnl_ratio = pnl_ratio      # 需要扩展 SignalAttempt
    attempt._exit_reason = exit_reason

# Step 6: 计算模拟胜率
simulated_win_rate, avg_gain, avg_loss = await self._simulate_win_rate(...)
```

**注意**: 需要扩展 `SignalAttempt` 模型以支持新字段：

```python
@dc_dataclass
class SignalAttempt:
    """一次完整信号尝试的记录，无论是否最终触发信号"""
    strategy_name: str
    pattern: Optional['PatternResult']
    filter_results: list
    final_result: str
    kline_timestamp: Optional[int] = None
    
    # BT-4 新增字段
    _pnl_ratio: Optional[float] = None
    _exit_reason: Optional[str] = None
    
    @property
    def pnl_ratio(self) -> Optional[float]:
        return self._pnl_ratio
    
    @property
    def exit_reason(self) -> Optional[str]:
        return self._exit_reason
```

---

## 3. 影响范围评估

### 3.1 对现有代码的影响

| 文件 | 修改类型 | 影响行数 | 向后兼容性 |
|------|---------|---------|-----------|
| `src/domain/matching_engine.py` | 新增字段赋值 | 2 行 | ✅ 兼容 (新增字段) |
| `src/domain/filter_factory.py` | 扩展 metadata | ~100 行 | ✅ 兼容 (metadata 为 dict) |
| `src/application/backtester.py` | 扩展序列化 | ~50 行 | ✅ 兼容 (新增字段) |
| `src/domain/models.py` | 扩展 SignalAttempt | 10 行 | ✅ 兼容 (可选字段) |

### 3.2 对现有测试的影响

#### 需要更新的测试文件：

1. **`tests/unit/test_matching_engine.py`**
   - 需要验证 `order.filled_at` 被正确设置
   - 新增测试用例：`test_ut_018_filled_at_timestamp`

2. **`tests/unit/test_filter_factory.py`**
   - 需要验证各过滤器 metadata 结构
   - 更新现有断言以检查标准化字段

3. **`tests/unit/test_backtester_*.py`**
   - 需要验证 `_attempt_to_dict` 输出包含新字段
   - 更新相关集成测试

#### 测试影响评估：

```
现有测试总数：~50 个回测相关测试
需要更新的测试：~15 个
新增测试用例：~10 个
预估测试更新工时：4h
```

### 3.3 数据迁移需求

**结论**: 不需要数据迁移

**原因**:
1. `filled_at` 是订单模型的新增字段，仅在订单成交时设置
2. `metadata` 结构变更不影响现有数据（字典结构向后兼容）
3. `pnl_ratio` 和 `exit_reason` 是回测报告的衍生字段，不需要持久化

**注意**: 如果数据库中有历史订单记录，新增的 `filled_at` 字段将有默认值 `None`，不影响查询。

---

## 4. 验收标准

### 4.1 单元测试要求

#### 任务 3: filled_at 设置

```python
def test_ut_018_filled_at_timestamp():
    """验证 _execute_fill 正确设置 filled_at"""
    engine = MockMatchingEngine()
    kline = create_kline(timestamp=1711785600000)
    order = create_order(order_type=OrderType.MARKET, order_role=OrderRole.ENTRY)
    position = create_position()
    account = create_account()
    positions_map = {"sig": position}
    
    engine._execute_fill(order, Decimal("70000"), position, account, positions_map, kline.timestamp)
    
    assert order.filled_at == 1711785600000
    assert order.updated_at == 1711785600000
```

#### 任务 4: metadata 标准化

```python
def test_filter_metadata_standardization():
    """验证各过滤器 metadata 结构标准化"""
    # EMA Filter
    ema_filter = EmaTrendFilterDynamic(period=60)
    event = ema_filter.check(pattern, context)
    assert "filter_name" in event.metadata
    assert "filter_type" in event.metadata
    assert event.metadata["filter_type"] == "ema_trend"
    
    # MTF Filter
    mtf_filter = MtfFilterDynamic()
    event = mtf_filter.check(pattern, context)
    assert "higher_timeframe" in event.metadata
    assert "higher_trend" in event.metadata
    
    # ATR Filter
    atr_filter = AtrFilterDynamic(period=14)
    event = atr_filter.check(pattern, context)
    assert "candle_range" in event.metadata
    assert "atr_value" in event.metadata
    assert "volatility_ratio" in event.metadata
```

#### 任务 5: _attempt_to_dict 扩展

```python
def test_attempt_to_dict_includes_pnl_exit():
    """验证 _attempt_to_dict 包含 pnl_ratio 和 exit_reason"""
    backtester = Backtester(...)
    attempt = SignalAttempt(
        strategy_name="pinbar",
        final_result="SIGNAL_FIRED",
        ...
    )
    result = backtester._attempt_to_dict(attempt)
    
    assert "pnl_ratio" in result
    assert "exit_reason" in result
    assert isinstance(result["filter_results"][0]["metadata"], dict)
```

### 4.2 集成测试要求

```python
async def test_backtest_data_integrity_e2e():
    """端到端验证回测数据完整性"""
    # 1. 执行回测
    report = await backtester.run_backtest(request)
    
    # 2. 验证订单 filled_at
    for attempt in report.attempts:
        if attempt["final_result"] == "SIGNAL_FIRED":
            assert attempt.get("filled_at") is not None
    
    # 3. 验证 filter metadata
    for filter_result in attempt["filter_results"]:
        assert "filter_name" in filter_result["metadata"]
        assert "filter_type" in filter_result["metadata"]
    
    # 4. 验证 pnl_ratio 和 exit_reason
    fired_signals = [a for a in report.attempts if a["final_result"] == "SIGNAL_FIRED"]
    for signal in fired_signals:
        assert signal.get("pnl_ratio") is not None
        assert signal.get("exit_reason") in ["STOP_LOSS", "TAKE_PROFIT", "TIME_EXIT", None]
```

---

## 5. 实施建议

### 5.1 任务执行顺序

建议按以下顺序串行执行：

```
┌─────────────────────────────────────────────────────────────────┐
│                    任务执行顺序                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Step 1: 任务 3 - filled_at 设置 (1h)                           │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ • 修改 matching_engine.py _execute_fill()                │  │
│  │ • 添加单元测试 test_ut_018_filled_at_timestamp          │  │
│  │ • 验证现有测试通过                                        │  │
│  └───────────────────────────────────────────────────────────┘  │
│                            │                                    │
│                            ▼                                    │
│  Step 2: 任务 4 - metadata 标准化 (3h)                          │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ • 修改 filter_factory.py 各过滤器 check() 方法            │  │
│  │ • 添加 metadata 标准化字段                                 │  │
│  │ • 更新 test_filter_factory.py 测试断言                   │  │
│  └───────────────────────────────────────────────────────────┘  │
│                            │                                    │
│                            ▼                                    │
│  Step 3: 任务 5 - _attempt_to_dict 扩展 (2h)                    │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ • 扩展 SignalAttempt 模型                                 │  │
│  │ • 修改 _attempt_to_dict() 方法                            │  │
│  │ • 添加 _calculate_attempt_outcome() 辅助方法              │  │
│  │ • 更新回测测试                                             │  │
│  └───────────────────────────────────────────────────────────┘  │
│                            │                                    │
│                            ▼                                    │
│  Step 4: 集成测试验证 (2h)                                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ • 运行 test_backtest_data_integrity_e2e()                │  │
│  │ • 验证 BT-4 策略归因分析数据完整性                          │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 预估工时确认

| 阶段 | 任务 | 预估工时 | 负责人 |
|------|------|---------|--------|
| **开发** | 任务 3: filled_at 设置 | 1h | 后端开发 |
| **开发** | 任务 4: metadata 标准化 | 3h | 后端开发 |
| **开发** | 任务 5: _attempt_to_dict 扩展 | 2h | 后端开发 |
| **测试** | 单元测试更新 | 2h | QA |
| **测试** | 集成测试编写 | 2h | QA |
| **评审** | 代码审查 + 架构评审 | 1h | 架构师 |
| **总计** | | **11h** | |

### 5.3 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 现有测试失败 | 中 | 保持向后兼容，仅新增字段，不修改现有逻辑 |
| metadata 结构变更影响前端 | 低 | metadata 为字典结构，前端按需读取字段 |
| pnl_ratio 计算逻辑复杂 | 中 | 复用现有 `_simulate_win_rate` 和 `_determine_trade_outcome` 逻辑 |

---

## 6. 附录

### 6.1 相关文档

- [BT-4 策略归因分析需求](../planning/pms-backtest-requirements.md)
- [回测订单生命周期](./backtest-order-lifecycle.md)
- [v3 Phase 2 撮合引擎设计](../designs/phase2-matching-engine-contract.md)

### 6.2 参考代码位置

| 组件 | 文件路径 | 关键方法/类 |
|------|---------|------------|
| MockMatchingEngine | `src/domain/matching_engine.py` | `_execute_fill()` |
| FilterResult | `src/domain/models.py` | `FilterResult` |
| Filter Factory | `src/domain/filter_factory.py` | `EmaTrendFilterDynamic`, `MtfFilterDynamic`, `AtrFilterDynamic` |
| Backtester | `src/application/backtester.py` | `_attempt_to_dict()`, `_simulate_win_rate()` |

### 6.3 缩略语

| 缩略语 | 含义 |
|--------|------|
| BT-4 | Backtest Task 4: 策略归因分析 |
| PnL | Profit and Loss (盈亏) |
| MTF | Multi-Timeframe (多时间框架) |
| ATR | Average True Range (平均真实波幅) |
| EMA | Exponential Moving Average (指数移动平均) |

---

**文档状态**: 待评审 (Pending Review)

**下一步**: 
1. 架构师评审
2. 开发人员确认实现方案
3. QA 确认测试方案
4. 进入实施阶段
