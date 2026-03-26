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
| F-2 | 实现递归评估引擎 | pending | backend-dev |
| F-3 | 升级 StrategyDefinition | pending | backend-dev |
| F-4 | 实现热预览接口 | pending | backend-dev |
| E-1 | 定义前端递归类型 | pending | frontend-dev |
| E-2 | 实现递归渲染组件 | pending | frontend-dev |
| E-3 | 实现热预览交互 | pending | frontend-dev |

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
