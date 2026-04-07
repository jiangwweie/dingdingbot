# 任务计划：T009 - P2-9 Worker 异常处理增强

> **创建时间**: 2026-04-07  
> **状态**: 已完成  
> **优先级**: P2  
> **工时估算**: 2h

---

## 任务概述

**任务 ID**: T009  
**问题位置**: `src/infrastructure/order_audit_repository.py:71-83`  
**修复目标**:
- 添加详细异常日志记录
- 实现连续错误计数和告警机制
- 避免异常静默导致问题难以排查

---

## 任务分解

### 阶段 1: 代码修改
- [x] 阅读当前实现代码
- [x] 修改 `_worker()` 方法添加异常处理增强
- [x] 添加 logger 导入

### 阶段 2: 单元测试编写
- [x] 创建测试文件 `tests/unit/infrastructure/test_order_audit_repository.py`
- [x] `test_worker_logs_error_on_exception` - 测试异常时记录错误日志
- [x] `test_worker_consecutive_error_count` - 测试连续错误计数
- [x] `test_worker_critical_alert_on_max_errors` - 测试达到阈值时告警
- [x] `test_worker_resets_count_on_success` - 测试成功后重置计数

### 阶段 3: 测试验证
- [x] 运行 `pytest tests/unit/infrastructure/test_order_audit_repository.py -v`
- [x] 确认新增 5 个测试全部通过
- [x] 确认现有测试无回归 (16 passed)

### 阶段 4: 文档更新
- [x] 更新 `docs/planning/task_plan.md`
- [ ] 更新 `docs/planning/progress.md`
- [ ] Git 提交

---

## 验收标准

- ✅ Worker 捕获异常后记录详细错误日志（含堆栈跟踪）
- ✅ 实现连续错误计数机制
- ✅ 达到阈值 (10 次) 时触发 CRITICAL 告警
- ✅ 新增 5 个单元测试全部通过 (5 passed)
- ✅ 现有测试无回归 (16 passed)

---

## 相关文件

| 文件 | 路径 | 状态 |
|------|------|------|
| 设计文档 | `docs/arch/order-management-fix-design.md` | 已阅读 |
| 源代码 | `src/infrastructure/order_audit_repository.py` | 已修改 |
| 测试文件 | `tests/unit/infrastructure/test_order_audit_repository.py` | 已创建 |
| 任务计划 | `docs/planning/task_plan.md` | 已更新 |
| 进度日志 | `docs/planning/progress.md` | 待更新 |

---

## 修改摘要

### 源代码修改

**文件**: `src/infrastructure/order_audit_repository.py`

1. 添加 logger 导入：
```python
from src.infrastructure.logger import setup_logger
logger = setup_logger(__name__)
```

2. 增强 `_worker()` 方法：
- 添加 `consecutive_errors` 计数器和 `max_consecutive_errors` 阈值
- 异常时记录详细日志（含堆栈跟踪）
- 成功后重置错误计数
- 达到阈值时触发 CRITICAL 告警
- 优雅处理 CancelledError

### 测试文件

**文件**: `tests/unit/infrastructure/test_order_audit_repository.py`

新增测试类：
- `TestP2_9_WorkerErrorHandling` - 4 个测试用例
- `TestP2_9_WorkerCancellation` - 1 个测试用例

测试结果：5 passed
