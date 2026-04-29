# ORD-6: 批量删除功能 - P0/P1/P2 问题修复方案

> **创建时间**: 2026-04-06  
> **状态**: 架构设计  
> **优先级**: P0 - 阻塞交付  
> **关联审查**: `docs/reviews/ord-6-code-review-report.md`

---

## 一、问题总览

| 优先级 | 数量 | 说明 | 修复状态 |
|--------|------|------|----------|
| **P0** | 3 | 阻塞性问题，必须修复 | 待修复 |
| **P1** | 5 | 重要问题，强烈建议修复 | 待修复 |
| **P2** | 4 | 改进建议，可后续迭代 | 建议部分修复 |

---

## 二、P0 问题修复方案 (阻塞交付)

### P0-1: ExchangeGateway 未初始化

**文件**: `src/infrastructure/order_repository.py:1174-1190`

#### 问题分析

当前代码中 `gateway` 变量始终为 `None`，导致交易所取消功能完全不可用：

```python
# 行 1174-1190
from src.infrastructure.exchange_gateway import ExchangeGateway
gateway = None  # ← 问题：gateway 始终为 None

for order in orders_to_delete:
    if order.status in [OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]:
        if order.exchange_order_id:
            try:
                # 懒加载 ExchangeGateway
                if gateway is None:
                    # TODO: 从配置或依赖注入获取 ExchangeGateway 实例
                    logger.warning(f"跳过交易所取消：ExchangeGateway 未注入")
                    result["failed_to_cancel"].append({
                        "order_id": order.id,
                        "reason": "ExchangeGateway not initialized",
                    })
                    continue  # ← 直接跳过，从未真正初始化
```

**影响**:
- 核心功能"交易所取消"完全不可用
- 所有订单取消请求都返回 `ExchangeGateway not initialized` 错误
- 违反架构设计文档验收标准

#### 修复方案对比

| 方案 | 优点 | 缺点 | 复杂度 |
|------|------|------|--------|
| **方案 1: 依赖注入（推荐）** | 符合 Clean Architecture，易于测试，解耦 | 需要修改 OrderRepository 构造函数 | 中 |
| **方案 2: 全局单例** | 实现简单，与现有 API 层一致 | 全局状态难以测试，隐含依赖 | 低 |
| **方案 3: 配置初始化** | 独立于外部依赖 | 代码冗余，每次调用都需初始化 | 中 |

#### 方案 1: 依赖注入（推荐）⭐

**设计思路**:
通过构造函数注入 `ExchangeGateway`，符合 Clean Architecture 原则。

**接口契约**:
```python
class OrderRepository:
    def __init__(
        self,
        db_path: Optional[str] = None,
        exchange_gateway: Optional[ExchangeGateway] = None,
        audit_logger: Optional[OrderAuditLogger] = None,
    ):
        self._db_path = db_path
        self._db = None
        self._exchange_gateway = exchange_gateway
        self._audit_logger = audit_logger
    
    async def initialize(self) -> None:
        """初始化数据库连接"""
        # ... 现有初始化逻辑
    
    def set_exchange_gateway(self, gateway: ExchangeGateway) -> None:
        """设置交易所网关（依赖注入）"""
        self._exchange_gateway = gateway
    
    def set_audit_logger(self, logger: OrderAuditLogger) -> None:
        """设置审计日志器（依赖注入）"""
        self._audit_logger = logger
```

**使用方式**:
```python
# 在 main.py 或 API 层初始化时注入
from src.infrastructure.order_repository import OrderRepository
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.application.order_audit_logger import OrderAuditLogger

# 创建实例
order_repo = OrderRepository()
await order_repo.initialize()

# 注入依赖
order_repo.set_exchange_gateway(exchange_gateway)
order_repo.set_audit_logger(audit_logger)
```

