# 盯盘狗 🐶 Agent Team 配置

> **最后更新**: 2026-04-02 - v2.2 交互式沟通增强
> **重要**: 本文档包含团队角色配置和进度管理规范
> **核心改进**: 需求澄清和技术方案共创必须与用户交互式对话，禁止闷头写文档

---

## ⚠️ 全局强制要求 (红线)

### 所有成员必须使用 `planning-with-files-zh` 管理进度

**禁止使用**: 内置的 `writing-plans` / `executing-plans` 技能

**强制使用**: `planning-with-files-zh` 技能

**原因**:
- 内置 planning 不创建文件，上下文丢失后进度无法追溯
- `planning-with-files-zh` 强制创建持久化文件到 `docs/planning/` 目录
- 支持会话恢复和进度回溯

**三文件管理规范**:

| 文件 | 路径 | 用途 | 更新时机 |
|------|------|------|----------|
| **task_plan.md** | `docs/planning/task_plan.md` | 任务计划与阶段追踪 | 每个阶段完成后更新状态 |
| **findings.md** | `docs/planning/findings.md` | 研究发现与技术笔记 | 发现重要技术洞见时立即更新 |
| **progress.md** | `docs/planning/progress.md` | 进度日志与会话记录 | 每个会话结束时更新 |

**违反处理**: Code Reviewer 在审查时必须检查是否使用了 `planning-with-files-zh`，未使用则标记为 P0 问题。

---

## ⭐ 核心改进：交互式沟通 (v2.2)

### 核心原则

| 原则 | 说明 |
|------|------|
| **先对话，后文档** | 任何文档编写前必须先与用户交互式澄清 |
| **先共创，后决策** | 技术方案选项与用户共创，让用户理解 trade-off |
| **确认前置** | 用户确认环节从第 4 步提前到第 0/1/2 步 |
| **文档是对话的产物** | 文档是对话结果的记录，不是决策本身 |

### 交互式沟通检查点

| 阶段 | 负责人 | 强制检查点 |
|------|--------|-----------|
| **需求收集** | PdM | 提出至少 3 个澄清问题，复述需求并获得确认 |
| **产品定义** | PdM | 写 PRD 前与用户确认需求理解一致 |
| **架构设计** | Arch | 提出至少 2 个技术方案，解释 trade-off，获得用户确认 |
| **任务分解** | PM | 产品范围 + 技术方案 + 任务计划三重确认 |

### 违反处理

| 违规行为 | 处理 |
|----------|------|
| PdM 闷头写 PRD，不先对话澄清 | Code Reviewer 标记为 P0 问题 |
| Arch 闭门造车写 ADR，不提供方案选项 | Code Reviewer 标记为 P0 问题 |
| 跳过 brainstorming 技能 | 任务标记为"需改进"，返回重做 |

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
┌─────────────────────────────────────────────────────────────────┐
│                    Project Manager (统一入口)                    │
│              (用户沟通 / 进度追踪 / 代码提交)                    │
└────────────────────────┬────────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────────────┐
│  Product Mgr    │ │   Architect     │ │     Team                │
│  (产品经理)     │ │   (架构师)      │ │        PM                │
│ - 需求收集      │ │ - 架构设计      │ │     (项目经理)            │
│ - 优先级排序    │ │ - 契约设计      │ │ - 任务分解              │
│ - 用户故事      │ │ - 影响评估      │ │ - 并行调度              │
│                 │ │                 │ │ - 进度追踪              │
└─────────────────┘ └─────────────────┘ └─────────────────────────┘
                                               │
                    ┌──────────────────────────┼──────────────────┐
                    │                          │                  │
                    ▼                          ▼                  ▼
           ┌───────────────┐        ┌───────────────┐   ┌──────────────────┐
           │  Backend Dev  │        │  Frontend Dev │   │   QA Tester      │
           │   (后端)      │        │    (前端)     │   │    (测试)        │
           └───────────────┘        └───────────────┘   └──────────────────┘
                    │                          │                  │
                    └──────────────────────────┼──────────────────┘
                                               │
                                               ▼
                                      ┌─────────────────┐
                                      │  Code Reviewer  │
                                      │    (审查员)     │
                                      └─────────────────┘
                                               │
                                               ▼
                                      ┌─────────────────┐
                                      │ Diagnostic      │
                                      │ Analyst         │
                                      │ (诊断分析师)     │
                                      └─────────────────┘
