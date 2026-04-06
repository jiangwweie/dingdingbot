# ORD-5: 订单审计日志集成指南

> **创建时间**: 2026-04-06  
> **状态**: 已完成  
> **关联任务**: ORD-1 (订单状态机), ORD-2 (对账机制), ORD-6 (批量删除)

---

## 一、文件位置

| 文件 | 路径 | 说明 |
|------|------|------|
| 迁移脚本 | `src/infrastructure/migrations/004_create_order_audit_logs.sql` | 建表 SQL |
| 数据模型 | `src/domain/models.py` | `OrderAuditLog`, `OrderAuditLogCreate`, `OrderAuditEventType`, `OrderAuditTriggerSource` |
| Repository | `src/infrastructure/order_audit_repository.py` | 数据访问层 |
| 应用服务 | `src/application/order_audit_logger.py` | 应用层服务（含异步队列） |

---

## 二、数据库表结构

```sql
CREATE TABLE order_audit_logs (
    id              TEXT PRIMARY KEY,
    order_id        TEXT NOT NULL,
    signal_id       TEXT,
    old_status      TEXT,
    new_status      TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    triggered_by    TEXT NOT NULL,  -- USER | SYSTEM | EXCHANGE
    metadata        TEXT,           -- JSON 格式
    created_at      INTEGER NOT NULL
);
```

---

## 三、事件类型枚举（与 ORD-1 对齐）

| 事件类型 | old_status | new_status | 说明 |
|---------|------------|------------|------|
| `ORDER_CREATED` | NULL | CREATED | 订单创建 |
| `ORDER_SUBMITTED` | CREATED | SUBMITTED | 订单提交到交易所 |
| `ORDER_CONFIRMED` | SUBMITTED | OPEN | 订单确认挂单 |
| `ORDER_PARTIAL_FILLED` | OPEN | PARTIALLY_FILLED | 部分成交 |
| `ORDER_FILLED` | OPEN/PARTIALLY_FILLED | FILLED | 完全成交 |
| `ORDER_CANCELED` | * | CANCELED | 订单取消 |
| `ORDER_REJECTED` | SUBMITTED/OPEN | REJECTED | 交易所拒单 |
| `ORDER_EXPIRED` | OPEN | EXPIRED | 订单过期 |
| `ORDER_UPDATED` | * | * | 订单信息更新 |

---

## 四、触发来源枚举

| 来源 | 说明 | 示例 |
|------|------|------|
| `USER` | 用户主动操作 | 用户点击取消按钮 |
| `SYSTEM` | 系统自动触发 | OCO 逻辑自动撤销 |
| `EXCHANGE` | 交易所推送 | WebSocket 推送成交 |

---

## 五、使用示例

### 5.1 初始化审计日志服务

```python
# 在应用启动时初始化
from src.infrastructure.order_audit_repository import OrderAuditLogRepository
from src.application.order_audit_logger import OrderAuditLogger

# 创建 Repository（需要数据库 Session 工厂）
audit_repo = OrderAuditLogRepository(db_session_factory=get_db)

# 创建服务
audit_logger = OrderAuditLogger(audit_repo)

# 启动异步队列
await audit_logger.start(queue_size=1000)
```

### 5.2 在 ORD-1 OrderLifecycleService 中集成

```python
from src.application.order_audit_logger import OrderAuditLogger
from src.domain.models import OrderAuditTriggerSource

class OrderLifecycleService:
    def __init__(self, audit_logger: OrderAuditLogger):
        self._audit_logger = audit_logger

    async def _transition(
        self,
        order: Order,
        new_status: OrderStatus,
        triggered_by: OrderAuditTriggerSource,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Order:
        """状态转换方法"""
        old_status = order.status.value if order.status else None
        new_status_str = new_status.value

        # 执行状态转换逻辑
        order.status = new_status
        order.updated_at = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 【审计日志写入点】
        await self._audit_logger.log_status_change(
            order_id=order.id,
            signal_id=order.signal_id,
            old_status=old_status,
            new_status=new_status_str,
            triggered_by=triggered_by,
            metadata=metadata,
        )

        return order
```

### 5.3 在订单删除时集成