**delete_orders_batch 修改**:
```python
# Step 3: 取消 OPEN 状态的订单（调用交易所 API）
if cancel_on_exchange:
    for order in orders_to_delete:
        if order.status in [OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]:
            if order.exchange_order_id and self._exchange_gateway:
                try:
                    result_cancel = await self._exchange_gateway.cancel_order(
                        exchange_order_id=order.exchange_order_id,
                        symbol=order.symbol,
                    )
                    if result_cancel.is_success:
                        result["cancelled_on_exchange"].append(order.id)
                    else:
                        result["failed_to_cancel"].append({
                            "order_id": order.id,
                            "reason": result_cancel.error_message or "Unknown error",
                        })
                except Exception as e:
                    logger.warning(f"取消订单失败 {order.id}: {e}")
                    result["failed_to_cancel"].append({
                        "order_id": order.id,
                        "reason": str(e),
                    })
            elif not self._exchange_gateway:
                logger.warning(f"跳过交易所取消：ExchangeGateway 未注入")
                result["failed_to_cancel"].append({
                    "order_id": order.id,
                    "reason": "ExchangeGateway not initialized",
                })
            else:
                result["failed_to_cancel"].append({
                    "order_id": order.id,
                    "reason": "No exchange_order_id",
                })
```

#### 方案 2: 全局单例（备选）

通过全局函数获取单例，与现有 `api.py` 中的 `_get_exchange_gateway()` 一致。

```python
# 在 api.py 中
def _get_order_repo() -> Any:
    """Get order repository with dependencies injected."""
    if _order_repo is None:
        from src.infrastructure.order_repository import OrderRepository
        repo = OrderRepository()
        # 自动注入依赖
        if _exchange_gateway:
            repo.set_exchange_gateway(_exchange_gateway)
        if _audit_logger:
            repo.set_audit_logger(_audit_logger)
        return repo
    return _order_repo
```

#### 推荐方案

**选择方案 1（依赖注入）**，理由：
1. 符合 Clean Architecture 原则
2. 易于单元测试（可传入 Mock）
3. 显式依赖，代码更清晰
4. 与现有 `OrderAuditLogger` 注入模式一致

---

### P0-2: 审计日志资源泄漏

**文件**: `src/infrastructure/order_repository.py:1241-1243`

#### 问题分析

```python
# 行 1241-1243
from src.infrastructure.order_audit_repository import OrderAuditLogRepository
audit_repo = OrderAuditLogRepository()  # ← 每次调用都创建新实例
audit_logger = OrderAuditLogger(audit_repo)

await audit_logger.log(...)
# 问题：没有调用 await audit_repo.close() 关闭异步队列
```

**影响**:
- 每次批量删除都创建新的 `asyncio.Queue` 和 `asyncio.Task`
- 异步 Worker 永不关闭，导致资源泄漏
- 多次调用后可能耗尽系统资源

#### 修复方案对比

| 方案 | 优点 | 缺点 | 复杂度 |
|------|------|------|--------|
| **方案 1: 全局单例（推荐）** | 资源复用，易于管理，与现有模式一致 | 需要全局状态管理 | 低 |
| **方案 2: 上下文管理** | 资源明确释放，符合 Python 习惯 | 代码冗余，每次都要 try/finally | 中 |
| **方案 3: 依赖注入** | 与 P0-1 一致，统一管理 | 需要修改接口契约 | 中 |

#### 方案 1: 全局单例（推荐）⭐

在 `api.py` 中创建全局 `OrderAuditLogger` 单例：

```python
# api.py
_audit_logger: Optional[OrderAuditLogger] = None

async def _initialize_audit_logger() -> None:
    """初始化全局审计日志器"""
    global _audit_logger
    from src.application.order_audit_logger import OrderAuditLogger
    from src.infrastructure.order_audit_repository import OrderAuditLogRepository
    
    audit_repo = OrderAuditLogRepository(db_session_factory=get_db_session)
    await audit_repo.initialize(queue_size=1000)
    _audit_logger = OrderAuditLogger(audit_repo)

def _get_audit_logger() -> OrderAuditLogger:
    """获取全局审计日志器"""
    if _audit_logger is None:
        raise HTTPException(status_code=503, detail="Audit logger not initialized")
    return _audit_logger

@asynccontextmanager
async def lifespan(app: FastAPI):
    """管理应用生命周期"""
    # 启动时初始化
    await _initialize_audit_logger()
    yield
    # 关闭时清理
    await _audit_logger.stop()
```

