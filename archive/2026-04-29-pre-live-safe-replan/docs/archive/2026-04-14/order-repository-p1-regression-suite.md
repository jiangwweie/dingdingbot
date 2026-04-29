# OrderRepository P1 回归测试套件

> **文档版本**: v1.0  
> **创建日期**: 2026-04-07  
> **QA 负责人**: QA Tester  
> **执行频率**: 每次 P1 测试修改后执行

---

## 📊 回归测试概览

| 组别 | 方法数 | 用例数 | 优先级 | 执行时间 |
|------|-------|--------|--------|---------|
| **Group A** - 核心查询 | 2 | 17 | P0 | ~30 秒 |
| **Group B** - 过滤查询 | 5 | 19 | P1 | ~45 秒 |
| **Group C** - 别名方法 | 4 | 6 | P2 | ~15 秒 |
| **总计** | 11 | 42 | - | ~90 秒 |

---

## 🔧 执行命令

### 完整 P1 回归测试
```bash
# 运行 P1 相关测试（按方法名过滤）
pytest tests/unit/infrastructure/test_order_repository_unit.py -v -k "get_orders or get_orders_by_signal or get_open_orders or get_orders_by_symbol or get_orders_by_role or get_by_status or mark_order_filled or save_order or get_order_detail or get_by_signal_id"
```

### 分组执行

#### Group A - 核心查询
```bash
pytest tests/unit/infrastructure/test_order_repository_unit.py -v -k "get_orders"
```

#### Group B - 过滤查询
```bash
pytest tests/unit/infrastructure/test_order_repository_unit.py -v -k "get_open_orders or get_orders_by_symbol or get_orders_by_role or get_by_status or mark_order_filled"
```

#### Group C - 别名方法
```bash
pytest tests/unit/infrastructure/test_order_repository_unit.py -v -k "save_order or get_order_detail or get_by_signal_id"
```

### 覆盖率检查
```bash
# 生成 P1 方法覆盖率报告
pytest tests/unit/infrastructure/test_order_repository_unit.py --cov=src.infrastructure.order_repository --cov-report=html -v
```

---

## 📋 核心功能路径（P0 级）

### CP-001: get_orders() 基础查询路径
| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | 创建 3 个测试订单 | 订单保存成功 |
| 2 | 调用 `get_orders()` 无参数查询 | 返回 3 个订单 |
| 3 | 验证返回结构 | 包含 `items`, `total`, `limit`, `offset` |
| 4 | 验证排序 | 按 `created_at` 降序 |

**关联测试**: P1-001, P1-006, P1-010

### CP-002: get_orders() 分页查询路径
| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | 创建 20 个测试订单 | 订单保存成功 |
| 2 | 调用 `get_orders(limit=10, offset=0)` | 返回前 10 个订单 |
| 3 | 调用 `get_orders(limit=10, offset=10)` | 返回第 11-20 个订单 |
| 4 | 验证 `total` 值 | `total=20`（不受 limit 影响） |

**关联测试**: P1-006, P1-007, P1-008

### CP-003: get_orders() 多条件过滤路径
| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | 创建不同 symbol/status/role 的订单 | 订单保存成功 |
| 2 | 调用 `get_orders(symbol="BTC/USDT:USDT")` | 只返回 BTC 订单 |
| 3 | 调用 `get_orders(status=OPEN)` | 只返回 OPEN 订单 |
| 4 | 调用 `get_orders(symbol="BTC", status=OPEN, role=ENTRY)` | 返回精确匹配订单 |

**关联测试**: P1-002, P1-003, P1-004, P1-005

### CP-004: get_orders_by_signal_ids() 批量查询路径
| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | 创建 3 个信号，每个信号 2 个订单 | 订单保存成功 |
| 2 | 调用 `get_orders_by_signal_ids(["sig1"])` | 返回 sig1 的 2 个订单 |
| 3 | 调用 `get_orders_by_signal_ids(["sig1", "sig2"])` | 返回 4 个订单 |
| 4 | 验证分页 | `page=1, page_size=20` 正确 |

**关联测试**: P1-011, P1-012, P1-014, P1-015

---

## 📋 集成路径（与 P0 方法）

### IP-001: P1 查询与 P0 保存的集成
| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | 调用 `save(order)` 保存订单 | 订单持久化成功 |
| 2 | 调用 `get_orders()` 查询 | 返回刚保存的订单 |
| 3 | 调用 `get_order(order_id)` 查询 | 返回单个订单 |
| 4 | 验证数据一致性 | 查询结果与保存数据一致 |

**关联测试**: P1-001, P1-037, P1-039

### IP-002: P1 更新与 P0 查询的集成
| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | 调用 `save(order)` 保存 OPEN 订单 | 订单状态为 OPEN |
| 2 | 调用 `mark_order_filled(order_id, filled_at)` | 状态变更为 FILLED |
| 3 | 调用 `get_order(order_id)` 查询 | 返回 FILLED 状态订单 |
| 4 | 验证 `filled_at` 字段 | 时间戳正确设置 |

**关联测试**: P1-034, P1-035

### IP-003: P1 过滤与 P0 状态的集成
| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | 创建 OPEN, FILLED, CANCELLED 订单 | 各状态订单已保存 |
| 2 | 调用 `get_open_orders()` | 只返回 OPEN 和 PARTIALLY_FILLED |
| 3 | 调用 `get_by_status(FILLED)` | 只返回 FILLED 订单 |
| 4 | 调用 `get_by_status(CANCELED)` | 只返回 CANCELLED 订单 |

**关联测试**: P1-018, P1-021, P1-031

---

## ✅ 验收检查清单

### 执行前检查
- [ ] 测试数据库已清空
- [ ] 依赖已安装（pytest, pytest-asyncio）
- [ ] 测试文件格式正确

### 执行中检查
- [ ] 所有测试用例通过（100% 通过率）
- [ ] 无警告信息
- [ ] 执行时间在预期范围内（< 120 秒）

### 执行后检查
- [ ] 生成覆盖率报告
- [ ] 覆盖率 >= 75%
- [ ] 更新 `docs/qa/p1-verification-report.md`

---

## 📊 历史执行记录

| 执行日期 | 执行人 | 通过率 | 覆盖率 | 备注 |
|---------|-------|--------|--------|------|
| 2026-04-07 | QA Tester | -% | -% | 首次执行待记录 |

---

## 🔧 故障排查

### 常见问题

#### 问题 1: 测试失败 "table orders does not exist"
**原因**: 数据库表未创建  
**解决**: 确保 `await repo.initialize()` 在测试前调用

#### 问题 2: 测试超时
**原因**: 异步测试未正确 await  
**解决**: 检查测试函数是否使用 `@pytest.mark.asyncio` 装饰器

#### 问题 3: 断言失败 "assert 0 == 3"
**原因**: 查询返回空结果  
**解决**: 检查测试数据是否正确保存，确认 signal_id 匹配

---

*最后更新：2026-04-07*
*下次更新：P1 测试执行完成后*
