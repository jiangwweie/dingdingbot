# OrderRepository 未测试方法审查报告

> **审查日期**: 2026-04-07  
> **审查范围**: OrderRepository 28 个未测试方法  
> **审查者**: Code Reviewer  
> **总体评估**: 高风险

---

## 执行摘要

OrderRepository 当前测试覆盖率仅 **33%**（460 语句中 151 语句被覆盖），存在大量未测试的关键业务方法。这些未测试方法涉及：

1. **订单链管理** - 核心交易流程
2. **OCO 订单组** - 风险控制关键
3. **批量操作** - 事务完整性
4. **复杂查询** - 数据一致性

**风险评估**: 高风险 - 核心交易流程存在未测试代码，可能导致生产环境数据不一致或资金风险。

---

## 已测试方法确认

以下方法已有单元测试覆盖（✅）：

| 方法 | 测试用例 |
|------|----------|
| `save(order)` | UNIT-ORD-3-001 |
| `update_status(...)` | UNIT-ORD-3-002 |
| `delete_order(order_id, cascade)` | UNIT-ORD-3-003 |
| `clear_orders(signal_id, symbol)` | UNIT-ORD-3-004 |
| `set_exchange_gateway(gateway)` | UNIT-ORD-3-005 |
| `set_audit_logger(logger)` | UNIT-ORD-3-006 |
| `get_all_orders(limit)` | test_get_all_orders_with_limit |
| `get_orders_by_signal(signal_id)` | test_get_orders_by_signal_id |
| `get_orders_by_status(status, symbol)` | test_get_orders_by_status |

---

## 未测试方法分类与优先级

### P0 - 核心业务流程（必须测试）

> **理由**: 这些方法涉及订单链管理、对账、资金风险控制等核心业务，缺陷可能导致资金损失或数据不一致。

| 方法 | 风险等级 | 业务重要性 | 测试策略 | 预估工时 |
|------|----------|------------|----------|----------|
| `initialize()` | 🔴 高 | 数据库初始化，失败导致系统无法启动 | 集成测试（真实 SQLite） | 1h |
| `close()` | 🔴 高 | 连接关闭，泄露导致资源耗尽 | 集成测试 | 0.5h |
| `save_batch(orders)` | 🔴 高 | 批量建仓，事务失败导致部分成交 | 集成测试 + 事务边界 | 2h |
| `delete_orders_batch(order_ids, cancel_on_exchange, audit_info)` | 🔴 极高 | 批量删除+交易所取消+审计，级联逻辑复杂 | 集成测试 + Mock 交易所 | 3h |
| `get_order_chain(signal_id)` | 🔴 高 | 订单链展示，用于对账和监控 | 单元测试 | 1h |
| `get_order_chain_by_order_id(order_id)` | 🔴 高 | 从订单ID追溯完整链路 | 单元测试 | 1h |
| `get_order_tree(...)` | 🔴 高 | 订单管理级联展示，包含分页和子订单 | 集成测试 | 2h |
| `get_oco_group(oco_group_id)` | 🔴 极高 | OCO 风险控制，错误导致双单成交 | 单元测试 | 1h |
| `_get_all_related_order_ids(order_ids)` | 🔴 高 | 递归获取关联订单，级联删除依赖 | 单元测试 | 1h |
| `delete_orders_by_signal_id(signal_id, cascade)` | 🔴 高 | 信号级联清理，涉及父/子/OCO关系 | 集成测试 | 1.5h |

**P0 小计**: 10 个方法，预估 **14 小时**

### P1 - 重要查询方法（建议测试）

> **理由**: 这些方法支撑业务查询和监控功能，虽然不直接涉及资金操作，但数据准确性影响交易决策。

| 方法 | 风险等级 | 业务重要性 | 测试策略 | 预估工时 |
|------|----------|------------|----------|----------|
| `get_orders(...)` | 🟡 中 | 多条件分页查询，API 核心 | 单元测试 | 1.5h |
| `get_orders_by_signal_ids(...)` | 🟡 中 | 批量信号查询 | 单元测试 | 1h |
| `get_orders_by_symbol(symbol, limit)` | 🟡 低 | 币种查询 | 单元测试 | 0.5h |
| `get_open_orders(symbol)` | 🟡 中 | 未成交订单监控 | 单元测试 | 0.5h |
| `get_by_status(status)` | 🟡 低 | 按状态查询（别名方法） | 单元测试 | 0.5h |
| `get_orders_by_role(role, signal_id, symbol)` | 🟡 中 | 按角色查询 | 单元测试 | 0.5h |
| `get_by_signal_id(signal_id)` | 🟡 低 | 别名方法 | 单元测试 | 0.5h |
| `get_order_detail(order_id)` | 🟡 低 | 别名方法 | 单元测试 | 0.5h |
| `get_order_count(signal_id)` | 🟡 低 | 订单计数 | 单元测试 | 0.5h |
| `mark_order_filled(order_id, filled_at)` | 🟡 中 | T4专用成交标记 | 单元测试 | 0.5h |
| `save_order(order)` | 🟡 低 | save 的别名 | 单元测试 | 0.5h |

