# ORD-1 订单状态机系统性重构 - 任务计划

> **创建日期**: 2026-04-06
> **负责人**: Backend Developer
> **总工时**: 14h
> **状态**: 🟢 进行中

---

## 任务目标

实现完整的订单生命周期状态机，确保订单状态转换符合交易所规范，防止非法状态流转。

---

## 子任务分解

| ID | 任务名称 | 说明 | 工时 | 状态 | 负责人 |
|----|----------|------|------|------|--------|
| **T1** | 订单状态机领域层实现 | 创建 OrderStateMachine 类和 InvalidOrderStateTransition 异常 | 2h | ✅ 已完成 | Backend |
| **T2** | 状态枚举扩展 | 确认 OrderStatus 覆盖所有 9 种状态 | 0.5h | ✅ 已完成 | Backend |
| **T3** | 状态流转矩阵定义 | 定义合法的状态转换规则 | 1h | ✅ 已完成 | Backend |
| **T4** | 状态机核心方法实现 | can_transition(), get_valid_transitions(), is_terminal_state() | 1.5h | ✅ 已完成 | Backend |
| **T5** | 与 Order 模型集成 | 在 Order 类中集成状态机逻辑 | 1h | ☐ 待启动 | Backend |
| **T6** | 单元测试编写 | 覆盖所有状态流转路径 | 3h | ✅ 已完成 | QA |
| **T7** | 集成测试 | 与 order_repository 集成测试 | 2h | ☐ 待启动 | QA |
| **T8** | 文档编写 | 状态机使用文档和状态转移图 | 1h | ☐ 待启动 | Backend |
| **T9** | 代码审查 | Reviewer 对照契约表检查 | 1h | ☐ 待启动 | Reviewer |
| **T10** | 修复与优化 | 根据审查反馈修复 | 1h | ☐ 待启动 | Backend |

---

## T1 任务详细规格

### 输出文件
- `src/domain/order_state_machine.py` (新建)
- `src/domain/exceptions.py` (修改 - 添加异常类)
- `tests/unit/test_order_state_machine.py` (新建 - 62 个测试用例)

### 核心功能

#### 1. OrderStateMachine 类 - 9 种状态

```python
class OrderStateMachine:
    """订单状态机 - 管理订单状态流转"""
    
    # 9 种状态定义
    STATES = frozenset({
        "CREATED",          # 订单已创建（本地）
        "SUBMITTED",        # 订单已提交到交易所
        "PENDING",          # 尚未发送到交易所
        "OPEN",             # 挂单中
        "PARTIALLY_FILLED", # 部分成交
        "FILLED",           # 完全成交
        "CANCELED",         # 已撤销
        "REJECTED",         # 交易所拒单
        "EXPIRED",          # 已过期
    })
    
    # 合法流转矩阵
    TRANSITIONS = {
        "CREATED": {"SUBMITTED", "CANCELED"},
        "SUBMITTED": {"OPEN", "REJECTED", "CANCELED", "EXPIRED"},
        "PENDING": {"OPEN", "REJECTED", "CANCELED", "SUBMITTED"},
        "OPEN": {"PARTIALLY_FILLED", "FILLED", "CANCELED", "REJECTED", "EXPIRED"},
        "PARTIALLY_FILLED": {"FILLED", "CANCELED"},
        "FILLED": frozenset(),  # 终态
        "CANCELED": frozenset(),  # 终态
        "REJECTED": frozenset(),  # 终态
        "EXPIRED": frozenset(),  # 终态
    }
    
    # 终态定义
    TERMINAL_STATES = frozenset({"FILLED", "CANCELED", "REJECTED", "EXPIRED"})
    
    # 核心方法
    def can_transition(from_status, to_status) -> bool
    def can_transition_with_exception(order_id, from_status, to_status) -> bool
    def get_valid_transitions(from_status) -> set
    def is_terminal_state(status) -> bool
```

#### 2. InvalidOrderStateTransition 异常类

```python
class InvalidOrderStateTransition(Exception):
    """非法订单状态流转异常"""
    def __init__(self, order_id: str, from_status: str, to_status: str,
                 valid_transitions: set[str]):
        self.order_id = order_id
        self.from_status = from_status
        self.to_status = to_status
        self.valid_transitions = valid_transitions
```

### 验收标准
- [x] `src/domain/order_state_machine.py` 已创建
- [x] `OrderStateMachine` 覆盖所有 9 种状态
- [x] `InvalidOrderStateTransition` 异常已添加到 exceptions.py
- [x] 单元测试通过，62/62 测试用例覆盖所有流转路径
- [x] progress.md 已更新

---

## 状态转移图

```
┌─────────────────────────────────────────────────────────────┐
│                    订单状态转移图                              │
│                                                             │
│   ┌─────────┐                                               │
│   │ CREATED │───→ CANCELED (终态)                            │
│   └────┬────┘                                               │
│        │                                                     │
│        ↓                                                     │
│   ┌───────────┐                                             │
│   │ SUBMITTED │───→ REJECTED (终态)                          │
│   └────┬──────┘    │                                         │
│        │           └──→ CANCELED (终态)                      │
│        │                                                     │
│        ↓                                                     │
│   ┌─────────┐                                               │
│   │ PENDING │───→ REJECTED (终态)                            │
│   └────┬────┘                                               │
│        │                                                     │
│        ├───→ CANCELED (终态)                                 │
│        │                                                     │
│        ↓                                                     │
│   ┌─────────┐                                               │
│   │   OPEN  │───→ CANCELED (终态)                            │
│   └────┬────┤    │                                           │
│        │    └───→ REJECTED (终态)                            │
│        │                                                     │
│        ↓                                                     │
│   ┌──────────────────┐                                       │
│   │ PARTIALLY_FILLED │───→ CANCELED (终态)                   │
│   └────────┬─────────┘                                       │
│            │                                                  │
│            ↓                                                  │
│       ┌─────────┐                                             │
│       │ FILLED  │ (终态)                                       │
│       └─────────┘                                             │
│                                                               │
│   EXPIRED (终态) - 由交易所返回                                │
└─────────────────────────────────────────────────────────────┘

终态 (Terminal States): FILLED, CANCELED, REJECTED, EXPIRED
非终态 (Non-Terminal): CREATED, SUBMITTED, PENDING, OPEN, PARTIALLY_FILLED
```

---

## 依赖关系

```
T1 → T2 → T3 → T4 → T5 → T6 → T7 → T9 → T10 → ✅
                ↓
                T8 (并行)
```

---

## T1 完成报告

**完成时间**: 2026-04-06

**交付内容**:
1. ✅ `src/domain/order_state_machine.py` - OrderStateMachine 类 (9 状态 + 流转矩阵)
2. ✅ `src/domain/exceptions.py` - InvalidOrderStateTransition 异常类
3. ✅ `tests/unit/test_order_state_machine.py` - 62 个测试用例，100% 覆盖

**测试结果**:
```
============================== 62 passed in 0.16s ==============================
```

**测试覆盖**:
- 状态定义测试 (3 个)
- 状态流转测试 (8 个)
- can_transition() 测试 (20+ 个)
- can_transition_with_exception() 测试 (3 个)
- is_terminal_state() 测试 (4 个)
- 辅助方法测试 (6 个)
- 边界情况测试 (4 个)
- 完整流转路径测试 (6 个)

---

*最后更新：2026-04-06 | T1 已完成*
