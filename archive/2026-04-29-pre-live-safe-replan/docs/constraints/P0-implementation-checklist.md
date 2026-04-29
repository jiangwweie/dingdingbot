# P0 WebSocket K 线选择逻辑修复 - 实施清单

> **文档类型**: 实施清单 (Implementation Checklist)  
> **关联 ADR**: [P0-websocket-kline-fix-design.md](./P0-websocket-kline-fix-design.md)  
> **创建日期**: 2026-04-08  
> **状态**: 待实施 (Pending Implementation)  
> **预计工时**: 4-6 小时

---

## 一、修改文件总览

### 1.1 核心修改文件 (必须修改)

| # | 文件路径 | 修改类型 | 优先级 | 预计工时 |
|---|----------|----------|--------|----------|
| 1 | `src/infrastructure/exchange_gateway.py` | 🔴 核心修复 | P0 | 2h |
| 2 | `src/domain/strategy_engine.py` | 🟡 增强 | P0 | 1h |
| 3 | `src/domain/models.py` | 🟡 模型扩展 | P0 | 0.5h |
| 4 | `src/domain/filter_factory.py` | 🟢 配置确认 | P1 | 0.5h |

### 1.2 测试文件 (新增/更新)

| # | 文件路径 | 修改类型 | 优先级 |
|---|----------|----------|--------|
| 1 | `tests/unit/test_exchange_gateway_websocket.py` | 新增 | P0 |
| 2 | `tests/unit/test_strategy_engine_pinbar.py` | 更新 | P0 |
| 3 | `tests/unit/test_filter_factory_atr.py` | 更新 | P1 |

---

## 二、详细实施步骤

### 2.1 文件 1: `src/infrastructure/exchange_gateway.py`

**修改位置 1**: `KlineData` 模型定义 (如尚未在 `models.py` 中添加)

```python
# 确认 KlineData 包含以下字段
@dc.dataclass
class KlineData:
    symbol: str
    timeframe: str
    timestamp: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    # ✅ 确认以下字段存在
    is_closed: bool = True
    info: Optional[Dict[str, Any]] = None  # 交易所原始数据
```

---

**修改位置 2**: `_parse_ohlcv()` 方法

**当前代码位置**: 约 第 340-380 行

**修改前**:
```python
def _parse_ohlcv(
    self, 
    candle: List[Any], 
    symbol: str, 
    timeframe: str
) -> Optional[KlineData]:
    """解析 OHLCV 蜡烛图"""
    return KlineData(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=int(candle[0]),
        open=Decimal(str(candle[1])),
        high=Decimal(str(candle[2])),
        low=Decimal(str(candle[3])),
        close=Decimal(str(candle[4])),
        volume=Decimal(str(candle[5])),
        is_closed=True,  # ← 硬编码为 True
    )
```

**修改后**:
```python
def _parse_ohlcv(
    self, 
    candle: List[Any], 
    symbol: str, 
    timeframe: str,
    raw_info: Optional[Dict] = None  # ✅ 新增参数
) -> Optional[KlineData]:
    """
    解析 OHLCV 蜡烛图为 KlineData 模型。
    
    核心逻辑：
    1. 优先使用交易所 info.x 字段判断收盘状态
    2. 后备使用时间戳推断
    """
    # 方案 1: 优先使用交易所 x 字段
    is_closed = True  # 默认假设已收盘
    
    if raw_info and 'x' in raw_info:
        is_closed = bool(raw_info['x'])
        logger.debug(
            f"[K 线解析] {symbol} {timeframe} x={is_closed} "
            f"ts={candle[0]} close={candle[4]}"
        )
    
    return KlineData(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=int(candle[0]),
        open=Decimal(str(candle[1])),
        high=Decimal(str(candle[2])),
        low=Decimal(str(candle[3])),
        close=Decimal(str(candle[4])),
        volume=Decimal(str(candle[5])),
        is_closed=is_closed,  # ✅ 使用动态值
        info=raw_info,  # ✅ 保留原始数据（可选）
    )
```

---

**修改位置 3**: `_subscribe_ohlcv_loop()` 方法 (核心修复)

**当前代码位置**: 约 第 380-440 行

**修改前**:
```python
async def _subscribe_ohlcv_loop(
    self,
    symbol: str,
    timeframe: str,
    callback: Callable[[KlineData], Awaitable[None]],
    history_bars: int = 100,
) -> None:
    while self._ws_running:
        try:
            ohlcv = await self.ws_exchange.watch_ohlcv(symbol, timeframe)
            
            if not ohlcv:
                continue
            
            # ❌ 错误：直接使用 ohlcv[-1]
            candle = ohlcv[-1]
            kline = self._parse_ohlcv(candle, symbol, timeframe)
            
            if not kline:
                continue
            
            # ❌ 错误：时间戳推断逻辑基于未收盘 K 线
            if self._is_candle_closed(kline, symbol, timeframe):
                await callback(kline)
```

