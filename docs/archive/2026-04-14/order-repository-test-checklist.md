# OrderRepository 测试质量检查清单

> **文档目的**: 验证 OrderRepository 测试覆盖完整性和质量
> **创建日期**: 2026-04-07
> **QA 负责人**: QA Tester
> **验收标准**: P0 方法 100% 覆盖，P1 方法 80% 覆盖

---

## 📊 测试概览

| 文件路径 | 测试类型 | 用例数量 | 状态 |
|----------|----------|----------|------|
| `tests/unit/infrastructure/test_order_repository_unit.py` | 单元测试 | 12 | ✅ 已完成 |
| `tests/unit/test_order_repository.py` | 单元测试 | 24 | ✅ 已完成 |
| `tests/integration/test_order_repository_queries.py` | 集成测试 | 4 | ✅ 已完成 |

---

## 🔴 P0 极高风险方法测试检查

### 1. `save(order: Order)` - 保存订单

| 测试场景 | 测试用例 | 覆盖状态 | 备注 |
|----------|----------|----------|------|
| 基础保存功能 | `test_save_order` | ✅ 已覆盖 | UNIT-ORD-3-001 |
| 可选字段为 None | `test_save_order_with_null_values` | ✅ 已覆盖 | UNIT-ORD-3-007 |
| 批量保存 | `test_order_repository_save_batch` | ✅ 已覆盖 | UT-P5-011-003 |
| 更新已存在订单 (UPSERT) | ❌ 缺失 | 🔴 待补充 | 需要测试 ON CONFLICT 逻辑 |
| filled_at 字段保留 (COALESCE) | `test_order_repository_save_order_with_filled_at` | ✅ 已覆盖 | T4-001 |

**边界条件检查**:
- [x] 空值处理 (price=None, average_exec_price=None)
- [x] 必填字段缺失 (signal_id, symbol, direction 等)
- [ ] 极大值测试 (Decimal 超大数值)
- [ ] 特殊字符测试 (symbol 包含特殊字符)

### 2. `update_status()` - 更新订单状态

| 测试场景 | 测试用例 | 覆盖状态 | 备注 |
|----------|----------|----------|------|
| 基础状态更新 | `test_update_order_status` | ✅ 已覆盖 | UNIT-ORD-3-002 |
| 更新 filled_qty | `test_update_order_status` | ✅ 已覆盖 | 部分覆盖 |
| 更新 average_exec_price | `test_update_order_status` | ✅ 已覆盖 | 部分覆盖 |
| 更新 filled_at | ❌ 缺失 | 🔴 待补充 | 参数存在但未测试 |
| 更新 exchange_order_id | ❌ 缺失 | 🔴 待补充 | 参数存在但未测试 |
| 更新 exit_reason | ❌ 缺失 | 🔴 待补充 | 参数存在但未测试 |
| 并发更新 | `test_update_order_concurrent` | ✅ 已覆盖 | UNIT-ORD-3-008 |

**边界条件检查**:
- [ ] 更新不存在的订单 ID
- [ ] 状态回退测试 (FILLED → OPEN)
- [x] 并发更新冲突

### 3. `delete_orders_batch()` - 批量删除订单

| 测试场景 | 测试用例 | 覆盖状态 | 备注 |
|----------|----------|----------|------|
| 空列表验证 | `test_delete_orders_batch_empty_list` | ✅ 已覆盖 | ORD-6 |
| 超过 100 个订单验证 | `test_delete_orders_batch_exceeds_limit` | ✅ 已覆盖 | ORD-6 |
| 取消成功场景 | `test_delete_orders_batch_cancel_success` | ✅ 已覆盖 | ORD-6 |
| 取消失败场景 | `test_delete_orders_batch_cancel_failure` | ✅ 已覆盖 | ORD-6 |
| 审计日志创建 | `test_delete_orders_batch_audit_log_created` | ✅ 已覆盖 | ORD-6 |
| 级联删除子订单 | `test_delete_orders_batch_with_children` | ✅ 已覆盖 | ORD-6 |
| 部分订单不存在 | `test_delete_orders_batch_partial_failure` | ✅ 已覆盖 | ORD-6 |
| ExchangeGateway 未注入 | ❌ 缺失 | 🔴 待补充 | 依赖注入场景 |
| AuditLogger 未注入 | ❌ 缺失 | 🔴 待补充 | 依赖注入场景 |

