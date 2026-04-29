# OrderRepository 测试覆盖率修复建议

> **文档版本**: v1.0  
> **生成日期**: 2026-04-07  
> **基于报告**: `docs/reviews/order-repository-test-coverage-review.md`  
> **当前覆盖率**: 33% (460 语句中 151 语句)  
> **目标覆盖率**: 75%+ (P1 阶段完成) / 85%+ (P2 阶段完成)

---

## 一、关键问题总结

### 1.1 风险概览

OrderRepository 存在 **28 个未测试方法**，其中包含 **2 个极高风险方法**，可能导致：

| 风险类型 | 影响 | 可能后果 |
|---------|------|---------|
| 资金风险 | OCO 组查询错误 | 止损止盈双单同时成交 |
| 数据风险 | 批量删除级联逻辑错误 | 部分删除导致数据不一致 |
| 系统风险 | 初始化/关闭失败 | 数据库连接泄露，系统无法启动 |
| 事务风险 | 批量操作回滚失败 | 部分订单入库，部分失败 |

### 1.2 极高风险方法（2 个）

#### 🔴 `delete_orders_batch()` - 风险等级：极高

**问题本质**: 该方法涉及 4 步复杂操作，任何一步失败都可能导致数据不一致。

```
Step 1: 递归收集关联订单 ID（_get_all_related_order_ids）
Step 2: 获取订单详情
Step 3: 调用交易所取消接口（ExchangeGateway.cancel_order）
Step 4: 批量删除数据库记录（事务保护）
Step 5: 记录审计日志（OrderAuditLogger）
```

**测试盲区**:
- ❌ 交易所取消失败但 DB 删除成功的场景
- ❌ 部分订单取消成功、部分失败的场景
- ❌ 事务回滚触发条件验证
- ❌ 并发删除同一订单链的冲突处理

**修复优先级**: **P0-1（最高）**

---

#### 🔴 `get_oco_group()` - 风险等级：极高

**问题本质**: OCO（One-Cancels-Other）订单是风险控制的核心，查询错误可能导致双单成交。

**业务场景**:
```
ENTRY 订单成交后 → 生成 TP 止盈订单 + SL 止损订单
TP 和 SL 属于同一 OCO 组 → 任一成交后，另一个必须自动取消
系统依赖 get_oco_group() 查询 OCO 状态 → 判断是否需要取消
```

**测试盲区**:
- ❌ OCO 组 ID 不存在的边界处理
- ❌ OCO 组内部分订单已成交的场景
- ❌ 并发查询下 OCO 订单状态一致性

**修复优先级**: **P0-2（最高）**

---

## 二、修复优先级列表

### 2.1 P0 核心方法（必须测试，14 小时）

> **标准**: 涉及资金安全、事务完整性、系统稳定性的方法

| 优先级 | 方法 | 风险等级 | 工时 | 测试类型 | 关键测试场景 |
|-------|------|---------|-----|---------|-------------|
| **P0-1** | `delete_orders_batch()` | 🔴 极高 | 3h | 集成测试 | 交易所取消失败、事务回滚、级联删除、审计日志 |
| **P0-2** | `get_oco_group()` | 🔴 极高 | 1h | 单元测试 | OCO 组不存在、部分成交、并发查询 |
| **P0-3** | `save_batch()` | 🔴 高 | 2h | 集成测试 | 事务回滚、UPSERT 更新、Decimal 精度 |
| **P0-4** | `initialize()` | 🔴 高 | 1h | 集成测试 | 重复初始化幂等性、目录创建、索引创建 |
| **P0-5** | `close()` | 🔴 高 | 0.5h | 集成测试 | 连接关闭、重复关闭安全 |
| **P0-6** | `get_order_chain()` | 🔴 高 | 1h | 单元测试 | 完整订单链、空结果、信号关联 |
| **P0-7** | `get_order_chain_by_order_id()` | 🔴 高 | 1h | 单元测试 | 从子订单追溯、从父订单追溯、订单不存在 |
| **P0-8** | `get_order_tree()` | 🔴 高 | 2h | 集成测试 | 分页边界、时间过滤、树形组装 |
| **P0-9** | `_get_all_related_order_ids()` | 🔴 高 | 1h | 单元测试 | 递归子订单、递归父订单、循环引用防护 |
| **P0-10** | `delete_orders_by_signal_id()` | 🔴 高 | 1.5h | 集成测试 | 级联删除、非级联、OCO 组清理 |