**order_repository.py 修改**:
```python
# Step 5: 记录审计日志
audit_log_id = str(uuid.uuid4())
result["audit_log_id"] = audit_log_id

try:
    from src.application.order_audit_logger import OrderAuditLogger
    
    # 使用注入的审计日志器（全局单例）
    if self._audit_logger:
        await self._audit_logger.log(
            order_id="BATCH_DELETE",
            signal_id=None,
            old_status=None,
            new_status="DELETED",
            event_type=OrderAuditEventType.ORDER_CANCELED,
            triggered_by=OrderAuditTriggerSource.USER,
            metadata={
                "operation": "DELETE_BATCH",
                "order_ids": order_ids,
                "cancelled_on_exchange": result["cancelled_on_exchange"],
                "deleted_from_db": result["deleted_from_db"],
                "failed_to_cancel": result["failed_to_cancel"],
                "failed_to_delete": result.get("failed_to_delete", []),
                "operator_id": audit_info.get("operator_id") if audit_info else None,
                "ip_address": audit_info.get("ip_address") if audit_info else None,
            },
        )
        logger.info(f"审计日志已记录：{audit_log_id}")
    else:
        logger.warning("审计日志器未注入，跳过日志记录")
except Exception as audit_error:
    logger.error(f"记录审计日志失败：{audit_error}")
```

#### 方案 2: 上下文管理（备选）

```python
try:
    from src.infrastructure.order_audit_repository import OrderAuditLogRepository
    from src.application.order_audit_logger import OrderAuditLogger
    
    audit_repo = OrderAuditLogRepository()
    await audit_repo.initialize()
    audit_logger = OrderAuditLogger(audit_repo)
    
    await audit_logger.log(...)
finally:
    await audit_repo.close()  # 确保关闭
```

#### 推荐方案

**选择方案 1（全局单例 + 依赖注入）**，理由：
1. 资源复用，避免重复创建
2. 统一管理，易于维护
3. 与 P0-1 方案一致
4. 符合现有 `api.py` 模式

---

### P0-3: 前端逻辑重复

**文件**: `gemimi-web-front/src/pages/Orders.tsx:140-174` 和 `243-258`

#### 问题分析

存在两套批量删除处理逻辑：

1. **逻辑 1** (行 140-174): `handleDeleteConfirm` 处理删除逻辑
2. **逻辑 2** (行 243-258): 内联 `Modal.confirm` 触发删除

**问题**:
- `DeleteChainConfirmModal` 组件 (行 409-415) 未被使用，代码冗余
- 两套逻辑状态管理混乱 (`selectedRowKeys` vs `pendingDeleteOrderIds`)
- 可能触发两次确认对话框

#### 修复方案

**统一使用 `DeleteChainConfirmModal` 组件**:

```typescript
// 修改后代码结构

// 1. 状态定义
const [pendingDeleteOrderIds, setPendingDeleteOrderIds] = useState<string[]>([]);
const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);

// 2. 批量删除按钮 - 统一入口
{selectedRowKeys.length > 0 && (
  <button
    onClick={() => handleDeleteChainClick(selectedRowKeys)}
    className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg"
  >
    <Trash2 className="w-4 h-4" />
    批量删除 ({selectedRowKeys.length})
  </button>
)}

// 3. 统一点击处理
const handleDeleteChainClick = useCallback(async (orderIds: string[]) => {
  setPendingDeleteOrderIds(orderIds);
  setIsDeleteModalOpen(true);  // 打开 DeleteChainConfirmModal
}, []);

// 4. 删除确认处理
const handleDeleteConfirm = useCallback(async () => {
  try {
    const request: OrderBatchDeleteRequest = {
      order_ids: pendingDeleteOrderIds,
      cancel_on_exchange: true,
      audit_info: {
        operator_id: user?.id || 'unknown',  // 从登录上下文获取
        ip_address: await getClientIP(),
        user_agent: navigator.userAgent,
      },
    };

    const response = await deleteOrderChain(request);

    // 显示完整结果
    if (response.deleted_from_db.length > 0) {
      message.success(`已从数据库删除 ${response.deleted_from_db.length} 个订单`);
    }
    if (response.cancelled_on_exchange.length > 0) {
      message.success(`已在交易所取消 ${response.cancelled_on_exchange.length} 个订单`);
    }
    if (response.failed_to_cancel.length > 0) {
      message.warning(
        `交易所取消失败：${response.failed_to_cancel.map(f => `${f.order_id}(${f.reason})`).join(', ')}`
      );
    }
    if (response.failed_to_delete && response.failed_to_delete.length > 0) {
      message.error(
        `数据库删除失败：${response.failed_to_delete.map(f => `${f.order_id}(${f.reason})`).join(', ')}`
      );
    }

    setIsDeleteModalOpen(false);
    setPendingDeleteOrderIds([]);
    setSelectedRowKeys([]);
    await loadOrderTree();
  } catch (error) {
    message.error(`删除失败：${error.message || '请重试'}`);
    throw error;
  }
}, [pendingDeleteOrderIds, loadOrderTree, user]);

// 5. 删除确认对话框组件
<DeleteChainConfirmModal
  isOpen={isDeleteModalOpen}
  orderIds={pendingDeleteOrderIds}
  onConfirm={handleDeleteConfirm}
  onCancel={() => {
    setIsDeleteModalOpen(false);
    setPendingDeleteOrderIds([]);
  }}
/>
```

