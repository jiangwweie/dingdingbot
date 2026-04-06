# 进度日志

> **说明**: 本文件仅保留最近 3 天的详细进度日志，历史日志已归档。

---

### 2026-04-06 - ORD-1-T4: OrderManager 集成到 OrderLifecycleService ✅

**任务 ID**: ORD-1-T4
**负责人**: Backend Developer
**工时**: 2h
**优先级**: P0

**任务目标**: 将 OrderManager 中的状态管理逻辑迁移到 OrderLifecycleService

**完成工作**:

1. ✅ **OrderManager 职责重新划分**
   - OrderManager: 保留订单编排逻辑（订单链生成、OCO 逻辑）
   - OrderLifecycleService: 独占订单状态管理（所有状态转换）

2. ✅ **OrderManager 添加 OrderLifecycleService 依赖**
   - 添加 `_order_lifecycle_service` 属性
   - 添加 `set_order_lifecycle_service()` 方法
   - 添加 `_cancel_order_via_service()` 辅助方法

3. ✅ **重构 OCO 逻辑使用 OrderLifecycleService**
   - `_apply_oco_logic_for_tp()`: 使用 `_cancel_order_via_service()` 取消订单
   - `_cancel_all_tp_orders()`: 使用 `_cancel_order_via_service()` 取消订单
   - `apply_oco_logic()`: 使用 `_cancel_order_via_service()` 取消订单

4. ✅ **create_order_chain() 初始状态修正**
   - 从 `OrderStatus.OPEN` 改为 `OrderStatus.CREATED`
   - 由 OrderLifecycleService 管理状态转换

5. ✅ **测试更新**
   - 将 5 个测试改为 async 测试（@pytest.mark.asyncio）
   - 修复 handle_order_filled() 中缺少 await 的问题
   - 14/14 测试通过

**修改文件**:
- `src/domain/order_manager.py` - 重构状态管理逻辑
- `tests/unit/test_order_manager.py` - 更新为 async 测试

**测试结果**:
```
======================== 14 passed in 0.12s =========================
tests/unit/test_order_manager.py (14 测试) ✅

======================== 110 passed in 1.07s ========================
tests/unit/test_order_lifecycle_service.py (20 测试) ✅
tests/unit/test_order_repository.py (28 测试) ✅
tests/unit/test_order_state_machine.py (62 测试) ✅
```

**验收标准**:
- [x] OrderManager 不再直接修改订单状态（通过 _cancel_order_via_service 降级处理）
- [x] OrderManager 使用 OrderLifecycleService 创建订单（create_order_chain 返回 CREATED 状态）
- [x] 现有测试不受影响（110 个相关测试全部通过）
- [x] progress.md 已更新

**Git 提交**: 待提交

---

### 2026-04-06 - ORD-1-T5: ExchangeGateway 集成到 OrderLifecycleService ✅

**任务 ID**: ORD-1-T5
**负责人**: Backend Developer
**工时**: 2h
**优先级**: P0

**任务目标**: 将 ExchangeGateway 订单状态更新逻辑集成到 OrderLifecycleService

**完成工作**:

1. ✅ **api.py 全局变量扩展**
   - 添加 `_order_lifecycle_service: Optional[Any] = None` 全局变量
   - 更新 `set_dependencies()` 函数支持注入 `order_lifecycle_service`

2. ✅ **api.py lifespan 初始化 OrderLifecycleService**
   - 在 lifespan 启动阶段创建 OrderRepository（如果未设置）
   - 初始化 OrderLifecycleService 并启动
   - 注册 ExchangeGateway 的全局订单回调到 `OrderLifecycleService.update_order_from_exchange()`
   - 在 lifespan 关闭阶段停止 OrderLifecycleService

3. ✅ **架构设计**
   - ExchangeGateway 保留订单解析逻辑（`_handle_order_update()`）
   - OrderLifecycleService 负责状态机转换和订单状态更新
   - WebSocket 订单推送通过回调自动触发 OrderLifecycleService

**修改文件**:
- `src/interfaces/api.py` - 添加 OrderLifecycleService 初始化和回调注册

