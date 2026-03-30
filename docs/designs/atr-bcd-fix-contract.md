# ATR 问题 BCD 方案修复 - 接口契约表

> **创建日期**: 2026-03-30
> **任务 ID**: Task #3
> **Coordinator**: Claude Code

---

## 1. 修改范围定义

本次修复不涉及新 API 端点，仅修改现有逻辑。契约表聚焦于**数据结构变更**和**行为变更**。

---

## 2. 后端 Schema 变更

### 2.1 FilterResult.metadata 保存（方案 D）

**修改位置**: `src/infrastructure/signal_repository.py`

#### save_attempt() 方法

```python
# 修改前：metadata 被丢弃
details_dict = {
    "pattern": attempt.pattern.details if attempt.pattern else None,
    "filters": [
        {"name": f_name, "passed": f_result.passed, "reason": f_result.reason}
        for f_name, f_result in attempt.filter_results
    ]
}

# 修改后：包含 metadata
details_dict = {
    "pattern": attempt.pattern.details if attempt.pattern else None,
    "filters": [
        {
            "name": f_name,
            "passed": f_result.passed,
            "reason": f_result.reason,
            "metadata": f_result.metadata  # ✅ 新增
        }
        for f_name, f_result in attempt.filter_results
    ]
}
```

#### _build_trace_tree() 方法

```python
# 修改前：metadata 只有 filter_name/filter_type
filter_node = {
    "node_id": str(uuid.uuid4()),
    "node_type": "filter",
    "passed": f_result.passed,
    "reason": f_result.reason,
    "metadata": {
        "filter_name": f_name,
        "filter_type": f_name,
    },
    "children": []
}

# 修改后：合并 FilterResult.metadata
filter_node = {
    "node_id": str(uuid.uuid4()),
    "node_type": "filter",
    "passed": f_result.passed,
    "reason": f_result.reason,
    "metadata": {
        "filter_name": f_name,
        "filter_type": f_name,
        **f_result.metadata  # ✅ 合并
    },
    "children": []
}
```

### 2.2 AtrFilterDynamic 新增字段（方案 C）

**修改位置**: `src/domain/filter_factory.py::AtrFilterDynamic`

#### 新增配置字段

```python
class AtrFilterDynamic:
    def __init__(self, ..., min_absolute_range: Decimal = Decimal("0.1")):
        self._min_atr_ratio = min_atr_ratio
        self._min_absolute_range = min_absolute_range  # ✅ 新增
```

#### check() 方法返回值变更

```python
# 新增绝对波幅检查
if candle_range < self._min_absolute_range:
    return TraceEvent(
        passed=False,
        reason="insufficient_absolute_volatility",
        metadata={
            "candle_range": float(candle_range),
            "min_required": float(self._min_absolute_range),
        }
    )
```

### 2.3 最小止损距离检查（方案 B）

**修改位置**: `src/domain/risk_calculator.py` 或 `src/domain/strategy_engine.py`

#### 新增检查逻辑

```python
# 在生成 SignalResult 前检查
stop_distance = abs(entry_price - suggested_stop_loss) / entry_price
min_stop_distance = Decimal("0.001")  # 0.1%

if stop_distance < min_stop_distance:
    return FilterResult(
        passed=False,
        reason="stop_loss_too_close",
        metadata={
            "stop_distance": float(stop_distance),
            "min_required": float(min_stop_distance),
        }
    )
```

---

## 3. API 响应变更（方案 D 影响）

### 3.1 GET /api/attempts 响应增强

| 字段路径 | 原类型 | 新类型 | 说明 |
|----------|--------|--------|------|
| `data[].details.filters[].metadata` | 无 | `object` | 新增过滤器详细数据 |

**示例响应**:
```json
{
  "data": [{
    "details": {
      "filters": [
        {
          "name": "atr_volatility",
          "passed": true,
          "reason": "volatility_sufficient",
          "metadata": {
            "candle_range": 0.5,
            "atr": 0.8,
            "ratio": 0.625
          }
        }
      ]
    }
  }]
}
```

### 3.2 GET /api/signals/{id}/context 响应增强