**边界条件检查**:
- [x] 空列表
- [x] 超限列表 (101 个)
- [x] 部分订单不存在
- [x] 级联删除
- [ ] 交易所取消超时
- [ ] 数据库删除失败回滚

### 4. `get_order_chain_by_order_id()` - 获取订单链

| 测试场景 | 测试用例 | 覆盖状态 | 备注 |
|----------|----------|----------|------|
| ENTRY 订单 (有子订单) | `test_get_order_chain_by_order_id_entry_order` | ✅ 已覆盖 | T4-006 |
| 子订单查询 (返回父订单 + 兄弟) | `test_get_order_chain_by_order_id_child_order` | ✅ 已覆盖 | T4-007 |
| 无子订单的 ENTRY | `test_get_order_chain_by_order_id_no_children` | ✅ 已覆盖 | T4-008 |
| 不存在的订单 | `test_get_order_chain_by_order_id_not_found` | ✅ 已覆盖 | T4-009 |
| TP5/SL 等多角色 | ❌ 缺失 | 🔴 待补充 | 多 TP 层级测试 |

---

## 🟠 P1 高风险方法测试检查

### 5. `get_orders_by_signal()` - 按信号查询

| 测试场景 | 测试用例 | 覆盖状态 | 备注 |
|----------|----------|----------|------|
| 基础查询 | `test_get_orders_by_signal_id` | ✅ 已覆盖 | UT-P5-011-005 |
| 空结果 | ❌ 缺失 | 🟡 部分覆盖 | 隐含在其他测试中 |
| 多信号混合 | ❌ 缺失 | 🔴 待补充 | 多 signal_id 混杂场景 |

### 6. `get_open_orders()` - 获取未完成订单

| 测试场景 | 测试用例 | 覆盖状态 | 备注 |
|----------|----------|----------|------|
| 基础查询 | `test_get_open_orders_integration` | ✅ 已覆盖 | INT-ORD-1-002 |
| 按币种过滤 | `test_get_open_orders` | ✅ 已覆盖 | T4-004 |
| 空结果 | ❌ 缺失 | 🟡 部分覆盖 | 隐含在其他测试中 |

### 7. `get_order_tree()` - 获取订单树

| 测试场景 | 测试用例 | 覆盖状态 | 备注 |
|----------|----------|----------|------|
| 分页加载 | ❌ 缺失 | 🔴 待补充 | page/page_size测试 |
| 币种过滤 | ❌ 缺失 | 🔴 待补充 | symbol 参数测试 |
| 日期范围过滤 | ❌ 缺失 | 🔴 待补充 | start_date/end_date/days |
| 树形结构验证 | ❌ 缺失 | 🔴 待补充 | children 层级验证 |

### 8. `get_oco_group()` - 获取 OCO 组订单

| 测试场景 | 测试用例 | 覆盖状态 | 备注 |
|----------|----------|----------|------|
| 基础查询 | `test_order_repository_get_oco_group` | ✅ 已覆盖 | UT-P5-011-007 |
| 空结果 | ❌ 缺失 | 🔴 待补充 | 不存在的 oco_group_id |

---

## 🟡 P2 中风险方法测试检查

### 9. `delete_order()` - 删除单订单 (级联)

| 测试场景 | 测试用例 | 覆盖状态 | 备注 |
|----------|----------|----------|------|
| 删除 ENTRY (cascade=True) | ❌ 缺失 | 🔴 待补充 | 级联删除测试 |
| 删除 ENTRY (cascade=False) | ❌ 缺失 | 🔴 待补充 | 非级联测试 |
| 删除子订单 | ❌ 缺失 | 🔴 待补充 | TP/SL订单删除 |
| 删除不存在订单 | ❌ 缺失 | 🔴 待补充 | 边界条件 |

### 10. `clear_orders()` - 批量清理

