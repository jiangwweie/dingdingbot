# OrderRepository P1 方法测试修复详细方案

> **文档版本**: v1.0  
> **生成日期**: 2026-04-07  
> **阶段**: P1（重要查询方法）  
> **目标覆盖率**: 75%+  
> **预估工时**: 6.5 小时

---

## 一、P1 方法概述

### 1.1 方法清单（11 个）

| 优先级 | 方法名 | 风险等级 | 工时 | 方法类型 | 核心功能 |
|-------|--------|---------|-----|---------|---------|
| **P1-1** | `get_orders()` | 🟡 中 | 1.5h | 核心查询 | 分页 + 多条件过滤 |
| **P1-2** | `get_orders_by_signal_ids()` | 🟡 中 | 1h | 批量查询 | 多信号批量查询 |
| **P1-3** | `get_open_orders()` | 🟡 中 | 0.5h | 状态查询 | 获取未结订单 |
| **P1-4** | `mark_order_filled()` | 🟡 中 | 0.5h | 状态更新 | T4 专用成交标记 |
| **P1-5** | `get_orders_by_role()` | 🟡 中 | 0.5h | 角色查询 | 按订单角色过滤 |
| **P1-6** | `get_orders_by_symbol()` | 🟡 低 | 0.5h | 币种查询 | 按币种过滤 |
| **P1-7** | `get_by_status()` | 🟡 低 | 0.5h | 别名方法 | 状态过滤别名 |
| **P1-8** | `get_order_count()` | 🟡 低 | 0.5h | 计数方法 | 信号订单计数 |
| **P1-9** | `save_order()` | 🟡 低 | 0.5h | 别名方法 | save 别名验证 |
| **P1-10** | `get_order_detail()` | 🟡 低 | 0.5h | 别名方法 | get_order 别名 |
| **P1-11** | `get_by_signal_id()` | 🟡 低 | 0.5h | 别名方法 | get_orders_by_signal 别名 |

---

## 二、依赖关系分析

### 2.1 依赖关系图

```
                    ┌─────────────────────────────────────────────────────┐
                    │              前置依赖（P0 已测试）                    │
                    │  - initialize() - 数据库初始化                        │
                    │  - save() / save_batch() - 订单保存                   │
                    │  - get_order() - 单订单查询                           │
                    │  - get_orders_by_signal() - 信号订单查询              │
                    └─────────────────────────────────────────────────────┘
                                         │
                                         ▼
        ┌────────────────────────────────┼────────────────────────────────┐
        │                                │                                │
        ▼                                ▼                                ▼
┌───────────────────┐          ┌───────────────────┐          ┌───────────────────┐
│  Group A: 核心查询 │          │  Group B: 过滤查询 │          │  Group C: 别名方法 │
│  (可并行)          │          │  (可并行)          │          │  (可并行)          │
│                   │          │                   │          │                   │
│  - get_orders()   │          │  - get_open_orders()        │  - save_order()   │
│  - get_orders_by_ │          │  - get_orders_by_symbol()   │  - get_order_     │
│    signal_ids()   │          │  - get_orders_by_role()     │    detail()       │
│                   │          │  - get_by_status()          │  - get_by_signal_ │
│                   │          │                   │          │    id()           │
│                   │          │  - mark_order_    │          │  - get_order_     │
│                   │          │    filled()       │          │    count()        │
│                   │          │                   │          │                   │
│  工时：2.5h        │          │  工时：2.5h        │          │  工时：1.5h        │
└───────────────────┘          └───────────────────┘          └───────────────────┘
```

### 2.2 依赖矩阵

| 方法 | 依赖方法 | 依赖状态 |
|------|---------|---------|
| `get_orders()` | `save()`, `_row_to_order()` | ✅ P0 已测 |
| `get_orders_by_signal_ids()` | `save()`, `_row_to_order()` | ✅ P0 已测 |
| `get_open_orders()` | `save()`, `_row_to_order()` | ✅ P0 已测 |
| `mark_order_filled()` | `save()`, `get_order()` | ✅ P0 已测 |
| `get_orders_by_role()` | `save()`, `_row_to_order()` | ✅ P0 已测 |
| `get_orders_by_symbol()` | `save()`, `_row_to_order()` | ✅ P0 已测 |
| `get_by_status()` | `save()`, `_row_to_order()` | ✅ P0 已测 |
| `get_order_count()` | `save()` | ✅ P0 已测 |
| `save_order()` | `save()` | ✅ P0 已测 |
| `get_order_detail()` | `get_order()` | ✅ P0 已测 |
| `get_by_signal_id()` | `get_orders_by_signal()` | ✅ P0 已测 |

---

## 三、方法分组（3 组，可并行开发）

### 3.1 分组总览