**P1 小计**: 11 个方法，预估 **6.5 小时**

### P2 - 辅助/内部方法（可选测试）

> **理由**: 这些方法主要是内部辅助方法，复杂度较低，或被其他方法间接测试。

| 方法 | 风险等级 | 测试策略 | 备注 |
|------|----------|----------|------|
| `_get_entry_orders(...)` | 🟢 低 | 延后测试 | 被 get_order_tree 调用，间接测试 |
| `_get_child_orders(parent_ids)` | 🟢 低 | 延后测试 | 被 get_order_tree 调用，间接测试 |
| `_order_to_response(order)` | 🟢 低 | 延后测试 | 纯数据转换，被查询方法间接测试 |
| `_row_to_order(row)` | 🟢 低 | 延后测试 | 被所有查询方法间接测试 |
| `_ensure_lock()` | 🟢 低 | 延后测试 | 并发场景已在 save/update 中间接测试 |
| `get_order(order_id)` | 🟢 低 | 延后测试 | 被 delete/update 间接测试 |

**P2 小计**: 6 个方法，建议延后或仅在被调用方测试时验证

---

## 高风险方法详细分析

### 🔴 极高风险

#### 1. `delete_orders_batch()`

**风险分析**:
- **事务复杂度**: 涉及 4 个步骤（收集关联订单 → 取消交易所订单 → 批量删除 → 审计日志）
- **级联递归**: 使用 `_get_all_related_order_ids()` 递归获取子/父订单
- **外部依赖**: 调用 ExchangeGateway.cancel_order() 和 OrderAuditLogger.log()
- **失败处理**: 需要验证交易所取消失败但 DB 删除成功的场景

**测试重点**:
```python
# 必须测试的场景
1. 正常批量删除（含子订单、OCO组）
2. 交易所取消失败但继续删除 DB
3. 部分成功场景（部分取消成功）
4. 事务回滚（DB 删除失败时）
5. 审计日志记录完整性
6. 空订单列表参数验证
7. 超过 100 个订单限制验证
```

#### 2. `get_oco_group()`

**风险分析**:
- **资金风险**: OCO 订单（One-Cancels-Other）用于止损止盈，错误查询可能导致双单同时成交
- **场景**: ENTRY 订单成交后，TP 和 SL 订单应该互斥，系统依赖此查询判断 OCO 状态

**测试重点**:
```python
# 必须测试的场景
1. 正常 OCO 组查询
2. OCO 组 ID 不存在
3. OCO 组包含部分已成交订单
4. 并发场景下 OCO 订单状态一致性
```

### 🔴 高风险

#### 3. `save_batch()`

**风险分析**:
- **事务边界**: 使用显式 BEGIN/COMMIT/ROLLBACK
- **分批风险**: 如果批量过大，可能部分失败
- **UPSERT 逻辑**: ON CONFLICT DO UPDATE 需要验证更新字段正确性

**测试重点**:
```python
# 必须测试的场景
1. 正常批量保存
2. 事务回滚（中间失败）
3. UPSERT 更新现有订单
4. Decimal 精度保持
5. NULL 字段处理
```

#### 4. `get_order_tree()`

**风险分析**:
- **复杂查询**: 分页 + 时间过滤 + 币种过滤 + 级联子订单
- **内存组装**: 数据库行转对象后在内存组装树形结构
- **性能**: 大数据量时可能内存溢出

**测试重点**:
```python
# 必须测试的场景
1. 正常树形结构返回
2. 分页边界（最后一页不满）
3. 时间范围过滤（start_date/end_date/days）
4. 空结果集处理
5. 大量子订单性能
```

---

## 分阶段测试计划

### 阶段 1: P0 核心方法（14 小时）

**目标**: 覆盖核心交易流程，消除资金风险

**执行顺序**（按依赖关系）:

```
Week 1:
  Day 1-2: initialize(), close(), save_batch()
  Day 3-4: get_order_chain(), get_order_chain_by_order_id(), get_oco_group()
  Day 5:   delete_orders_by_signal_id(), _get_all_related_order_ids()

Week 2:
  Day 1-2: get_order_tree()（最复杂，需要充分时间）
  Day 3-4: delete_orders_batch()（极高风险，需细致测试）
  Day 5:   回归测试 + 修复
```

