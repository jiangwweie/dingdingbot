# P0 修复实施清单

> **任务级别**: P0 关键缺陷修复  
> **创建日期**: 2026-04-08  
> **关联 ADR**: [P0-websocket-kline-fix-design.md](../arch/P0-websocket-kline-fix-design.md)  
> **关联契约**: [P0-websocket-kline-fix-contract.md](../designs/P0-websocket-kline-fix-contract.md)

---

## 实施阶段概览

| 阶段 | 任务 | 负责人 | 预计工时 | 状态 |
|------|------|--------|---------|------|
| 阶段 1 | 数据模型扩展 | Backend Dev | 0.5h | ⏳ 待开始 |
| 阶段 2 | WebSocket K线选择修复 | Backend Dev | 1.5h | ⏳ 待开始 |
| 阶段 3 | Pinbar 最小波幅检查 | Backend Dev | 1h | ⏳ 待开始 |
| 阶段 4 | 单元测试编写 | QA Tester | 2h | ⏳ 待开始 |
| 阶段 5 | 集成测试验证 | QA Tester | 1h | ⏳ 待开始 |
| 阶段 6 | 文档更新 | Backend Dev | 0.5h | ⏳ 待开始 |

**总计工时**: 约 6.5 小时

---

## 阶段 1: 数据模型扩展 (0.5h)

### 任务 1.1: 修改 KlineData 模型

**文件**: `src/domain/models.py`

**修改内容**:

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

**验证步骤**:
- [ ] 添加 `info` 字段
- [ ] 运行 `pyright src/domain/models.py` 无错误
- [ ] 运行 `pytest tests/unit/test_models.py`（如有）

---

## 阶段 2: WebSocket K线选择修复 (1.5h)

### 任务 2.1: 扩展 `_parse_ohlcv()` 方法

**文件**: `src/infrastructure/exchange_gateway.py`