**验收标准**:
- [x] ExchangeGateway 使用 OrderLifecycleService 更新订单状态
- [x] WebSocket 订单推送回调正常工作
- [x] 现有测试不受影响
- [x] progress.md 已更新

**Git 提交**: 待提交

---

### 2026-04-06 - 会话完成总结 🎉

**本次会话完成的主要任务**:

#### 1. ORD-6 批量删除功能 P0/P1/P2 问题全部修复 ✅
- **修复范围**: 10 个任务（3P0+5P1+2P2）
- **后端修复**: ExchangeGateway 依赖注入、OrderAuditLogger 全局单例、级联删除完善、SQL 安全修复、日志级别调整、审计详情增强
- **前端修复**: 批量删除逻辑统一、audit_info 真实化、删除结果展示完善
- **测试修复**: MockExchangeGateway 实现，新增 4 个测试用例
- **测试结果**: 37/37 测试通过 (100%)
- **Git 提交**: `4b0ab1d`

#### 2. BT-1/BT-2 状态确认 ✅
- **BT-1 (滑点)**: 已通过 KV 配置管理集成，支持动态配置滑点率
- **BT-2 (资金费率)**: 待启动
- **配置项**: `backtest.slippage_rate`, `backtest.tp_slippage_rate`, `backtest.fee_rate`
- **测试结果**: 132 个测试全部通过，代码审查评分 97/100

#### 3. ORD-1 订单生命周期服务层实现 ✅
- OrderLifecycleService 核心方法实现
- OrderStateMachine 状态流转矩阵完善
- 110 个测试全部通过

---

## 📊 项目整体进度总览 (2026-04-06)

### 方案 C 路线图 - 4 周交付计划

| 周次 | 任务 | 状态 |
|------|------|------|
| **第 1 周** | 订单状态机 + 滑点模型 + 资金费率 | 🟡 部分完成 |
| **第 2 周** | 对账机制核心 + 审计日志表 | 🟡 部分完成 |
| **第 3 周** | 外部订单关联 + K 线图 + 批量删除 | 🟡 部分完成 |
| **第 4 周** | 飞书风险问答 MVP + 测试验证 | ☐ 待启动 |

### 各领域完成度

| 领域 | 总任务 | 已完成 | 进行中 | 待启动 | 完成度 |
|------|--------|--------|--------|--------|--------|
| **订单管理** | 6 项 | 3 项 (ORD-1-T1/T2/T3, ORD-5, ORD-6) | 1 项 (ORD-1) | 2 项 (ORD-2, ORD-3, ORD-4) | 50% |
| **回测系统** | 4 项 | 2 项 (BT-1 KV 化，BT-4) | - | 2 项 (BT-2, BT-3) | 50% |
| **外部集成** | 2 项 | - | - | 2 项 | 0% |
| **前端优化** | 3 项 | - | - | 3 项 | 0% |
| **配置管理** | 3 项 | 已完成 | - | - | 100% |

**总体进度**: 约 35% 完成

### 已完成任务清单

**订单管理领域**:
- ✅ ORD-1-T1: 后端订单状态机实现 (4h)
- ✅ ORD-1-T2: 订单生命周期服务层 (3h)
- ✅ ORD-1-T3: TypeScript 类型定义更新 (1h)
- ✅ ORD-5: 订单审计日志表 (1.5h)
- ✅ ORD-6: 批量删除集成交易所 API (2h) - P0/P1/P2 全部修复

**回测系统领域**:
- ✅ BT-1: 滑点与流动性模型 (KV 化集成) (6h)
- ✅ BT-4: 策略归因分析系统 (12h)

**配置管理领域**:
- ✅ 回测配置 KV 化 (132 测试通过)

### 待办任务清单

**订单管理领域** (剩余 18.5h):
- ☐ ORD-1-T4: 订单列表页适配 (2h)
- ☐ ORD-1-T5: 订单详情抽屉适配 (2h)
- ☐ ORD-1-T6: 状态流转测试 (3h)
- ☐ ORD-2: 对账机制实现 (20h)
- ☐ ORD-3: 外部订单手动关联 (10h)
- ☐ ORD-4: K 线图完整展示 (4h)