| 字段路径 | 原类型 | 新类型 | 说明 |
|----------|--------|--------|------|
| `trace_tree.children[].metadata` | `object` | `object` | 新增过滤器详细数据 |

---

## 4. 配置变更（方案 C）

### 4.1 config/core.yaml 新增配置

```yaml
atr_volatility:
  enabled: true
  period: 14
  min_atr_ratio: 0.5         # 现有配置
  min_absolute_range: 0.1    # ✅ 新增：最小绝对波幅 (USDT)
```

---

## 5. 前端影响评估

| 组件 | 变更 | 说明 |
|------|------|------|
| SignalAttempts.tsx | 无 | 自动显示新 metadata |
| SignalDetailsDrawer.tsx | 无 | 自动显示新 trace_tree metadata |

**说明**: 前端无需修改，metadata 为透传数据，UI 自动渲染。

---

## 6. 数据流图

```
┌──────────────────────────────────────────────────────────────────┐
│                     方案 D: metadata 保存链路                      │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  AtrFilterDynamic.check()                                        │
│    ↓ TraceEvent(metadata={candle_range, atr, ratio})            │
│  FilterResult.metadata                                           │
│    ↓                                                             │
│  SignalAttempt.filter_results                                    │
│    ↓                                                             │
│  SignalRepository.save_attempt()                                 │
│    ↓ (新增) 保存到 details 字段                                   │
│  SQLite: signal_attempts.details                                 │
│    ↓                                                             │
│  API: GET /api/attempts                                          │
│    ↓ (新增) 返回 metadata                                         │
│  Frontend: SignalAttempts.tsx                                    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                     方案 B: 止损距离检查                           │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  StrategyEngine 检测到 Pinbar 形态                                 │
│    ↓                                                             │
│  计算止损 = K 线低点                                                │
│    ↓                                                             │
│  计算止损距离 = |entry - stop| / entry                            │
│    ↓ 新增检查                                                     │
│  if stop_distance < 0.001 (0.1%):                                │
│    → 拒绝信号，返回 FILTERED                                      │
│    → reason: "stop_loss_too_close"                               │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                    方案 C: ATR 绝对波幅检查                         │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  AtrFilterDynamic.check()                                        │
│    ↓                                                             │
│  1. 获取 ATR 值                                                    │
│    ↓                                                             │
│  2. 计算 candle_range = high - low                               │
│    ↓ 新增检查                                                     │
│  3. if candle_range < 0.1 USDT:                                  │
│    → 拒绝，reason: "insufficient_absolute_volatility"            │
│    ↓ 原有检查                                                     │
│  4. if candle_range / atr < min_atr_ratio:                       │
│    → 拒绝，reason: "insufficient_volatility"                     │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 7. 类型对齐检查

### 7.1 后端 FilterResult

```python
@dc_dataclass
class FilterResult:
    passed: bool
    reason: str
    metadata: Dict[str, Any] = None
```

### 7.2 前端 TraceEvent

```typescript
export interface TraceEvent {
  passed: boolean;
  reason: string;
  metadata?: Record<string, any>;
}
```

### 7.3 对齐检查表

| 字段 | 后端类型 | 前端类型 | 是否一致 |
|------|----------|----------|----------|
| passed | bool | boolean | ✅ |
| reason | str | string | ✅ |
| metadata | Dict[str, Any] | Record<string, any> | ✅ |

---

## 8. 验收标准

| 方案 | 验收项 | 验证方法 |
|------|--------|----------|
| **B** | 止损距离 < 0.1% 的信号被过滤 | 单元测试 + 回测验证 |
| **C** | ATR 绝对波幅 < 0.1 USDT 被过滤 | 单元测试 + 回测验证 |
| **D** | API 返回完整 metadata | 手动调用 /api/attempts 验证 |

---

## 9. 变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
|------|------|----------|--------|
| v1.0 | 2026-03-30 | 初始版本 | Coordinator |

---

## 审查签字

| 角色 | 日期 | 状态 |
|------|------|------|
| Coordinator | 2026-03-30 | ✅ 已创建 |
| Backend Dev | - | ⏳ 待开发 |
| Frontend Dev | - | ✅ 无变更 |
| QA Tester | - | ⏳ 待测试 |
| Code Reviewer | - | ⏳ 待审查 |