**P0 阶段验收标准**:
- [ ] 所有 P0 方法单元测试覆盖率 100%
- [ ] 事务边界测试通过（回滚场景验证）
- [ ] 级联删除场景 100% 覆盖
- [ ] 整体覆盖率提升至 **60%+**

---

### 2.2 P1 重要查询（建议测试，6.5 小时）

> **标准**: 支撑业务查询和监控功能，数据准确性影响交易决策

| 优先级 | 方法 | 风险等级 | 工时 | 测试类型 | 关键测试场景 |
|-------|------|---------|-----|---------|-------------|
| **P1-1** | `get_orders()` | 🟡 中 | 1.5h | 单元测试 | 分页、多条件组合过滤、空结果 |
| **P1-2** | `get_orders_by_signal_ids()` | 🟡 中 | 1h | 单元测试 | 批量信号查询、分页、角色过滤 |
| **P1-3** | `get_open_orders()` | 🟡 中 | 0.5h | 单元测试 | 只返回 OPEN 状态、多币种 |
| **P1-4** | `mark_order_filled()` | 🟡 中 | 0.5h | 单元测试 | T4 专用成交标记、状态变更 |
| **P1-5** | `get_orders_by_role()` | 🟡 中 | 0.5h | 单元测试 | 按角色查询、组合信号过滤 |
| **P1-6** | `get_orders_by_symbol()` | 🟡 低 | 0.5h | 单元测试 | 币种过滤、limit 限制 |
| **P1-7** | `get_by_status()` | 🟡 低 | 0.5h | 单元测试 | 状态过滤（别名方法） |
| **P1-8** | `get_order_count()` | 🟡 低 | 0.5h | 单元测试 | 信号订单计数 |
| **P1-9** | `save_order()` | 🟡 低 | 0.5h | 单元测试 | save 别名验证 |
| **P1-10** | `get_order_detail()` | 🟡 低 | 0.5h | 单元测试 | get_order 别名验证 |
| **P1-11** | `get_by_signal_id()` | 🟡 低 | 0.5h | 单元测试 | get_orders_by_signal 别名验证 |

**P1 阶段验收标准**:
- [ ] 所有 P1 方法单元测试覆盖率 100%
- [ ] 分页逻辑 100% 覆盖（边界值）
- [ ] 过滤条件组合测试
- [ ] 整体覆盖率提升至 **75%+**

---

### 2.3 P2 辅助方法（可选测试，3 小时）

> **标准**: 内部辅助方法，复杂度低，可被其他方法间接测试

| 优先级 | 方法 | 建议 | 理由 |
|-------|------|-----|------|
| **P2-1** | `_get_entry_orders()` | 延后 | 被 get_order_tree 间接测试 |
| **P2-2** | `_get_child_orders()` | 延后 | 被 get_order_tree 间接测试 |
| **P2-3** | `_order_to_response()` | 延后 | 被所有查询方法间接测试 |
| **P2-4** | `_row_to_order()` | 延后 | 被所有查询方法间接测试 |
| **P2-5** | `_ensure_lock()` | 延后 | 并发场景已在其他方法中间接测试 |
| **P2-6** | `get_order()` | 已覆盖 | 被 delete/update 方法间接测试 |

**P2 阶段验收标准**:
- [ ] 确认被调用方测试间接覆盖
- [ ] 或：编写直接单元测试
- [ ] 整体覆盖率提升至 **85%+**

---

## 三、测试策略详述

### 3.1 集成测试（推荐用于 P0）

**理由**: OrderRepository 与 SQLite 紧密耦合，Mock 数据库无法验证 SQL 正确性。

**推荐夹具设计**:

