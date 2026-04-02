# 盯盘狗 🐶 Agent Team 配置

> **最后更新**: 2026-04-02 - 诊断分析师新增五维分析法
> **重要**: 本文档包含团队角色配置和进度管理规范

---

## 核心工作准则 ⭐⭐⭐

### 1. planning-with-files 标准进度管理（必须遵守）

**所有复杂任务必须使用 planning-with-files 三文件管理**：

| 文件 | 路径 | 用途 | 更新时机 |
|------|------|------|----------|
| **task_plan.md** | `docs/planning/task_plan.md` | 任务计划与阶段追踪 | 任务启动时创建计划，每个阶段完成后更新状态 |
| **findings.md** | `docs/planning/findings.md` | 研究发现与技术笔记 | 发现重要技术洞见、架构决策、踩坑记录时立即更新 |
| **progress.md** | `docs/planning/progress.md` | 进度日志与会话记录 | 每个会话结束时更新，记录完成的工作和待办事项 |

**检查清单**（每个会话结束前必须确认）:
- [ ] task_plan.md 已更新当前任务阶段状态
- [ ] findings.md 已记录今日技术发现
- [ ] progress.md 已更新今日进度日志
- [ ] 所有文件已 git add + commit + push

**违反后果**: 上下文丢失后无法追溯进度，导致重复工作和 AI 幻觉

### 2. 复杂任务工作流

**涉及前端 + 后端 + 测试的复杂任务必须走全自动流水线**：

```
【阶段 0】需求接收 → 【阶段 1】契约设计 → 【阶段 2】任务分解 → 【阶段 3】并行开发
                                                                    ↓
【阶段 6】提交汇报 ←─【阶段 5】测试执行 ←─【阶段 4】审查验证 ←──────────┘
```

**详细文档**: `docs/workflows/auto-pipeline.md`

### 3. 会话交接规范

**每个会话结束时**（尤其是跨天/跨会话的任务）:

1. **创建交接文档**: `docs/planning/<session-id>-handoff.md`
2. **内容包括**:
   - 已完成工作详情
   - 审查发现的问题清单
   - 下一步计划与预计工时
   - 相关文件索引
3. **更新 progress.md**: 记录今日完成工作和待办事项
4. **Git 提交**: 所有代码和文档提交并推送

---

## Team 结构

```
┌─────────────────────────────────────────────────┐
│              Team Coordinator                    │
│         (任务分解 + 协调 + 结果整合)              │
└─────────────────────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┬─────────────┬─────────────┐
        ▼             ▼             ▼             ▼             ▼
┌───────────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌──────────────┐
│ Frontend Dev  │ │ Backend   │ │   QA      │ │  Code     ││  Diagnostic  │
│    (前端)     │ │  (后端)   │ │  Tester   │ │ Reviewer  ││   Analyst    │
│               │ │           │ │  (测试)   │ │  (审查)   ││  (诊断分析师)│
└───────────────┘ └───────────┘ └───────────┘ └───────────┘ └──────────────┘
```

---

## 角色技能说明

### Team Coordinator (`/coordinator`)
- **职责**: 任务分解、角色调度、进度追踪、结果整合
- **触发场景**: 完整功能开发、跨模块任务
- **使用方式**: 输入 `/coordinator` 或直接描述需求

### Frontend Developer (`/frontend`)
- **职责**: React + TypeScript + TailwindCSS 前端实现
- **触发场景**: UI 组件、页面、样式、交互
- **使用方式**: 输入 `/frontend` 或分配前端任务

### Backend Developer (`/backend`)
- **职责**: Python + FastAPI + asyncio 后端实现
- **触发场景**: API、领域模型、基础设施
- **使用方式**: 输入 `/backend` 或分配后端任务

### QA Tester (`/qa`)
- **职责**: 测试策略、单元测试、集成测试
- **触发场景**: 编写测试、验证功能、回归测试
- **使用方式**: 输入 `/qa` 或分配测试任务

