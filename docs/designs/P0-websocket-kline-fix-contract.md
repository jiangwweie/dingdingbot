# P0 修复契约表 - WebSocket K 线选择逻辑

> **契约级别**: P0 关键缺陷修复  
> **创建日期**: 2026-04-08  
> **关联 ADR**: [P0-websocket-kline-fix-design.md](../arch/P0-websocket-kline-fix-design.md)  
> **实施负责人**: Project Manager

---

## 1. 数据模型契约

### 1.1 KlineData 模型扩展

**修改文件**: `src/domain/models.py`

**变更内容**:

```python
class KlineData(BaseModel):
    """Single closed K-line (candlestick) data"""
    symbol: str
    timeframe: str
    timestamp: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    is_closed: bool = True
    info: Optional[Dict[str, Any]] = None  # ✅ 新增字段
```

**契约要点**:
- `info` 字段存储交易所原始数据（包含 `x` 字段）
- 默认值为 `None`（向后兼容）
- 如果 `info` 包含 `x` 字段，优先用于判断 `is_closed`

---

## 2. 方法签名契约

### 2.1 `_parse_ohlcv()` 方法扩展

**修改文件**: `src/infrastructure/exchange_gateway.py`

**变更前**:
```python
def _parse_ohlcv(
    self, 
    candle: List[Any], 
    symbol: str, 
    timeframe: str
) -> Optional[KlineData]:
```

**变更后**:
```python
def _parse_ohlcv(
    self, 
    candle: List[Any], 
    symbol: str, 
    timeframe: str,
    raw_info: Optional[Dict] = None  # ✅ 新增参数
) -> Optional[KlineData]:
```

**契约要点**:
- `raw_info` 参数可选，默认为 `None`
- 如果 `raw_info` 包含 `x` 字段，使用其值设置 `is_closed`
- 如果 `raw_info` 为 `None` 或无 `x` 字段，默认 `is_closed=True`

---

### 2.2 `_get_closed_candle()` 方法重构

**修改文件**: `src/infrastructure/exchange_gateway.py`

**当前逻辑**:
```python
def _get_closed_candle(self, ohlcv: List[Any], symbol: str, timeframe: str) -> Optional[KlineData]:
    # 仅使用时间戳推断
    if len(ohlcv) < 2:
        return None
    
    key = f"{symbol}:{timeframe}"
    current_ts = ohlcv[-1][0]
    
    if key in self._candle_timestamps:
        if current_ts != self._candle_timestamps[key]:
            self._candle_timestamps[key] = current_ts
            closed_candle = ohlcv[-2]
            return self._parse_ohlcv(closed_candle, symbol, timeframe)
    else:
        self._candle_timestamps[key] = current_ts
    
    return None
```

**修复后逻辑**:
```python
def _get_closed_candle(self, ohlcv: List[Any], symbol: str, timeframe: str) -> Optional[KlineData]:
    """
    检测 K 线收盘并返回收盘 K 线数据（修复版）。
    
    优先级：
    1. 使用交易所 x 字段判断（最准确）
    2. 时间戳推断后备（兼容不支持 x 字段的交易所）
    """
    if not ohlcv or len(ohlcv) < 1:
        return None
    
    # ============================================================
    # 🔴 方案 1: 优先使用交易所 x 字段
    # ============================================================
    latest_candle = ohlcv[-1]
    
    # CCXT Pro 返回的 ohlcv 数组第 7 个元素（index 6）是原始信息
    if len(latest_candle) > 6 and isinstance(latest_candle[6], dict):
        raw_info = latest_candle[6]
        
        if 'x' in raw_info:
            is_closed = bool(raw_info['x'])
            
            if is_closed:
                # ✅ 当 x=true 时，ohlcv[-1] 就是刚收盘的 K 线
                logger.debug(
                    f"[X_FIELD] Detected closed candle via x=true: "
                    f"{symbol} {timeframe} @ {latest_candle[0]}"
                )
                return self._parse_ohlcv(latest_candle, symbol, timeframe, raw_info)
            else:
                # x=false，未收盘，跳过
                logger.debug(
                    f"[X_FIELD] Skipping unclosed candle (x=false): "
                    f"{symbol} {timeframe} @ {latest_candle[0]}"
                )
                return None
    
    # ============================================================
    # 🔴 方案 2: 时间戳推断后备
    # ============================================================
    if len(ohlcv) < 2:
        return None
    
    key = f"{symbol}:{timeframe}"
    current_ts = ohlcv[-1][0]  # 新 K 线时间戳
    
    if key in self._candle_timestamps:
        if current_ts != self._candle_timestamps[key]:
            # 时间戳变化 → 前一根 K 线刚收盘
            self._candle_timestamps[key] = current_ts
            
            closed_candle = ohlcv[-2]
            logger.debug(
                f"[TIMESTAMP_FALLBACK] Detected closed candle via timestamp: "
                f"{symbol} {timeframe} @ {closed_candle[0]}"
            )
            return self._parse_ohlcv(closed_candle, symbol, timeframe)
    else:
        # 首次见到该 symbol:timeframe
        self._candle_timestamps[key] = current_ts
    
    return None
```