**修改文件清单**:
- `gemimi-web-front/src/pages/Orders.tsx`
  - 移除内联 `Modal.confirm` (行 243-258)
  - 修复 `handleDeleteChainClick` 统一入口
  - 完善删除结果展示
  - 集成 `DeleteChainConfirmModal` 组件

---

## 三、P1 问题修复方案 (强烈建议)

### P1-1: 级联删除逻辑不完整

**文件**: `src/infrastructure/order_repository.py:1137-1157`

#### 问题分析

当前代码只获取直接子订单，未考虑多层级联：

```python
if target_order.order_role == OrderRole.ENTRY:
    cursor = await self._db.execute(
        "SELECT id FROM orders WHERE parent_order_id = ?",
        (target_order.id,)
    )
    # ← 只获取直接子订单，未递归获取 TP/SL 的子订单
```

#### 修复方案

**递归获取所有关联订单 ID**:

```python
async def _get_all_related_order_ids(self, order_ids: List[str]) -> Set[str]:
    """
    递归获取所有关联订单 ID（包括子订单和父订单）

    Args:
        order_ids: 初始订单 ID 列表

    Returns:
        所有关联订单 ID 集合
    """
    all_ids = set(order_ids)
    queue = list(order_ids)

    while queue:
        current_id = queue.pop(0)

        # 获取子订单
        cursor = await self._db.execute(
            "SELECT id FROM orders WHERE parent_order_id = ?",
            (current_id,)
        )
        child_rows = await cursor.fetchall()
        await cursor.close()

        for child_row in child_rows:
            child_id = child_row[0]
            if child_id not in all_ids:
                all_ids.add(child_id)
                queue.append(child_id)

        # 获取父订单
        cursor = await self._db.execute(
            "SELECT parent_order_id FROM orders WHERE id = ?",
            (current_id,)
        )
        parent_row = await cursor.fetchone()
        await cursor.close()

        if parent_row and parent_row[0] and parent_row[0] not in all_ids:
            all_ids.add(parent_row[0])
            queue.append(parent_row[0])

    return all_ids
```

**修改文件清单**:
- `src/infrastructure/order_repository.py`
  - 新增 `_get_all_related_order_ids()` 方法
  - 修改 `delete_orders_batch()` 调用新方法

---

### P1-2: SQL 注入风险

**文件**: `src/infrastructure/order_repository.py:1219-1222`

#### 问题分析

```python
placeholders = ','.join('?' * len(orders_to_delete))
await self._db.execute(
    f"DELETE FROM orders WHERE id IN ({placeholders})",  # f-string 拼接
    tuple(o.id for o in orders_to_delete)
)
```

虽然使用了 `?` 占位符，但 SQL 语句通过 f-string 拼接，存在理论风险。

#### 修复方案

**分批删除 + 参数化查询**:

```python
# 分批删除，避免单次操作过大
BATCH_SIZE = 50
for i in range(0, len(orders_to_delete), BATCH_SIZE):
    batch = orders_to_delete[i:i + BATCH_SIZE]
    placeholders = ','.join('?' * len(batch))
    await self._db.execute(
        f"DELETE FROM orders WHERE id IN ({placeholders})",
        tuple(o.id for o in batch)
    )
```

**说明**: 由于 `?` 占位符已经是参数化查询，`placeholders` 仅由数字控制，风险较低。此修复为最佳实践加固。

**修改文件清单**:
- `src/infrastructure/order_repository.py`

---

### P1-3: 前端 audit_info 字段硬编码