### Code Reviewer (`/reviewer`)
- **职责**: 代码审查、架构一致性检查、安全隐患识别
- **触发场景**: 代码完成后审查、架构把关、合并前审查
- **使用方式**: 输入 `/reviewer` 或分配审查任务

### Diagnostic Analyst (`/diagnostic`)
- **职责**: 问题根因分析、共性问题排查、技术债识别
- **核心原则**: **只分析问题，不修改代码**
- **专长**: 五维分析法（请求/响应/日志/数据库/代码）
- **触发场景**: 用户报告问题、疑难杂症诊断、系统性问题排查
- **使用方式**: 输入 `/diagnostic` 或分配诊断任务

---

## 使用方式

### 方式 1: 角色切换命令
```bash
# 切换到协调器角色
/coordinator

# 切换到前端角色
/frontend

# 切换到后端角色
/backend

# 切换到测试角色
/qa
```

### 方式 2: 直接描述需求（自动分解）
```
用户：我想添加一个策略预览功能，用户可以点击按钮测试当前策略

→ Team Coordinator 自动分解：
   - 后端：实现 /api/strategies/preview 接口
   - 前端：实现预览按钮和结果展示
   - 测试：编写对应测试用例
```

### 方式 3: 并行调度（使用 Agent 工具）
```python
# 并行执行多个角色
Agent(subagent_type="frontend-dev", prompt="...")
Agent(subagent_type="backend-dev", prompt="...")
Agent(subagent_type="qa-tester", prompt="...")
```

---

## 任务分解示例

### 示例 1: 新功能开发
**需求**: "添加策略模板保存功能"

**分解结果**:
| 任务 ID | 角色 | 任务描述 |
|---------|------|----------|
| T1 | 后端 | 实现 POST /api/strategies 接口 |
| T2 | 后端 | 实现 GET /api/strategies 列表接口 |
| T3 | 后端 | 实现 StrategyRepository 数据库操作 |
| T4 | 前端 | 实现保存按钮和表单 |
| T5 | 前端 | 实现策略列表展示 |
| T6 | 测试 | 后端 API 测试 |
| T7 | 测试 | 前端组件测试 |

### 示例 2: Bug 修复
**需求**: "MTF 过滤器表单无法选择大周期"

**分解结果**:
| 任务 ID | 角色 | 任务描述 |
|---------|------|----------|
| T1 | 后端 | 检查 Schema 是否正确下发 |
| T2 | 前端 | 移除硬编码，改用动态 Schema |
| T3 | 测试 | 验证所有过滤器类型 |

---

## 文件边界规则 (File Boundaries)

> ⚠️ **核心原则**: 每个角色只能修改自己负责的文件，避免协作冲突

### 文件所有权矩阵

| 文件路径 | Frontend | Backend | QA | Coordinator | Reviewer | Diagnostic |
|----------|----------|---------|----|-------------|----------|------------|
| `web-front/**` | ✅ 全权 | ❌ 禁止 | ⚠️ 仅测试 | ⚠️ 仅配置 | 🔍 审查 | 🔍 审查 |
| `src/**` | ❌ 禁止 | ✅ 全权 | ⚠️ 仅测试 | ⚠️ 仅协调 | ✅ 修改测试 | 🔍 审查 |
| `tests/**` | ⚠️ 协助 | ⚠️ 协助 | ✅ 全权 | ⚠️ 仅协调 | ✅ 修改测试 | ⚠️ 运行验证 |
| `config/**` | ❌ 禁止 | ✅ 全权 | ❌ 禁止 | ⚠️ 仅协调 | 🔍 审查 | 🔍 审查 |
| `CLAUDE.md` | ❌ 禁止 | ❌ 禁止 | ❌ 禁止 | ✅ 全权 | 🔍 审查 | ❌ 禁止 |
| `.claude/team/**` | ⚠️ 建议 | ⚠️ 建议 | ⚠️ 建议 | ✅ 全权 | 🔍 审查 | ❌ 禁止 |
| `docs/**` | ⚠️ 建议 | ⚠️ 建议 | ⚠️ 建议 | ✅ 全权 | ⚠️ 建议 | ✅ 全权 |

