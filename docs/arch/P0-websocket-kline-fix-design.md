# ADR-P0: WebSocket K 线选择逻辑修复设计

> **架构决策记录 (Architecture Decision Record)**  
> **文档级别**: P0 关键缺陷修复  
> **创建日期**: 2026-04-08  
> **状态**: 待用户确认 (Pending Approval)  
> **影响范围**: ExchangeGateway, WebSocket K 线处理，Pinbar 形态检测  
> **关联任务**: P0 缺陷修复计划

---

## 摘要

修复 WebSocket K 线选择逻辑错误，确保系统处理**已收盘 K 线**而非**未收盘 K 线**。当前逻辑错误地使用 `ohlcv[-1]`（最新未收盘 K 线）进行形态检测，导致信号误判。修复后采用**交易所契约优先 + 多层防御**方案，优先使用交易所 `x` 字段判断 K 线收盘状态，后备采用时间戳推断机制。

---

## 1. 问题背景

### 1.1 WebSocket 推送机制

| K 线索引 | 收盘状态 | `info.x` 字段 | 数据特性 |
|----------|----------|--------------|----------|
| `ohlcv[-1]` | 未收盘 | `x=false` (或缺失) | 实时更新，每 250ms (合约) / 1 秒 (现货) |
| `ohlcv[-2]` | 已收盘 | `x=true` (或缺失) | 最终值，不再变化 |

**当前错误行为**:
```python
# ❌ 错误逻辑
candle = ohlcv[-1]  # 最新未收盘 K 线
if self._is_candle_closed(kline, ...):
    await callback(kline)  # 返回的是未收盘的数据
```

**问题表现**:
1. K 线尚未收盘时触发形态检测
2. 检测基于实时变动的价格（非最终值）
3. 可能导致虚假信号（价格在收盘前反转）

### 1.2 核心问题清单

| 编号 | 问题描述 | 严重级别 | 当前状态 |
|------|----------|----------|----------|
| P0-1 | WebSocket K 线选择逻辑错误 | 🔴 严重 | 待修复 |
| P0-2 | ATR 过滤器默认值过小 (`min_atr_ratio=0.001`) | 🟡 警告 | 保持默认不启用 |
| P0-3 | Pinbar 形态检测缺少最小波幅检查 | 🟡 警告 | 待修复 |

---

## 2. 决策方案

### 2.1 方案选择：交易所契约优先 + 多层防御

| 方案 | 描述 | 优点 | 缺点 | 选择 |
|------|------|------|------|------|
| **方案 A** | 优先使用交易所 `x` 字段，后备时间戳推断 | 准确性高，兼容多交易所 | 实现稍复杂 | ✅ **已选择** |
| 方案 B | 仅使用时间戳推断 | 实现简单 | 依赖本地时钟，精度较低 | ❌ |
| 方案 C | 仅使用 `x` 字段 | 最准确 | 部分交易所不支持 | ❌ |

### 2.2 技术决策清单

| 决策项 | 选择 | 理由 |
|--------|------|------|
| **K 线选择策略** | 交易所 `x` 字段优先 | 交易所官方契约，准确性最高 |
| **后备机制** | 时间戳推断 | 兼容不支持 `x` 字段的交易所 |
| **ATR 阈值** | 动态 ATR（Pinbar 使用 10%） | 自适应不同币种/时间框架 |
| **ATR 过滤器** | ⚠️ **默认不启用** (`enabled=False`) | 用户明确要求 |
| **日志策略** | DEBUG 级别 | 避免刷屏，便于问题排查 |

---

## 3. 技术方案详细设计

### 3.1 K 线收盘状态判断逻辑

```python
def _parse_ohlcv(
    self, 
    candle: List[Any], 
    symbol: str, 
    timeframe: str,
    raw_info: Optional[Dict] = None  # 新增：交易所原始数据
) -> Optional[KlineData]:
    """
    解析 OHLCV 蜡烛图为 KlineData 模型。
    
    核心逻辑：
    1. 优先使用交易所 info.x 字段判断收盘状态
    2. 后备使用时间戳推断
    """
    # 方案 1: 优先使用交易所 x 字段
    if raw_info and 'x' in raw_info:
        is_closed = bool(raw_info['x'])  # True = 已收盘，False = 未收盘
    else:
        # 方案 2: 时间戳推断（后备）
        # 在 subscribe_ohlcv 中通过时间戳变化判断
        is_closed = True  # 默认假设已收盘
    
    return KlineData(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=int(candle[0]),
        open=Decimal(str(candle[1])),
        high=Decimal(str(candle[2])),
        low=Decimal(str(candle[3])),
        close=Decimal(str(candle[4])),
        volume=Decimal(str(candle[5])),
        is_closed=is_closed,  # 新增字段
        info=raw_info,  # 保留原始数据（可选）
    )
```

