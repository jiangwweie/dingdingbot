# OrderRepository P1 Group B 过滤查询测试任务计划

> **任务 ID**: TEST-3-P1-GroupB  
> **优先级**: P1  
> **工时**: 2.5 小时  
> **负责人**: 后端开发  
> **创建日期**: 2026-04-07

---

## 一、任务目标

实现 OrderRepository P1 Group B 过滤查询方法的完整单元测试，包含 5 个方法共 19 个测试用例。

---

## 二、方法清单

| 方法 | 测试用例数 | 工时 |
|------|-----------|------|
| `get_open_orders()` | 4 | 0.5h |
| `get_orders_by_symbol()` | 4 | 0.5h |
| `get_orders_by_role()` | 5 | 0.5h |
| `get_by_status()` | 3 | 0.5h |
| `mark_order_filled()` | 3 | 0.5h |
| **合计** | **19** | **2.5h** |

---

## 三、测试用例设计

### 3.1 `get_open_orders()` - 4 个用例

| ID | 场景 | 要点 |
|----|------|------|
| P1-018 | 无币种过滤 | 查询所有 OPEN 订单 |
| P1-019 | 币种过滤 | 指定 symbol 过滤 |
| P1-020 | 多币种混合 | 多币种正确过滤 |
| P1-021 | 无 OPEN 订单 | 全部 FILLED/CANCELLED 返回空 |

### 3.2 `get_orders_by_symbol()` - 4 个用例

| ID | 场景 | 要点 |
|----|------|------|
| P1-022 | 单币种查询 | 指定 symbol |
| P1-023 | limit 限制 | limit=5 |
| P1-024 | 不存在的币种 | 无数据返回空 |
| P1-025 | 排序验证 | created_at 降序 |

### 3.3 `get_orders_by_role()` - 5 个用例

| ID | 场景 | 要点 |
|----|------|------|
| P1-026 | 单角色查询 | ENTRY 角色 |
| P1-027 | 组合 signal_id 过滤 | role + signal_id |
| P1-028 | 组合 symbol 过滤 | role + symbol |
| P1-029 | 三重过滤 | role + signal_id + symbol |
| P1-030 | 空结果 | 无匹配数据 |

### 3.4 `get_by_status()` - 3 个用例

| ID | 场景 | 要点 |
|----|------|------|
| P1-031 | 单状态查询 | FILLED 状态 |
| P1-032 | 排序验证 | created_at 降序 |
| P1-033 | 空结果 | 无匹配状态 |

### 3.5 `mark_order_filled()` - 3 个用例

| ID | 场景 | 要点 |
|----|------|------|
| P1-034 | 正常标记成交 | OPEN → FILLED |
| P1-035 | updated_at 更新 | 验证时间戳变更 |
| P1-036 | 不存在的订单 | order_id 无效 |

---

## 四、执行步骤

1. ✅ 阅读 P1 详细方案文档
2. ✅ 阅读 OrderRepository 源代码
3. ✅ 阅读现有测试文件结构
4. ⏳ 实现 19 个测试用例
5. ⏳ 运行测试验证
6. ⏳ 更新进度文档

---

## 五、验收标准

- [ ] 19 个测试用例全部通过
- [ ] 测试代码符合命名规范（P1-XXX）
- [ ] 测试数据隔离（临时数据库）
- [ ] 无 lint 错误
- [ ] 进度文档已更新

---

## 六、输出文件

- `tests/unit/infrastructure/test_order_repository_unit.py` - 新增测试类
- `docs/planning/order-repo-p1-group-b-plan.md` - 任务计划（本文档）

---

## 七、进度追踪

| 时间 | 完成内容 | 状态 |
|------|---------|------|
| - | get_open_orders() 测试 | ⏳ |
| - | get_orders_by_symbol() 测试 | ⏳ |
| - | get_orders_by_role() 测试 | ⏳ |
| - | get_by_status() 测试 | ⏳ |
| - | mark_order_filled() 测试 | ⏳ |
| - | 全部测试通过 | ⏳ |