**修改内容**:

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
    
    Args:
        candle: [timestamp, open, high, low, close, volume, ...]
        symbol: Trading symbol
        timeframe: Timeframe
        raw_info: 交易所原始数据（包含 x 字段）
    
    Returns:
        KlineData 对象或 None
    """
    try:
        # ... 原有验证逻辑 ...
        
        # ✅ 新增：使用 x 字段判断收盘状态
        if raw_info and 'x' in raw_info:
            is_closed = bool(raw_info['x'])
        else:
            is_closed = True  # 默认值
        
        return KlineData(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=int(candle[0]),
            open=Decimal(str(candle[1])),
            high=Decimal(str(candle[2])),
            low=Decimal(str(candle[3])),
            close=Decimal(str(candle[4])),
            volume=Decimal(str(candle[5])),
            is_closed=is_closed,
            info=raw_info,  # ✅ 新增
        )
    except Exception as e:
        logger.error(f"Failed to parse OHLCV: {e}")
        return None
```

**验证步骤**:
- [ ] 添加 `raw_info` 参数
- [ ] 增加 `x` 字段处理逻辑
- [ ] 传递 `info` 到 `KlineData`
- [ ] 运行 `pyright` 无错误

---

### 任务 2.2: 重构 `_get_closed_candle()` 方法

**文件**: `src/infrastructure/exchange_gateway.py`

**修改内容**: 参见契约表 § 2.2

**核心逻辑**:
1. 检查 `ohlcv[-1]` 的 `x` 字段
2. 如果 `x=true` → 返回 `ohlcv[-1]`
3. 如果 `x=false` → 返回 `None`
4. 如果无 `x` 字段 → 使用时间戳推断

**验证步骤**:
- [ ] 实现 `x` 字段优先逻辑
- [ ] 实现时间戳后备逻辑
- [ ] 添加 DEBUG 日志
- [ ] 运行 `pyright` 无错误

---

## 阶段 3: Pinbar 最小波幅检查 (1h)

### 任务 3.1: 扩展 `PinbarStrategy.detect()` 方法

**文件**: `src/domain/strategy_engine.py`

**修改内容**:

```python
def detect(
    self, 
    kline: KlineData, 
    atr_value: Optional[Decimal] = None
) -> Optional[PatternResult]:
    """检测 Pinbar 形态（修复版）。"""
    
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

**验证步骤**:
- [ ] 添加最小波幅检查逻辑
- [ ] 动态 ATR 阈值计算
- [ ] 固定后备阈值
- [ ] 添加 DEBUG 日志
- [ ] 运行 `pyright` 无错误

---

### 任务 3.2: 确认 ATR 过滤器配置

**文件**: `src/domain/filter_factory.py`

**验证内容**:

```python
def __init__(
    self, 
    period: int = 14, 
    min_atr_ratio: Decimal = Decimal("0.001"),
    min_absolute_range: Decimal = Decimal("0.1"),
    enabled: bool = False  # ✅ 确认为 False
):
```

**验证步骤**:
- [ ] 确认 `enabled=False` 默认值
- [ ] 运行 `pyright` 无错误

---

## 阶段 4: 单元测试编写 (2h)

### 任务 4.1: WebSocket K线处理测试

**文件**: `tests/unit/test_exchange_gateway.py`

**测试用例**:

| 测试方法 | 测试目标 | 输入 | 期望输出 |
|---------|---------|------|---------|
| `test_parse_ohlcv_with_x_true` | x=true 处理 | `candle=[...], raw_info={'x': True}` | `KlineData(is_closed=True)` |
| `test_parse_ohlcv_with_x_false` | x=false 处理 | `candle=[...], raw_info={'x': False}` | `KlineData(is_closed=False)` |
| `test_parse_ohlcv_without_x` | 无 x 字段处理 | `candle=[...], raw_info=None` | `KlineData(is_closed=True)` |
| `test_get_closed_candle_x_true` | x=true 返回 K线 | `ohlcv=[..., candle_with_x_true]` | `KlineData` 对象 |
| `test_get_closed_candle_x_false` | x=false 跳过 | `ohlcv=[..., candle_with_x_false]` | `None` |
| `test_get_closed_candle_fallback` | 时间戳后备 | `ohlcv` 时间戳变化 | `KlineData` 对象 |

**验证步骤**:
- [ ] 编写 6 个测试用例
- [ ] 运行 `pytest tests/unit/test_exchange_gateway.py -v`
- [ ] 所有测试通过

---

### 任务 4.2: Pinbar 最小波幅测试

**文件**: `tests/unit/test_strategy_engine.py`

**测试用例**:

| 测试方法 | 测试目标 | 输入 | 期望输出 |
|---------|---------|------|---------|
| `test_pinbar_min_range_with_atr` | ATR 10% 阈值 | `candle_range=3, atr=50` | `None` (min=5) |
| `test_pinbar_min_range_without_atr` | 固定阈值 | `candle_range=0.3, atr=None` | `None` (min=0.5) |
| `test_pinbar_valid_range` | 合法波幅 | `candle_range=10, atr=50` | `PatternResult` |

**验证步骤**:
- [ ] 编写 3 个测试用例
- [ ] 运行 `pytest tests/unit/test_strategy_engine.py -v`
- [ ] 所有测试通过

---

## 阶段 5: 集成测试验证 (1h)

### 任务 5.1: 运行完整测试套件

**命令**:
```bash
pytest tests/unit/ -v --cov=src --cov-report=term-missing
```

**验收标准**:
- [ ] 所有新增测试通过
- [ ] 所有现有测试通过（除极小波幅边界情况）
- [ ] 代码覆盖率 > 85%

---

### 任务 5.2: 手动验证（可选）

**验证场景**:

1. **启动实盘服务**
   ```bash
   python3 -m src.main
   ```

2. **观察日志**
   ```bash
   tail -f data/main.log | grep -E "(X_FIELD|TIMESTAMP_FALLBACK)"
   ```

3. **验证输出**
   - 看到 `[X_FIELD]` 日志（币安支持 x 字段）
   - 仅处理已收盘 K 线

**验收标准**:
- [ ] 服务启动成功
- [ ] 看到预期的 DEBUG 日志
- [ ] 无错误日志

---

## 阶段 6: 文档更新 (0.5h)

### 任务 6.1: 更新 CLAUDE.md

**修改内容**:
- 在"开发注意事项"章节增加 WebSocket K 线处理说明
- 记录 `x` 字段优先使用原则

**验证步骤**:
- [ ] 更新 CLAUDE.md
- [ ] Git commit

---

### 任务 6.2: 更新 progress.md

**修改内容**:
- 记录 P0 修复完成
- 更新待办事项

**验证步骤**:
- [ ] 更新 `docs/planning/progress.md`
- [ ] Git commit

---

## 验收检查清单

### 代码质量

- [ ] 所有修改文件通过 `pyright` 类型检查
- [ ] 所有修改文件通过 `pylint` 检查（评分 > 8.0）
- [ ] 无新增警告

### 测试覆盖

- [ ] 新增单元测试 9 个
- [ ] 所有新增测试通过
- [ ] 代码覆盖率 > 85%
- [ ] 边界情况覆盖

### 文档完整

- [ ] ADR 文档完整
- [ ] 契约表完整
- [ ] 实施清单完整
- [ ] Git commit message 清晰

### 功能验证

- [ ] WebSocket 仅处理已收盘 K 线
- [ ] `x` 字段优先逻辑正确
- [ ] 时间戳后备逻辑正确
- [ ] Pinbar 最小波幅检查正确

---

## 回滚方案

如果修复失败，执行以下回滚：

```bash
# 查看 Git 日志
git log --oneline -5

# 回滚到修复前
git revert <commit-hash>

# 或重置到修复前
git reset --hard <commit-hash>
```

---

## 风险记录

| 风险 | 发生概率 | 影响 | 缓解措施 | 状态 |
|------|---------|------|---------|------|
| 交易所 x 字段缺失 | 低 | 中 | 时间戳后备 | 已实施 |
| 极小波幅测试失败 | 中 | 低 | 更新测试断言 | 待处理 |
| 现有测试失败 | 低 | 中 | 检查并更新断言 | 待处理 |

---

## 完成确认

- [ ] 所有阶段完成
- [ ] 所有验收标准达成
- [ ] Git commit + push
- [ ] 更新 progress.md
- [ ] 用户确认

---

*本实施清单遵循项目工作流程规范*

*文档版本: 1.0*  
*创建日期: 2026-04-08*