```python
@pytest_asyncio.fixture
async def order_repository():
    """创建带临时数据库的 OrderRepository"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    
    repo = OrderRepository(db_path=path)
    await repo.initialize()
    yield repo
    
    await repo.close()
    if os.path.exists(path):
        os.remove(path)
```

**外部依赖 Mock**:

```python
@pytest.fixture
def mock_exchange_gateway():
    """Mock ExchangeGateway"""
    gateway = MagicMock()
    gateway.cancel_order = AsyncMock(return_value=CancelResult(is_success=True))
    return gateway

@pytest.fixture
def mock_audit_logger():
    """Mock OrderAuditLogger"""
    logger = MagicMock()
    logger.log = AsyncMock(return_value=None)
    return logger
```

---

### 3.2 极高风险方法测试设计

#### 3.2.1 `delete_orders_batch()` 测试用例

```python
class TestDeleteOrdersBatch:
    
    async def test_normal_batch_delete(self, order_repository):
        """正常批量删除场景"""
        # 准备：创建 3 个订单（含子订单）
        # 执行：delete_orders_batch([...], cancel_on_exchange=False)
        # 验证：所有订单已删除、审计日志已创建
        
    async def test_exchange_cancel_failure(self, order_repository, mock_exchange_gateway):
        """交易所取消失败但继续删除 DB"""
        # 准备：Mock cancel_order 抛出异常
        mock_exchange_gateway.cancel_order.side_effect = Exception("API Error")
        # 执行：批量删除
        # 验证：failed_to_cancel 有记录、deleted_from_db 完整
        
    async def test_partial_success_scenario(self, order_repository):
        """部分订单取消成功、部分失败"""
        # 准备：2 个 OPEN 订单，1 个 FILLED 订单
        # 执行：批量删除
        # 验证：cancelled_on_exchange 只有 OPEN 订单
        
    async def test_transaction_rollback(self, order_repository):
        """事务回滚场景（DB 删除失败）"""
        # 准备：创建订单后破坏数据库状态
        # 执行：批量删除
        # 验证：抛出异常、订单未被部分删除
        
    async def test_cascade_delete_children(self, order_repository):
        """级联删除子订单验证"""
        # 准备：ENTRY + TP1 + SL 订单链
        # 执行：只删除 ENTRY 订单 ID
        # 验证：所有 3 个订单都被删除
        
    async def test_empty_list_validation(self, order_repository):
        """空订单列表参数验证"""
        # 执行：delete_orders_batch([])
        # 验证：抛出 ValueError("订单 ID 列表不能为空")
        
    async def test_exceeds_limit_validation(self, order_repository):
        """超过 100 个订单限制验证"""
        # 执行：delete_orders_batch([f"ord_{i}" for i in range(101)])
        # 验证：抛出 ValueError("批量删除最多支持 100 个订单")
        
    async def test_audit_log_creation(self, order_repository):
        """审计日志创建验证"""
        # 准备：审计信息 audit_info
        # 执行：delete_orders_batch([...], audit_info={...})
        # 验证：result["audit_log_id"] 存在
```

#### 3.2.2 `get_oco_group()` 测试用例

```python
class TestGetOcoGroup:
    
    async def test_normal_oco_group_query(self, order_repository):
        """正常 OCO 组查询"""
        # 准备：创建 TP + SL 订单（同 oco_group_id）
        # 执行：get_oco_group("oco_sig_001")
        # 验证：返回 2 个订单、OCO 组 ID 正确
        
    async def test_oco_group_not_found(self, order_repository):
        """OCO 组 ID 不存在"""
        # 执行：get_oco_group("oco_not_exists")
        # 验证：返回空列表 []
        
    async def test_oco_group_partial_filled(self, order_repository):
        """OCO 组包含部分已成交订单"""
        # 准备：TP 订单 FILLED，SL 订单 OPEN
        # 执行：get_oco_group("oco_sig_001")
        # 验证：返回 2 个订单（含已成交的）
        
    async def test_oco_group_concurrent_query(self, order_repository):
        """并发场景下 OCO 订单状态一致性"""
        # 准备：创建 OCO 组
        # 执行：并发调用 get_oco_group 10 次
        # 验证：所有返回结果一致
```

---