| 组别 | 方法数 | 工时 | 负责人 | 开发周期 |
|-----|-------|-----|-------|---------|
| **Group A** - 核心查询 | 2 | 2.5h | 高级开发 A | Day 1 上午 |
| **Group B** - 过滤查询 | 5 | 2.5h | 中级开发 B | Day 1 下午 |
| **Group C** - 别名方法 | 4 | 1.5h | 初级开发 C | Day 2 上午 |

---

### 3.2 Group A: 核心查询（2.5h）

**方法**: `get_orders()`, `get_orders_by_signal_ids()`

**特点**: 复杂查询逻辑，涉及分页、多条件组合过滤

#### 3.2.1 `get_orders()` - 测试用例设计（1.5h）

| 用例 ID | 场景 | 测试要点 | 预期结果 |
|--------|------|---------|---------|
| **P1-001** | 无过滤条件查询 | 空参数调用，验证默认行为 | 返回所有订单，按 created_at 降序 |
| **P1-002** | symbol 过滤 | 单币种过滤 | 只返回指定币种订单 |
| **P1-003** | status 过滤 | 单状态过滤 | 只返回指定状态订单 |
| **P1-004** | order_role 过滤 | 单角色过滤 | 只返回指定角色订单 |
| **P1-005** | 多条件组合过滤 | symbol + status + order_role | 返回同时满足所有条件的订单 |
| **P1-006** | 分页测试 - 第一页 | limit=10, offset=0 | 返回前 10 条 |
| **P1-007** | 分页测试 - 第二页 | limit=10, offset=10 | 返回第 11-20 条 |
| **P1-008** | 分页边界 - 空结果 | 超出总记录数 | 返回空列表，total 正确 |
| **P1-009** | limit 边界值 | limit=1 | 只返回 1 条 |
| **P1-010** | 空数据库查询 | 无任何订单 | 返回空列表，total=0 |

**关键代码结构**:
```python
# get_orders() 返回结构
{
    'items': [Order, ...],  # 订单列表
    'total': int,           # 总记录数
    'limit': int,           # 请求的 limit
    'offset': int,          # 请求的 offset
}
```

#### 3.2.2 `get_orders_by_signal_ids()` - 测试用例设计（1h）

| 用例 ID | 场景 | 测试要点 | 预期结果 |
|--------|------|---------|---------|
| **P1-011** | 单信号查询 | 单个 signal_id | 返回该信号所有订单 |
| **P1-012** | 多信号批量查询 | 多个 signal_ids | 返回所有信号的订单 |
| **P1-013** | 带角色过滤 | signal_ids + order_role | 返回过滤后的订单 |
| **P1-014** | 分页测试 - page=1 | 第一页 | 返回前 page_size 条 |
| **P1-015** | 分页测试 - page=2 | 第二页 | 返回第二页数据 |
| **P1-016** | 空信号列表 | signal_ids=[] | 空列表或抛出异常 |
| **P1-017** | 不存在的信号 | signal_ids 不含有效数据 | 返回空列表 |

**关键代码结构**:
```python
# get_orders_by_signal_ids() 返回结构
{
    'orders': [Order, ...],  # 订单列表
    'total': int,            # 总记录数
    'page': int,             # 当前页码 (1-based)
    'page_size': int,        # 每页数量
}
```

---

### 3.3 Group B: 过滤查询（2.5h）

**方法**: `get_open_orders()`, `get_orders_by_symbol()`, `get_orders_by_role()`, `get_by_status()`, `mark_order_filled()`

**特点**: 单一维度过滤，逻辑相对简单

#### 3.3.1 `get_open_orders()` - 测试用例设计（0.5h）

| 用例 ID | 场景 | 测试要点 | 预期结果 |
|--------|------|---------|---------|
| **P1-018** | 无币种过滤 | 查询所有 OPEN 订单 | 返回 OPEN + PARTIALLY_FILLED |
| **P1-019** | 币种过滤 | 指定 symbol | 只返回该币种的 OPEN 订单 |
| **P1-020** | 多币种混合 | 多个币种订单 | 正确过滤 |
| **P1-021** | 无 OPEN 订单 | 全部为 FILLED/CANCELLED | 返回空列表 |

**关键逻辑**:
```python
# 状态条件：status IN ('OPEN', 'PARTIALLY_FILLED')
```

#### 3.3.2 `get_orders_by_symbol()` - 测试用例设计（0.5h）

| 用例 ID | 场景 | 测试要点 | 预期结果 |
|--------|------|---------|---------|
| **P1-022** | 单币种查询 | 指定 symbol | 返回该币种所有订单 |
| **P1-023** | limit 限制 | limit=5 | 最多返回 5 条 |
| **P1-024** | 不存在的币种 | symbol 无数据 | 返回空列表 |
| **P1-025** | 排序验证 | 多订单 | 按 created_at 降序 |