**文件**: `gemimi-web-front/src/pages/Orders.tsx:146-150`

#### 问题分析

```typescript
audit_info: {
  operator_id: 'user-001', // TODO: 从登录信息获取  ← 硬编码
  ip_address: '',
  user_agent: navigator.userAgent,
},
```

#### 修复方案

**从登录上下文获取用户信息**:

```typescript
import { useAuth } from '../hooks/useAuth';

// 在组件内
const { user } = useAuth();

// 获取客户端 IP（通过 API）
const getClientIP = async (): Promise<string> => {
  try {
    const response = await fetch('/api/v1/client/info');
    const data = await response.json();
    return data.ip_address || '';
  } catch {
    return '';
  }
};

// 修改 handleDeleteConfirm
const handleDeleteConfirm = useCallback(async () => {
  const request: OrderBatchDeleteRequest = {
    order_ids: pendingDeleteOrderIds,
    cancel_on_exchange: true,
    audit_info: {
      operator_id: user?.id || 'unknown',
      ip_address: await getClientIP(),
      user_agent: navigator.userAgent,
    },
  };
  // ...
}, [pendingDeleteOrderIds, loadOrderTree, user]);
```

**修改文件清单**:
- `gemimi-web-front/src/pages/Orders.tsx`
- `gemimi-web-front/src/hooks/useAuth.ts` (如不存在则新建)

---

### P1-4: 测试 Mock 未使用

**文件**: `tests/integration/test_batch_delete.py:216-236`

#### 问题分析

定义了 `MockExchangeGateway` 但从未使用，测试用例名称与内容不符。

#### 修复方案

**完善 Mock 测试**:

```python
@pytest.mark.asyncio
async def test_batch_delete_with_exchange_mock(order_repository):
    """
    INT-ORD-6-002: 使用 Mock 交易所的批量删除测试

    测试场景:
    1. 创建带有 exchange_order_id 的 OPEN 状态订单
    2. Mock ExchangeGateway 的 cancel_order 方法
    3. 执行批量删除（cancel_on_exchange=True）
    4. 验证交易所取消成功
    5. 验证数据库记录已删除
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建 OPEN 状态的订单（有 exchange_order_id）
    orders = [
        Order(
            id=f"ord_exchange_mock_{i}",
            signal_id=f"sig_exchange_mock_{i}",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            price=Decimal('70000'),
            requested_qty=Decimal('0.5'),
            filled_qty=Decimal('0'),
            status=OrderStatus.OPEN,
            created_at=current_time,
            updated_at=current_time,
            exchange_order_id=f"binance_mock_{i}",
            reduce_only=True,
        )
        for i in range(3)
    ]

    # 保存订单
    for order in orders:
        await order_repository.save(order)

    # 准备：Mock ExchangeGateway
    cancelled_exchange_ids = []
    failed_exchange_ids = []

    class MockCancelResult:
        def __init__(self, success: bool, error: str = None):
            self.is_success = success
            self.error_message = error

    class MockExchangeGateway:
        async def cancel_order(self, exchange_order_id: str, symbol: str):
            # 模拟：第 2 个订单取消失败
            if exchange_order_id == "binance_mock_1":
                failed_exchange_ids.append(exchange_order_id)
                return MockCancelResult(success=False, error="Order already filled")
            else:
                cancelled_exchange_ids.append(exchange_order_id)
                return MockCancelResult(success=True)

    # 注入 Mock Gateway
    mock_gateway = MockExchangeGateway()
    order_repository.set_exchange_gateway(mock_gateway)

    # 执行：批量删除
    result = await order_repository.delete_orders_batch(
        order_ids=["ord_exchange_mock_0", "ord_exchange_mock_1", "ord_exchange_mock_2"],
        cancel_on_exchange=True,
    )

    # 验证：交易所取消结果
    assert len(result["cancelled_on_exchange"]) == 2
    assert len(result["failed_to_cancel"]) == 1
    assert result["failed_to_cancel"][0]["order_id"] == "ord_exchange_mock_1"

    # 验证：数据库删除结果
    assert result["deleted_count"] == 3
    assert len(result["deleted_from_db"]) == 3

    # 验证：订单确实被删除
    for i in range(3):
        order = await order_repository.get_order(f"ord_exchange_mock_{i}")
        assert order is None
```