### 3.3 事务边界测试

```python
async def test_save_batch_transaction_rollback(order_repository):
    """验证事务失败时回滚"""
    # 准备：创建有效订单 + 无效订单（触发 IntegrityError）
    valid_order = create_valid_order("ord_valid")
    invalid_order = create_invalid_order("ord_invalid")  # 缺少必填字段
    
    # 执行：期望抛出异常
    with pytest.raises(Exception):
        await order_repository.save_batch([valid_order, invalid_order])
    
    # 验证：valid_order 也未被保存（事务回滚）
    saved = await order_repository.get_order("ord_valid")
    assert saved is None
```

---

### 3.4 并发安全测试

```python
async def test_concurrent_delete_orders_batch(order_repository):
    """验证批量删除并发安全"""
    # 准备：创建 10 个订单
    orders = [create_order(f"ord_{i}") for i in range(10)]
    await order_repository.save_batch(orders)
    
    # 执行：并发执行两个批量删除
    await asyncio.gather(
        order_repository.delete_orders_batch(
            [o.id for o in orders[:5]], 
            cancel_on_exchange=False
        ),
        order_repository.delete_orders_batch(
            [o.id for o in orders[5:]], 
            cancel_on_exchange=False
        ),
    )
    
    # 验证：所有订单都被删除，无冲突
    remaining = await order_repository.get_all_orders()
    assert len(remaining) == 0
```

---

## 四、执行计划

### 4.1 阶段 1: P0 核心方法（14 小时）

**目标**: 覆盖核心交易流程，消除资金风险

**执行顺序（按依赖关系）**:

| 日期 | 任务 | 方法 | 验收标准 |
|-----|------|------|---------|
| **Day 1** | 基础设施 + 初始化 | `initialize()`, `close()`, `save_batch()` | 3 个方法测试通过 |
| **Day 2** | 订单链查询 | `get_order_chain()`, `get_order_chain_by_order_id()` | 2 个方法测试通过 |
| **Day 3** | OCO 风险控制 | `get_oco_group()` | 1 个方法测试通过 + 并发测试 |
| **Day 4** | 级联删除 | `_get_all_related_order_ids()`, `delete_orders_by_signal_id()` | 2 个方法测试通过 |
| **Day 5** | 批量删除（极高风险） | `delete_orders_batch()` | 1 个方法测试通过 + 8 个场景验证 |
| **Day 6** | 订单树查询 | `get_order_tree()` | 1 个方法测试通过 + 分页测试 |
| **Day 7** | 回归测试 + 修复 | 所有 P0 方法 | 覆盖率 60%+，所有测试通过 |

---

### 4.2 阶段 2: P1 重要查询（6.5 小时）

**目标**: 覆盖业务查询和监控功能

**执行顺序**:

| 日期 | 任务 | 方法 |
|-----|------|------|
| **Day 8** | 核心查询 | `get_orders()`, `get_orders_by_signal_ids()` |
| **Day 9** | 状态查询 | `get_orders_by_symbol()`, `get_open_orders()`, `get_by_status()` |
| **Day 10** | 角色查询 + 更新 | `get_orders_by_role()`, `mark_order_filled()` |
| **Day 11** | 别名方法 | `get_by_signal_id()`, `get_order_detail()`, `save_order()`, `get_order_count()` |
| **Day 12** | 回归测试 | 所有 P1 方法 + 覆盖率提升至 75%+ |

---

### 4.3 阶段 3: P2 辅助方法（可选，3 小时）

**目标**: 补充内部方法测试，或验证被间接覆盖

| 日期 | 任务 | 方法 |
|-----|------|------|
| **Day 13** | 内部方法 | `_row_to_order()`, `_order_to_response()` |
| **Day 14** | 树形辅助 | `_get_entry_orders()`, `_get_child_orders()` |
| **Day 15** | 并发锁 | `_ensure_lock()` 并发场景验证 |

---

## 五、团队分工建议

### 5.1 人员配置（推荐 3 人小组）