| 测试场景 | 测试用例 | 覆盖状态 | 备注 |
|----------|----------|----------|------|
| 按 signal_id 清理 | `test_delete_order` | ✅ 已覆盖 | UNIT-ORD-3-003 |
| 按 symbol 清理 | ❌ 缺失 | 🔴 待补充 | 币种过滤清理 |
| 清理全部订单 | ❌ 缺失 | 🔴 待补充 | 无参数清理 |
| 返回删除数量 | `test_batch_delete_orders` | ✅ 已覆盖 | UNIT-ORD-3-004 |

### 11. `_row_to_order()` - 行转订单

| 测试场景 | 测试用例 | 覆盖状态 | 备注 |
|----------|----------|----------|------|
| 正常转换 | ✅ 已覆盖 | 隐含在所有查询测试中 |
| NULL 字段处理 | ✅ 已覆盖 | `test_save_order_with_null_values` |
| Decimal 精度 | ❌ 缺失 | 🔴 待补充 | 精度保留测试 |

---

## 🔵 P3 低风险方法测试检查

### 12. 依赖注入方法

| 测试场景 | 测试用例 | 覆盖状态 | 备注 |
|----------|----------|----------|------|
| `set_exchange_gateway()` | `test_set_exchange_gateway` | ✅ 已覆盖 | UNIT-ORD-3-005 |
| `set_audit_logger()` | `test_set_audit_logger` | ✅ 已覆盖 | UNIT-ORD-3-006 |

### 13. 工具方法

| 测试场景 | 测试用例 | 覆盖状态 | 备注 |
|----------|----------|----------|------|
| `initialize()` | `test_order_repository_initialization` | ✅ 已覆盖 | UT-P5-011-001 |
| `close()` | ❌ 缺失 | 🔴 待补充 | 连接关闭测试 |
| `get_order_count()` | ❌ 缺失 | 🔴 待补充 | 计数测试 |

---

## 📋 边界条件覆盖总结

### 数据边界
| 检查项 | 覆盖状态 | 相关测试 |
|--------|----------|----------|
| 空值 (None) | ✅ 已覆盖 | `test_save_order_with_null_values` |
| 空字符串 | ❌ 待补充 | - |
| 空集合 | ✅ 已覆盖 | `test_delete_orders_batch_empty_list` |
| 零值 (0) | ❌ 待补充 | - |
| 负值 | ❌ 待补充 | - |
| 极大值 | ❌ 待补充 | - |

### 业务边界
| 检查项 | 覆盖状态 | 相关测试 |
|--------|----------|----------|
| 第一条数据 | ❌ 待补充 | - |
| 最后一条数据 | ❌ 待补充 | - |
| 单元素集合 | ❌ 待补充 | - |
| 重复数据 | ❌ 待补充 | - |
| 时间边界 (跨天/月/年) | ❌ 待补充 | - |

### 并发边界
| 检查项 | 覆盖状态 | 相关测试 |
|--------|----------|----------|
| 竞态条件 | ✅ 已覆盖 | `test_update_order_concurrent` |
| 事务回滚 | ✅ 已覆盖 | `test_transaction_rollback` |
| 资源竞争 | ❌ 待补充 | - |

---

## ⚠️ 异常处理覆盖检查

| 异常类型 | 测试用例 | 覆盖状态 |
|----------|----------|----------|
| `ValueError` (空列表) | `test_delete_orders_batch_empty_list` | ✅ 已覆盖 |
| `ValueError` (超限) | `test_delete_orders_batch_exceeds_limit` | ✅ 已覆盖 |
| 数据库连接失败 | ❌ 缺失 | 🔴 |
| 交易所 API 超时 | ❌ 缺失 | 🔴 |
| 审计日志失败 | ❌ 缺失 | 🔴 |

---

## 🏭 工厂类使用规范性检查

### Fixture 使用规范

