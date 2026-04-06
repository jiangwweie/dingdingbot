# ORD-6: 批量删除集成交易所 API - 架构设计文档

> **创建时间**: 2026-04-06  
> **状态**: 架构设计完成  
> **优先级**: P0 - 第 3 周交付任务  
> **关联任务**: ORD-1 (订单状态机), ORD-5 (审计日志表)

---

## 一、需求概述

### 1.1 功能目标

实现批量删除订单时同步取消交易所订单，确保数据库与交易所状态一致。

### 1.2 核心场景

| 场景 | 说明 |
|------|------|
| 用户手动删除订单 | 前端点击删除按钮，后端调用交易所取消 API |
| 批量删除订单链 | 删除 ENTRY 订单时级联取消 TP/SL 子订单 |
| 部分订单取消失败 | 交易所 API 失败时回滚数据库操作 |

### 1.3 验收标准

- [ ] 批量删除时自动调用交易所取消 API
- [ ] 取消失败时回滚数据库删除操作
- [ ] 记录审计日志（操作人、时间、结果）
- [ ] 前端显示取消结果（成功/失败列表）

---

## 二、架构设计

### 2.1 系统架构图

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Frontend  │────▶│  API Layer       │────▶│  OrderRepository│
│  Orders.tsx │     │  /api/v3/orders  │     │  delete_orders_ │
│             │     │  /batch          │     │  batch()        │
└─────────────┘     └──────────────────┘     └────────┬────────┘
                                                      │
                    ┌─────────────────────────────────┼─────────────────────────────────┐
                    │                                 │                                 │
                    ▼                                 ▼                                 ▼
         ┌──────────────────┐            ┌──────────────────┐            ┌──────────────────┐
         │ ExchangeGateway  │            │ OrderAuditLogger │            │   SQLite Orders  │
         │ cancel_order()   │            │ log()            │            │   DELETE         │
         └──────────────────┘            └──────────────────┘            └──────────────────┘
```

### 2.2 核心组件职责

| 组件 | 职责 |
|------|------|
| **Orders.tsx** | 前端批量删除按钮处理，调用 API 刷新列表 |
| **DELETE /api/v3/orders/batch** | API 端点，参数验证，调用 Repository |
| **OrderRepository.delete_orders_batch()** | 事务协调：1.取消交易所 2.删除 DB 3.记录审计 |
| **ExchangeGateway.cancel_order()** | 调用交易所取消 API |
| **OrderAuditLogger.log()** | 记录审计日志到 order_audit_logs 表 |

---

## 三、接口契约

### 3.1 请求/响应模型

**请求**:
```typescript
interface OrderBatchDeleteRequest {
  order_ids: string[];           // 订单 ID 列表（1-100）
  cancel_on_exchange: boolean;   // 是否调用交易所取消（默认 true）
  audit_info?: {
    operator_id: string;
    ip_address: string;
    user_agent: string;
  };
}
```

**响应**:
```typescript
interface OrderBatchDeleteResponse {
  deleted_count: number;
  cancelled_on_exchange: string[];    // 交易所成功取消的订单 ID
  failed_to_cancel: Array<{
    order_id: string;
    reason: string;
  }>;
  deleted_from_db: string[];
  failed_to_delete: Array<{
    order_id: string;
    reason: string;
  }>;
  audit_log_id?: string;
}
```

### 3.2 交易所取消接口

```python
# ExchangeGateway.cancel_order()
async def cancel_order(
    self,
    exchange_order_id: str,  # 交易所订单 ID
    symbol: str,             # 币种对
) -> OrderCancelResult:
    """
    取消交易所订单
    
    Returns:
        OrderCancelResult:
            - order_id: str
            - exchange_order_id: str
            - status: OrderStatus.CANCELED
            - message: str
            - error_code: Optional[str]
            - error_message: Optional[str]
    """
```

---

## 四、实现方案

### 4.1 OrderRepository.delete_orders_batch() 修改点

**当前位置**: `src/infrastructure/order_repository.py:1068-1210`

**待修改代码段**:
```python
# Step 3: 取消 OPEN 状态的订单（调用交易所 API）
if cancel_on_exchange:
    for order in orders_to_delete:
        if order.status in [OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]:
            # TODO: 调用交易所取消 API
            # 需要：1.获取 exchange_order_id 2.调用 gateway.cancel_order()
            pass

# Step 5: 记录审计日志
# TODO: 调用 OrderAuditLogger.log()
```

**修改后代码**:
```python
# Step 3: 取消 OPEN 状态的订单（调用交易所 API）
if cancel_on_exchange:
    for order in orders_to_delete:
        if order.status in [OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]:
            if order.exchange_order_id:
                try:
                    # 获取 ExchangeGateway 实例（通过依赖注入或单例）
                    gateway = self._get_exchange_gateway()
                    result = await gateway.cancel_order(
                        exchange_order_id=order.exchange_order_id,
                        symbol=order.symbol,
                    )
                    if result.is_success:
                        result["cancelled_on_exchange"].append(order.id)
                    else:
                        result["failed_to_cancel"].append({
                            "order_id": order.id,
                            "reason": result.error_message,
                        })
                except Exception as e:
                    result["failed_to_cancel"].append({
                        "order_id": order.id,
                        "reason": str(e),
                    })
            else:
                # 没有 exchange_order_id，无法调用交易所
                result["failed_to_cancel"].append({
                    "order_id": order.id,
                    "reason": "No exchange_order_id",
                })