| 角色 | 人员 | 职责 | 负责方法 |
|-----|------|-----|---------|
| **高级开发 A** | 后端资深 | P0 极高风险方法 | `delete_orders_batch()`, `get_oco_group()`, `save_batch()` |
| **中级开发 B** | 后端开发 | P0 核心方法 + P1 查询 | `get_order_chain*()`, `get_order_tree()`, `get_orders*()` |
| **初级开发 C** | 测试开发 | P0 基础设施 + P2 辅助 | `initialize()`, `close()`, 别名方法验证、覆盖率报告 |

### 5.2 分工原则

1. **风险匹配**: 极高风险方法由资深开发负责
2. **并行开发**: 3 人并行开发，每日合并代码
3. **代码审查**: 每段测试代码需经另一人审查

### 5.3 每日站会检查点

| 时间 | 检查内容 |
|-----|---------|
| Day 1 晚 | 初始化测试完成、save_batch 事务测试通过 |
| Day 3 晚 | OCO 组测试通过、订单链查询测试通过 |
| Day 5 晚 | delete_orders_batch 所有场景验证通过 |
| Day 7 晚 | P0 阶段完成，覆盖率 60%+ |
| Day 12 晚 | P1 阶段完成，覆盖率 75%+ |

---

## 六、工时估算汇总

| 阶段 | 方法数 | 预估工时 | 优先级 | 建议执行周期 |
|-----|-------|---------|-------|-------------|
| **P0 核心** | 10 | 14 小时 | 立即 | Week 1 |
| **P1 重要** | 11 | 6.5 小时 | 高 | Week 2 |
| **P2 辅助** | 6 | 3 小时 | 中 | Week 3 (可选) |
| **总计** | 27 | 23.5 小时 | - | 3 周 |

**注**: 
- `get_order(order_id)` 和 `get_by_signal_id(signal_id)` 已在其他测试中间接覆盖，未计入未测试清单
- 工时包含测试编写、执行、修复和代码审查时间

---

## 七、行动建议（给 PM）

### 7.1 立即行动（本周）

1. **分配负责人**: 指定 1 名资深开发负责 P0 极高风险方法
2. **创建任务**: 在项目管理工具中创建 10 个 P0 测试任务
3. **设置检查点**: Day 3 和 Day 5 设置里程碑检查点

### 7.2 短期行动（下周）

1. **启动 P1 阶段**: P0 完成后立即启动
2. **覆盖率监控**: 每日报告覆盖率进度
3. **代码审查**: 安排专人审查测试代码质量

### 7.3 长期建议

1. **测试规范**: 建立新增方法必须附带测试的规范
2. **CI 集成**: 在 CI 流水线中设置覆盖率门槛（75%）
3. **定期审查**: 每季度审查一次测试覆盖率

---

## 八、依赖关系图

```
                        ┌─────────────────┐
                        │   initialize    │  ← 所有测试前提 (P0-4)
                        └────────┬────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
        ▼                        ▼                        ▼
┌───────────────┐      ┌─────────────────┐      ┌─────────────────┐
│   save_batch  │◄────►│   save (已测)   │      │ delete_orders_  │
│   (P0-3)      │      │                 │      │ batch (P0-1)    │
└───────┬───────┘      └─────────────────┘      └────────┬────────┘
        │                                                │
        │                          ┌─────────────────────┘
        │                          │
        ▼                          ▼
┌───────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  get_order_   │      │ _get_all_related│◄────►│ delete_orders_  │
│  chain        │      │ _order_ids      │      │ by_signal_id    │
│  (P0-6)       │      │ (P0-9)          │      │ (P0-10)         │
└───────┬───────┘      └─────────────────┘      └─────────────────┘
        │
        │         ┌─────────────────┐
        └────────►│ get_order_tree  │◄──── _get_entry_orders (P2)
                  │ (P0-8)          │◄──── _get_child_orders (P2)
                  └─────────────────┘

┌─────────────────┐
│ get_oco_group   │  ← 独立，但高风险 (P0-2)
│ (P0-2)          │
└─────────────────┘
```

---

*文档生成时间：2026-04-07*  
*审查者：Code Reviewer Agent*  
*下次审查建议：P0 测试完成后重新评估覆盖率*