**验收标准**:
- [ ] 所有 P0 方法有测试用例
- [ ] 事务边界测试通过
- [ ] 级联删除场景验证
- [ ] 覆盖率提升至 60%+

### 阶段 2: P1 重要查询（6.5 小时）

**目标**: 覆盖业务查询和监控功能

**执行顺序**:

```
Week 2 (续):
  Day 6:   get_orders(), get_orders_by_signal_ids()
  Day 7:   get_orders_by_symbol(), get_open_orders(), get_by_status()
  Day 8:   get_orders_by_role(), mark_order_filled()
  Day 9:   别名方法测试（get_by_signal_id, get_order_detail, save_order）
  Day 10:  get_order_count() + 回归测试
```

**验收标准**:
- [ ] 所有 P1 方法有测试用例
- [ ] 分页逻辑验证
- [ ] 过滤条件组合测试
- [ ] 覆盖率提升至 75%+

### 阶段 3: P2 辅助方法（可选，3 小时）

**目标**: 补充内部方法测试，或验证被间接覆盖

**执行顺序**:

```
Week 3 (可选):
  Day 1:   _row_to_order(), _order_to_response()
  Day 2:   _get_entry_orders(), _get_child_orders()
  Day 3:   _ensure_lock() 并发场景验证
```

**验收标准**:
- [ ] 或：确认被调用方测试间接覆盖
- [ ] 或：编写直接测试
- [ ] 覆盖率提升至 85%+

---

## 测试策略建议

### 1. 集成测试（推荐用于 P0）

**理由**: OrderRepository 与 SQLite 紧密耦合，Mock 数据库无法验证 SQL 正确性。

```python
# 使用临时数据库的集成测试
@pytest_asyncio.fixture
async def order_repository():
    fd, path = tempfile.mkstemp(suffix='.db')
    repo = OrderRepository(db_path=path)
    await repo.initialize()
    yield repo
    await repo.close()
    os.remove(path)
```

### 2. Mock 外部依赖

**ExchangeGateway** 和 **OrderAuditLogger** 需要 Mock:

```python
@pytest.fixture
def mock_exchange_gateway():
    gateway = MagicMock()
    gateway.cancel_order = AsyncMock(return_value=CancelResult(is_success=True))
    return gateway

@pytest.fixture
def mock_audit_logger():
    logger = MagicMock()
    logger.log = AsyncMock(return_value=None)
    return logger
```

### 3. 事务边界测试

```python
async def test_save_batch_transaction_rollback(order_repository):
    """验证事务失败时回滚"""
    # 准备：创建无效订单（触发 IntegrityError）
    orders = [valid_order, invalid_order]

    # 执行：期望抛出异常
    with pytest.raises(Exception):
        await order_repository.save_batch(orders)

    # 验证：valid_order 也未被保存（事务回滚）
    saved = await order_repository.get_order(valid_order.id)
    assert saved is None
```

### 4. 并发安全测试

```python
async def test_concurrent_delete_orders_batch(order_repository):
    """验证批量删除并发安全"""
    # 创建多个订单
    orders = [create_order() for _ in range(10)]

    # 并发执行两个批量删除
    await asyncio.gather(
        order_repository.delete_orders_batch([o.id for o in orders[:5]]),
        order_repository.delete_orders_batch([o.id for o in orders[5:]]),
    )

    # 验证：所有订单都被删除，无冲突
```

---

## 依赖关系图

```
                        ┌─────────────────┐
                        │   initialize    │  ← 所有测试前提
                        └────────┬────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
        ▼                        ▼                        ▼
┌───────────────┐      ┌─────────────────┐      ┌─────────────────┐
│   save_batch  │◄────►│   save (已测)   │      │ delete_orders_  │
└───────┬───────┘      └─────────────────┘      │   batch         │
        │                                       └────────┬────────┘
        │                                                │
        │                          ┌─────────────────────┘
        │                          │
        ▼                          ▼
┌───────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  get_order_   │      │ _get_all_related│◄────►│ delete_orders_  │
│  chain        │      │ _order_ids      │      │ by_signal_id    │
└───────┬───────┘      └─────────────────┘      └─────────────────┘
        │
        │         ┌─────────────────┐
        └────────►│ get_order_tree  │◄──── _get_entry_orders (P2)
                  └─────────────────┘◄──── _get_child_orders (P2)

┌─────────────────┐
│ get_oco_group   │  ← 独立，但高风险
└─────────────────┘
```

---

## 结论与建议

### 总体结论

OrderRepository 测试覆盖不足，**存在 28 个未测试方法**，其中 **10 个 P0 核心方法** 涉及资金风险，必须优先测试。

### 关键风险点