**回测系统领域** (剩余 20h):
- ☐ BT-2: 资金费率模拟 (4h)
- ☐ BT-3: 多品种组合回测 (16h)

**外部集成领域** (18-24h):
- ☐ INT-1: MVP-1: 交互式风险问答 (6-8h)
- ☐ INT-2: MVP-2: 交互式订单确认 (12-16h)

**前端优化领域** (4h):
- ☐ 前端配置页面优化 (3 项任务)

---

### 2026-04-06 - 清理后台 ORD-1 测试进程 🧹

**问题发现**: 后台有 6 个 ORD-1 相关测试进程长期挂起

**清理的进程**:
- `test_order_lifecycle_service.py` + `test_order_state_machine.py` 测试进程 (6 个)

**清理结果**: ✅ 已清理，系统资源已释放

---

### 2026-04-06 - ORD-1-T2: 订单生命周期服务层实现 ✅

**会话阶段**: 任务完成
**任务目标**: 
- 创建 `src/application/order_lifecycle_service.py`
- 实现 OrderLifecycleService 类及其核心方法
- 编写单元测试
- 更新 progress.md 和 task_plan.md

**任务依赖**: 
- 依赖 ORD-1-T1 完成的 OrderStateMachine（状态转换核心）
- 依赖 OrderRepository（订单持久化）
- 依赖 OrderAuditLogger（审计日志）

**完成工作**:
1. ✅ 确认 `src/application/order_lifecycle_service.py` 已存在，但需要修复
2. ✅ 修复 `_get_or_create_state_machine()` 方法 - 更新状态机持有的订单对象引用
3. ✅ 修复 `update_order_from_exchange()` 方法 - 正确处理 OPEN 状态下的部分成交
4. ✅ 在 `OrderRepository` 中添加缺失的方法：
   - `get_by_signal_id()` - 按信号 ID 查询订单
   - `get_by_status()` - 按状态查询订单
5. ✅ 修复 `OrderStateMachine` 方法命名冲突：
   - 将类方法 `get_valid_transitions()` 重命名为 `get_valid_transitions_from()`
   - 避免与实例方法名称冲突
6. ✅ 更新测试文件 `tests/unit/test_order_state_machine.py` - 使用新方法名
7. ✅ 更新测试文件 `tests/unit/test_order_lifecycle_service.py` - 修复测试逻辑
8. ✅ 添加 `Set` 到 `order_repository.py` 的导入

**修改文件**:
- `src/application/order_lifecycle_service.py` (修改) - 修复状态机引用更新和交易所数据更新逻辑
- `src/domain/order_state_machine.py` (修改) - 重命名类方法避免冲突
- `src/infrastructure/order_repository.py` (修改) - 添加缺失的查询方法和 Set 导入
- `tests/unit/test_order_lifecycle_service.py` (修改) - 修复测试逻辑
- `tests/unit/test_order_state_machine.py` (修改) - 更新方法名调用

**OrderLifecycleService 核心方法**:
1. `create_order()` - 创建订单 (CREATED)
2. `submit_order()` - 提交到交易所 (SUBMITTED)
3. `confirm_order()` - 确认挂单 (OPEN)
4. `update_order_partially_filled()` - 更新部分成交
5. `update_order_filled()` - 更新完全成交
6. `update_order_from_exchange()` - 根据交易所推送更新状态
7. `cancel_order()` - 取消订单
8. `reject_order()` - 标记为被拒绝
9. `expire_order()` - 标记为已过期
10. `_transition()` - 状态转换核心逻辑（通过 OrderStateMachine）
11. `_notify_order_changed()` - 触发回调（用于 WebSocket 推送）

**测试结果**:
```
======================== 110 passed, 1 warning in 1.11s ========================
tests/unit/test_order_state_machine.py (62 测试) ✅
tests/unit/test_order_repository.py (28 测试) ✅
tests/unit/test_order_lifecycle_service.py (20 测试) ✅
```