```

**角色总数**: 10 人（4 个决策角色 + 3 个执行角色 + 3 个支持角色）

### 角色分类

| 分类 | 角色 | 职责 |
|------|------|------|
| **决策层** | PM, PdM, Arch | 需求决策、技术决策、优先级决策 |
| **执行层** | PM, Backend, Frontend | 任务执行、代码实现 |
| **支持层** | QA, Reviewer, Diagnostic | 测试、审查、诊断 |

---

## 角色技能说明

### Project Manager (`/pm`) - 统一入口 ⭐
- **职责**: 用户沟通、进度追踪、任务计划、代码提交、交付验收
- **触发场景**: **日常对话首选入口**、进度查询、任务安排
- **使用方式**: 输入 `/pm` 或直接描述需求

### Product Manager (`/product-manager`) - 产品经理
- **职责**: 需求收集、优先级排序、用户故事编写、MVP 范围定义
- **触发场景**: 新功能需求评估、需求优先级讨论
- **使用方式**: PM 自动路由，或手动输入 `/product-manager`

### Architect (`/architect`) - 架构师
- **职责**: 架构设计、契约设计、技术选型、**关联影响评估**
- **触发场景**: 技术方案评审、架构审查、技术选型讨论
- **使用方式**: PM 自动路由，或手动输入 `/architect`

### PM (`/pm`) - 项目经理（统一协调入口）
- **职责**: PM 的执行代理，专注于任务分解、并行调度、结果整合
- **触发场景**: PM 分配任务后，由 PM 执行具体调度
- **使用方式**: 由 PM 调用，用户无需直接使用

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
# 决策层角色
/pm                    # 项目经理（统一入口，日常首选）
/product-manager         # 产品经理（需求评估）
/architect              # 架构师（技术方案）

# 执行层角色
/pm            # 团队协调器（PM 调用，用户无需直接使用）
/backend                # 后端开发
/frontend               # 前端开发

# 支持层角色
/qa                     # 质量保障
/reviewer               # 代码审查
/diagnostic             # 诊断分析师
```

**日常对话推荐**: 直接与 PM 对话，无需使用命令

```
用户："我想加个止损功能"        → PM 自动路由到 PdM
用户："进度怎么样了"            → PM 直接回答
用户："记录待办：下周安排..."    → PM 记录并安排
```

### 方式 2: 直接描述需求（PM 自动路由）