**修改文件清单**:
- `tests/integration/test_batch_delete.py`

---

### P1-5: 删除结果展示不完整

**文件**: `gemimi-web-front/src/pages/Orders.tsx:155-163`

#### 问题分析

未显示 `failed_to_delete` 和 `deleted_from_db` 详情。

#### 修复方案

已在 P0-3 中统一修复，显示完整结果：

```typescript
// 显示完整结果
if (response.deleted_from_db.length > 0) {
  message.success(`已从数据库删除 ${response.deleted_from_db.length} 个订单`);
}
if (response.cancelled_on_exchange.length > 0) {
  message.success(`已在交易所取消 ${response.cancelled_on_exchange.length} 个订单`);
}
if (response.failed_to_cancel.length > 0) {
  message.warning(
    `交易所取消失败：${response.failed_to_cancel.map(f => `${f.order_id}(${f.reason})`).join(', ')}`
  );
}
if (response.failed_to_delete && response.failed_to_delete.length > 0) {
  message.error(
    `数据库删除失败：${response.failed_to_delete.map(f => `${f.order_id}(${f.reason})`).join(', ')}`
  );
}
```

**修改文件清单**:
- `gemimi-web-front/src/pages/Orders.tsx`

---

## 四、P2 问题修复建议 (改进建议)

| 编号 | 问题 | 建议 | 优先级 |
|------|------|------|--------|
| **P2-1** | 日志级别不当 | 调整日志级别：预期行为→INFO，业务异常→WARNING，系统错误→ERROR | 建议本次修复 |
| **P2-2** | 缺少订单状态预检查 | 前端增加删除前状态检查提示 | 延后 |
| **P2-3** | 审计日志缺少删除详情 | 增加 `failed_to_cancel` 和 `failed_to_delete` 详情 | 建议本次修复 |
| **P2-4** | 缺少批量删除快捷键 | 增加 Delete 键快捷触发 | 延后 |

### P2-1: 日志级别调整

```python
# 修改前
logger.warning(f"跳过交易所取消：ExchangeGateway 未注入")  # 预期行为

# 修改后
logger.info(f"跳过交易所取消：cancel_on_exchange=false 或 ExchangeGateway 未注入")
```

```python
# 修改前
logger.warning(f"记录审计日志失败：{audit_error}")  # 系统错误

# 修改后
logger.error(f"记录审计日志失败：{audit_error}")
```

### P2-3: 审计日志详情增强

已在 P0-2 修复方案中增加：
```python
metadata={
    "operation": "DELETE_BATCH",
    "order_ids": order_ids,
    "cancelled_on_exchange": result["cancelled_on_exchange"],
    "deleted_from_db": result["deleted_from_db"],
    "failed_to_cancel": result["failed_to_cancel"],
    "failed_to_delete": result.get("failed_to_delete", []),
    "operator_id": ...,
    "ip_address": ...,
}
```

---

## 五、修复任务分解

| 任务 ID | 任务名称 | 负责人 | 预计工时 | 依赖关系 |
|---------|----------|--------|----------|----------|
| **FIX-001** | ExchangeGateway 依赖注入 | 后端开发 | 2h | - |
| **FIX-002** | OrderAuditLogger 全局单例 | 后端开发 | 1h | FIX-001 |
| **FIX-003** | 前端批量删除逻辑统一 | 前端开发 | 1.5h | - |
| **FIX-004** | 级联删除逻辑完善 | 后端开发 | 1.5h | FIX-001 |
| **FIX-005** | SQL 注入风险修复 | 后端开发 | 0.5h | FIX-001 |
| **FIX-006** | 前端 audit_info 真实化 | 前端开发 | 1h | FIX-003 |
| **FIX-007** | 测试 Mock 完善 | QA | 1.5h | FIX-001, FIX-002 |
| **FIX-008** | 删除结果展示完善 | 前端开发 | 0.5h | FIX-003 |
| **FIX-009** | 日志级别调整 (P2-1) | 后端开发 | 0.5h | - |
| **FIX-010** | 审计日志详情增强 (P2-3) | 后端开发 | 0.5h | FIX-002 |

---

## 六、修复顺序建议

根据依赖关系，建议修复顺序：