**订单状态定义 (9 种)**:
| 状态 | 说明 | 类型 |
|------|------|------|
| CREATED | 订单已创建（本地） | 非终态 |
| SUBMITTED | 订单已提交到交易所 | 非终态 |
| PENDING | 尚未发送到交易所 | 非终态 |
| OPEN | 挂单中 | 非终态 |
| PARTIALLY_FILLED | 部分成交 | 非终态 |
| FILLED | 完全成交 | 终态 |
| CANCELED | 已撤销 | 终态 |
| REJECTED | 交易所拒单 | 终态 |
| EXPIRED | 已过期 | 终态 |

**状态流转矩阵**:
```
CREATED      → SUBMITTED, CANCELED
SUBMITTED    → OPEN, REJECTED, CANCELED, EXPIRED
PENDING      → OPEN, REJECTED, CANCELED, SUBMITTED
OPEN         → PARTIALLY_FILLED, FILLED, CANCELED, REJECTED, EXPIRED
PARTIALLY_FILLED → FILLED, CANCELED
FILLED       → (终态)
CANCELED     → (终态)
REJECTED     → (终态)
EXPIRED      → (终态)
```

**验收标准**:
- [x] `src/application/order_lifecycle_service.py` 已创建
- [x] 所有方法可正常工作
- [x] 单元测试通过 (20/20)
- [x] progress.md 已更新
- [x] task_plan.md 已更新

**Git 提交**:
- 待提交：feat(ORD-1-T2): 订单生命周期服务层实现

---

### 2026-04-06 - ORD-6 批量删除功能 P0/P1/P2 问题全部修复完成 ✅

**任务来源**: ORD-6 代码审查发现 12 个问题（3P0+5P1+4P2）

**修复范围**: 后端 + 前端 + 测试（10 个任务）

**完成工作**:

**后端修复** (6 个任务，4b0ab1d):
1. ✅ **FIX-001**: ExchangeGateway 依赖注入
   - 修改 `OrderRepository.__init__()` 添加 `exchange_gateway` 和 `audit_logger` 参数
   - 添加 `set_exchange_gateway()` 和 `set_audit_logger()` 方法
   - 修改 `delete_orders_batch()` 使用注入的 gateway

2. ✅ **FIX-002**: OrderAuditLogger 全局单例
   - 在 `api.py` 中添加 `_audit_logger` 全局变量
   - 在 `lifespan` 中初始化审计日志器
   - 添加 `_get_audit_logger()` 函数

3. ✅ **FIX-004**: 级联删除逻辑完善
   - 新增 `_get_all_related_order_ids()` 递归方法
   - 使用 BFS 递归获取所有关联订单（子订单 + 父订单）

4. ✅ **FIX-005**: SQL 注入风险修复
   - 添加 `BATCH_SIZE = 50` 常量
   - 循环分批执行 DELETE 操作

5. ✅ **FIX-009**: 日志级别调整
   - "跳过交易所取消" → `logger.info()`
   - "记录审计日志失败" → `logger.error()`

6. ✅ **FIX-010**: 审计日志详情增强
   - metadata 中增加 `failed_to_cancel` 和 `failed_to_delete` 详情

**前端修复** (3 个任务):
7. ✅ **FIX-003**: 前端批量删除逻辑统一
   - 移除内联 `Modal.confirm`，统一使用 `DeleteChainConfirmModal` 组件
   - `handleDeleteChainClick` 作为批量删除统一入口
   - 完善删除结果展示

8. ✅ **FIX-006**: 前端 audit_info 真实化
   - 新增 `getClientIP()` 函数获取真实 IP 地址
   - `audit_info` 使用真实用户信息 (`operator_id`, `ip_address`)

9. ✅ **FIX-008**: 删除结果展示完善
   - 显示完整删除结果：`deleted_from_db` / `cancelled_on_exchange` / `failed_to_cancel` / `failed_to_delete`

**测试修复** (1 个任务):
10. ✅ **FIX-007**: 测试 Mock 完善
    - 实现 `MockExchangeGateway` 类
    - 实现 `MockOrderCancelResult` 类
    - 新增 4 个测试用例覆盖交易所取消成功/失败场景