```
用户：我想添加一个策略预览功能

→ PM 自动分析并路由:
   1. PdM: 评估需求优先级和 MVP 范围
   2. Arch: 设计技术方案和契约表
   3. PM: 分解任务并请求用户确认
   4. PM: 执行并行开发
   5. PM: 代码提交和交付汇报
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

| 文件路径 | PdM | Arch | PM | Coord | Frontend | Backend | QA | Reviewer | Diagnostic |
|---------|-----|------|-----|-------|----------|---------|----|---------|------------|
| `docs/products/**` | ✅ 全权 | ⚠️ 只读 | ⚠️ 只读 | ❌ | ❌ | ❌ | ❌ | 🔍 审查 | 🔍 审查 |
| `docs/arch/**` | ⚠️ 只读 | ✅ 全权 | ⚠️ 只读 | ⚠️ 只读 | ❌ | ❌ | ❌ | 🔍 审查 | 🔍 审查 |
| `docs/planning/**` | ⚠️ 只读 | ⚠️ 只读 | ✅ 全权 | ⚠️ 执行 | ❌ | ❌ | ❌ | 🔍 审查 | ✅ 全权 |
| `docs/designs/**` | ⚠️ 只读 | ✅ 全权 | ⚠️ 只读 | ⚠️ 执行 | ⚠️ 只读 | ⚠️ 只读 | ⚠️ 只读 | 🔍 审查 | 🔍 审查 |
| `web-front/**` | ❌ | ❌ | ❌ | ❌ | ✅ 全权 | ❌ | ⚠️ 测试 | 🔍 审查 | 🔍 审查 |
| `src/**` | ❌ | 🔍 审查 | ❌ | ❌ | ❌ | ✅ 全权 | ⚠️ 测试 | ✅ 修改测试 | 🔍 审查 |
| `tests/**` | ❌ | 🔍 审查 | ⚠️ 协调 | ⚠️ 协调 | ⚠️ 协助 | ⚠️ 协助 | ✅ 全权 | ✅ 修改测试 | ⚠️ 运行 |
| `config/**` | ❌ | 🔍 审查 | ❌ | ❌ | ❌ | ✅ 全权 | ❌ | 🔍 审查 | 🔍 审查 |
| `CLAUDE.md` | ❌ | ❌ | ⚠️ 建议 | ✅ 全权 | ❌ | ❌ | ❌ | 🔍 审查 | ❌ |
| `.claude/team/**` | ⚠️ 建议 | ⚠️ 建议 | ⚠️ 建议 | ✅ 全权 | ⚠️ 建议 | ⚠️ 建议 | ⚠️ 建议 | 🔍 审查 | ❌ |

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

#### PM 边界
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
2. 通知 PM → 说明冲突情况
3. PM 调用 PM 分析 → 重新分配任务
4. 按新分配执行 → 验证无冲突后继续
```

### 常见冲突场景

| 场景 | 原因 | 解决方案 |
|------|------|----------|
| API 字段不匹配 | 后端改了返回结构，前端未更新 | PM 同步分配两个任务 |
| 测试失败需改业务代码 | QA 发现 Bug | QA 报告 → PM 分配给对应 Dev |
| 多人改同一文件 | 任务分解不清 | PM 调用 PM 重新分配 |
| 需求变更 | PdM 调整优先级 | PM 重新评估任务计划 |

---

## 最佳实践

### ✅ 推荐做法
- 日常对话首选 PM 作为统一入口
- 完整功能开发走完整工作流（PdM → Arch → PM → PM）
- 独立任务直接调用对应角色
- 测试先行：先写测试再实现功能
- 并行执行：前端和后端任务同时进行

### ❌ 避免做法
- 跳过产品评估直接开发
- 跳过架构设计直接编码
- 跳过用户确认直接执行
- 跳过测试直接交付
- 接口未对齐就合并代码
- 缺少任务追踪（使用 TaskCreate）

---

## 配置说明

### 技能文件位置
```
.claude/team/
├── product-manager/SKILL.md    # 产品经理（需求评估）
├── architect/SKILL.md          # 架构师（技术设计）
├── project-manager/SKILL.md    # 项目经理（统一入口）
├── team-pm/SKILL.md   # 团队协调器（PM 执行代理）
├── frontend-dev/SKILL.md       # 前端开发专家
├── backend-dev/SKILL.md        # 后端开发专家
├── qa-tester/SKILL.md          # 质量保障专家
├── code-reviewer/SKILL.md      # 代码审查员
└── diagnostic-analyst/SKILL.md # 诊断分析师
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
| **Product Manager** | `brainstorming` | 需求探索、竞品分析 |
| | `planning-with-files-zh` | 需求文档编写 |
| | `web-search` | 竞品调研 |
| **Architect** | `brainstorming` | 技术方案探索 |
| | `planning-with-files-zh` | 架构文档编写 |
| | `web-search` | 技术调研、最佳实践 |
| **Project Manager** | `planning-with-files-zh` | 任务计划制定 |
| | `dispatching-parallel-agents` | 并行任务调度 |
| | `verification-before-completion` | 完成前验证 |
| **Frontend Dev** | `ui-ux-pro-max` | UI 设计、配色方案 |
| | `frontend-design` | 高设计质量实现 |
| | `web-artifacts-builder` | 复杂多组件工件 |
| | `code-simplifier` | 代码优化简化 |
| **Backend Dev** | `code-simplifier` | 代码优化简化 |
| | `brainstorming` | 复杂需求分析 |
| | `systematic-debugging` | Bug 调试 |
| **QA Tester** | `webapp-testing` | Playwright E2E 测试 |
| | `code-simplifier` | 测试代码简化 |
| | `systematic-debugging` | 测试失败分析 |
| **Code Reviewer** | `code-review` | 正式审查流程 |
| | `code-simplifier` | 识别复杂度问题 |
| **Diagnostic Analyst** | `systematic-debugging` | 系统性排查 |
| | `brainstorming` | 5 Why 根因分析 |
| | `planning-with-files-zh` | 诊断计划 | |

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
Product Manager 工作流:
  1. 接收需求
  2. 需求模糊 → 调用 brainstorming 探索
  3. 编写 PRD → 调用 planning-with-files-zh
  4. 优先级评估 → RICE/WSJF 评分
  5. 移交 Arch → 输出 PRD 文档

Architect 工作流:
  1. 阅读 PRD
  2. 技术调研 → 调用 web-search
  3. 复杂方案 → 调用 brainstorming 探索
  4. 编写架构设计 → 调用 planning-with-files-zh
  5. 关联影响评估 → 输出 ADR + 契约表

Project Manager 工作流:
  1. 接收用户需求
  2. 需求类 → 转 PdM
  3. 技术类 → 转 Arch
  4. 任务类 → 调用 planning-with-files-zh 制定计划
  5. 请求用户确认 → 调用 PM 执行
  6. 完成前 → 调用 verification-before-completion

Frontend Dev 工作流:
  1. 阅读契约表
  2. 需要 UI 设计 → 调用 ui-ux-pro-max
  3. 实现组件
  4. 完成后 → 调用 code-simplifier 优化

Backend Dev 工作流:
  1. 阅读契约表
  2. 复杂需求 → 调用 brainstorming 分析
  3. 实现功能
  4. 完成后 → 调用 code-simplifier 优化
  5. 遇到 Bug → 调用 systematic-debugging

QA Tester 工作流:
  1. 阅读契约表
  2. 编写测试
  3. E2E 测试 → 调用 webapp-testing
  4. 测试失败 → 调用 systematic-debugging 分析
  5. 完成后 → 调用 code-simplifier 简化

Diagnostic Analyst 工作流:
  1. 接收问题报告
  2. 问题澄清 → 复述问题、确认期望行为
  3. 生成假设 → 列出 3-5 个可能原因
  4. 系统排查 → 调用 systematic-debugging
  5. 根因分析 → 调用 brainstorming 进行 5 Why 分析
  6. 输出报告 → 调用 planning-with-files-zh 整理诊断报告

PM 工作流:
  1. 接收 PM 任务计划
  2. 阅读契约表
  3. 分解任务 → TaskCreate
  4. 并行调度 → dispatching-parallel-agents
  5. 汇总结果 → 汇报给 PM
```

---

## 故障排除

### 问题 1: 子 Agent 无法加载技能
**解决**: 在 prompt 中明确指定技能文件路径
```
prompt="请阅读 .claude/team/backend-dev/SKILL.md 并按规范实现..."
```

### 问题 2: 任务依赖顺序混乱
**解决**: 使用 TaskCreate + TaskUpdate 设置依赖关系
```python
# 步骤 1: 创建任务
task_backend = TaskCreate(subject="后端 Schema 定义", description="...")
task_frontend = TaskCreate(subject="前端 UI 实现", description="...")

# 步骤 2: 使用 TaskUpdate 设置依赖
TaskUpdate(taskId=task_frontend.id, addBlockedBy=[task_backend.id])  # 前端等待后端
```

### 问题 3: 接口定义不一致
**解决**: Team PM 主持接口对齐会议，输出契约文档

---

*本团队配置旨在提高开发效率，确保代码质量和接口对齐。*