#### 3.3.3 `get_orders_by_role()` - 测试用例设计（0.5h）

| 用例 ID | 场景 | 测试要点 | 预期结果 |
|--------|------|---------|---------|
| **P1-026** | 单角色查询 | ENTRY 角色 | 返回所有 ENTRY 订单 |
| **P1-027** | 组合 signal_id 过滤 | role + signal_id | 精确过滤 |
| **P1-028** | 组合 symbol 过滤 | role + symbol | 精确过滤 |
| **P1-029** | 三重过滤 | role + signal_id + symbol | 精确过滤 |
| **P1-030** | 空结果 | 无匹配数据 | 返回空列表 |

#### 3.3.4 `get_by_status()` - 测试用例设计（0.5h）

| 用例 ID | 场景 | 测试要点 | 预期结果 |
|--------|------|---------|---------|
| **P1-031** | 单状态查询 | FILLED 状态 | 返回所有 FILLED 订单 |
| **P1-032** | 排序验证 | 多订单 | 按 created_at 降序 |
| **P1-033** | 空结果 | 无匹配状态 | 返回空列表 |

**注意**: 这是别名方法，验证与 `get_orders_by_status()` 行为一致

#### 3.3.5 `mark_order_filled()` - 测试用例设计（0.5h）

| 用例 ID | 场景 | 测试要点 | 预期结果 |
|--------|------|---------|---------|
| **P1-034** | 正常标记成交 | OPEN 订单 → FILLED | 状态变更，filled_at 设置 |
| **P1-035** | 验证 updated_at 更新 | 标记后检查 | updated_at 变更 |
| **P1-036** | 不存在的订单 | order_id 无效 | 不抛异常，但无影响 |

**关键逻辑**:
```python
# UPDATE orders SET status='FILLED', filled_at=?, updated_at=? WHERE id=?
```

---

### 3.4 Group C: 别名方法和辅助方法（1.5h）

**方法**: `save_order()`, `get_order_detail()`, `get_by_signal_id()`, `get_order_count()`

**特点**: 简单别名或委托方法，验证转发逻辑

#### 3.4.1 `save_order()` - 测试用例设计（0.5h）

| 用例 ID | 场景 | 测试要点 | 预期结果 |
|--------|------|---------|---------|
| **P1-037** | 保存新订单 | 验证委托给 save() | 订单成功保存 |
| **P1-038** | 更新已存在订单 | UPSERT 行为 | 订单成功更新 |

**验收标准**: 验证与 `save()` 行为完全一致

#### 3.4.2 `get_order_detail()` - 测试用例设计（0.5h）

| 用例 ID | 场景 | 测试要点 | 预期结果 |
|--------|------|---------|---------|
| **P1-039** | 查询存在订单 | 验证委托给 get_order() | 返回订单对象 |
| **P1-040** | 查询不存在订单 | order_id 无效 | 返回 None |

**验收标准**: 验证与 `get_order()` 行为完全一致

#### 3.4.3 `get_by_signal_id()` - 测试用例设计（0.5h）

| 用例 ID | 场景 | 测试要点 | 预期结果 |
|--------|------|---------|---------|
| **P1-041** | 查询存在信号 | 验证委托给 get_orders_by_signal() | 返回订单列表 |
| **P1-042** | 查询不存在信号 | signal_id 无效 | 返回空列表 |

**验收标准**: 验证与 `get_orders_by_signal()` 行为完全一致

#### 3.4.4 `get_order_count()` - 测试用例设计（已在 P0 部分覆盖，验证即可）

| 用例 ID | 场景 | 测试要点 | 预期结果 |
|--------|------|---------|---------|
| **P0-015** | 正常计数 | 5 个订单 | 返回 5 |
| **P0-016** | 空结果 | 无订单 | 返回 0 |

**状态**: ✅ 已有测试，无需新增

---

## 四、执行计划

### 4.1 时间安排

| 日期 | 时间段 | 任务 | 负责人 |
|-----|-------|------|-------|
| **Day 1** | 上午 (9:00-11:30) | Group A: 核心查询测试 | 高级开发 A |
| **Day 1** | 下午 (14:00-16:30) | Group B: 过滤查询测试 | 中级开发 B |
| **Day 2** | 上午 (9:00-10:30) | Group C: 别名方法测试 | 初级开发 C |
| **Day 2** | 下午 (14:00-15:00) | 回归测试 + 覆盖率检查 | 全体 |

### 4.2 里程碑

| 里程碑 | 验收条件 | 时间 |
|-------|---------|-----|
| M1: Group A 完成 | `get_orders()`, `get_orders_by_signal_ids()` 测试通过 | Day 1 11:30 |
| M2: Group B 完成 | 5 个过滤查询方法测试通过 | Day 1 16:30 |
| M3: Group C 完成 | 别名方法验证通过 | Day 2 10:30 |
| M4: P1 阶段完成 | 覆盖率 75%+，所有测试通过 | Day 2 15:00 |