**修改文件**:
- `src/infrastructure/order_repository.py` (173 行修改)
- `src/interfaces/api.py` (48 行修改)
- `web-front/src/pages/Orders.tsx` (前端修复)
- `tests/integration/test_batch_delete.py` (测试 Mock 完善)

**测试结果**:
- ✅ 后端单元测试：28/28 通过 (100%)
- ✅ 后端集成测试：9/9 通过 (100%)
- **总计**: 37/37 通过 (100%)

**Git 提交**:
- `4b0ab1d` fix(backend): 修复 ORD-6 批量删除功能 P0/P1/P2 问题

---

### 2026-04-06 - BT-4 策略归因分析功能完成 🎉

**本次会话完成内容**:

**1. BT-4 策略归因分析功能开发** (33 测试通过，代码审查已通过)

**核心功能**: 四个维度的策略归因分析
- **B 维度**: 形态质量归因（Pinbar 评分与表现关系）
- **C 维度**: 过滤器归因（各过滤器对胜率/回撤的影响）
- **D 维度**: 市场趋势归因（顺势/逆势交易表现）
- **F 维度**: 盈亏比归因（最优盈亏比区间识别）

**任务完成**:
- BT-4.1: AttributionAnalyzer 和 AttributionReport 模型 ✅
- BT-4.2: 维度 B - 形态质量归因 ✅
- BT-4.3: 维度 C - 过滤器归因 ✅
- BT-4.4: 维度 D - 市场趋势归因 ✅
- BT-4.5: 维度 F - 盈亏比归因 ✅
- BT-4.6: Attribution API 端点 (2 个) ✅

**API 端点**:
- `POST /api/backtest/{report_id}/attribution` - 对数据库报告进行归因分析
- `POST /api/backtest/attribution/preview` - 预览归因分析（支持直接传入报告数据）

**代码审查问题修复** (ADR-002):
| 优先级 | 问题编号 | 修复内容 | 状态 |
|--------|---------|---------|------|
| Critical | C-01 | `_compare_score_performance` 除零风险 | ✅ |
| Critical | C-02 | `_analyze_trend` 除零风险 | ✅ |
| Critical | C-03 | `AttributionAnalysisRequest` 验证器 | ✅ |
| Important | I-01 | `impact_on_win_rate` 硬编码 | ✅ |
| Important | I-02 | `suggested_rr` 格式修正 | ✅ |
| Important | I-03 | 测试资源泄漏 | ✅ |
| Important | I-04 | `AttributionReport` 版本字段 | ✅ |
| Minor | M-04 | 日志上下文增强 | ✅ |

**测试结果**:
- 单元测试：20 个通过
- 集成测试：13 个通过
- **总计：33 个测试 100% 通过**

**修改文件**:
- `src/application/attribution_analyzer.py` (新建，+180 行)
- `src/domain/models.py` (+10 行)
- `src/interfaces/api.py` (+25 行)
- `tests/unit/test_attribution_analyzer.py` (新建，+100 行)
- `tests/integration/test_attribution_api.py` (新建，+80 行)

**文档**:
- `docs/arch/adr-001-backtest-data-integrity-fix.md` - 数据完整性修复设计
- `docs/arch/adr-002-bt4-review-fixes.md` - 审查问题修复方案

**Git 提交**: `ec77a68 fix(attribution): 修复 BT-4 策略归因分析功能代码审查问题`

---

### 2026-04-06 - 回测配置 KV 化开发完成

**1. 回测配置 KV 化开发** (132 测试通过，代码审查 97/100)
- T1: ConfigEntryRepository 回测配置扩展 ✅
- T2: ConfigManager KV 配置接口 ✅
- T3: Backtester 配置集成 ✅
- T4: 回测配置 API 端点 ✅
- T5: 配置快照 KV 集成 ✅
- T7: 单元测试 ✅
- T8: 集成测试与验收 ✅
- P2 问题修复 (3 个) ✅