**契约要点**:
- 优先检查 `x` 字段（交易所官方契约）
- `x=true` → 返回 `ohlcv[-1]`（刚收盘的 K 线）
- `x=false` → 返回 `None`（跳过未收盘 K 线）
- 无 `x` 字段 → 降级到时间戳推断（使用 `ohlcv[-2]`）
- 所有路径都调用 `_parse_ohlcv()` 并传入 `raw_info`

---

### 2.3 `PinbarStrategy.detect()` 方法扩展

**修改文件**: `src/domain/strategy_engine.py`

**变更前**:
```python
def detect(self, kline: KlineData, atr_value: Optional[Decimal] = None) -> Optional[PatternResult]:
    # 无最小波幅检查
```

**变更后**:
```python
def detect(self, kline: KlineData, atr_value: Optional[Decimal] = None) -> Optional[PatternResult]:
    """
    检测 Pinbar 形态（修复版）。
    
    新增：最小波幅检查（防止开盘初期波幅极小误判）
    """
    # ... 计算波幅 ...
    
    # ✅ 新增：最小波幅检查
    if atr_value and atr_value > 0:
        min_required_range = atr_value * Decimal("0.1")  # ATR 的 10%
    else:
        min_required_range = Decimal("0.5")  # 固定后备值
    
    if candle_range < min_required_range:
        logger.debug(
            f"Pinbar min range check failed: range={candle_range} < min={min_required_range} "
            f"(atr={atr_value}) for {kline.symbol} {kline.timeframe}"
        )
        return None
    
    # ... 原有检测逻辑 ...
```

**契约要点**:
- 动态 ATR 阈值：`min_range = atr * 0.1`（ATR 的 10%）
- 固定后备阈值：`min_range = 0.5` USDT（当 ATR 不可用时）
- 检查失败 → 返回 `None`（跳过形态）
- 所有日志使用 DEBUG 级别

---

## 3. 行为契约

### 3.1 WebSocket K 线处理流程

**期望行为**:

```
WebSocket 推送 (每 250ms/1s)
    ↓
检查 ohlcv[-1] 的 x 字段
    ↓
┌─────────────────┐
│ x 字段存在？    │
└────┬────────────┘
     │
     ├─ Yes ──┐
     │        │
     │    ┌───▼──────────┐
     │    │ x = true？   │
     │    └───┬──────────┘
     │        │
     │        ├─ Yes ──→ 返回 ohlcv[-1]（刚收盘）
     │        │
     │        └─ No ────→ 跳过（未收盘）
     │
     └─ No ──→ 使用时间戳推断
                    ↓
              时间戳变化？
                    ↓
                 ┌──┴──┐
                 │     │
              Yes│     │No
                 │     │
                 ▼     ▼
          返回 ohlcv[-2]  跳过
```

**关键断言**:
1. ✅ 当且仅当 K 线已收盘时，才触发回调
2. ✅ 优先使用交易所 `x` 字段（准确性最高）
3. ✅ 后备使用时间戳推断（兼容性）
4. ✅ 所有路径都标记 `is_closed` 字段

---

### 3.2 Pinbar 形态检测流程

**期望行为**:

```
K 线收盘 → process_kline(kline)
    ↓
PinbarStrategy.detect(kline, atr_value)
    ↓
计算 candle_range = high - low
    ↓
检查最小波幅
    ↓
┌──────────────────────┐
│ candle_range >= min? │
└──────┬───────────────┘
       │
       ├─ Yes ──→ 执行 Pinbar 检测
       │
       └─ No ────→ 返回 None（跳过）
```

**最小波幅计算**:
```python
if atr_value > 0:
    min_range = atr_value * 0.1  # ATR 的 10%
else:
    min_range = 0.5  # 固定值 USDT
```

**关键断言**:
1. ✅ 波幅小于阈值 → 跳过检测（返回 None）
2. ✅ ATR 不可用 → 使用固定阈值 0.5 USDT
3. ✅ 所有跳过都记录 DEBUG 日志

