# 子任务 F 和 E 实现计划

**目标**: 将平铺式策略引擎升级为递归逻辑树引擎，并实现前端递归渲染组件

**架构**:
- 后端：Pydantic 递归模型 + Discriminator Union + 递归评估算法
- 前端：React 递归组件 + Schema 驱动表单 + Trace 树可视化

**依赖关系**:
```
子任务 F (后端) → 子任务 E (前端)
```

**阶段概览**:
| 阶段 | 任务 | 状态 | 负责人 |
|------|------|------|--------|
| F-1 | 定义递归 LogicNode 类型 | completed | backend-dev |
| F-2 | 实现递归评估引擎 | completed | backend-dev |
| F-3 | 升级 StrategyDefinition | completed | backend-dev |
| F-4 | 实现热预览接口 | completed | backend-dev |
| E-1 | 定义前端递归类型 | completed | frontend-dev |
| E-2 | 实现递归渲染组件 | completed | frontend-dev |
| E-3 | 实现热预览交互 | completed | frontend-dev |

---

## 阶段详情

### 阶段 F-1: 定义递归 LogicNode 类型

**目标**: 创建强类型递归数据模型

**文件**:
- 创建：`src/domain/logic_tree.py`
- 修改：`src/domain/models.py`

**步骤**:
1. [ ] 创建递归 LogicNode 类型定义
2. [ ] 编写单元测试验证类型定义
3. [ ] 运行类型检查 `python -c "from src.domain.logic_tree import LogicNode; print('OK')"`
4. [ ] 提交

**验收标准**:
- 支持 AND/OR/NOT 逻辑门
- 支持 Trigger 和 Filter 叶子节点
- 使用 Discriminator Union
- 限制嵌套深度 ≤ 3

---

### 阶段 F-2: 实现递归评估引擎

**目标**: 实现 `evaluate_node()` 递归函数

**文件**:
- 创建：`src/domain/recursive_engine.py`
- 测试：`tests/unit/test_recursive_engine.py`

**步骤**:
1. [ ] 编写单元测试 (覆盖 AND/OR/NOT/Leaf 场景)
2. [ ] 运行测试验证失败
3. [ ] 实现 `evaluate_node()` 函数
4. [ ] 运行测试验证通过
5. [ ] 提交

**验收标准**:
- AND 节点：all() 短路判定
- OR 节点：any() 短路判定
- NOT 节点：结果反转
- 返回 Trace 树记录评估路径

---

### 阶段 F-3: 升级 StrategyDefinition

**目标**: 支持递归逻辑树配置

**文件**:
- 修改：`src/domain/models.py`
- 修改：`src/domain/strategy_engine.py`

**步骤**:
1. [ ] 更新 `StrategyDefinition` 添加 `logic_tree` 字段
2. [ ] 实现从平铺模式迁移到递归树的验证器
3. [ ] 更新 `create_dynamic_runner()` 支持递归树
4. [ ] 向后兼容测试
5. [ ] 提交

**验收标准**:
- 新策略使用递归树
- 旧策略自动迁移
- 向后兼容

---

### 阶段 F-4: 实现热预览接口

**目标**: 实现 `POST /api/strategies/preview`

**文件**:
- 修改：`src/interfaces/api.py`

**步骤**:
1. [ ] 定义 PreviewRequest/PreviewResponse 模型
2. [ ] 实现 preview 端点
3. [ ] 临时 Runner 执行评估
4. [ ] 返回完整 Trace 树
5. [ ] 提交

**验收标准**:
- 不持久化
- 不热重载
- 返回评估路径追踪

---

### 阶段 E-1: 定义前端递归类型

**目标**: TypeScript 递归类型定义

**文件**:
- 修改：`web-front/src/types/strategy.ts`

**步骤**:
1. [ ] 定义 AndNode, OrNode, NotNode 接口
2. [ ] 定义 TriggerNode, FilterNode 接口
3. [ ] 定义 LogicNode 联合类型
4. [ ] 运行 TypeScript 类型检查
5. [ ] 提交

**验收标准**:
- 与后端模型对齐
- TypeScript 无类型错误

---

### 阶段 E-2: 实现递归渲染组件

**目标**: 递归组件 `NodeRenderer`

**文件**:
- 创建：`web-front/src/components/NodeRenderer.tsx`
- 创建：`web-front/src/components/LogicGateControl.tsx`
- 创建：`web-front/src/components/LeafNodeForm.tsx`

**步骤**:
1. [ ] 创建逻辑门控制组件
2. [ ] 创建叶子节点表单组件
3. [ ] 创建递归渲染器
4. [ ] 集成到策略工作台
5. [ ] 提交

**验收标准**:
- 支持递归渲染
- Schema 驱动表单
- 视觉层次清晰

---

### 阶段 E-3: 实现热预览交互

**目标**: "立即测试" 按钮 + Trace 树可视化

**文件**:
- 修改：`web-front/src/pages/StrategyWorkbench.tsx`
- 修改：`web-front/src/lib/api.ts`