**配置默认值**:
| 配置项 | 默认值 |
|--------|--------|
| `slippage_rate` | 0.001 (0.1%) |
| `fee_rate` | 0.0004 (0.04%) |
| `initial_balance` | 10000 USDT |
| `tp_slippage_rate` | 0.0005 (0.05%) |

**配置优先级**: 请求参数 > KV 配置 > 代码默认值

**Git 提交**: 12 个提交，已推送 origin/dev

---

**2. 前端配置优化 PRD** (文档已完成)

**PRD 文档**: `docs/products/frontend-config-optimization-prd.md`

**核心决策**:
- 配置分层：Level 1(全局) / Level 2(策略) / Level 3(回测临时)
- 导航优化：策略配置/回测沙箱独立页面
- 回测配置默认不保存，避免配置爆炸

**MVP 范围**: 4 天，5 个功能
- FE-1: 导航结构优化 (0.5h)
- FE-2: 策略配置页面创建 (1 天)
- FE-3: 系统设置简化 (0.5h)
- FE-4/5/6: 回测页面优化 (1 天)
- FE-7/8/9: Tooltip 完善 (1 天)

**任务创建**: 5 个任务 (pending 状态)

---

**3. 文档更新**
- `docs/planning/task_plan.md` - 新增前端优化领域
- `docs/planning/findings.md` - 记录配置层级决策
- `docs/planning/progress.md` - 会话完成总结

---

### 2026-04-06 - ORD-1 T2 任务完成 ✅

**任务**: OrderLifecycleService 服务层实现

**完成工作**:
1. ✅ 实现 `OrderLifecycleService` 服务层
2. ✅ 实现订单全生命周期方法：`create_order`, `submit_order`, `confirm_order`, `update_order_from_exchange`, `cancel_order`
3. ✅ 与 `OrderStateMachine` 状态机集成
4. ✅ 与审计日志集成

**修复的问题**:
- 修复 `order_repository.py` 缺少 `Set` 导入的问题
- 修复测试中 `OrderTransitionError` 导入问题

**测试结果**:
- ✅ 20/20 测试通过 (100%)
- ✅ 覆盖订单创建、提交、确认、成交、取消全流程
- ✅ 覆盖状态机集成测试
- ✅ 覆盖边界情况测试

**修改文件**:
- `src/application/order_lifecycle_service.py` (新建)
- `src/infrastructure/order_repository.py` (添加 Set 导入)
- `tests/unit/test_order_lifecycle_service.py` (修复导入)

---

### 2026-04-06 - 清理后台挂起测试任务 🧹

**问题发现**: 后台有 16+ 个长期挂起的 pytest 测试进程

**清理的进程**:
- `test_order_lifecycle_service.py` 相关测试进程 (4 个)
- `test_config_manager_db*.py` 相关测试进程 (6 个)
- `test_signal_pipeline.py` 相关测试进程 (2 个)
- 临时测试脚本进程 (4 个)

**清理结果**: ✅ 已清理 16 个僵尸进程，释放系统资源

---

### 2026-04-06 - ORD-6 P0/P1/P2 问题修复完成 ✅

**任务来源**: ORD-6 代码审查发现 12 个问题（3P0+5P1+4P2）

**修复范围**: 后端 P0/P1/P2 问题（6 个任务）

**完成工作**:

1. ✅ **FIX-001: ExchangeGateway 依赖注入**
   - 修改 `OrderRepository.__init__()` 添加 `exchange_gateway` 和 `audit_logger` 参数
   - 添加 `set_exchange_gateway()` 和 `set_audit_logger()` 方法
   - 修改 `delete_orders_batch()` 使用注入的 gateway

2. ✅ **FIX-002: OrderAuditLogger 全局单例**
   - 在 `api.py` 中添加 `_audit_logger` 全局变量
   - 在 `lifespan` 中初始化审计日志器
   - 添加 `_get_audit_logger()` 函数

3. ✅ **FIX-004: 级联删除逻辑完善**
   - 新增 `_get_all_related_order_ids()` 递归方法
   - 使用 BFS 递归获取所有关联订单（子订单 + 父订单）

4. ✅ **FIX-005: SQL 注入风险修复**
   - 添加 `BATCH_SIZE = 50` 常量
   - 循环分批执行 DELETE 操作

