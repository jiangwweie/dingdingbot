# 架构问题反馈流程详细说明

> **用途**：为 QA Tester 提供架构问题反馈的详细流程和示例
> **最后更新**：2026-04-07

---

## 🎯 流程概览

```
发现架构问题 → 停止修改 → 标记任务 → 创建修复任务 → 通知架构师 → 等待确认 → 继续测试
```

---

## 🔴 架构问题识别标准详解

### 1. 接口契约不一致

**识别信号**：
- 实际返回字段与 OpenAPI Spec 定义不符
- 必填字段在 Spec 中标注为 required，但实际可选
- 返回数据类型与 Spec 定义不符（如 Spec 定义 string，实际返回 number）

**示例**：
```python
# OpenAPI Spec 定义
class OrderResponse:
    order_id: str
    status: OrderStatus  # 必填字段

# 实际代码
class Order:
    id: str  # 字段名不一致：order_id vs id
    # 缺少 status 属性 ❌
```

**处理**：立即停止测试编写，通知架构师更新 Spec 或代码。

---

### 2. 数据模型设计缺陷

**识别信号**：
- 模型缺少必要属性（如 Order 缺少 status）
- 枚举值定义不完整（如 Direction 只有 LONG，缺少 SHORT）
- Decimal 精度设计不合理（如使用 float 而非 Decimal）
- 数据库表缺少必要字段或索引

**示例**：
```python
# 领域模型
class Order:
    id: str
    symbol: str
    # 缺少 status 属性 ❌
    # 缺少 created_at, updated_at ❌

# 数据库表
CREATE TABLE orders (
    id TEXT PRIMARY KEY,
    symbol TEXT
    -- 缺少 status 列 ❌
    -- 缺少 created_at 列 ❌
);
```

**处理**：通知架构师补充模型设计。

---

### 3. 模块边界问题

**识别信号**：
- 跨层依赖（如 Domain 层导入 Infrastructure）
- 文件所有权冲突（Backend Agent 修改 Frontend 文件）
- 循环依赖（A 导入 B，B 导入 A）
- 违反 Clean Architecture 原则

**示例**：
```python
# Domain 层文件（错误示例）
from src.infrastructure.exchange_gateway import ExchangeGateway  # ❌ 跨层导入

class StrategyEngine:
    def __init__(self, gateway: ExchangeGateway):  # ❌ Domain 依赖 Infrastructure
        ...
```

**正确设计**：
```python
# Domain 层文件（正确示例）
class StrategyEngine:
    def __init__(self, gateway: ExchangeGatewayProtocol):  # ✅ 依赖接口（Protocol）
        ...
```

**处理**：通知架构师调整模块边界。

---

### 4. 向后兼容性问题

**识别信号**：
- 新功能破坏旧 API 兼容性（如移除旧字段）
- 数据库变更缺少迁移方案
- 配置变更缺少兼容方案
- 前端变更导致旧浏览器无法使用

**示例**：
```python
# 旧版本 API
{
    "order_id": "123",
    "symbol": "BTC/USDT",
    "quantity": 0.001
}

# 新版本 API（破坏兼容性）
{
    "order_id": "123",
    "symbol": "BTC/USDT",
    "qty": 0.001  # 字段名从 quantity 改为 qty ❌ 破坏兼容性
}
```

**正确设计**：
```python
# 新版本 API（保持兼容）
{
    "order_id": "123",
    "symbol": "BTC/USDT",
    "quantity": 0.001,  # 保留旧字段 ✅
    "qty": 0.001        # 新增字段（别名）✅
}
```

**处理**：通知架构师提供迁移方案。

---

## 📋 反馈流程详解（5 步）

### Step 1: 停止修改代码

**动作**：
- ❌ **禁止**绕过架构问题只改测试代码
- ❌ **禁止**修改业务代码来让测试通过
- ✅ **允许**记录测试失败现象（截图、日志）