```

### 4.2 审计日志集成

```python
# Step 6: 记录审计日志
from src.application.order_audit_logger import OrderAuditLogger
from src.domain.models import OrderAuditEventType, OrderAuditTriggerSource

audit_logger = OrderAuditLogger(self._audit_repo)
await audit_logger.log(
    order_id="BATCH_DELETE",  # 特殊标记
    signal_id=None,
    old_status=None,
    new_status="DELETED",
    event_type=OrderAuditEventType.ORDER_CANCELED,
    triggered_by=OrderAuditTriggerSource.USER,
    metadata={
        "operation": "DELETE_BATCH",
        "order_ids": order_ids,
        "cancelled_on_exchange": result["cancelled_on_exchange"],
        "operator_id": audit_info.get("operator_id") if audit_info else None,
        "ip_address": audit_info.get("ip_address") if audit_info else None,
    },
)
```

### 4.3 前端修改点

**文件**: `web-front/src/pages/Orders.tsx`

**当前代码** (行 140-160 附近):
```typescript
const handleBatchDelete = async () => {
  const selectedIds = selectedRows.map(r => r.id);
  if (selectedIds.length === 0) return;

  const request: OrderBatchDeleteRequest = {
    order_ids: selectedIds,
    cancel_on_exchange: true,
  };

  await deleteOrderChain(request);
  // TODO: 显示结果，刷新列表
};
```

**修改后**:
```typescript
const handleBatchDelete = async () => {
  const selectedIds = selectedRows.map(r => r.id);
  if (selectedIds.length === 0) {
    message.warning('请选择要删除的订单');
    return;
  }

  // 确认对话框
  Modal.confirm({
    title: `确认删除 ${selectedIds.length} 个订单？`,
    content: '此操作将同步取消交易所挂单，无法撤销。',
    onOk: async () => {
      try {
        const request: OrderBatchDeleteRequest = {
          order_ids: selectedIds,
          cancel_on_exchange: true,
          audit_info: {
            operator_id: 'user-001', // TODO: 从登录信息获取
            ip_address: '',
            user_agent: navigator.userAgent,
          },
        };

        const response = await deleteOrderChain(request);

        // 显示结果
        if (response.deleted_count > 0) {
          message.success(`成功删除 ${response.deleted_count} 个订单`);
        }
        if (response.failed_to_cancel.length > 0) {
          message.warning(
            `${response.failed_to_cancel.length} 个订单取消失败：${response.failed_to_cancel.map(f => f.reason).join(', ')}`
          );
        }

        // 刷新列表
        await fetchOrderTree();
        setSelectedRows([]);
      } catch (error) {
        message.error(`删除失败：${error.message}`);
      }
    },
  });
};
```

---

## 五、错误处理

### 5.1 错误场景与处理策略

| 错误场景 | 处理策略 |
|----------|----------|
| 交易所 API 超时 | 重试 3 次，仍失败则回滚 DB 操作 |
| 订单已成交 | 跳过该订单，记录到 `failed_to_cancel` |
| 订单不存在于交易所 | 视为幽灵订单，仅删除 DB 记录 |
| API 频率限制 | 指数退避重试，失败则回滚 |
| 数据库删除失败 | 回滚所有操作，返回错误 |

### 5.2 事务保护

```python
async with self._db.transaction():
    # Step 1: 调用交易所取消 API（非事务内，但失败可回滚）
    # Step 2: 数据库 DELETE 操作（事务内）
    # Step 3: 记录审计日志（独立写入）
```

---

## 六、测试计划

### 6.1 单元测试

| 测试用例 | 说明 |
|----------|------|
| `test_delete_orders_batch_empty_list` | 空列表验证 |
| `test_delete_orders_batch_exceeds_limit` | 超过 100 个订单验证 |
| `test_delete_orders_batch_cancel_success` | 取消成功场景 |
| `test_delete_orders_batch_cancel_failure` | 取消失败场景 |
| `test_delete_orders_batch_db_rollback` | 数据库回滚验证 |

### 6.2 集成测试

| 测试用例 | 说明 |
|----------|------|
| `test_batch_delete_with_exchange_cancel` | 真实交易所取消 |
| `test_batch_delete_audit_log_created` | 审计日志创建 |
| `test_batch_delete_frontend_flow` | 前端完整流程 |

---

## 七、文件清单

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `src/infrastructure/order_repository.py` | 修改 | 集成交易所取消 + 审计日志 |
| `web-front/src/pages/Orders.tsx` | 修改 | 批量删除 UI 逻辑 |
| `tests/unit/test_order_repository.py` | 新增 | 单元测试 |
| `tests/integration/test_batch_delete.py` | 新增 | 集成测试 |

---

## 八、依赖关系

```
ORD-5 (审计日志表) ✅ 已完成
    ↓
ORD-6 (批量删除集成) ← 本任务
    ↓
ORD-2 (对账机制) ← 依赖审计日志查询
```

---

## 九、实施计划

| 阶段 | 任务 | 工时 | 负责人 |
|------|------|------|--------|
| T1 | 后端集成交易所取消接口 | 1h | 后端开发 |
| T2 | 后端集成审计日志 | 0.5h | 后端开发 |
| T3 | 前端批量删除 UI | 0.5h | 前端开发 |
| T4 | 单元测试编写 | 0.5h | QA |
| T5 | 代码审查 | 0.5h | Reviewer |

**总计**: 3h

---

*最后更新：2026-04-06*