**步骤**:
1. [ ] 添加预览 API 调用函数
2. [ ] 添加"立即测试"按钮
3. [ ] 实现 Trace 树视觉渲染
4. [ ] 成功/失败状态标记
5. [ ] 提交

**验收标准**:
- 点击按钮发送预览请求
- 渲染评估结果树
- 节点标记✅/❌

---

## 错误日志

| 错误 | 尝试次数 | 解决方案 |
|------|---------|---------|
| - | - | - |

---

## 关键决策

| 决策 | 原因 | 日期 |
|------|------|------|
| 使用 Pydantic Discriminator | 类型安全、自动 Schema 生成 | - |
| 限制递归深度≤3 | 防止无限递归、UI 可读性 | - |
| Trace 树返回 | 前端可视化需求 | - |

---

## 相关文件

- `docs/tasks/2026-03-25-子任务 F-强类型递归引擎与 Schema 自动化开发.md`
- `docs/tasks/2026-03-25-子任务 E-递归表单驱动与动态预览重构.md`
- `src/domain/models.py`
- `src/domain/strategy_engine.py`
- `web-front/src/types/strategy.ts`
- `web-front/src/components/`

---

## 第二阶段：交互升维（当前阶段）

**目标**: 完成技术债清理和核心重构，实现策略模板到实盘监控的无缝对接

### 阶段概览
| 阶段 | 任务 | 状态 | 负责人 | 优先级 |
|------|------|------|--------|--------|
| S2-2 | 统一 TraceEvent 字段命名 | ✅ completed | backend-dev | 高 |
| S2-4 | 信号标签动态化（子任务 C） | ⏸️ pending | backend-dev | 高 |
| S2-1 | 一键下发实盘热重载（子任务 A） | ⏸️ pending | backend-dev | 高 |
| S2-3 | 前端硬编码组件清理 | ⏸️ pending | frontend-dev | 中 |

---

## 执行顺序与依赖

```
S2-2 (字段统一) ✅
    ↓
S2-4 (信号标签动态化) ← 独立，可先行
    ↓
S2-1 (实盘热重载) ← 依赖 S2-4 完成
    ↓
S2-3 (前端清理) ← 独立，可并行
```

---

### 阶段 S2-2: 统一 TraceEvent 字段命名 ✅

**完成时间**: 2026-03-26

**文件**:
- 修改：`src/domain/filter_factory.py` - `TraceEvent.filter_name` → `node_name`, `context_data` → `metadata`
- 修改：`src/domain/recursive_engine.py` - `TraceNode.details` → `metadata`
- 修改：`web-front/src/lib/api.ts` - `TraceEvent.stage` → `node_name`, `details` → `metadata`
- 修改：`tests/unit/test_filter_factory.py` - 测试适配
- 修改：`tests/unit/test_recursive_engine.py` - 测试适配
- 修改：`tests/unit/test_preview_api.py` - 测试适配

**测试结果**:
```
======================== 48 passed, 3 warnings in 0.30s ========================
```

---

### 阶段 S2-4: 信号标签动态化（子任务 C）

**目标**: 移除 `ema_trend`/`mtf_status` 硬编码字段，改用动态 tags 数组

**文件**:
- 修改：`src/domain/models.py` - SignalResult 模型
- 修改：`src/domain/risk_calculator.py` - 移除硬编码标签
- 修改：`src/application/signal_pipeline.py` - 动态标签生成逻辑
- 修改：`src/infrastructure/notifier.py` - 通知消息格式化
- 修改：`src/infrastructure/signal_repository.py` - 落库字段升级
- 修改：`web-front/src/lib/api.ts` - Signal 接口定义

**步骤**:
1. [ ] 更新 SignalResult 模型，添加 `tags: List[Dict[str, str]]`
2. [ ] 移除 `ema_trend`/`mtf_status` 字段
3. [ ] 更新 risk_calculator.calculate_signal_result() 签名
4. [ ] 更新 signal_pipeline.process_kline() 动态标签生成
5. [ ] 更新 notifier 通知卡片渲染
6. [ ] 更新 signal_repository 落库逻辑 (tags_json)
7. [ ] 更新前端 Signal 接口
8. [ ] 编写测试验证

**验收标准**:
- 信号结果支持动态标签数组
- 通知卡片显示动态标签内容
- 移除对 Legacy 引擎的依赖
- 向后兼容旧数据格式

---

### 阶段 S2-1: 一键下发实盘热重载（子任务 A）

**目标**: 实现策略模板到实盘监控的无缝下发，支持热重载不重启

**文件**:
- 修改：`src/application/signal_pipeline.py` - 热重载 Observer 模式
- 修改：`src/application/config_manager.py` - 配置监听器
- 修改：`src/interfaces/api.py` - 新增 `/api/strategies/{id}/apply` 端点
- 新增：`src/infrastructure/strategy_repository.py` - 策略模板仓储