### 3.2 WebSocket K 线选择逻辑（核心修复）

```python
async def _subscribe_ohlcv_loop(
    self,
    symbol: str,
    timeframe: str,
    callback: Callable[[KlineData], Awaitable[None]],
    history_bars: int = 100,
) -> None:
    """
    订阅 K 线循环（修复版）。
    
    核心逻辑：
    - 当 x=true 时，ohlcv[-1] 就是刚收盘的 K 线
    - 当 x=false 或无 x 字段时，使用 ohlcv[-2]（前一根已收盘 K 线）
    """
    while self._ws_running:
        try:
            # Watch OHLCV (blocking call that receives updates)
            ohlcv = await self.ws_exchange.watch_ohlcv(symbol, timeframe)
            
            if not ohlcv or len(ohlcv) < 1:
                continue
            
            # ============================================================
            # 🔴 核心修复：正确处理刚收盘的 K 线
            # ============================================================
            
            # 方案 1: 优先使用交易所 x 字段
            latest_candle = ohlcv[-1]
            if len(latest_candle) > 6 and isinstance(latest_candle[6], dict):
                raw_info = latest_candle[6]
                if 'x' in raw_info:
                    is_closed = bool(raw_info['x'])
                    
                    if is_closed:
                        # ✅ 当 x=true 时，ohlcv[-1] 就是刚收盘的 K 线
                        kline = self._parse_ohlcv(latest_candle, symbol, timeframe, raw_info)
                        if kline:
                            await callback(kline)
                    # else: x=false，未收盘，跳过
                    
                    continue  # 已处理，跳过后续逻辑
            
            # 方案 2: 时间戳推断（后备）
            if len(ohlcv) >= 2:
                prev_candle = ohlcv[-2]  # 🔴 前一根已收盘 K 线
                kline = self._parse_ohlcv(prev_candle, symbol, timeframe)
                if kline:
                    # 使用时间戳检测变化
                    key = f"{symbol}:{timeframe}"
                    current_ts = kline.timestamp
                    
                    if key not in self._candle_timestamps:
                        self._candle_timestamps[key] = current_ts
                    elif current_ts != self._candle_timestamps[key]:
                        self._candle_timestamps[key] = current_ts
                        await callback(kline)
            
            # ... 异常处理和重连逻辑 ...
```

### 3.3 Pinbar 最小波幅检查（形态检测层）

```python
# src/domain/strategy_engine.py - PinbarStrategy.detect()

def detect(
    self, 
    kline: KlineData, 
    atr_value: Optional[Decimal] = None
) -> Optional[PatternResult]:
    """
    检测 Pinbar 形态（修复版）。
    
    新增：最小波幅检查（防止开盘初期波幅极小误判）
    
    逻辑：
    - 如果 ATR 可用：min_required_range = atr * 0.1 (10%)
    - 后备：min_required_range = 0.5 USDT (固定值)
    """
    high = kline.high
    low = kline.low
    close = kline.close
    open_price = kline.open
    
    # Calculate candle range
    candle_range = high - low
    if candle_range == Decimal(0):
        return None
    
    # ============================================================
    # 🔴 新增：最小波幅检查（形态检测层）
    # ============================================================
    if atr_value and atr_value > 0:
        min_required_range = atr_value * Decimal("0.1")  # ATR 的 10%
    else:
        min_required_range = Decimal("0.5")  # 固定后备值
    
    if candle_range < min_required_range:
        # 波幅太小，可能是开盘初期或低波动市场
        return None
    
    # ... 原有 Pinbar 检测逻辑 ...
```

### 3.4 ATR 过滤器配置（保持默认不启用）