---

## 五、验收标准

### 5.1 功能验收

- [ ] 所有 P1 方法单元测试覆盖率 100%
- [ ] 分页逻辑 100% 覆盖（边界值验证）
- [ ] 过滤条件组合测试 100% 覆盖
- [ ] 别名方法委托验证 100% 覆盖

### 5.2 质量验收

- [ ] 所有测试用例命名规范（P1-XXX）
- [ ] 测试代码通过 lint 检查
- [ ] 无重复测试逻辑
- [ ] 测试数据隔离（使用临时数据库）

### 5.3 覆盖率验收

| 指标 | 当前 | 目标 | 验收 |
|-----|------|------|------|
| 整体覆盖率 | 33% | 75%+ | □ |
| P1 方法覆盖率 | 0% | 100% | □ |
| 分支覆盖率 | - | 85%+ | □ |

---

## 六、测试夹具设计

### 6.1 核心夹具

```python
@pytest.fixture
def temp_db_path():
    """创建临时数据库文件"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest_asyncio.fixture
async def order_repository(temp_db_path):
    """创建 OrderRepository 实例"""
    from src.infrastructure.order_repository import OrderRepository
    repo = OrderRepository(db_path=temp_db_path)
    await repo.initialize()
    yield repo
    await repo.close()


@pytest.fixture
def sample_orders():
    """创建示例订单数据"""
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    return [
        Order(
            id=f"ord_p1_test_{i}",
            signal_id=f"sig_p1_{i % 3}",
            symbol=["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"][i % 3],
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=[OrderRole.ENTRY, OrderRole.TP1, OrderRole.SL][i % 3],
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('0'),
            status=[OrderStatus.OPEN, OrderStatus.FILLED, OrderStatus.CANCELLED][i % 3],
            created_at=current_time + i * 1000,
            updated_at=current_time + i * 1000,
            reduce_only=False,
        )
        for i in range(10)
    ]
```

---

## 七、风险与缓解

| 风险 | 影响 | 缓解措施 |
|-----|------|---------|
| 分页逻辑复杂 | 测试遗漏边界场景 | 使用参数化测试覆盖所有边界值 |
| 别名方法验证 | 可能忽略委托逻辑 | 明确验收标准：与源方法行为一致 |
| 时间依赖 | filled_at/updated_at 验证困难 | 使用 mock 时间或时间范围验证 |
| 并发问题 | 多条件组合测试复杂 | 按组并行开发，每日合并代码 |

---

## 八、输出物

### 8.1 测试文件

- `tests/unit/infrastructure/test_order_repository_unit.py` - 新增 P1 方法测试

### 8.2 测试报告

- 覆盖率报告（执行 `pytest --cov` 生成）
- 测试执行报告（CI/CD 自动收集）

---

## 九、附录：方法签名速查

### 9.1 `get_orders()`
```python
async def get_orders(
    self,
    symbol: Optional[str] = None,
    status: Optional[OrderStatus] = None,
    order_role: Optional[OrderRole] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]
```

### 9.2 `get_orders_by_signal_ids()`
```python
async def get_orders_by_signal_ids(
    self,
    signal_ids: List[str],
    page: int = 1,
    page_size: int = 20,
    order_role: Optional[str] = None,
) -> Dict[str, Any]
```

### 9.3 `get_open_orders()`
```python
async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]
```

### 9.4 `mark_order_filled()`
```python
async def mark_order_filled(self, order_id: str, filled_at: int) -> None
```

### 9.5 `get_orders_by_role()`
```python
async def get_orders_by_role(
    self,
    role: OrderRole,
    signal_id: Optional[str] = None,
    symbol: Optional[str] = None,
) -> List[Order]
```

### 9.6 `get_orders_by_symbol()`
```python
async def get_orders_by_symbol(self, symbol: str, limit: int = 100) -> List[Order]
```

### 9.7 `get_by_status()`
```python
async def get_by_status(self, status: str) -> List[Order]
```

### 9.8 `get_order_count()`
```python
async def get_order_count(self, signal_id: str) -> int
```

### 9.9 `save_order()`
```python
async def save_order(self, order: Order) -> None
```

### 9.10 `get_order_detail()`
```python
async def get_order_detail(self, order_id: str) -> Optional[Order]
```

### 9.11 `get_by_signal_id()`
```python
async def get_by_signal_id(self, signal_id: str) -> List[Order]
```

---

*文档生成时间：2026-04-07*  
*审查者：架构师 Agent*  
*下次审查：P1 测试完成后重新评估覆盖率*
