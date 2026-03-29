# S6-2 Pinbar 评分优化与信号覆盖 - 交付报告

**交付时间**: 2026-03-29
**交付状态**: ✅ 已完成

---

## 一、任务概述

完成 S6-2 剩余的两个子任务：
- **S6-2-4**: 信号覆盖逻辑 + 冷却缓存重建
- **S6-2-5**: 通知消息增强

---

## 二、完成内容

### ✅ S6-2-4: 信号覆盖逻辑

**修改文件**: `src/application/signal_pipeline.py`

**实现内容**:

1. **覆盖检查逻辑** (`_check_cover()` 方法):
   - 检查是否存在同币种/周期/方向/策略的活跃信号
   - 比较新旧信号评分
   - 时间窗口限制（15m→4h, 1h→24h, 4h→72h, 1d→30 天）
   - 新信号评分必须更高才执行覆盖

2. **冷却缓存重建** (`initialize()` 方法):
   - 启动时从数据库加载 ACTIVE/PENDING 信号
   - 重建 `_signal_cache` 缓存
   - 确保重启后覆盖逻辑正常工作

3. **流程整合** (`process_kline()` 方法):
   - 在信号发送前调用覆盖检查
   - 覆盖时调用 `repository.update_superseded_by()` 标记旧信号
   - 通知服务传入覆盖信息

**核心代码**:
```python
async def _check_cover(
    self,
    kline: KlineData,
    attempt: SignalAttempt,
    score: float,
) -> tuple[bool, Optional[str], Optional[dict]]:
    """检查是否应该覆盖旧信号"""
    dedup_key = f"{kline.symbol}:{kline.timeframe}:{attempt.pattern.direction.value}:{attempt.strategy_name}"

    # 检查时间窗口和评分比较
    if score > old_score and within_time_window:
        return True, old_signal_id, old_signal_data
    return False, None, None
```

---

### ✅ S6-2-5: 通知消息增强

**修改文件**: `src/infrastructure/notifier.py`

**实现内容**:

1. **修改 `send_signal()` 方法签名**:
```python
async def send_signal(
    self,
    signal: SignalResult,
    superseded_signal: Optional[dict] = None,  # 新增
    opposing_signal: Optional[dict] = None,     # 新增
) -> None:
```

2. **新增覆盖通知模板** (`format_cover_signal_message()`):
   - 展示新旧信号评分对比
   - 显示评分提升百分比
   - 包含覆盖原因说明

3. **新增反向信号通知模板** (`format_opposing_signal_message()`):
   - 展示市场分歧提示
   - 对比当前和反向信号评分
   - 提供风险警示

**通知示例**:
```
【信号覆盖提醒】⚡

币种：BTC/USDT:USDT
周期：15m
方向：🟢 看多 (LONG)

【覆盖原因】
新信号评分：0.85（原信号评分：0.72）
评分提升：+18%

⚡ 此信号覆盖了之前的信号 (ID: xxx),因为形态质量更优
```

---

### ✅ 前端字段对齐（已完成 - S6-2-6）

**修改文件**:
- `web-front/src/lib/api.ts` - Signal 接口添加覆盖字段
- `web-front/src/components/SignalStatusBadge.tsx` - 被覆盖信号视觉降级
- `web-front/src/pages/Signals.tsx` - 被覆盖信号和对立信号显示

**前端实现**:
- `SignalStatus.SUPERSEDED = 'superseded'` 枚举
- `superseded_by?: string` - 覆盖者 ID
- `opposing_signal_id?: string` - 反向信号 ID
- `opposing_signal_score?: number` - 反向信号评分
- 视觉降级：`opacity-50 grayscale`

---

## 三、测试修复

**修复文件**: `tests/unit/test_filter_factory.py`
**修复问题**: 测试代码使用了已废弃的 `_atr_values` 属性名

**修改内容**:
```python
# 旧代码
f._atr_values[key] = [Decimal("1.0")] * 14

# 新代码
f._atr_state[key] = {"tr_values": [Decimal("1.0")] * 14, "atr": Decimal("1.0"), "prev_close": None}
```

**修复文件**: `src/domain/strategy_engine.py`
**修复问题**: `AtrFilterDynamic` 未导入

**修改内容**:
```python
from .filter_factory import FilterBase, FilterContext, TraceEvent, FilterFactory, AtrFilterDynamic
```

**测试结果**:
```
38 passed (filter_factory 测试)
401 passed (总测试)
6 failed → 0 failed (已修复)
```

---

## 四、设计文档

**创建文件**: `docs/planning/s6-2-design.md`

**内容包括**:
- 数据库表设计
- 接口设计规范
- 前后端字段对齐表
- 覆盖逻辑详细设计
- 通知模板设计
- 测试计划

---

## 五、修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `src/application/signal_pipeline.py` | 覆盖逻辑 + 冷却缓存重建 |
| `src/infrastructure/notifier.py` | 通知模板增强 |
| `src/domain/strategy_engine.py` | 导入 AtrFilterDynamic |
| `tests/unit/test_filter_factory.py` | 修复测试属性名 |
| `docs/planning/s6-2-design.md` | 创建设计文档 |
| `docs/planning/s62-progress-summary.md` | 进度总结（已存在） |
| `web-front/src/lib/api.ts` | Signal 接口字段（已完成） |
| `web-front/src/components/SignalStatusBadge.tsx` | 视觉降级（已完成） |
| `web-front/src/pages/Signals.tsx` | 覆盖显示（已完成） |

---

## 六、验收标准

- [x] 信号覆盖逻辑正确，评分高的信号覆盖评分低的信号
- [x] 冷却缓存启动时正确重建
- [x] 通知消息包含覆盖和反向信号信息
- [x] 前端正确展示被覆盖信号（视觉降级）
- [x] 所有测试通过（401 passed）

---

## 七、技术要点

### 时间窗口映射
| 周期 | 覆盖时间窗口 |
|------|------------|
| 15m  | 4 小时      |
| 1h   | 24 小时     |
| 4h   | 72 小时     |
| 1d   | 30 天       |
| 1w   | 90 天       |

### 覆盖条件
```python
should_cover = (
    old_signal_exists
    and old_signal_status in ['ACTIVE', 'PENDING']
    and now - old_timestamp < time_window  # 在时间窗口内
    and new_score > old_score              # 新信号评分更高
)
```

### 通知模板
- 标准通知：`format_signal_message()`
- 覆盖通知：`format_cover_signal_message()`
- 反向通知：`format_opposing_signal_message()`

---

## 八、后续建议

1. **监控覆盖频率**: 记录覆盖事件发生的频率，优化时间窗口参数
2. **评分权重调优**: 根据实际效果调整评分公式权重（当前 0.7/0.3）
3. **用户反馈收集**: 收集交易员对覆盖通知的反馈，优化通知格式

---

*交付完成 - S6-2 Pinbar 评分优化与信号覆盖功能已全部实现并测试通过*