```python
# 在 OrderRepository.delete() 中
async def delete(self, order_id: str, deleted_by: str = "user") -> bool:
    # 1. 先查询订单
    order = await self.get_by_id(order_id)
    if not order:
        return False

    # 2. 执行删除
    async with self._db_session() as session:
        await session.execute(
            text("DELETE FROM orders WHERE id = :order_id"),
            {"order_id": order_id},
        )
        await session.commit()

    # 3. 【审计日志写入点】记录删除操作
    await self._audit_logger.log(
        order_id=order_id,
        signal_id=order.signal_id,
        old_status=order.status.value if order.status else None,
        new_status="DELETED",
        event_type=OrderAuditEventType.ORDER_CANCELED,
        triggered_by=OrderAuditTriggerSource.USER,
        metadata={"deleted_by": deleted_by},
    )

    return True
```

### 5.4 查询审计历史

```python
# 获取订单的完整审计历史
audit_logs = await audit_logger.get_audit_history(order_id="ord_xxxxx")

# 获取信号关联的所有订单审计历史（用于追踪订单链）
signal_audits = await audit_logger.get_signal_audit_history(signal_id="sig_xxxxx")

# 通用查询
from src.domain.models import OrderAuditLogQuery, OrderAuditEventType

query = OrderAuditLogQuery(
    order_id="ord_xxxxx",
    event_type=OrderAuditEventType.ORDER_FILLED,
    limit=50,
)
audits = await audit_logger.query(query)
```

---

## 六、API 端点设计

### 6.1 查询订单审计历史

```
GET /api/v1/orders/{order_id}/audit-logs

Response 200:
{
  "order_id": "ord_xxxxx",
  "audit_logs": [
    {
      "id": "audit_001",
      "order_id": "ord_xxxxx",
      "signal_id": "sig_xxxxx",
      "old_status": null,
      "new_status": "CREATED",
      "event_type": "ORDER_CREATED",
      "triggered_by": "USER",
      "metadata": {
        "user_id": "user_001",
        "strategy_name": "pinbar"
      },
      "created_at": 1712400000000
    },
    ...
  ]
}
```

### 6.2 按信号 ID 查询

```
GET /api/v1/signals/{signal_id}/audit-logs

Response 200:
{
  "signal_id": "sig_xxxxx",
  "audit_logs": [...]
}
```

---

## 七、验收标准

### 功能验收
- [ ] 所有订单状态变更都记录审计日志
- [ ] 审计历史可按订单 ID 查询
- [ ] 审计历史可按信号 ID 查询
- [ ] 元数据 JSON 格式正确

### 性能验收
- [ ] 审计日志写入不阻塞订单状态流转（异步队列）
- [ ] 队列满时降级为同步写入
- [ ] 查询审计历史响应时间 < 100ms

### 代码验收
- [ ] 代码审查通过（Reviewer 确认）
- [ ] 单元测试覆盖所有事件类型
- [ ] 集成测试通过

---

## 八、与 ORD-1 的接口契约

| 依赖项 | ORD-1 责任 | ORD-5 责任 |
|--------|------------|------------|
| 状态枚举 | 定义 `OrderStatus` | 使用相同枚举值 |
| 事件类型 | 提供事件类型映射 | 实现日志写入 |
| 集成点 | 调用审计日志接口 | 提供审计日志服务 |
| 数据库 | - | 建表 + 迁移脚本 |

---

## 九、待确认问题（需用户决策）

1. **审计日志保留策略**: 保留多久？是否需要自动清理？
   - 建议：生产环境永久保留，开发环境 30 天

2. **元数据扩展**: 是否需要添加 `user_id`、`session_id`、`ip_address`？
   - 建议：通过 `metadata` 字典灵活扩展

3. **写入失败处理**: 审计日志写入失败是否需要重试？
   - 建议：不重试（审计日志为次要功能，失败不影响主流程）

4. **API 权限**: 查询审计日志是否需要权限控制？
   - 建议：需要（至少登录验证）

---

## 十、下一步

1. 运行迁移脚本创建表
2. 在 `OrderLifecycleService` 中集成审计日志
3. 在订单删除功能中集成审计日志
4. 添加 API 端点
5. 编写单元测试

---

*最后更新：2026-04-06*