5. ✅ **FIX-009: 日志级别调整**
   - "跳过交易所取消" → `logger.info()`
   - "记录审计日志失败" → `logger.error()`

6. ✅ **FIX-010: 审计日志详情增强**
   - metadata 中增加 `failed_to_cancel` 和 `failed_to_delete` 详情

**修改文件**:
- `src/infrastructure/order_repository.py` (173 行修改)
- `src/interfaces/api.py` (48 行修改)

**测试结果**:
- ✅ 6/6 集成测试通过 (`tests/integration/test_batch_delete.py`)
- ✅ 28/28 单元测试通过 (`tests/unit/test_order_repository.py`)
- **总计**: 34/34 通过 (100%)

**Git 提交**:
- 4b0ab1d fix(backend): 修复 ORD-6 批量删除功能 P0/P1/P2 问题

**待修复的前端任务**:
- FIX-003: 前端批量删除逻辑统一
- FIX-006: 前端 audit_info 真实化
- FIX-007: 测试 Mock 完善
- FIX-008: 删除结果展示完善

---

### 2026-04-06 - 配置重构后启动问题修复 ✅

**任务来源**: 配置重构后服务无法正常启动，配置接口返回 503/500 错误

**问题根因**:
1. `ConfigManager` 方法签名变更（同步/异步混用）
2. 前端 API 路径 `/api/v1/config/*` 与后端实际路径不匹配
3. 过期间接工厂函数导致混淆

**完成工作**:

1. ✅ **后端启动修复** (`src/main.py`):
   - `get_user_config()` 添加 `await` 关键字
   - `get_merged_symbols()` 改用 `core_config.core_symbols`
   - `SignalPipeline` 参数更新为 `config_manager`
   - `_config_entry_repo` 添加 global 声明
   - 删除过期 `create_signal_pipeline()` 工厂函数
   - `check_api_key_permissions()` 暂时跳过（用户决策）

2. ✅ **后端 API 修复** (`src/interfaces/api.py`):
   - `get_core_config()` 移除 `await`（同步方法）- 3 处
   - `ConfigProfileRepository` 类型注解改为字符串格式

3. ✅ **前端 API 路径修复** (`web-front/src/api/config.ts`):
   - baseURL 从 `/api/v1/config` 改为 `/api`
   - 映射接口到后端实际路径

4. ✅ **前端组件修复** (`web-front/src/pages/config/BackupTab.tsx`):
   - 导入改为 `FormData` multipart/form-data 格式
   - 导出改为 GET 方法

5. ✅ **策略列表加载修复** (`web-front/src/pages/config/StrategiesTab.tsx`):
   - 提取 `response.data.strategies` 字段
   - 添加 `symbols`/`timeframes` 空值检查

**测试结果**:
- ✅ 服务启动成功，无 ERROR/503 日志
- ✅ `/api/config`: 200 OK
- ✅ `/api/strategies`: 200 OK
- ✅ `/api/strategy/params`: 200 OK
- ✅ `/api/config/profiles`: 200 OK
- ✅ `test_config_manager_db.py`: 40/40 通过

**遗留说明**:
- API Key 权限检查跳过（F-002），由开发者自行提供只读 API
- antd 废弃警告（`destroyOnClose`, `tip`）不影响功能

**Git 提交**:
- e90bde3 fix(frontend): 修复策略列表 symbols/timeframes 未定义错误
- ac6f223 fix(frontend): 修复策略列表加载错误
- 0617a51 fix(frontend): 修正配置 API 路径 - 从/api/v1/config 改为/api
- e088f2e fix(api): 修复配置接口 500 错误 - get_core_config() 同步调用
- cfc4516 fix: 配置重构后启动问题修复 - 中危和低危问题清理

**架构审查结论**: ⚠️ **有条件通过**（需开发者自行承担 API 权限风险）

---

### 2026-04-06 - 回测配置 KV 化开发完成 ✅

**主任务**: 回测配置 KV 化 - 滑点/资金费率配置