**修改后**:
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
            ohlcv = await self.ws_exchange.watch_ohlcv(symbol, timeframe)
            
            if not ohlcv or len(ohlcv) < 1:
                continue
            
            # ============================================================
            # 🔴 核心修复：正确处理刚收盘的 K 线
            # ============================================================
            
            latest_candle = ohlcv[-1]
            
            # 方案 1: 优先使用交易所 x 字段
            # CCXT Pro 规范：candle[6] 可能包含 info 字典，其中有 x 字段
            if len(latest_candle) > 6 and isinstance(latest_candle[6], dict):
                raw_info = latest_candle[6]
                if 'x' in raw_info:
                    is_closed = bool(raw_info['x'])
                    
                    if is_closed:
                        # ✅ 当 x=true 时，ohlcv[-1] 就是刚收盘的 K 线
                        kline = self._parse_ohlcv(latest_candle, symbol, timeframe, raw_info)
                        if kline:
                            logger.debug(
                                f"[WebSocket K 线] {symbol} {timeframe} "
                                f"收盘确认 x=true ts={kline.timestamp} close={kline.close}"
                            )
                            await callback(kline)
                    # else: x=false，未收盘，跳过
                    continue  # 已处理，跳过后续逻辑
            
            # 方案 2: 时间戳推断（后备）
            # 适用于不支持 x 字段的交易所
            if len(ohlcv) >= 2:
                prev_candle = ohlcv[-2]  # 🔴 前一根已收盘 K 线
                kline = self._parse_ohlcv(prev_candle, symbol, timeframe)
                if kline:
                    key = f"{symbol}:{timeframe}"
                    current_ts = kline.timestamp
                    
                    if key not in self._candle_timestamps:
                        self._candle_timestamps[key] = current_ts
                    elif current_ts != self._candle_timestamps[key]:
                        self._candle_timestamps[key] = current_ts
                        logger.debug(
                            f"[WebSocket K 线] {symbol} {timeframe} "
                            f"时间戳推断收盘 ts={current_ts} close={kline.close}"
                        )
                        await callback(kline)
            
            # ... 异常处理和重连逻辑保持不变 ...
```

---

**检查清单**:

- [ ] 确认 `_parse_ohlcv()` 方法签名已更新
- [ ] 确认 `x` 字段解析逻辑正确
- [ ] 确认时间戳后备机制正确
- [ ] 添加 DEBUG 级别日志（避免刷屏）
- [ ] 确认异常处理逻辑完整

---

### 2.2 文件 2: `src/domain/strategy_engine.py`

**修改位置**: `PinbarStrategy.detect()` 方法

**当前代码位置**: 约 第 184-276 行

**修改内容**: 在形态检测前增加最小波幅检查

**修改前**:
```python
def detect(self, kline: KlineData, atr_value: Optional[Decimal] = None) -> Optional[PatternResult]:
    """Detect Pinbar geometric pattern..."""
    cfg = self._config
    
    high = kline.high
    low = kline.low
    close = kline.close
    open_price = kline.open
    
    # Calculate candle range
    candle_range = high - low
    if candle_range == Decimal(0):
        return None
    
    # ❌ 缺失：最小波幅检查
    # 直接继续检测...
```

**修改后**:
```python
def detect(self, kline: KlineData, atr_value: Optional[Decimal] = None) -> Optional[PatternResult]:
    """
    Detect Pinbar geometric pattern on a single K-line.
    
    新增：最小波幅检查（防止开盘初期波幅极小误判）
    
    逻辑：
    - 如果 ATR 可用：min_required_range = atr * 0.1 (10%)
    - 后备：min_required_range = 0.5 USDT (固定值)
    """
    cfg = self._config
    
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
        logger.debug(
            f"[Pinbar] 波幅过小过滤：{kline.symbol} {kline.timeframe} "
            f"range={candle_range} min={min_required_range} "
            f"(ATR={atr_value})"
        )
        return None  # 波幅太小，可能是开盘初期或低波动市场
    
    # ... 原有 Pinbar 检测逻辑保持不变 ...
```

---

**检查清单**:

- [ ] 确认 `detect()` 方法已接受 `atr_value` 参数
- [ ] 确认最小波幅检查逻辑正确
- [ ] 确认 ATR 10% 阈值使用正确
- [ ] 确认固定后备值 0.5 USDT 正确
- [ ] 添加 DEBUG 级别日志

---

### 2.3 文件 3: `src/domain/models.py`

**修改位置**: `KlineData` 模型定义

**当前代码位置**: 约 第 84-95 行

**确认内容**:

```python
@dc.dataclass
class KlineData:
    """Single closed K-line (candlestick) data"""
    symbol: str                 # e.g., "BTC/USDT:USDT"
    timeframe: str              # "15m", "1h", "4h", "1d", "1w"
    timestamp: int              # Millisecond timestamp
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal             # Volume in base asset
    # ✅ 确认以下字段存在
    is_closed: bool = True      # K 线是否已收盘
    info: Optional[Dict[str, Any]] = None  # 交易所原始数据（可选）
