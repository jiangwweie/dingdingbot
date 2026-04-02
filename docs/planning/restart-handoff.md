# 订单管理级联展示功能 - 重启交接单

> **创建日期**: 2026-04-02  
> **状态**: 🔄 开发中（暂停待重启）  
> **重启后请执行**: 前端 F2 集成 + 测试 T1

---

## 📊 任务进度概览

| 阶段 | 任务 | 状态 | 说明 |
|------|------|------|------|
| 需求分析 | 需求沟通与确认 | ✅ 已完成 | 11 项需求细节确认 |
| 架构设计 | 架构审查 | ✅ 已完成 | 修正 3 个问题 |
| 后端开发 | B1: Repository 方法 | ✅ 已完成 | `get_order_tree()`, `delete_orders_batch()` |
| 后端开发 | B2: API 端点 | ✅ 已完成 | GET/DELETE /api/v3/orders/tree |
| 前端开发 | F1: 树形表格组件 | ✅ 已完成 | OrderChainTreeTable + DeleteChainConfirmModal |
| 前端开发 | F2: Orders 页面集成 | ☐ **待执行** | 依赖 B2 |
| 测试验证 | T1: 功能测试 | ☐ **待执行** | 依赖 F2 |

---

## ✅ 已完成工作详情

### 后端 B1: OrderRepository 树形查询实现

**修改文件**: `src/infrastructure/order_repository.py`

**新增方法**:
- `get_order_tree()` - 获取订单树形结构
- `_get_entry_orders()` - 获取 ENTRY 订单列表
- `_get_child_orders()` - 批量获取子订单
- `_order_to_response()` - Order 转 ResponseFull 字典
- `get_order_chain()` - 获取完整订单链
- `delete_orders_batch()` - 批量删除订单（带事务保护）

**TODO 待完善**:
1. 创建 `order_audit_logs` 表（审计日志持久化）
2. 集成 `exchange_gateway` 取消订单（交易所 API 调用）

---

### 后端 B2: 订单树 API 端点实现

**修改文件**: `src/interfaces/api.py`

**新增端点**:
- `GET /api/v3/orders/tree` - 获取订单树形结构
- `DELETE /api/v3/orders/batch` - 批量删除订单链

**TODO**: 无（已完成）

---

### 前端 F1: 订单链树形表格组件开发

**新增文件**:
- `web-front/src/types/order.ts` - 扩展类型定义
- `web-front/src/components/v3/OrderChainTreeTable.tsx` - 树形表格组件
- `web-front/src/components/v3/DeleteChainConfirmModal.tsx` - 删除确认弹窗
- `web-front/src/components/v3/__tests__/OrderChainTreeTable.test.tsx` - 单元测试

**测试结果**: 3/3 通过

**依赖安装**: `react-window` v2.2.7

---

## ☐ 待执行任务

### 前端 F2: Orders 页面集成树形表格

**任务 ID**: #15  
**依赖**: 后端 B2 已完成

**工作内容**:
1. 改造 `Orders.tsx` 页面，集成 `OrderChainTreeTable` 组件
2. 集成 `DeleteChainConfirmModal` 弹窗
3. 调用后端 API: `GET /api/v3/orders/tree`
4. 调用后端 API: `DELETE /api/v3/orders/batch`

**启动命令**:
```
Agent(subagent_type="frontend-dev", prompt="前端 F2: Orders 页面集成树形表格")
```

---

### 测试 T1: 订单链功能测试

**任务 ID**: #13  
**依赖**: 前端 F2 已完成

**工作内容**:
1. 后端单元测试：`tests/unit/test_order_tree_api.py`
2. 集成测试：`tests/integration/test_order_chain_api.py`
3. E2E 测试：`tests/e2e/test_order_chain_e2e.py`

**启动命令**:
```
Agent(subagent_type="qa-tester", prompt="测试 T1: 订单链功能测试")
```

---

## 📁 相关文件索引

### 设计文档
- `docs/designs/order-chain-tree-contract.md` - 接口契约表（架构审查修正版）
- `docs/planning/findings.md` - 技术发现（含架构审查修正记录）
- `docs/planning/task_plan.md` - 任务计划

### 代码文件
- `src/infrastructure/order_repository.py` - Repository 方法
- `src/interfaces/api.py` - API 端点
- `web-front/src/components/v3/OrderChainTreeTable.tsx` - 树形表格组件
- `web-front/src/components/v3/DeleteChainConfirmModal.tsx` - 删除确认弹窗
- `web-front/src/pages/Orders.tsx` - 订单页面（待改造）

### 测试文件
- `web-front/src/components/v3/__tests__/OrderChainTreeTable.test.tsx` - 已通过 3/3
- `tests/unit/test_order_tree_api.py` - 待创建
- `tests/integration/test_order_chain_api.py` - 待创建
- `tests/e2e/test_order_chain_e2e.py` - 待创建

---

## ⚠️ 注意事项

1. **审计日志表**: `order_audit_logs` 表尚未创建，批量删除功能的审计日志持久化待实现
2. **交易所取消**: `delete_orders_batch()` 中交易所 API 调用逻辑待集成（需要 exchange_gateway）
3. **虚拟滚动依赖**: `react-window` 已安装，需确认 `package.json` 已记录

---

## 🔄 重启后快速恢复步骤

1. **检查后端 B2 状态** - 确认 API 端点已实现
2. **启动前端 F2** - Orders 页面集成
3. **启动测试 T1** - 完整测试覆盖
4. **更新 progress.md** - 记录进度

---

**最后更新**: 2026-04-02 (暂停待重启)
