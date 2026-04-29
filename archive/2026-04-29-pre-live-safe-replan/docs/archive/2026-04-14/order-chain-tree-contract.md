# 订单管理级联展示功能 - 接口契约表

> **创建日期**: 2026-04-02  
> **优先级**: P1 (RICE 评分：6.2)  
> **预计工时**: 16h  
> **状态**: ✅ 架构审查通过（已修正）  
> **架构审查**: 🟡 有条件通过 → ✅ 已修正 3 个问题

---

## 📋 需求概述

**核心需求**: 在订单管理页面实现树形展示订单链（ENTRY→TP1/TP2/SL），支持展开/折叠、批量删除操作

**用户确认的需求细节**:
1. **展示形式**: 树形表格（选项 A）
2. **批量操作**: 批量删除（支持删除选中订单链）
3. **展示范围**: 包括所有状态的订单（已成交 + 挂单中）
4. **入口订单**: 所有 `order_role = 'ENTRY'` 的订单
5. **展开状态**: 仅会话级持久化
6. **删除确认**: 需要二次确认弹窗
7. **筛选逻辑**: 订单链作为整体展示
8. **分页处理**: ✅ **架构审查修正**: 改为一次性加载（前端虚拟滚动）
9. **数据格式**: 后端返回树形结构
10. **删除限制**: 终态订单可直接删除，OPEN 状态先取消再删除
11. **UI 层级**: 标准缩进（每层 24px）

---

## 🏗️ 架构设计（架构审查修正版）

### 核心架构变更

**变更 1: 分页逻辑修正** (🔴 架构审查发现问题 - 已修正)

原设计：分页仅针对根订单（ENTRY）  
**问题**: 分页会割裂订单链的完整性，用户无法看到已分页 ENTRY 订单新增的子订单

**修正方案**: 一次性加载 + 前端虚拟滚动
- 后端：返回完整订单树（支持时间范围过滤）
- 前端：使用虚拟滚动处理大数据量

**变更 2: 树形数据结构修正** (🟡 架构审查发现问题 - 已修正)

原设计：`OrderTreeNode.isExpanded` 由后端返回  
**问题**: `isExpanded` 是前端 UI 状态，不应由后端返回

**修正方案**:
```typescript
// 后端返回
interface OrderTreeNode {
  order: OrderResponseFull
  children: OrderTreeNode[]
  level: number
  has_children: boolean  // 用于懒加载指示
}

// 前端维护展开状态
const [expandedRowKeys, setExpandedRowKeys] = useState<string[]>([])
```

**变更 3: 批量删除事务完善** (🟡 架构审查发现问题 - 已修正)

原设计：缺少交易所 API 调用失败处理和审计日志

**修正方案**:
- 添加 `cancel_on_exchange` 参数控制是否调用交易所
- 返回详细的成功/失败列表
- 添加审计日志记录

---

### 数据流程图（修正版）

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Frontend      │     │   Backend API    │     │  OrderRepository │
│  Orders.tsx     │────▶│  GET /orders/tree│────▶│  get_order_tree()│
│  VirtualScroll  │◀────│  ?symbol&days=7  │◀────│                  │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │  SQLite Database │
                       │  orders table    │
                       │  parent_order_id │
                       └──────────────────┘
```

### 树形数据结构（修正版）

```typescript
// 后端返回
interface OrderTreeNode {
  order: OrderResponseFull          // 订单详情
  children: OrderTreeNode[]         // 子订单列表（TP1-5, SL）
  level: number                     // 层级深度（0=根节点，1=子订单）
  has_children: boolean             // 是否有子订单（用于 UI 展示）
}