```

---

**检查清单**:

- [ ] 确认 `is_closed` 字段存在
- [ ] 确认 `info` 字段存在（可选）
- [ ] 确认字段默认值正确

---

### 2.4 文件 4: `src/domain/filter_factory.py`

**修改位置**: `AtrFilterDynamic.__init__()` 方法

**当前代码位置**: 约 第 425-430 行

**确认内容** (用户要求保持默认不启用):

```python
def __init__(
    self, 
    period: int = 14, 
    min_atr_ratio: Decimal = Decimal("0.001"),  # ⚠️ 保持当前值
    enabled: bool = False  # ✅ 用户要求：默认不启用
):
    self._period = period
    self._min_atr_ratio = min_atr_ratio
    self._enabled = enabled  # ✅ 确认默认为 False
    self._atr_state: Dict[str, Dict[str, Any]] = {}
```

---

**检查清单**:

- [ ] 确认 `enabled=False` 默认值
- [ ] 确认 `min_atr_ratio=0.001` 保持当前值
- [ ] 在代码注释中说明：如启用，建议调整为 0.02 (2%)

---

## 三、代码修改要点

### 3.1 核心修复点

| 修复点 | 描述 | 文件位置 |
|--------|------|----------|
| 🔴 P0-1 | WebSocket K 线选择逻辑 | `exchange_gateway.py:_subscribe_ohlcv_loop()` |
| 🟡 P0-2 | `x` 字段优先解析 | `exchange_gateway.py:_parse_ohlcv()` |
| 🟡 P0-3 | 时间戳后备机制 | `exchange_gateway.py:_subscribe_ohlcv_loop()` |
| 🟢 P0-4 | Pinbar 最小波幅检查 | `strategy_engine.py:PinbarStrategy.detect()` |
| 🟢 P0-5 | ATR 过滤器默认值确认 | `filter_factory.py:AtrFilterDynamic.__init__()` |

### 3.2 技术约束

- **Clean Architecture**: `domain/` 层禁止依赖 `infrastructure/` 层
- **金融精度**: 所有金额/比率计算使用 `Decimal`（禁止 `float`）
- **日志级别**: 使用 `DEBUG`（避免刷屏）
- **交易所字段**: 优先使用 `x` 字段，后备时间戳推断

### 3.3 关键决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| K 线选择策略 | 交易所 `x` 字段优先 | 交易所官方契约，准确性最高 |
| 后备机制 | 时间戳推断 | 兼容不支持 `x` 字段的交易所 |
| ATR 阈值 | 动态 ATR（Pinbar 使用 10%） | 自适应不同币种/时间框架 |
| ATR 过滤器 | 默认不启用 (`enabled=False`) | 用户明确要求 |

---

## 四、实施前检查

### 4.1 环境准备

- [ ] 确认 Python 版本 >= 3.10
- [ ] 确认 CCXT Pro 已安装 (`pip show ccxt`)
- [ ] 确认测试环境可用

### 4.2 代码审查准备

- [ ] 阅读完整 ADR 文档
- [ ] 理解 WebSocket K 线推送机制
- [ ] 理解 Clean Architecture 分层约束

### 4.3 分支管理

- [ ] 创建新分支：`git checkout -b feature/p0-websocket-kline-fix`
- [ ] 确认基于最新 `main` 分支

---

## 五、实施后检查

### 5.1 代码质量

- [ ] 所有修改文件通过 `flake8` 检查
- [ ] 所有修改文件通过 `mypy` 类型检查
- [ ] 代码格式符合项目规范

### 5.2 功能验证

- [ ] WebSocket K 线只处理已收盘数据
- [ ] Pinbar 最小波幅检查生效
- [ ] ATR 过滤器默认不启用
- [ ] 日志输出为 DEBUG 级别

### 5.3 文档更新

- [ ] 更新 CHANGELOG
- [ ] 更新相关 API 文档

---

## 六、回滚方案

如修复导致问题，可按以下步骤回滚：

1. **Git 回滚**: `git revert <commit-hash>`
2. **配置开关**: 如需要，可增加配置项禁用新逻辑
3. **日志分析**: 检查 DEBUG 日志定位问题

---

*文档版本: 1.0*  
*创建日期: 2026-04-08*  
*最后更新: 2026-04-08*
