# T006 - AuditLogger 类型校验缺失修复计划

> **任务 ID**: T006  
> **优先级**: P2  
> **工时估算**: 2h  
> **依赖**: 无  
> **创建时间**: 2026-04-07

---

## 问题描述

`src/application/order_audit_logger.py` 中的 `log_status_change` 方法缺少对 `event_type` 和 `triggered_by` 参数的类型校验。

**风险**:
- 传入无效的字符串可能导致数据库污染
- 类型错误在运行时才能发现
- 缺乏自动转换为枚举的容错机制

---

## 修复方案

### 1. 修改文件
- `src/application/order_audit_logger.py` - 添加类型校验逻辑

### 2. 测试文件
- `tests/unit/application/test_order_audit_logger.py` - 新增单元测试

### 3. 类型校验逻辑

```python
from src.domain.models import OrderAuditEventType, OrderAuditTriggerSource

def _validate_event_type(self, event_type) -> OrderAuditEventType:
    """验证并转换 event_type 为枚举类型"""
    if isinstance(event_type, OrderAuditEventType):
        return event_type
    try:
        return OrderAuditEventType(event_type)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid event_type: {event_type}")

def _validate_trigger_source(self, triggered_by) -> OrderAuditTriggerSource:
    """验证并转换 triggered_by 为枚举类型"""
    if isinstance(triggered_by, OrderAuditTriggerSource):
        return triggered_by
    try:
        return OrderAuditTriggerSource(triggered_by)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid triggered_by: {triggered_by}")
```

---

## 测试用例

| 测试用例 | 描述 | 预期结果 |
|----------|------|----------|
| `test_valid_enum_types` | 传入有效枚举类型 | 正常写入日志 |
| `test_string_to_enum_conversion` | 传入字符串自动转换 | 转换成功并写入 |
| `test_invalid_event_type` | 传入无效 event_type | 抛出 ValueError |
| `test_invalid_triggered_by` | 传入无效 triggered_by | 抛出 ValueError |

---

## 验收标准

- [ ] 方法参数添加类型注解
- [ ] 添加类型校验逻辑
- [ ] 支持字符串自动转换为枚举
- [ ] 新增 4 个单元测试全部通过
- [ ] 现有测试无回归

---

## 进度追踪

| 步骤 | 状态 | 完成时间 |
|------|------|----------|
| 1. 阅读源代码和枚举定义 | ☐ | - |
| 2. 实现类型校验逻辑 | ☐ | - |
| 3. 编写单元测试 | ☐ | - |
| 4. 运行测试验证 | ☐ | - |
| 5. 更新进度日志 | ☐ | - |
