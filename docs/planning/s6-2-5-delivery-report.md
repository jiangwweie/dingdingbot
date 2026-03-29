# S6-2-5 通知消息增强 - 交付报告

**完成时间**: 2026-03-29
**状态**: 已完成并合并到 dev 分支
**提交哈希**: 452f75f

---

## 一、需求概述

S6-2-5 通知消息增强的目标是在通知中清晰展示信号覆盖和反向信号信息，帮助用户理解信号关系。

### 核心功能

1. **覆盖通知**: 展示新旧信号评分对比
2. **反向信号通知**: 展示对立方向信号信息

---

## 二、实现内容

### 2.1 `src/infrastructure/notifier.py` 修改

#### 新增 `format_cover_signal_message()` 函数

```python
def format_cover_signal_message(signal: SignalResult, superseded_signal: dict) -> str:
    """
    覆盖通知模板 - 包含评分对比

    Args:
        signal: 新信号（覆盖者）
        superseded_signal: 旧信号数据（包含 score）

    Returns:
        Markdown formatted cover notification message
    """
```

**功能**:
- 显示新旧信号评分对比（如：新信号评分：0.85，原信号评分：0.72）
- 计算并显示评分提升百分比（如：评分提升：+18%）
- 显示被覆盖的旧信号 ID
- 使用特殊标题【信号覆盖提醒】⚡
- 标记更新字段（入场价、止损位标记为"更新"）

#### 新增 `format_opposing_signal_message()` 函数

```python
def format_opposing_signal_message(signal: SignalResult, opposing_signal: dict) -> str:
    """
    反向信号通知模板 - 包含市场分歧提示

    Args:
        signal: 当前信号
        opposing_signal: 反向信号数据（包含 direction, score）

    Returns:
        Markdown formatted opposing signal notification message
    """
```

**功能**:
- 显示市场分歧提示
- 显示当前方向和反向方向的信号评分
- 当反向信号评分更高时显示特别警告
- 使用特殊标题【反向信号提醒】⚠️

#### 修改 `format_signal_message()` 函数

```python
def format_signal_message(
    signal: SignalResult,
    superseded_signal: Optional[dict] = None,
    opposing_signal: Optional[dict] = None,
) -> str:
```

**修改内容**:
- 添加 `superseded_signal` 可选参数
- 添加 `opposing_signal` 可选参数
- 优先使用专用模板（覆盖/反向）
- 否则使用标准模板

#### 修改 `send_signal()` 方法

```python
async def send_signal(
    self,
    signal: SignalResult,
    superseded_signal: Optional[dict] = None,
    opposing_signal: Optional[dict] = None,
) -> None:
```

**修改内容**:
- 添加两个可选参数
- 传递给 `format_signal_message()` 函数

### 2.2 `src/application/signal_pipeline.py` 修改

#### 新增 `_check_opposing_signal()` 方法

```python
async def _check_opposing_signal(
    self,
    kline: KlineData,
    attempt: SignalAttempt,
) -> Optional[dict]:
    """
    Check if there's an active opposing signal (opposite direction).

    Returns:
        Opposing signal data dict if found, None otherwise
    """
```

**功能**:
- 检测是否存在相反方向的活跃信号
- 检查时间窗口
- 从数据库获取反向信号详情
- 支持测试环境的异常处理

#### 修改 `process_kline()` 方法

```python
# S6-2-5: Check for opposing signal
opposing_signal_data = await self._check_opposing_signal(kline, attempt)

# Send notification (with covering info and opposing signal if applicable)
await self._notification_service.send_signal(
    signal,
    superseded_signal=old_signal_data if should_cover else None,
    opposing_signal=opposing_signal_data,
)
```

**修改内容**:
- 调用 `_check_opposing_signal()` 检测反向信号
- 传递 `superseded_signal` 和 `opposing_signal` 给通知服务

### 2.3 `tests/unit/test_notifier.py` 新增测试

#### TestFormatCoverSignalMessage 类

- `test_format_cover_signal_basic` - 测试基本覆盖通知格式
- `test_format_cover_signal_score_decrease` - 测试不同评分提升场景

#### TestFormatOpposingSignalMessage 类

- `test_format_opposing_signal_basic` - 测试基本反向通知格式
- `test_format_opposing_signal_lower_score` - 测试反向信号评分较低场景

#### TestFormatSignalMessageWithOptionalParams 类

- `test_format_signal_standard` - 测试标准信号格式
- `test_format_signal_with_superseded` - 测试带覆盖信号的格式
- `test_format_signal_with_opposing` - 测试带反向信号的格式
- `test_format_signal_with_both` - 测试同时带两种信号的格式