**步骤**:
1. [ ] 实现 ConfigManager 异步监听器注册
2. [ ] 实现 SignalPipeline._build_and_warmup_runner()
3. [ ] 添加 asyncio.Lock() 保护并发竞争
4. [ ] 实现异步 Queue Worker 剥离 SQLite 同步背压
5. [ ] 实现配置变更时清空信号冷却缓存
6. [ ] 新增策略模板 Apply 端点
7. [ ] 更新 main.py 入口函数
8. [ ] 编写测试验证

**验收标准**:
- 策略模板一键下发实盘
- 配置热重载不重启进程
- EMA 等有状态指标无缝恢复
- 无并发竞争条件
- SQLite 异步批量落盘

---

### 阶段 S2-3: 前端硬编码组件清理

**目标**: 移除所有硬编码的过滤器组件，实现 100% Schema 驱动

**待清理组件**:
- `StrategyBuilder.tsx` → 替换为递归 NodeRenderer
- `PinbarParamsEditor.tsx` → 已移除
- `EmaFilterEditor.tsx` → 已移除
- `MtfFilterEditor.tsx` → 待移除

**文件**:
- 删除：`web-front/src/components/StrategyBuilder.tsx` (如仍存在)
- 删除：`web-front/src/components/*Editor.tsx` (所有硬编码编辑器)

**步骤**:
1. [ ] 检查并列出所有硬编码组件
2. [ ] 确认 NodeRenderer 已完全替代
3. [ ] 删除旧组件
4. [ ] 更新导入引用
5. [ ] 运行 TypeScript 编译验证

**验收标准**:
- 移除所有硬编码编辑器组件
- TypeScript 编译无错误
- 前端 100% Schema 驱动

---

## 第三阶段：风控执行（已完成）

**完成时间**: 2026-03-27

**交付物**:
- S3-1: MTF 多周期数据对齐优化 ✅
- S3-2: 动态风险头寸计算（方案 B） ✅
- S3-2: 16 个集成测试 ✅
- 测试修复：test_signal_repository.py 修复 ✅

**测试结果**:
```
tests/unit/test_risk_calculator.py: 35/35 通过 (100%)
tests/integration/test_risk_headroom.py: 16/16 通过 (100%)
tests/integration/test_mtf_e2e.py: 6/6 通过 (100%)
tests/unit/test_signal_repository.py: 21/21 通过 (100%)
tests/unit/: 329/329 通过 (100%)
tests/integration/: 41/41 通过 (100%)
总计：370/370 通过 (100%)
```

**Git 提交**:
- S3-2 核心功能：`1aa9619`
- S3-1 MTF 对齐：`93edce5`
- S3-2 集成测试：会话 13
- S3 测试修复：`8c5eb73`

---

### 阶段 S3-2: 动态风险头寸计算 ✅

**目标**: 根据账户实时状态动态计算风险头寸（方案 B）

**完成时间**: 2026-03-27

**交付物**:
- `src/domain/models.py` - RiskConfig 新增 `max_total_exposure` 字段
- `src/domain/risk_calculator.py` - 升级 `calculate_position_size()` 实现方案 B
- `tests/unit/test_risk_calculator.py` - 21 个新增测试用例（35 个测试 100% 通过）
- `tests/integration/test_risk_headroom.py` - 16 个集成测试（100% 通过）

**方案 B 逻辑**:
- 使用 `available_balance` 而非 `total_balance`
- 考虑当前持仓占用（通过 `current_exposure_ratio`）
- 当持仓接近 `max_total_exposure` (80%) 时自动降低风险
- 无可用风险空间时返回 0 仓位

**测试结果**:
```
tests/unit/test_risk_calculator.py: 35/35 通过 (100%)
tests/integration/test_risk_headroom.py: 16/16 通过 (100%)
tests/integration/ 总计：41/41 通过 (100%)
```

**Git 提交**: `1aa9619`

---

### 阶段 S3-1: 多周期数据对齐优化 ✅

**目标**: 优化 MTF 过滤器的多周期数据对齐逻辑

**完成时间**: 2026-03-27

**交付物**:
- `src/utils/timeframe_utils.py` - MTF 周期映射工具
- `src/application/config_manager.py` - 新增 MTF 配置字段
- `config/core.yaml` - MTF 默认配置
- `tests/integration/test_mtf_e2e.py` - 6 个集成测试

**测试结果**:
```
tests/integration/test_mtf_e2e.py: 6/6 通过 (100%)
```

**Git 提交**: `93edce5`

---

### 阶段 S3-3: 交易所挂单集成（可选） ⏸️ 暂缓

**目标**: 集成交易所挂单功能（需用户授权）

**状态**: 第三阶段完成后再评估

---

## 第四阶段：工业化调优（未来规划）

### 阶段 S4-1: 配置快照版本化（Rollback）

### 阶段 S4-2: 异步 I/O 队列

### 阶段 S4-3: 指标计算缓存