**示例**：
```python
# ❌ 错误做法：绕过架构问题
def test_order_status():
    order = Order(id="123")
    # Order 缺少 status 属性，但为了测试通过，直接跳过 ❌
    # pytest.skip("Order 缺少 status 属性") ❌
    pass

# ✅ 正确做法：停止修改，准备反馈
def test_order_status():
    order = Order(id="123")
    # 记录失败现象
    try:
        status = order.status  # AttributeError: Order has no attribute 'status'
    except AttributeError as e:
        # 停止测试编写，准备反馈 ❌ 不要继续写测试
        raise ArchitectureIssueDetected("Order 模型缺少 status 属性")
```

---

### Step 2: 标记任务为 blocked

**动作**：使用 `TaskUpdate` 标记当前测试任务为 `blocked`

**示例**：
```python
# 假设当前任务是 T124（测试订单状态）
TaskUpdate(
    taskId="T124",
    status="in_progress",  # 保持 in_progress
    metadata={
        "blocked_reason": "架构问题：Order 模型缺少 status 属性",
        "blocked_by": "架构设计缺陷",
        "blocked_tasks": ["T124", "T125", "T126"]  # 所有阻塞任务
    }
)
```

---

### Step 3: 创建架构修复任务

**动作**：使用 `TaskCreate` 创建架构修复任务

**示例**：
```python
TaskCreate(
    subject="修复 Order 模型缺少 status 属性",
    description="""
## 架构问题描述

**问题类型**: 数据模型设计缺陷
**问题描述**: Order 模型缺少 status 属性，但 OpenAPI Spec 中定义了 OrderResponse.status
**影响范围**:
- 所有订单相关测试（T124, T125, T126）
- 订单查询 API
- 订单生命周期管理

**建议方案**:
1. 在 Order 模型中增加 status 属性（OrderStatus 枚举）
2. 更新数据库表 orders 增加 status 列
3. 提供数据库迁移脚本

**阻塞任务**: T124, T125, T126

请架构师更新设计文档并通知我继续测试。
""",
    metadata={
        "issue_type": "architecture",
        "priority": "P0",
        "blocked_tasks": ["T124", "T125", "T126"]
    }
)
```

---

### Step 4: 通知架构师

**动作**：使用 `SendMessage` 给 architect

**示例**：
```python
SendMessage(
    to="architect",
    message="""发现架构层面问题，需要更新设计文档：

**问题类型**: 数据模型设计缺陷
**问题描述**: Order 模型缺少 status 属性，但 OpenAPI Spec 中定义了 OrderResponse.status
**发现任务**: T124（测试订单状态）
**阻塞任务**: T124, T125, T126
**建议方案**:
1. 在 Order 模型中增加 status 属性（OrderStatus 枚举）
2. 更新数据库表 orders 增加 status 列
3. 提供数据库迁移脚本

已创建架构修复任务：T127
请更新设计文档并通知我继续测试。
"""
)
```

---

### Step 5: 等待架构师确认

**动作**：
- ✅ 等待架构师回复确认
- ✅ 收到确认后，重新阅读更新后的设计文档
- ✅ 继续测试编写

**示例流程**：
```
QA Tester: SendMessage(to="architect", message="发现架构问题...")
           ↓
Architect: 阅读问题，更新设计文档
           ↓
Architect: SendMessage(to="qa-tester", message="已修复，请继续测试")
           ↓
QA Tester: 阅读更新后的设计文档
           ↓
QA Tester: TaskUpdate(taskId="T124", status="in_progress")  # 继续测试
           ↓
QA Tester: 编写测试代码
```

---

## 🎬 完整示例：订单状态测试发现架构问题

### 场景

QA Tester 在编写订单状态测试时，发现 Order 模型缺少 status 属性。

### Step 1: 停止修改

```python
# tests/unit/test_order.py
def test_order_status():
    """测试订单状态"""
    order = Order(
        id="ord_123",
        symbol="BTC/USDT:USDT",
        direction="LONG"
    )

    # 发现问题：Order 缺少 status 属性
    try:
        assert order.status == OrderStatus.PENDING
    except AttributeError as e:
        # ❌ 停止测试编写
        # ❌ 不要继续写其他测试
        print(f"发现问题：{e}")
        raise  # 抛出异常，停止测试
```

### Step 2: 标记任务