| Fixture 名称 | 用途 | 使用频率 | 规范性 |
|--------------|------|----------|--------|
| `temp_db_path` | 临时数据库文件 | 高 | ✅ 规范 |
| `order_repository` | Repository 实例 | 高 | ✅ 规范 |
| `mock_exchange_gateway` | Mock 网关 | 中 | ✅ 规范 |
| `mock_audit_logger` | Mock 日志器 | 中 | ✅ 规范 |
| `sample_order` | 示例订单 | 高 | ✅ 规范 |
| `sample_tp_order` | 示例 TP 订单 | 中 | ✅ 规范 |
| `sample_sl_order` | 示例 SL 订单 | 中 | ✅ 规范 |

### Mock 使用规范

```python
# ✅ 规范示例
@pytest.fixture
def mock_exchange_gateway():
    gateway = MagicMock()
    gateway.cancel_order = AsyncMock(return_value=True)
    return gateway

# ❌ 待改进：应该在测试中验证 mock 调用
```

---

## ✅ 验收标准

### 覆盖率要求
| 方法级别 | 目标覆盖率 | 当前状态 |
|----------|------------|----------|
| P0 极高风险 | 100% | 🟡 85% |
| P1 高风险 | 80% | 🟡 60% |
| P2 中风险 | 70% | 🔴 40% |
| P3 低风险 | 60% | 🟡 50% |

### 关键断言数量
| 测试文件 | 断言数量 | 目标 | 状态 |
|----------|----------|------|------|
| test_order_repository_unit.py | ~40 | ≥50 | 🟡 接近 |
| test_order_repository.py | ~100 | ≥100 | ✅ 达标 |
| test_order_repository_queries.py | ~30 | ≥30 | ✅ 达标 |

### 测试执行时间
| 测试类型 | 目标时间 | 当前状态 |
|----------|----------|----------|
| 单元测试 | < 5 秒 | ✅ 符合 |
| 集成测试 | < 30 秒 | ✅ 符合 |

---

## 🔧 待补充测试用例清单

### 高优先级 (P0/P1)

1. **UPSERT 逻辑测试** - 验证 ON CONFLICT DO UPDATE 的字段保留逻辑
2. **update_status 完整参数测试** - filled_at, exchange_order_id, exit_reason
3. **delete_orders_batch 依赖注入测试** - ExchangeGateway/AuditLogger 未注入场景
4. **get_order_tree 分页测试** - page/page_size 参数验证
5. **delete_order 级联测试** - cascade=True/False 对比

### 中优先级 (P2)

6. **get_oco_group 空结果测试**
7. **clear_orders 按 symbol 清理**
8. **get_order_count 计数测试**
9. **close 连接关闭测试**

### 低优先级 (P3)

10. **Decimal 精度保留测试**
11. **时间边界测试** (跨天/月/年)
12. **异常场景测试** (数据库失败、API 超时)

---

## 📝 测试命名规范检查

### 当前命名模式

```python
# ✅ 规范：test_<method>_<scenario>_<expected>
test_save_order                          # 方法名
test_save_order_with_null_values         # 方法 + 边界条件
test_update_order_concurrent             # 方法 + 场景
test_delete_orders_batch_empty_list      # 方法 + 边界 + 预期

# ⚠️ 待统一：部分测试使用前缀 UT-P5-011-XXX
# 建议统一为描述性命名
```

### 命名规范建议

```python
def test_<method>_<condition>_<result>():
    """
    <TEST_ID>: <description>
    
    Test Scenario:
    1. ...
    2. ...
    
    Acceptance Criteria:
    - ...
    """
```

---

## 📊 总体评估

| 评估维度 | 得分 | 说明 |
|----------|------|------|
| P0 方法覆盖 | 85/100 | 核心功能已覆盖，UPSERT 逻辑待补充 |
| P1 方法覆盖 | 60/100 | 基础查询已覆盖，树形/分页待补充 |
| 边界条件 | 50/100 | 空值已覆盖，数值边界待补充 |
| 异常处理 | 40/100 | ValueError 已覆盖，系统异常待补充 |
| 命名规范 | 80/100 | 大部分规范，部分待统一 |
| Fixture 规范 | 90/100 | 结构清晰，复用性好 |

**总体得分**: 65/100

**建议**:
1. 优先补充 P0 方法的边界测试
2. 增加异常场景模拟
3. 统一命名规范
4. 添加集成 E2E 测试

---

*最后更新：2026-04-07*
