# 工作流重构 v3.0 - 实施总结

**实施日期**: 2026-04-03  
**版本**: v3.0  
**状态**: ✅ 已完成

---

## 一、问题汇总与解决方案

| 问题 | 解决方案 | 实施状态 |
|------|----------|----------|
| Coordinator 不追踪任务，等用户 push | Task 系统自动追踪 + 自动触发 | ✅ 已完成 |
| 复杂任务上下文不够 | 会话切割：规划/开发/测试分离 | ✅ 已完成 |
| 文档负担重 | 简化 handoff 文档格式 | ✅ 已完成 |
| Coordinator 不调 Agent | 强制调用约束 + 代码示例 | ✅ 已完成 |
| 进度感知缺失 | 实时状态看板 | ✅ 已完成 |
| 任务阻塞没人管 | 阻塞检测 + 通知机制 | ✅ 已完成 |
| 新会话不知道旧会话进度 | Task 持久化 + handoff 文档 | ✅ 已完成 |

---

## 二、新工作流核心设计

### 2.1 会话切割

```
规划会话 (Session 1)
  ↓
用户确认
  ↓
开发会话 (Session 2)
  ↓
用户确认
  ↓
测试会话 (Session 3)
  ↓
交付
```

**触发条件**（满足任一即为复杂任务）：
- 任务数 > 5
- 预计工时 > 4h
- 多角色任务

### 2.2 规划会话强制交互式头脑风暴

| 阶段 | 负责人 | 交互要求 |
|------|--------|----------|
| 需求澄清 | Product Manager | ≥3 个澄清问题 + brainstorming |
| 架构设计 | Architect | ≥2 个技术方案 + trade-off |
| 任务分解 | Project Manager | 任务清单 + 并行簇识别 |

### 2.3 开发会话强制 Agent 调用

Coordinator SKILL 中写死代码示例：
```python
# 必须调用 Agent 工具！
Agent(
    subagent_type="team-backend-dev",
    prompt="B1: Schema 定义"
)
```

### 2.4 状态看板实时更新

文件：`docs/planning/board.md`

| 字段 | 说明 |
|------|------|
| 任务 ID | T1, T2, T3... |
| 任务名称 | 任务描述 |
| 角色 | backend-dev / frontend-dev / qa-tester |
| 状态 | ☐ 待开始 / 🔄 进行中 / ✅ 已完成 / 🔴 阻塞 |
| 阻塞依赖 | 依赖的任务 ID |

---

## 三、文档结构

### 3.1 核心文档（保留 planning-with-files）

| 文件 | 路径 | 说明 |
|------|------|------|
| task_plan.md | `docs/planning/task_plan.md` | 任务计划与阶段追踪 |
| findings.md | `docs/planning/findings.md` | 研究发现与技术笔记 |
| progress.md | `docs/planning/progress.md` | 进度日志与会话记录 |

### 3.2 新增文档（机器可读 + 状态追踪）

| 文件 | 路径 | 说明 |
|------|------|------|
| tasks.json | `docs/planning/tasks.json` | 任务清单（JSON 格式） |
| board.md | `docs/planning/board.md` | 实时状态看板 |
| handoff-*.md | `docs/planning/handoff-*.md` | 会话交接文档（简化版） |

### 3.3 契约与报告（保留）

| 文件 | 路径 | 说明 |
|------|------|------|
| contract.md | `docs/designs/<feature>-contract.md` | 接口契约表（SSOT） |
| test.md | `docs/reports/<feature>-test.md` | 测试报告 |
| brief.md | `docs/products/<feature>-brief.md` | PRD 产品需求文档 |

---

## 四、技能配置统一

### 4.1 团队技能（5 个）

| 技能名 | 命令 | 职责 |
|--------|------|------|
| `team-coordinator` | `/coordinator` | 兼任 PdM/Arch/PM，任务调度 |
| `team-backend-dev` | `/backend` | 后端开发 |
| `team-frontend-dev` | `/frontend` | 前端开发 |
| `team-qa-tester` | `/qa` | 测试专家 |
| `team-code-reviewer` | `/reviewer` | 代码审查 |

### 4.2 辅助技能（2 个，保留）

| 技能名 | 命令 | 职责 |
|--------|------|------|
| `tdd-self-heal` | `/tdd` | TDD 闭环自愈 |
| `type-precision-enforcer` | `/type-check` | 类型精度检查 |

### 4.3 配置位置

`~/.claude/settings.json` - 统一配置所有技能

---

## 五、文件结构清理

### 5.1 归档的旧文档

```
docs/archive/
├── auto-pipeline.md         # 旧工作流文档
└── checkpoints-checklist.md  # 旧检查点文档
```

### 5.2 保留的技能目录

```
.claude/
├── team/                    # 统一技能目录 ✅
│   ├── team-coordinator/
│   ├── backend-dev/
│   ├── frontend-dev/
│   ├── qa-tester/
│   └── code-reviewer/
├── skills/                  # 辅助技能（保留）
│   └── agentic-workflow/
│       ├── tdd-self-heal/
│       └── type-precision-enforcer/
└── settings.json            # 技能配置 ✅
```

---

## 六、使用指南

### 6.1 启动规划会话

```
/coordinator
我想添加一个移动止损功能，当价格达到新高后回撤 X% 时自动平仓。
```

Coordinator 会自动：
1. 提出 ≥3 个澄清问题
2. 提供 ≥2 个技术方案
3. 分解任务并创建 tasks.json
4. 生成交接文档

### 6.2 启动开发会话

新会话中：
```
阅读 docs/planning/handoff-001.md，开始开发。
```

Coordinator 会自动：
1. 读取 tasks.json
2. 按并行簇调用 Agent
3. 实时更新 board.md

### 6.3 启动测试会话

```
开始测试。
```

QA 会自动：
1. 阅读契约表
2. 运行测试
3. 生成测试报告

---

## 七、红线检查清单

### Coordinator 三条红线

1. 【强制】规划会话必须交互式头脑风暴（≥3 个澄清问题 + ≥2 个技术方案）
2. 【强制】开发会话必须调用 Agent 工具派发任务，不能只描述流程
3. 【强制】测试前必须通知用户确认 (耗时 30-60 分钟)

### 所有角色强制要求

- 必须使用 planning-with-files 三文件管理进度
- 禁止使用内置 writing-plans / executing-plans

---

## 八、验收标准

| 验收项 | 状态 |
|--------|------|
| Coordinator SKILL 已重写 | ✅ |
| 4 个团队技能名称已统一 | ✅ |
| settings.json 已更新 | ✅ |
| 模板文件已创建 | ✅ |
| 旧文档已归档 | ✅ |
| planning-with-files 三文件保留 | ✅ |

---

## 九、后续验证

建议创建一个测试任务验证新流程：

1. 启动规划会话，验证交互式头脑风暴
2. 启动开发会话，验证 Agent 调用
3. 启动测试会话，验证测试执行
4. 检查所有文档是否按预期更新

---

**实施完成**: 2026-04-03  
**下次迭代**: 根据实际使用情况优化