1. **delete_orders_batch()** - 级联删除逻辑复杂，涉及交易所调用和审计日志，风险最高
2. **get_oco_group()** - OCO 订单是风险控制核心，错误可能导致双单成交
3. **save_batch()** - 事务边界需要验证，失败可能导致部分成交
4. **订单链查询** - get_order_tree, get_order_chain 用于对账，数据准确性关键

### 行动建议

**立即执行**（本周）:
- [ ] 创建 P0 方法测试用例（10 个方法）
- [ ] 优先完成 delete_orders_batch 和 get_oco_group 测试
- [ ] 修复测试中发现的问题

**短期执行**（下周）:
- [ ] 完成 P1 方法测试（11 个方法）
- [ ] 达成 75% 覆盖率目标
- [ ] 代码审查和合并

**可选执行**（后续迭代）:
- [ ] 补充 P2 方法测试或验证间接覆盖
- [ ] 性能测试（get_order_tree 大数据量）
- [ ] 并发压力测试

### 测试工时估算

| 阶段 | 方法数 | 预估工时 | 优先级 |
|------|--------|----------|--------|
| P0 核心 | 10 | 14 小时 | 立即 |
| P1 重要 | 11 | 6.5 小时 | 高 |
| P2 辅助 | 6 | 3 小时 | 中 |
| **总计** | **27** | **23.5 小时** | - |

> 注: `get_order(order_id)` 和 `get_by_signal_id(signal_id)` 已在其他测试中间接覆盖，未计入未测试清单。

---

## 附录：方法清单完整版

### 已测试方法（✅）
1. `save(order)` - UNIT-ORD-3-001
2. `update_status(...)` - UNIT-ORD-3-002
3. `delete_order(order_id, cascade)` - UNIT-ORD-3-003
4. `clear_orders(signal_id, symbol)` - UNIT-ORD-3-004
5. `set_exchange_gateway(gateway)` - UNIT-ORD-3-005
6. `set_audit_logger(logger)` - UNIT-ORD-3-006
7. `get_all_orders(limit)` - test_get_all_orders_with_limit
8. `get_orders_by_signal(signal_id)` - test_get_orders_by_signal_id
9. `get_orders_by_status(status, symbol)` - test_get_orders_by_status

### 未测试方法（28 个）

#### P0 - 核心业务流程（10 个）
| # | 方法 | 行号 | 复杂度 |
|---|------|------|--------|
| 1 | `initialize()` | 92 | 中 |
| 2 | `close()` | 174 | 低 |
| 3 | `save_batch(orders)` | 244 | 高 |
| 4 | `delete_orders_batch(...)` | 1165 | 极高 |
| 5 | `get_order_chain(signal_id)` | 734 | 中 |
| 6 | `get_order_chain_by_order_id(order_id)` | 769 | 高 |
| 7 | `get_order_tree(...)` | 873 | 极高 |
| 8 | `get_oco_group(oco_group_id)` | 850 | 中 |
| 9 | `_get_all_related_order_ids(order_ids)` | 1121 | 中 |
| 10 | `delete_orders_by_signal_id(signal_id, cascade)` | 1480 | 高 |

#### P1 - 重要查询方法（11 个）
| # | 方法 | 行号 | 复杂度 |
|---|------|------|--------|
| 11 | `get_orders(...)` | 464 | 中 |
| 12 | `get_orders_by_signal_ids(...)` | 539 | 中 |
| 13 | `get_orders_by_symbol(symbol, limit)` | 605 | 低 |
| 14 | `get_open_orders(symbol)` | 653 | 低 |
| 15 | `get_by_status(status)` | 678 | 低 |
| 16 | `get_orders_by_role(role, ...)` | 698 | 低 |
| 17 | `get_by_signal_id(signal_id)` | 452 | 低（别名） |
| 18 | `get_order_detail(order_id)` | 395 | 低（别名） |
| 19 | `get_order_count(signal_id)` | 1328 | 低 |
| 20 | `mark_order_filled(order_id, filled_at)` | 360 | 低 |
| 21 | `save_order(order)` | 386 | 低（别名） |

#### P2 - 辅助/内部方法（7 个）
| # | 方法 | 行号 | 复杂度 |
|---|------|------|--------|
| 22 | `_get_entry_orders(...)` | 973 | 中 |
| 23 | `_get_child_orders(parent_ids)` | 1046 | 中 |
| 24 | `_order_to_response(order)` | 1085 | 低 |
| 25 | `_row_to_order(row)` | 1351 | 低 |
| 26 | `_ensure_lock()` | 71 | 低 |
| 27 | `get_order(order_id)` | 410 | 低（被间接测试） |
| 28 | `get_order(order_id)` | 452 | 低（别名，被间接测试） |

---

*报告生成时间: 2026-04-07*  
*审查工具: Code Reviewer Agent*  
*下次审查建议: P0 测试完成后*