```python
# src/domain/filter_factory.py - AtrFilterDynamic.__init__()

def __init__(
    self, 
    period: int = 14, 
    min_atr_ratio: Decimal = Decimal("0.001"),  # ⚠️ 保持当前值
    enabled: bool = False  # ✅ 用户要求：默认不启用
):
    self._period = period
    self._min_atr_ratio = min_atr_ratio  # 如果启用，建议调整为 0.02 (2%)
    self._enabled = enabled
    self._atr_state: Dict[str, Dict[str, Any]] = {}
```

**注意**: 
- ATR 过滤器与 Pinbar 最小波幅检查处于**不同层次**，不冲突
- 形态检测层：ATR 10%（防止开盘初期误判）
- ATR 过滤器层：ATR 2%（过滤低波动市场，可选，默认不启用）

---

## 4. 修改文件清单

### 4.1 核心修改文件

| 文件路径 | 修改类型 | 修改内容 |
|----------|----------|----------|
| `src/infrastructure/exchange_gateway.py` | 🔴 核心修复 | `_parse_ohlcv()` 增加 `x` 字段支持；`_subscribe_ohlcv_loop()` 修复 K 线选择逻辑 |
| `src/domain/strategy_engine.py` | 🟡 增强 | `PinbarStrategy.detect()` 增加最小波幅检查 |
| `src/domain/models.py` | 🟡 增强 | `KlineData` 增加 `is_closed` 和 `info` 字段（如尚未存在） |
| `src/domain/filter_factory.py` | 🟢 配置 | `AtrFilterDynamic.__init__()` 确认 `enabled=False` 默认值 |

### 4.2 辅助修改文件

| 文件路径 | 修改类型 | 修改内容 |
|----------|----------|----------|
| `src/interfaces/api.py` | 🟢 配置 | 确认默认 ATR 参数（`enabled=false`） |
| `tests/unit/test_exchange_gateway.py` | 🟢 测试 | 更新 WebSocket K 线处理测试 |
| `tests/unit/test_strategy_engine.py` | 🟢 测试 | 增加 Pinbar 最小波幅检查测试 |

---

## 5. 接口契约变更

### 5.1 `KlineData` 模型变更

```python
@dc.dataclass
class KlineData:
    """K 线数据模型（更新版）"""
    symbol: str
    timeframe: str
    timestamp: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    # ✅ 新增字段
    is_closed: bool = True  # K 线是否已收盘
    info: Optional[Dict[str, Any]] = None  # 交易所原始数据（可选）
```

### 5.2 `_parse_ohlcv()` 方法签名变更

```python
# 旧签名
def _parse_ohlcv(
    self, 
    candle: List[Any], 
    symbol: str, 
    timeframe: str
) -> Optional[KlineData]:

# 新签名
def _parse_ohlcv(
    self, 
    candle: List[Any], 
    symbol: str, 
    timeframe: str,
    raw_info: Optional[Dict] = None  # ✅ 新增参数
) -> Optional[KlineData]:
```

### 5.3 `PinbarStrategy.detect()` 方法签名变更

```python
# 旧签名
def detect(self, kline: KlineData) -> Optional[PatternResult]:

# 新签名
def detect(
    self, 
    kline: KlineData, 
    atr_value: Optional[Decimal] = None  # ✅ 新增参数
) -> Optional[PatternResult]:
```

---

## 6. 测试验证要求

### 6.1 单元测试

| 测试用例 | 测试目标 | 验收标准 |
|----------|----------|----------|
| `test_x_field_priority()` | 验证 `x` 字段优先使用 | 当 `x=true` 时返回已收盘 K 线 |
| `test_x_false_skip()` | 验证 `x=false` 时跳过 | 当 `x=false` 时不触发回调 |
| `test_timestamp_fallback()` | 验证时间戳后备机制 | 无 `x` 字段时正确推断 |
| `test_pinbar_min_range_with_atr()` | 验证 ATR 10% 最小波幅 | ATR=50 时，最小波幅=5 |
| `test_pinbar_min_range_without_atr()` | 验证固定后备值 | 无 ATR 时，最小波幅=0.5 |

### 6.2 集成测试