```
阶段 1 (P0 修复 - 阻塞交付):
  FIX-001 → FIX-002 → FIX-003
  (依赖注入)  (审计单例)  (前端统一)

阶段 2 (P1 修复 - 强烈建议):
  FIX-004 → FIX-005 → FIX-006 → FIX-007 → FIX-008
  (级联删除)  (SQL 注入)  (审计信息)  (测试 Mock)  (结果展示)

阶段 3 (P2 修复 - 本次建议):
  FIX-009 → FIX-010
  (日志级别)  (审计详情)

延后 (P2 修复 - 下次迭代):
  - P2-2: 订单状态预检查
  - P2-4: 批量删除快捷键
```

---

## 七、接口契约更新

### OrderRepository 构造函数

```python
class OrderRepository:
    """
    订单数据仓库

    依赖注入:
    - ExchangeGateway: 交易所网关（可选）
    - OrderAuditLogger: 审计日志器（可选）
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        exchange_gateway: Optional[Any] = None,  # ExchangeGateway
        audit_logger: Optional[Any] = None,      # OrderAuditLogger
    ):
        """
        初始化订单仓库

        Args:
            db_path: 数据库路径（默认使用配置路径）
            exchange_gateway: 交易所网关（依赖注入）
            audit_logger: 审计日志器（依赖注入）
        """
        self._db_path = db_path
        self._db = None
        self._exchange_gateway = exchange_gateway
        self._audit_logger = audit_logger

    async def initialize(self) -> None:
        """初始化数据库连接"""
        # ...

    def set_exchange_gateway(self, gateway: Any) -> None:
        """设置交易所网关（依赖注入）"""
        self._exchange_gateway = gateway

    def set_audit_logger(self, logger: Any) -> None:
        """设置审计日志器（依赖注入）"""
        self._audit_logger = logger
```

### OrderBatchDeleteResponse 更新

```typescript
interface OrderBatchDeleteResponse {
  deleted_count: number;
  cancelled_on_exchange: string[];       // 交易所成功取消的订单 ID
  failed_to_cancel: Array<{              // 交易所取消失败详情
    order_id: string;
    reason: string;
  }>;
  deleted_from_db: string[];             // 数据库成功删除的订单 ID
  failed_to_delete?: Array<{             // 数据库删除失败详情（可选）
    order_id: string;
    reason: string;
  }>;
  audit_log_id?: string;
}
```

---

## 八、测试覆盖要求

修复后测试覆盖率要求：

| 测试类型 | 最低覆盖率 | 测试文件 |
|----------|------------|----------|
| 单元测试 | >85% | `tests/unit/test_order_repository.py` |
| 集成测试 | >80% | `tests/integration/test_batch_delete.py` |
| 端到端测试 | 核心流程覆盖 | `tests/e2e/test_batch_delete_e2e.py` |

**必须覆盖的场景**:
- [ ] ExchangeGateway 取消成功
- [ ] ExchangeGateway 取消失败
- [ ] 无 exchange_order_id 的幽灵订单
- [ ] 数据库删除事务回滚
- [ ] 审计日志记录成功/失败
- [ ] 级联删除多层订单
- [ ] 前端删除结果展示

---

## 九、验收标准

### 功能验收

- [ ] P0-1: ExchangeGateway 正确初始化，交易所取消功能可用
- [ ] P0-2: 审计日志资源正确释放，无内存泄漏
- [ ] P0-3: 前端批量删除逻辑统一，无重复确认对话框
- [ ] P1-1: 级联删除可递归获取所有关联订单
- [ ] P1-2: SQL 查询使用参数化，无注入风险
- [ ] P1-3: 审计信息中的 operator_id 来自真实用户
- [ ] P1-4: 测试用例完整，Mock 正确使用
- [ ] P1-5: 前端完整展示删除结果

### 代码质量验收

- [ ] 单元测试覆盖率 >85%
- [ ] 集成测试覆盖率 >80%
- [ ] 无 P0/P1 问题遗留
- [ ] 代码审查通过

---

## 十、风险评估

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| 依赖注入破坏现有代码 | 低 | 中 | 向后兼容构造函数，默认参数为 None |
| 全局单例初始化顺序问题 | 中 | 高 | 在 lifespan 中明确初始化顺序 |
| 前端用户上下文获取失败 | 低 | 低 | 降级为 'unknown'，不影响功能 |

---

*最后更新：2026-04-06*
