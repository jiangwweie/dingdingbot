# Agent Team 快速开始指南

> **最后更新**: 2026-03-25

---

## 🚀 30 秒快速开始

### 方式 1：最简单 - 直接描述需求

```bash
# 输入 /pm 然后描述你的需求
/pm

我想添加一个策略预览功能，用户可以：
1. 在策略编辑器中点击"测试"按钮
2. 输入测试参数
3. 看到测试结果（通过/失败，以及失败原因）
```

**会发生什么**：
1. PM 自动分解任务
2. 并行调用 Backend、Frontend、QA
3. 每个角色只修改自己负责的文件
4. 最后汇总输出

---

### 方式 2：指定角色 - 单点任务

```bash
# 只需要后端改动能直接调用
/backend

为 /api/strategies 添加一个新的 POST 接口
用于保存策略模板，接收以下参数：
- name: 策略名称
- description: 描述
- strategy_json: 策略配置 JSON
```

```bash
# 只需要前端改动能直接调用
/frontend

在策略编辑器页面添加一个"保存"按钮
点击后弹出表单，包含名称、描述输入框
```

```bash
# 需要测试时调用
/qa

为刚才添加的策略保存接口编写测试
覆盖正常保存、参数缺失、JSON 格式错误等场景
```

---

## 📋 完整工作流程示例

### 示例：开发"策略预览"功能

#### 步骤 1：启动 PM
```bash
/pm
```

#### 步骤 2：描述需求
```
我想实现一个策略预览功能：

用户故事：
- 用户在策略工作台编辑策略时
- 可以点击"立即测试"按钮
- 输入测试参数（币种、周期等）
- 看到测试结果（信号是否触发，以及判定路径）

技术要求：
- 后端需要提供预览接口
- 前端需要添加测试按钮和结果展示
- 需要有测试覆盖
```

#### 步骤 3：Coordinator 分解任务

Coordinator 会自动创建以下任务：

```
┌─────────────────────────────────────────────────────┐
│ 任务分解结果                                        │
├─────────────────────────────────────────────────────┤
│ Task 1 [Backend]   实现 /api/strategies/preview    │
│ Task 2 [Backend]   实现 evaluate_node() 递归引擎   │
│ Task 3 [Frontend]  实现预览按钮组件                │
│ Task 4 [Frontend]  实现结果展示 Modal               │
│ Task 5 [QA]        编写后端接口测试                │
│ Task 6 [QA]        编写前端组件测试                │
└─────────────────────────────────────────────────────┘
```

#### 步骤 4：并行执行

```python
# Coordinator 并行调用三个角色
Agent(subagent_type="backend-dev", prompt="实现预览接口...")
Agent(subagent_type="frontend-dev", prompt="实现预览按钮...")
Agent(subagent_type="qa-tester", prompt="编写测试...")
```

#### 步骤 5：等待完成 → 汇总输出

```markdown
## 任务完成汇总

### 后端实现 (by backend-dev)
- ✅ POST /api/strategies/preview 接口
- ✅ evaluate_node() 递归评估引擎
- ✅ 单元测试 15 个，覆盖率 92%

### 前端实现 (by frontend-dev)
- ✅ PreviewButton 组件
- ✅ PreviewResult Modal
- ✅ TypeScript 类型定义完整

### 测试覆盖 (by qa-tester)
- ✅ 后端接口测试 8 个
- ✅ 前端组件测试 4 个
- ✅ 全部通过

### 验证命令
pytest tests/unit/test_preview_api.py -v
cd web-front && npm test
```

---

## 🎯 常用场景速查

### 场景 1：添加新 API 接口
```bash
/backend

添加一个新的 API 接口：
GET /api/strategies/{id}/history

返回指定策略的历史信号记录
分页参数：page, page_size
```

### 场景 2：修改现有功能
```bash
/frontend

修改策略列表页面：
- 在每行添加"编辑"按钮
- 点击后跳转到编辑页面，携带策略 ID
```

### 场景 3：修复 Bug
```bash
/qa

发现 Bug：策略保存接口在名称重复时报 500 错误
期望：返回 409 Conflict，提示"名称已存在"

请编写测试复现这个问题
```

### 场景 4：完整功能开发
```bash
/coordinator

实现"策略模板导入/导出"功能：
1. 用户可以导出策略为 JSON 文件
2. 用户可以导入 JSON 文件创建新策略
3. 导入时校验格式，重复名称提示

需要后端、前端、测试配合
```

---

## ⚠️ 注意事项

### ✅ 推荐做法
- 完整功能开发 → 使用 `/coordinator`
- 单一角色任务 → 直接调用 `/frontend`、`backend`、`qa`
- 任务完成后 → 等待 Coordinator 汇总再验收

### ❌ 避免做法
- 同时调用多个角色做同一件事（会冲突）
- 跳过 Coordinator 直接并行多个 Agent
- 修改不属于自己负责的文件

---

## 🔧 故障排除

### 问题 1：角色说"无权修改此文件"
**原因**：任务分配给了错误的角色

**解决**：
```bash
/coordinator
刚才的任务分配有误，请重新分解：
- XX 文件应该由 frontend-dev 修改
- XX 文件应该由 backend-dev 修改
```

### 问题 2：多个角色报告冲突
**原因**：同时修改了同一文件

**解决**：
```bash
/coordinator
检测到文件冲突：XX 文件被多个角色修改
请重新协调任务边界，确保每人只改自己的文件
```

### 问题 3：任务卡住无法继续
**原因**：依赖任务未完成

**解决**：
```bash
/coordinator
Task X 依赖 Task Y 完成，但 Task Y 卡住了
请检查依赖关系，调整执行顺序
```

---

## 📚 相关文档

- `.claude/team/frontend-dev/SKILL.md` - 前端角色详细规范
- `.claude/team/backend-dev/SKILL.md` - 后端角色详细规范
- `.claude/team/qa-tester/SKILL.md` - 测试角色详细规范
- `.claude/team/project-manager/SKILL.md` - 项目经理详细规范 ⭐

---

## 💡 最佳实践

### 任务分解原则
1. **原子性**：每个任务只做一个事
2. **独立性**：任务之间无依赖或依赖清晰
3. **可测试**：每个任务有明确的验收标准

### 沟通技巧
1. **具体**：说明要修改的文件路径
2. **完整**：提供输入/输出示例
3. **可验证**：说明如何验证完成

### 文件边界
1. **先确认**：不确定文件归属时先问 Coordinator
2. **不越界**：只改自己负责的文件
3. **早报告**：发现冲突立即停止并报告

---

*开始使用吧！输入 `/coordinator` 然后描述你的第一个需求！*