| 测试用例 | 测试目标 | 验收标准 |
|----------|----------|----------|
| `test_websocket_kline_selection()` | WebSocket K 线选择 | 只处理已收盘 K 线 |
| `test_pinbar_with_low_volatility()` | 低波动 Pinbar 过滤 | 波幅<ATR 10% 不触发 |

### 6.3 验收标准

1. **功能性**: 所有新增测试用例 100% 通过
2. **正确性**: WebSocket 仅推送已收盘 K 线（通过日志验证）
3. **性能**: 无显著性能回退（对比修复前）
4. **覆盖率**: 修改代码行覆盖率 >85%

---

## 7. 风险评估

### 7.1 技术风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 交易所 `x` 字段格式不一致 | 中 | 中 | 增加异常处理，降级到时间戳推断 |
| 时间戳推断精度问题 | 低 | 中 | 增加单元测试覆盖边界情况 |
| Pinbar 最小波幅误杀 | 中 | 低 | 使用 ATR 10%（较宽松阈值） |

### 7.2 业务风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 信号数量减少 | 高 | - | 预期行为：过滤虚假信号 |
| 回测结果变化 | 高 | 中 | 预期行为：更准确反映实盘 |

### 7.3 回滚方案

1. **Git 回滚**: 保留修复前 commit hash，必要时 `git revert`
2. **配置开关**: 可通过配置禁用新逻辑（如需要）

---

## 8. 替代方案

### 方案 B: 仅使用时间戳推断

**描述**: 不依赖交易所 `x` 字段，完全通过时间戳变化判断。

**优点**:
- 实现简单
- 不依赖交易所特定字段

**缺点**:
- 精度较低（依赖本地时钟）
- 可能错过刚收盘的 K 线（需等待下一根 K 线开始）

**未采用理由**: 准确性不足，不符合 P0 级修复要求

### 方案 C: 仅使用 `x` 字段

**描述**: 完全依赖交易所 `x` 字段，无后备机制。

**优点**:
- 最准确

**缺点**:
- 部分交易所可能不支持
- 单点故障风险

**未采用理由**: 缺乏容错机制

---

## 9. 后果

### 9.1 积极影响

1. **信号质量提升**
   - 基于已收盘 K 线（最终值）
   - 减少虚假信号（收盘前反转）

2. **系统可靠性增强**
   - 多层防御机制
   - 优雅的后备处理

3. **可维护性改善**
   - 清晰的逻辑分层
   - 显式的收盘状态标识

### 9.2 消极影响

1. **信号数量可能减少**
   - 预期行为：过滤低质量信号
   - 影响：需要重新评估历史信号统计

2. **回测结果变化**
   - 预期行为：更准确
   - 影响：需要更新回测基准

### 9.3 后续工作

1. **监控**: 增加 K 线收盘状态日志（DEBUG 级别）
2. **分析**: 对比修复前后信号质量
3. **优化**: 根据实际数据调整 Pinbar 最小波幅阈值

---

## 10. 决策记录

| 角色 | 人员 |
|------|------|
| 决策人 | 用户确认 |
| 决策时间 | 待定 |
| 评审人 | 架构师 |
| 记录人 | 架构师 |

### 决策确认清单

| 决策项 | 确认选择 | 状态 |
|--------|----------|------|
| **K 线选择策略** | 交易所 `x` 字段优先 + 时间戳后备 | ⏳ 待确认 |
| **ATR 阈值** | 动态 ATR（Pinbar 使用 10%） | ✅ 已确认 |
| **ATR 过滤器** | 默认不启用 (`enabled=False`) | ✅ 已确认 |
| **日志策略** | DEBUG 级别 | ✅ 已确认 |

---

## 11. 附录

### 11.1 参考文档

- [CCXT Pro OHLCV 文档](https://docs.ccxt.com/en/latest/manual.html#ohlcv)
- [Exchange API 规范](../api-contracts/)
- [Clean Architecture 分层约束](2026-03-25-系统开发规范与红线.md)

### 11.2 相关文件

- [P0 实施清单](./P0-implementation-checklist.md)
- [P0 测试清单](./P0-test-checklist.md)

---

*本 ADR 遵循 [Joel Parker Henderson](https://adr.github.io/) 的 ADR 模板格式*

*文档版本: 1.0*  
*创建日期: 2026-04-08*