```python
# QA Tester 使用 TaskUpdate
TaskUpdate(
    taskId="T124",
    status="in_progress",
    metadata={
        "blocked_reason": "Order 模型缺少 status 属性",
        "blocked_by": "架构设计缺陷",
        "blocked_tasks": ["T124", "T125", "T126"]
    }
)
```

### Step 3: 创建修复任务

```python
# QA Tester 使用 TaskCreate
fix_task = TaskCreate(
    subject="修复 Order 模型缺少 status 属性",
    description="""
## 架构问题描述

**问题类型**: 数据模型设计缺陷
**问题描述**: Order 模型缺少 status 属性，但 OpenAPI Spec 中定义了 OrderResponse.status
**影响范围**:
- 所有订单相关测试（T124, T125, T126）
- 订单查询 API
- 订单生命周期管理

**建议方案**:
1. 在 Order 模型中增加 status 属性（OrderStatus 枚举）
2. 更新数据库表 orders 增加 status 列
3. 提供数据库迁移脚本

**阻塞任务**: T124, T125, T126
""",
    metadata={
        "issue_type": "architecture",
        "priority": "P0",
        "blocked_tasks": ["T124", "T125", "T126"]
    }
)
# fix_task.id = "T127"
```

### Step 4: 通知架构师

```python
# QA Tester 使用 SendMessage
SendMessage(
    to="architect",
    message="""发现架构层面问题，需要更新设计文档：

**问题类型**: 数据模型设计缺陷
**问题描述**: Order 模型缺少 status 属性，但 OpenAPI Spec 中定义了 OrderResponse.status
**发现任务**: T124（测试订单状态）
**阻塞任务**: T124, T125, T126
**建议方案**:
1. 在 Order 模型中增加 status 属性（OrderStatus 枚举）
2. 更新数据库表 orders 增加 status 列
3. 提供数据库迁移脚本

已创建架构修复任务：T127
请更新设计文档并通知我继续测试。
"""
)
```

### Step 5: 等待确认

```
# QA Tester 等待架构师回复
（停止工作，等待 SendMessage 回复）

↓

# Architect 收到消息后
1. 阅读 T127 任务描述
2. 更新设计文档（ADR）
3. 通知 Backend Dev 实现
4. 等待 Backend Dev 完成后
5. SendMessage(to="qa-tester", message="已修复 Order 模型，status 属性已添加，请继续测试")

↓

# QA Tester 收到确认后
1. 重新阅读更新后的设计文档
2. TaskUpdate(taskId="T124", status="in_progress")
3. 继续编写测试代码
```

---

## ⚠️ 违反后果

### ❌ 错误做法：只修代码不反馈

```python
# ❌ 错误示例：绕过架构问题
def test_order_status():
    order = Order(id="123")
    # 为了让测试通过，直接跳过 ❌
    pytest.skip("Order 缺少 status 属性")
    # 或者修改 Order 类（QA 禁止修改业务代码）❌
```

**后果**：
- Code Reviewer 检查时发现测试跳过或缺少覆盖 → P0 问题
- 测试退回重做
- 架构问题未修复，累积到生产环境引发更大问题

---

### ✅ 正确做法：反馈机制

```python
# ✅ 正确示例：停止修改，通知架构师
def test_order_status():
    order = Order(id="123")
    try:
        assert order.status == OrderStatus.PENDING
    except AttributeError:
        # 停止测试编写 ✅
        # 标记任务 ✅
        # 创建修复任务 ✅
        # 通知架构师 ✅
        raise ArchitectureIssueDetected("Order 模型缺少 status 属性")
```

**效果**：
- 架构师及时修复设计问题
- 所有 Agent 都基于更新后的设计工作
- 防止架构问题累积
- 保持系统架构一致性

---

## 📚 参考资源

- `.claude/team/architect/SKILL.md` - 架构师强制红线
- `docs/templates/openapi-template.md` - OpenAPI Spec 模板
- `docs/workflows/checkpoints-checklist.md` - 检查点清单

---

*本流程由 `/qa-tester` skill 强制要求，确保架构问题及时反馈和修复*