// 前端维护展开状态（不在后端响应中）
interface OrderTreeNodeUI {
  ...OrderTreeNode
  isExpanded: boolean               // 前端本地维护
}
```

---

## 🔌 后端 API 契约

### 1. GET /api/v3/orders/tree (新增专用接口)

**用途**: 获取订单树形结构（一次性加载完整树）

**请求参数**:

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `symbol` | string | 否 | - | 币种对过滤 |
| `start_date` | string | 否 | - | 开始日期 (ISO 8601) |
| `end_date` | string | 否 | - | 结束日期 (ISO 8601) |
| `days` | int | 否 | 7 | 最近 N 天（与 start_date/end_date 互斥） |
| `limit` | int | 否 | 200 | 根订单数量上限（防止大数据量） |

**响应格式**:

```json
{
  "items": [
    {
      "order": {
        "order_id": "uuid-123",
        "symbol": "BTC/USDT:USDT",
        "order_role": "ENTRY",
        "status": "FILLED",
        "direction": "LONG",
        "quantity": "0.1",
        "filled_qty": "0.1",
        "price": "50000",
        "average_exec_price": "50000",
        "created_at": 1711785660000,
        "filled_at": 1711785660000
      },
      "children": [
        {
          "order": {
            "order_id": "uuid-124",
            "parent_order_id": "uuid-123",
            "order_role": "TP1",
            "status": "FILLED",
            ...
          },
          "children": [],
          "level": 1,
          "has_children": false
        },
        {
          "order": {
            "order_id": "uuid-125",
            "parent_order_id": "uuid-123",
            "order_role": "TP2",
            "status": "OPEN",
            ...
          },
          "children": [],
          "level": 1,
          "has_children": false
        }
      ],
      "level": 0,
      "has_children": true
    }
  ],
  "total": 50,
  "metadata": {
    "symbol_filter": "BTC/USDT:USDT",
    "days_filter": 7,
    "loaded_at": 1711785660000
  }
}
```

**性能建议**:
- 默认 `days=7`，限制加载最近 7 天的订单树
- 默认 `limit=200`，防止单次加载过多数据
- 前端使用虚拟滚动优化渲染性能

---

### 2. DELETE /api/v3/orders/batch (新增批量删除接口)

**用途**: 批量删除订单链（支持级联删除子订单）

**请求体**:
```json
{
  "order_ids": ["uuid-123", "uuid-124", "uuid-125"],
  "cancel_on_exchange": true,
  "audit_info": {
    "operator_id": "user-001",
    "ip_address": "192.168.1.1",
    "user_agent": "Mozilla/5.0..."
  }
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `order_ids` | string[] | 是 | - | 要删除的订单 ID 列表（上限 100） |
| `cancel_on_exchange` | boolean | 否 | `true` | 是否调用交易所取消接口 |
| `audit_info.operator_id` | string | 否 | - | 操作人 ID |
| `audit_info.ip_address` | string | 否 | - | 操作 IP |
| `audit_info.user_agent` | string | 否 | - | 用户代理 |

**响应**:
```json
{
  "deleted_count": 5,
  "cancelled_on_exchange": ["uuid-124", "uuid-125"],
  "failed_to_cancel": [
    {
      "order_id": "uuid-126",
      "reason": "交易所 API 超时"
    }
  ],
  "deleted_from_db": ["uuid-123", "uuid-124", "uuid-125", "uuid-126", "uuid-127"],
  "failed_to_delete": [],
  "audit_log_id": "audit-20260402-001"
}
```

**删除逻辑**:
1. 对于每个订单 ID，查询其完整订单链（包括所有子订单）
2. 收集所有需要删除的订单 ID
3. 对于状态为 `OPEN` 或 `PARTIALLY_FILLED` 的订单，调用交易所取消接口
4. 记录取消成功/失败的订单
5. 数据库事务删除所有订单记录
6. 记录审计日志
7. 返回详细结果

**错误处理**:

| 状态码 | 错误码 | 说明 |
|--------|--------|------|
| 400 | ORDER-001 | 订单 ID 列表为空 |
| 400 | ORDER-002 | 订单 ID 数量超限（>100） |
| 400 | ORDER-003 | 订单状态不允许删除 |
| 404 | ORDER-004 | 订单不存在 |
| 500 | ORDER-005 | 删除失败（数据库错误） |
| 502 | EXCHANGE-001 | 交易所 API 调用失败（非阻塞） |

---

## 🗃️ Repository 层契约

### OrderRepository 新增方法

```python
class OrderRepository:
    async def get_order_tree(
        self,
        symbol: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        days: Optional[int] = 7,
        limit: int = 200,
    ) -> Dict[str, Any]:
        """
        获取订单树形结构（一次性加载完整树）
        
        实现思路:
        1. 查询所有 ENTRY 订单（根节点）
        2. 批量查询这些 ENTRY 的子订单（通过 parent_order_id IN (...)）
        3. 在内存中组装树形结构
        
        返回:
        {
            "items": List[Dict[str, Any]],  # 树形结构列表
            "total": int,                    # 总根订单数
            "metadata": Dict[str, Any],      # 元数据
        }
        """

    async def get_order_chain(self, order_id: str) -> List[Order]:
        """
        获取完整订单链（包括父订单和所有子订单）
        
        返回:
        List[Order] - 父订单 + 所有子订单列表
        """

    async def delete_orders_batch(
        self,
        order_ids: List[str],
        cancel_on_exchange: bool = True,
        audit_info: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        批量删除订单（带事务保护）
        
        返回:
        {
            "deleted_count": int,
            "cancelled_on_exchange": List[str],
            "failed_to_cancel": List[Dict[str, str]],
            "deleted_from_db": List[str],
            "failed_to_delete": List[Dict[str, str]],
            "audit_log_id": str,
        }
        """
```

---

## 🎨 前端组件契约

### Orders.tsx 改造

**新增状态**:
```typescript
const [treeData, setTreeData] = useState<OrderTreeNode[]>([]);
const [expandedRowKeys, setExpandedRowKeys] = useState<string[]>([]);
const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([]);
const [isLoading, setIsLoading] = useState(false);
```

**API 调用**:
```typescript
// 获取订单树
const fetchOrderTree = async (filters: {
  symbol?: string;
  days?: number;
}) => {
  const response = await api.get('/api/v3/orders/tree', { params: filters });
  setTreeData(response.items);
};

// 批量删除
const handleBatchDelete = async (orderIds: string[]) => {
  const result = await api.post('/api/v3/orders/batch/delete', {
    order_ids: orderIds,
    cancel_on_exchange: true,
    audit_info: {
      operator_id: currentUser.id,
      ip_address: await getClientIP(),
    },
  });
  
  // 处理结果：显示成功/失败提示
  if (result.failed_to_cancel.length > 0 || result.failed_to_delete.length > 0) {
    message.warning('部分订单删除失败');
  } else {
    message.success('删除成功');
  }
  
  // 刷新列表
  fetchOrderTree(filters);
};
```

### OrderChainTreeTable 组件 Props

```typescript
interface OrderChainTreeTableProps {
  data: OrderTreeNode[];                    // 树形数据
  expandedRowKeys: string[];                // 展开的行 keys
  onExpand: (keys: string[]) => void;       // 展开/折叠回调
  selectedRowKeys: string[];                // 选中的行 keys
  onSelectChange: (keys: string[]) => void; // 选择变化回调
  onCancelOrder: (orderId: string, symbol: string) => Promise<void>;
  onDeleteChain: (orderIds: string[]) => Promise<void>;
  isLoading?: boolean;                      // 加载状态
}
```

### 批量删除确认弹窗

```typescript
interface DeleteChainConfirmModalProps {
  selectedCount: number;         // 选中的订单链数量
  totalChainCount: number;       // 预计删除的订单总数（包括子订单）
  openOrdersCount: number;       // 挂单中的订单数量（需要先取消）
  onConfirm: () => Promise<void>;
  onCancel: () => void;
}
```

**弹窗文案**:
```
即将删除 {selectedCount} 个订单链
（共 {totalChainCount} 个订单，包括子订单）

此操作将：
1. 取消 {openOrdersCount} 个挂单中的订单 (OPEN 状态)
2. 删除所有已终态的订单

此操作不可逆，是否继续？
```

---

## 📊 数据模型扩展

### OrderTreeNode (后端返回)

```python
class OrderTreeNode(BaseModel):
    order: OrderResponseFull
    children: List['OrderTreeNode'] = []
    level: int = 0
    has_children: bool = False
```

### OrderDeleteRequest (后端请求体)

```python
class OrderDeleteRequest(BaseModel):
    order_ids: List[str] = Field(..., max_items=100)
    cancel_on_exchange: bool = Field(default=True)
    audit_info: Optional[Dict[str, str]] = None
    
    @field_validator('order_ids')
    @classmethod
    def validate_order_ids(cls, v):
        if not v:
            raise ValueError('订单 ID 列表不能为空')
        return v
```

### OrderDeleteResponse (后端响应)

```python
class OrderDeleteResponse(BaseModel):
    deleted_count: int
    cancelled_on_exchange: List[str]
    failed_to_cancel: List[Dict[str, str]]
    deleted_from_db: List[str]
    failed_to_delete: List[Dict[str, str]]
    audit_log_id: Optional[str]
```

---

## ✅ 验收标准

### 功能验收

| ID | 验收项 | 期望结果 |
|----|--------|----------|
| F1 | 树形展示订单链 | ENTRY 订单显示为根节点，TP/SL 显示为子节点 |
| F2 | 展开/折叠交互 | 点击展开/折叠图标可显示/隐藏子订单 |
| F3 | 批量选择 | 可勾选多个订单链 |
| F4 | 批量删除 | 删除选中订单链，包括所有子订单 |
| F5 | 删除确认 | 显示确认弹窗，告知删除总数和 OPEN 订单数 |
| F6 | OPEN 状态处理 | 自动取消挂单后再删除 |
| F7 | 筛选器联动 | 筛选后订单链作为整体展示 |
| F8 | 一次性加载 | 默认加载最近 7 天完整订单树 |

### 性能验收

| ID | 验收项 | 期望结果 |
|----|--------|----------|
| P1 | 列表加载时间 | < 1s (100 条订单树) |
| P2 | 展开响应时间 | < 100ms (本地展开) |
| P3 | 批量删除时间 | < 3s (10 个订单链) |
| P4 | 前端渲染性能 | 虚拟滚动支持 500+ 节点流畅渲染 |

### 测试验收

| ID | 验收项 | 期望结果 |
|----|--------|----------|
| T1 | 单元测试覆盖 | > 85% |
| T2 | 集成测试 | 全部通过 |
| T3 | E2E 测试 | 全部通过 |

---

## 📝 架构审查问题解决追踪

| 问题 | 状态 | 解决方案 |
|------|------|----------|
| 分页逻辑缺陷 | ✅ 已解决 | 改为一次性加载 + 前端虚拟滚动 |
| 树形数据结构 | ✅ 已解决 | 移除 `isExpanded`，添加 `has_children` |
| 批量删除事务 | ✅ 已解决 | 添加 `cancel_on_exchange` 参数 + 审计日志 |

---

## 🔗 相关文档

- [Phase 6 v3 API 契约](docs/designs/phase6-v3-api-contract.md)
- [订单 Repository 实现](src/infrastructure/order_repository.py)
- [订单管理页面](gemimi-web-front/src/pages/Orders.tsx)
- [架构审查报告](docs/reviews/order-chain-arch-review.md)