---

## 三、通知模板示例

### 3.1 覆盖信号通知

```
【信号覆盖提醒】⚡

币种：BTC/USDT:USDT
周期：15m
方向：🟢 看多 (LONG)
入场价：65200.00（更新）
止损位：64700.00（更新）
建议仓位：0.15 BTC
当前杠杆：10x

【覆盖原因】
新信号评分：0.85（原信号评分：0.72）
评分提升：+18%

指标标签:
  EMA: Bullish
  MTF: Confirmed
  ATR: Strong

风控信息：最大亏损 1%，盈亏比 1:3.0

---
⚡ 此信号覆盖了之前的信号 (ID: signal-123)，因为形态质量更优
⚠️ 本系统仅为观测与通知工具，不构成投资建议
```

### 3.2 反向信号通知（反向评分更高）

```
【反向信号提醒】⚠️

币种：BTC/USDT:USDT
周期：15m
方向：🔴 看空 (SHORT) ← 与原信号相反
入场价：64800.00
止损位：65300.00
建议仓位：0.15 BTC
当前杠杆：10x

【市场分歧提示】
当前方向信号评分：0.78
反向方向信号评分：0.82（更高）

⚠️ 注意：存在更优的反向信号，市场可能出现分歧

指标标签:
  EMA: Bearish
  MTF: Confirmed

风控信息：最大亏损 1%，盈亏比 1:2.8

---
⚠️ 市场存在反向信号，请谨慎判断
⚠️ 本系统仅为观测与通知工具，不构成投资建议
```

### 3.3 反向信号通知（当前评分更高）

```
【反向信号提醒】⚠️

币种：ETH/USDT:USDT
周期：1h
方向：🟢 看多 (LONG) ← 与原信号相反
入场价：2200.00
止损位：2150.00
建议仓位：1.0 ETH
当前杠杆：5x

【市场分歧提示】
当前方向信号评分：0.85
反向方向信号评分：0.70

⚠️ 市场存在反向信号，请谨慎判断

指标标签：无

风控信息：最大亏损 1%，盈亏比 1:2.5

---
⚠️ 市场存在反向信号，请谨慎判断
⚠️ 本系统仅为观测与通知工具，不构成投资建议
```

---

## 四、测试结果

### 单元测试

```bash
$ python3 -m pytest tests/unit/test_notifier.py -v
======================== 26 passed, 2 warnings in 0.12s ========================
```

### 完整测试

```bash
$ python3 -m pytest tests/unit/test_notifier.py tests/unit/test_signal_pipeline.py tests/unit/test_strategy_engine.py -v
======================= 102 passed, 3 warnings in 0.26s ========================
```

**测试覆盖率**:
- 所有 26 个 notifier 测试通过
- 所有 102 个相关单元测试通过
- 新增 8 个测试用例全部通过

---

## 五、代码统计

| 文件 | 新增行数 | 修改内容 |
|------|----------|----------|
| `src/infrastructure/notifier.py` | +156 | 新增 2 个模板函数，修改 2 个现有函数 |
| `src/application/signal_pipeline.py` | +261 | 新增 1 个方法，修改 1 个方法 |
| `tests/unit/test_notifier.py` | +233 | 新增 3 个测试类，8 个测试用例 |
| **合计** | **+650** | |

---

## 六、验收标准

- [x] `send_signal()` 方法签名已修改，支持可选参数
- [x] `format_cover_signal_message()` 函数已实现
- [x] `format_opposing_signal_message()` 函数已实现
- [x] 覆盖通知包含评分对比和提升百分比
- [x] 反向通知包含市场分歧提示
- [x] 与 `signal_pipeline.py` 集成调用正确
- [x] 所有单元测试通过

---

## 七、相关文件

- `src/infrastructure/notifier.py` - 通知服务实现
- `src/application/signal_pipeline.py` - 信号处理管道
- `tests/unit/test_notifier.py` - 单元测试
- `docs/planning/s6-2-design.md` - 设计文档
- `docs/planning/s62-progress-summary.md` - 进度总结

---

## 八、后续建议

1. **S6-2-4 集成验证**: 与信号覆盖逻辑进行端到端测试
2. **通知渠道测试**: 验证飞书和企业微信的实际通知效果
3. **用户反馈**: 收集交易员对通知格式的反馈并优化

---

**交付完成** - S6-2-5 通知消息增强功能已实现并测试通过。