**图例**: ✅ 全权负责 | ❌ 禁止修改 | ⚠️ 有限权限 | 🔍 仅审查

### 各角色详细边界

#### Frontend 边界
```
✅ 可修改：web-front/** (全部前端文件)
❌ 禁止：src/**, tests/**, config/**
```

#### Backend 边界
```
✅ 可修改：src/**, config/**
❌ 禁止：web-front/**
```

#### QA 边界
```
✅ 可修改：tests/** (全部测试文件)
❌ 禁止：src/** (业务代码), web-front/** (前端代码)
```

#### Coordinator 边界
```
✅ 可修改：CLAUDE.md, .claude/team/**
⚠️ 协调：跨角色文件变更
```

#### Reviewer 边界
```
✅ 可修改：tests/** (测试代码)
🔍 审查：src/**, web-front/**, config/** (仅审查意见，不直接修改)
```

#### Diagnostic Analyst 边界
```
✅ 可修改：docs/** (诊断报告、分析笔记)
🔍 审查：src/**, web-front/**, config/** (仅分析问题，不修改代码)
⚠️ 运行：tests/** (运行测试验证假设，但不修改测试代码)
```

### 冲突解决流程

```
1. 发现冲突 → 立即停止修改
2. 通知 Coordinator → 说明冲突情况
3. Coordinator 分析 → 重新分配任务
4. 按新分配执行 → 验证无冲突后继续
```

### 常见冲突场景

| 场景 | 原因 | 解决方案 |
|------|------|----------|
| API 字段不匹配 | 后端改了返回结构，前端未更新 | Coordinator 同步分配两个任务 |
| 测试失败需改业务代码 | QA 发现 Bug | QA 报告 → Coordinator 分配给对应 Dev |
| 多人改同一文件 | 任务分解不清 | Coordinator 重新分配，使用 git 分支 |

---

## 最佳实践

### ✅ 推荐做法
- 完整功能开发优先使用 Team Coordinator 模式
- 独立任务直接调用对应角色
- 测试先行：先写测试再实现功能
- 并行执行：前端和后端任务同时进行

### ❌ 避免做法
- 单一角色处理全栈任务（效率低）
- 跳过测试直接交付
- 接口未对齐就合并代码
- 缺少任务追踪（使用 TaskCreate）

---

## 配置说明

### 技能文件位置
```
.claude/team/
├── frontend-dev/SKILL.md       # 前端开发专家
├── backend-dev/SKILL.md        # 后端开发专家
├── qa-tester/SKILL.md          # 质量保障专家
├── code-reviewer/SKILL.md      # 代码审查员
├── diagnostic-analyst/SKILL.md # 诊断分析师
└── team-coordinator/SKILL.md   # 团队协调器
```

### 如何扩展团队
添加新角色：
1. 创建 `.claude/team/<role-name>/SKILL.md`
2. 定义角色职责、技术栈、工作流程
3. 在 `README.md` 中添加角色说明

---

## 全局技能集成 (Global Skills Integration)

**每个 Agent Team 成员都应主动调用全局 skills 来提升工作质量：**

### 全局 Skills 与 Agent 映射