---

## 4. 测试契约

### 4.1 单元测试用例

| 测试 ID | 测试文件 | 测试方法 | 输入 | 期望输出 | 验证点 |
|---------|---------|---------|------|---------|--------|
| UT-1 | `test_exchange_gateway.py` | `test_parse_ohlcv_with_x_field` | `candle=[ts, o, h, l, c, v], raw_info={'x': True}` | `KlineData(is_closed=True)` | x 字段优先 |
| UT-2 | `test_exchange_gateway.py` | `test_parse_ohlcv_without_x_field` | `candle=[...], raw_info=None` | `KlineData(is_closed=True)` | 默认值 |
| UT-3 | `test_exchange_gateway.py` | `test_get_closed_candle_x_true` | `ohlcv=[..., candle_with_x_true]` | `KlineData` | x=true 返回 |
| UT-4 | `test_exchange_gateway.py` | `test_get_closed_candle_x_false` | `ohlcv=[..., candle_with_x_false]` | `None` | x=false 跳过 |
| UT-5 | `test_exchange_gateway.py` | `test_get_closed_candle_timestamp_fallback` | `ohlcv=[..., ..., ...], timestamps change` | `KlineData` | 时间戳后备 |
| UT-6 | `test_strategy_engine.py` | `test_pinbar_min_range_with_atr` | `candle_range=3, atr=50` | `None` (min=5) | ATR 10% 阈值 |
| UT-7 | `test_strategy_engine.py` | `test_pinbar_min_range_without_atr` | `candle_range=0.3, atr=None` | `None` (min=0.5) | 固定阈值 |

---

## 5. 兼容性契约

### 5.1 向后兼容性

**兼容性保证**:
1. ✅ `KlineData.info` 字段可选，默认 `None`（现有代码无需修改）
2. ✅ `_parse_ohlcv(raw_info=None)` 保持原有行为
3. ✅ `PinbarStrategy.detect(atr_value=None)` 保持原有行为
4. ✅ 回测功能不受影响（使用历史数据，时间戳正确）

**破坏性变更**: 无

---

### 5.2 测试兼容性

**现有测试影响**:
- ✅ 所有现有测试应继续通过（除边界情况）
- ⚠️ 使用极小波幅 K 线的测试可能失败（预期行为）

**新增测试**:
- ✅ 必须覆盖 `x` 字段优先逻辑
- ✅ 必须覆盖时间戳后备逻辑
- ✅ 必须覆盖最小波幅检查

---

## 6. 实施依赖关系

```
[Task 1] KlineData 模型扩展
    ↓
[Task 2] _parse_ohlcv() 方法扩展 ←─┐
    ↓                             │
[Task 3] _get_closed_candle() 重构 │ (依赖)
    ↓                             │
[Task 4] PinbarStrategy 扩展 ─────┘
    ↓
[Task 5] 单元测试编写
    ↓
[Task 6] 集成测试验证
    ↓
[Task 7] 文档更新
```

---

## 7. 验收标准

### 7.1 功能验收

- [ ] `x=true` 时，WebSocket 返回 `ohlcv[-1]`
- [ ] `x=false` 时，WebSocket 跳过 K 线
- [ ] 无 `x` 字段时，使用时间戳推断
- [ ] Pinbar 波幅 < ATR 10% 时，跳过检测
- [ ] 所有新增测试 100% 通过

### 7.2 质量验收

- [ ] 修改代码行覆盖率 > 85%
- [ ] 无新增 Pyright 类型错误
- [ ] 无新增 Pylint 警告
- [ ] 所有现有测试继续通过

### 7.3 文档验收

- [ ] ADR 文档完整
- [ ] 契约表完整
- [ ] 代码注释清晰
- [ ] Git commit message 清晰

---

## 8. 风险与缓解

| 风险 | 影响 | 缓解措施 | 责任人 |
|------|------|---------|--------|
| 交易所 `x` 字段缺失 | 中 | 降级到时间戳推断 | Backend Dev |
| 时间戳推断精度低 | 低 | 已验证可用 | Backend Dev |
| Pinbar 最小波幅误杀 | 低 | ATR 10% 较宽松 | Backend Dev |
| 测试覆盖不足 | 中 | 新增 7 个单元测试 | QA Tester |

---

## 9. 签署确认

| 角色 | 姓名 | 签署日期 |
|------|------|---------|
| 架构师 | Claude | 2026-04-08 |
| 项目经理 | - | 待签署 |

---

*本契约表遵循项目接口契约规范*

*文档版本: 1.0*  
*创建日期: 2026-04-08*