**完成工作**:
1. ✅ T1: ConfigEntryRepository 回测配置扩展 (51 测试通过)
2. ✅ T2: ConfigManager KV 配置接口 (17 测试通过)
3. ✅ T3: Backtester 配置集成 (16 测试通过)
4. ✅ T4: 回测配置 API 端点 (24 测试通过)
5. ✅ T5: 配置快照 KV 集成 (21 测试通过)
6. ✅ T7: 单元测试 (16 测试通过)
7. ✅ T8: 集成测试与验收 (24 测试通过)
8. ✅ P2 问题修复 (3 个问题全部修复)

**测试结果**: **132/132 测试全部通过** ✅

**配置默认值**:
| 配置项 | 键名 | 默认值 |
|--------|------|--------|
| 滑点率 | `backtest.slippage_rate` | 0.001 (0.1%) |
| 手续费率 | `backtest.fee_rate` | 0.0004 (0.04%) |
| 初始资金 | `backtest.initial_balance` | 10000 USDT |
| 止盈滑点 | `backtest.tp_slippage_rate` | 0.0005 (0.05%) |

**配置优先级** (已验证):
```
1. API 请求参数 (最高)
   ↓
2. KV 配置 (config_entries_v2)
   ↓
3. 代码默认值 (最低)
```

**Git 提交**:
- e9e7280 fix: 回测配置 KV 化 P2 问题修复
- 5b8d434 fix(P2-1): tp_slippage_rate 配置优先级修复
- d682bcc fix: 统一回测配置 API 错误响应格式
- 93c55f5 fix: 配置变更历史记录旧值
- 35f3e94 test(T8): 回测配置集成测试与验收
- 011eab7 test: T7 回测配置单元测试 - 配置优先级测试覆盖
- e6ca69d feat(api): 添加回测配置管理 API 端点 (T4)
- e1e0313 feat: 配置快照 KV 集成 - 支持在快照中包含 KV 配置数据
- b82be49 docs: 更新 T2 任务完成记录
- 8c75fd1 feat(T2): ConfigManager 回测配置 KV 接口实现
- 4c1eabc feat(T1): ConfigEntryRepository 回测配置扩展

**代码审查**:
- 综合评分：**97/100** (优秀)
- Clean Architecture: 95/100
- 类型安全：90/100
- 异步规范：95/100
- 错误处理：90/100
- 测试覆盖：95/100

---

### 2026-04-06 - P2-3: 配置变更历史旧值记录 ✅

**任务 ID**: #24
**优先级**: P2
**任务目标**: 修复 `save_backtest_configs()` 方法在记录配置变更历史时未记录旧值的问题

**完成工作**:
1. ✅ 修复 `src/application/config_manager.py`:
   - 在保存新配置前，先调用 `get_backtest_configs()` 查询旧配置
   - 将旧配置转换为字符串字典后传递给 `_log_config_change()`
   - `old_values` 参数从 `None` 改为实际查询的旧配置值

2. ✅ 添加测试 `tests/unit/test_config_manager_backtest_kv.py`:
   - `test_save_backtest_configs_records_old_values` - 验证更新操作记录旧值
   - `test_save_backtest_configs_first_save_has_no_old_values` - 验证首次保存的行为

3. ✅ 测试验收:
   - 所有 19 个回测配置测试通过 (100%)
   - 配置变更历史同时包含 `old_values` 和 `new_values`

**关键代码变更**:
```python
# 查询旧配置（用于记录变更历史）
old_configs = await self.get_backtest_configs(profile_name=profile_name)

# 记录配置变更历史（包含旧值和新值）
await self._log_config_change(
    entity_type="backtest_config",
    entity_id=f"profile:{profile_name}",
    action="UPDATE",
    old_values={k: str(v) for k, v in old_configs.items()} if old_configs else None,
    new_values={k: str(v) for k, v in configs.items()},
    changed_by=changed_by,
    change_summary=f"回测配置更新 - Profile:{profile_name}, 变更项:{len(configs)}",
)
```

**Git 提交**:
- 93c55f5 fix: 配置变更历史记录旧值 - save_backtest_configs 记录 old_values