| Agent 角色 | 应调用的全局 Skills | 使用场景 |
|-----------|---------------------|----------|
| **Frontend Dev** | `ui-ux-pro-max` | UI 设计、配色方案、组件样式优化 |
| | `frontend-design` | 高设计质量的前端实现 |
| | `web-artifacts-builder` | 复杂多组件 Web 工件 |
| | `code-simplifier` | 代码完成后优化简化 |
| | `banner-design` | Banner/视觉设计 |
| | `slides` | 幻灯片设计 |
| | `brand-guidelines` | 品牌规范指导 |
| **Backend Dev** | `code-simplifier` | 代码完成后优化简化 |
| | `brainstorming` | 复杂需求分析 |
| | `systematic-debugging` | 遇到 Bug 时调试 |
| **QA Tester** | `webapp-testing` | 前端 Playwright E2E 测试 |
| | `code-simplifier` | 测试代码简化 |
| | `systematic-debugging` | 测试失败分析 |
| **Coordinator** | `brainstorming` | 需求分解前探索 |
| | `planning-with-files-zh` | 制定执行计划（替代 writing-plans/executing-plans） |
| | `dispatching-parallel-agents` | 并行任务调度 |
| | `finishing-a-development-branch` | 完成分支合并 |
| | `verification-before-completion` | 完成前验证 |
| | `requesting-code-review` | 请求正式审查 |
| **Code Reviewer** | `code-review` | 正式代码审查流程 |
| | `code-simplifier` | 识别代码复杂度问题 |
| **Diagnostic Analyst** | `systematic-debugging` | 系统性 Bug 排查 |
| | `brainstorming` | 复杂问题根因分析 |
| | `planning-with-files-zh` | 制定诊断计划 |

### 调用方式

```python
# 方式 1: 使用 Agent 工具调用
Agent(subagent_type="ui-ux-pro-max", prompt="为递归逻辑树渲染器设计配色方案")

# 方式 2: 使用 Slash Command（如果已注册）
/simplify  # 简化当前代码

# 方式 3: 在分配任务时提醒
Agent(subagent_type="frontend-dev",
      prompt="实现预览按钮，完成后调用 code-simplifier 优化代码")
```

### 各角色技能调用时机

```
Frontend Dev 工作流:
  1. 接收需求
  2. 需要 UI 设计 → 调用 ui-ux-pro-max
  3. 实现组件
  4. 完成后 → 调用 code-simplifier 优化

Backend Dev 工作流:
  1. 接收需求
  2. 复杂需求 → 调用 brainstorming 分析
  3. 实现功能
  4. 完成后 → 调用 code-simplifier 优化
  5. 遇到 Bug → 调用 systematic-debugging

QA Tester 工作流:
  1. 编写测试
  2. E2E 测试 → 调用 webapp-testing
  3. 测试失败 → 调用 systematic-debugging 分析
  4. 完成后 → 调用 code-simplifier 简化测试代码

Diagnostic Analyst 工作流:
  1. 接收问题报告
  2. 问题澄清 → 复述问题、确认期望行为
  3. 生成假设 → 列出 3-5 个可能原因
  4. 系统排查 → 调用 systematic-debugging
  5. 根因分析 → 调用 brainstorming 进行 5 Why 分析
  6. 输出报告 → 调用 planning-with-files-zh 整理诊断报告

Coordinator 工作流:
  1. 接收需求
  2. 需求模糊 → 调用 brainstorming 探索
  3. 复杂项目 → 调用 planning-with-files-zh 制定计划
     → 文件创建在 docs/planning/ 目录
  4. 执行阶段 → 读取 docs/planning/task_plan.md 继续执行
     → 或调用 dispatching-parallel-agents 并行调度
  5. 完成前 → 调用 verification-before-completion 验证
```

---

## 故障排除

### 问题 1: 子 Agent 无法加载技能
**解决**: 在 prompt 中明确指定技能文件路径
```
prompt="请阅读 .claude/team/backend-dev/SKILL.md 并按规范实现..."
```

### 问题 2: 任务依赖顺序混乱
**解决**: 使用 TaskCreate 设置 `addBlockedBy` 依赖
```python
TaskCreate(subject="前端实现", addBlockedBy=["T1"])  # 等待后端完成
```

### 问题 3: 接口定义不一致
**解决**: Team Coordinator 主持接口对齐会议，输出契约文档

---

*本团队配置旨在提高开发效率，确保代码质量和接口对齐。*
