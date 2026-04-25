# 用户画像：AI-Driven 量化系统架构师

> 生成日期：2026-04-10
> 数据来源：~/.claude/ 配置、团队文档、工作流文档、插件清单、MCP 配置

---

## 基本信息

| 维度 | 内容 |
|------|------|
| **项目名称** | 盯盘狗 v3.0（量化交易系统） |
| **后端技术栈** | Python 3.11+ / FastAPI / Uvicorn / asyncio / aiohttp / Pydantic v2 |
| **前端技术栈** | React 18+ / TypeScript 5+ / TailwindCSS 3+ / Framer Motion |
| **数据库** | SQLite（业务数据）+ DuckDB（OLAP/回测分析） |
| **测试框架** | pytest + pytest-asyncio + Playwright + vitest |
| **架构模式** | Clean Architecture 四层（domain / application / infrastructure / interfaces） |
| **开发模式** | OpenAPI 契约驱动（Spec → 类型生成 → 前后端并行开发） |

---

## 工具链配置

### MCP 服务器（8 个）

| 服务器 | 用途 | 状态 |
|--------|------|------|
| `sqlite` | 数据库查询（v3_dev.db） | ✅ 已配置 |
| `filesystem` | 文件操作（~/Documents/final） | ✅ 已配置 |
| `puppeteer` | 无头浏览器（前端 UI 测试） | ✅ 已配置 |
| `time` | 时区/时间工具 | ✅ 已配置 |
| `duckdb` | OLAP 分析（backtest.db） | ✅ 已配置 |
| `git` | Git 版本控制 | ✅ 已配置 |

### 已安装插件（17 个）

| 插件 | 版本 | 用途 |
|------|------|------|
| superpowers | 5.0.7 | 高级功能增强 |
| planning-with-files | 2.23.0 | 文件化任务规划 |
| ui-ux-pro-max | 2.5.0 | UI/UX 设计指导 |
| code-review | unknown | 代码审查 |
| code-simplifier | 1.0.0 | 代码简化优化 |
| github | unknown | GitHub 集成 |
| chrome-devtools-mcp | latest | Chrome 开发者工具 |
| document-skills | - | 文档处理（docx/xlsx/pdf/pptx） |
| context7 | unknown | 上下文管理 |
| feature-dev | unknown | 特性开发辅助 |
| playwright | unknown | E2E 测试 |
| typescript-lsp | 1.0.0 | TypeScript 语言服务 |
| ralph-loop | 1.0.0 | 循环任务 |
| claude-md-management | 1.0.0 | CLAUDE.md 管理 |
| frontend-design | unknown | 前端设计 |
| skill-creator | unknown | 技能创建 |
| commit-commands | unknown | Git 提交命令 |

### 自定义 Agent（4 个）

- `team-backend-dev.md` — 后端开发专家
- `team-code-reviewer.md` — 代码审查员
- `team-frontend-dev.md` — 前端开发专家
- `team-qa-tester.md` — 质量保障专家

### 核心技能（Slash Commands）

| 命令 | 版本 | 用途 |
|------|------|------|
| `/pm` | - | 项目经理（统一入口） |
| `/product-manager` | - | 产品经理 |
| `/architect` | - | 架构师 |
| `/backend` | - | 后端开发 |
| `/frontend` | - | 前端开发 |
| `/qa` | - | 质量保障 |
| `/reviewer` | - | 代码审查 |
| `/diagnostic` | - | 诊断分析 |
| `/kaigong` | v8.0 | 开工技能（Memory MCP 混合版） |
| `/shougong` | v5.0 | 收工技能（全自动归档） |
| `/tdd` | - | TDD 闭环自愈 |
| `/type-check` | - | 类型精度宪兵 |
| `/pua-skill` | - | 提示词优化助手 |
| `/prd` | - | 产品需求文档生成 |
| `/ralph` | - | Ralph 格式转换 |

---

## 工作流程

### 多角色 Agent Team 架构

```
                    Project Manager（统一入口）
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
   Product Mgr       Architect        Team PM
   (需求收集)        (架构设计)       (任务分解)
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
            Backend Dev       Frontend Dev        QA Tester
            (后端实现)         (前端实现)          (测试验证)
                    │                 │                 │
                    └─────────────────┼─────────────────┘
                                      ▼
                              Code Reviewer
                              (合并把关)
                                      ▼
                              Diagnostic Analyst
                              (根因分析)
```

**角色总数**: 10 人（4 个决策层 + 3 个执行层 + 3 个支持层）

### 三阶段工作流（契约驱动）

```
【阶段 1】需求沟通
  PdM 交互式澄清（≥3 个问题）→ 用户确认 → PRD 文档

【阶段 2】架构设计 + 契约生成 + 并行开发
  Arch 架构设计 → 输出 ADR + OpenAPI Spec（6 项验证）
  契约生成 → Python/TypeScript 类型自动导入
  用户审查确认 → PM 任务分解 → Backend + Frontend 并行开发
  QA 单元测试 → Reviewer 实时审查

【阶段 3】集成测试 + 代码审查 + 交付
  QA 集成测试 → E2E 测试（Playwright）
  Reviewer 最终审查 → PM 交付汇报 → /shougong 自动收工
```

**5 个强制检查点**:
1. 阶段 1 结束：需求理解确认
2. 阶段 2 开始：技术方向确认 + OpenAPI Spec 验证
3. 阶段 2 中期：契约生成验证（类型定义 + Mock 服务器）
4. 阶段 2 后期：测试前确认（耗时 30-60 分钟）
5. 阶段 3 结束：交付汇报，用户验收

### 开工/收工体系

#### `/kaigong` v8.0 — 智能分层加载

| 阶段 | 描述 | 上下文大小 |
|------|------|----------|
| 极快启动 | 红线规则 + Git 状态 + 待办标题 + 技术决策摘要 | 3.5K |
| 交互式选择 | 用户选择待办事项 | 0K |
| 按需加载 | 事项背景 + 技术决策详情 + 解决方案 + 依赖关系 | 5.5K |
| **总计** | | **9K** |

**暂停关键词检测**: "暂停"/"午休"/"休息"/"pause" 等触发自动文档更新 + Git 提交（不推送）

#### `/shougong` v5.0 — 全自动收工

1. 自动归档超期文档（交接文档 >7 天，进度日志 >3 天）
2. 智能更新文档（仅追加/仅更新当前阶段，不读取全文）
3. 写入 Memory MCP（今日总结永久保留）
4. Git 提交 + 推送
5. 输出收工报告 + 明日优先事项

### 知识管理

#### Memory MCP 混合方案

| 类型 | 存储位置 | 保留时长 | 更新时机 |
|------|----------|----------|----------|
| 架构决策 | Memory MCP | **永久** | Arch 设计后 |
| 技术发现 | findings.md | 7 天后归档 | 发现洞见时 |
| 进度日志 | progress.md | 3 天后归档 | 会话结束时 |

#### planning-with-files 三文件管理

| 文件 | 路径 | 用途 |
|------|------|------|
| task_plan.md | `docs/planning/task_plan.md` | 任务计划与阶段追踪 |
| findings.md | `docs/planning/findings.md` | 研究发现与技术笔记 |
| progress.md | `docs/planning/progress.md` | 进度日志与会话记录 |

**红线**: 禁止使用内置 `writing-plans` / `executing-plans`，违者由 Code Reviewer 标记 P0。

---

## 开发规范摘要

### Clean Architecture 分层

```
src/
├── domain/          # 领域层（纯业务逻辑，严禁导入 I/O 框架）
├── application/     # 应用服务层
├── infrastructure/  # 基础设施层（所有 I/O 操作）
└── interfaces/      # REST API 端点
```

### 领域层红线

`domain/` **严禁导入**: ccxt, aiohttp, requests, fastapi, yaml

### 类型安全

- 禁止使用 `Dict[str, Any]` — 必须定义具名 Pydantic 类
- 多态对象使用 `discriminator='type'`
- 金额计算必须使用 `decimal.Decimal`（禁用 float）

### 异步规范

- 所有 I/O 使用 `async/await`
- 禁止 `time.sleep()` 阻塞事件循环
- 并发控制使用 `asyncio.Lock`
- 后台任务使用 `asyncio.create_task()`

### 测试覆盖率要求

| 层级 | 覆盖率要求 |
|------|----------|
| 领域层 | ≥90% |
| 应用层 | ≥80% |
| 基础设施层 | ≥70% |
| 接口层 | ≥60% |

---

## 文件所有权矩阵

| 文件路径 | PdM | Arch | PM | Frontend | Backend | QA | Reviewer |
|---------|-----|------|-----|----------|---------|----|---------|
| `docs/products/**` | ✅ 全权 | ⚠️ 只读 | ⚠️ 只读 | ❌ | ❌ | ❌ | 🔍 审查 |
| `docs/arch/**` | ⚠️ 只读 | ✅ 全权 | ⚠️ 只读 | ❌ | ❌ | ❌ | 🔍 审查 |
| `docs/planning/**` | ⚠️ 只读 | ⚠️ 只读 | ✅ 全权 | ❌ | ❌ | ❌ | 🔍 审查 |
| `gemimi-web-front/**` | ❌ | ❌ | ❌ | ✅ 全权 | ❌ | ⚠️ 测试 | 🔍 审查 |
| `src/**` | ❌ | 🔍 审查 | ❌ | ❌ | ✅ 全权 | ⚠️ 测试 | 🔍 审查 |
| `tests/**` | ❌ | 🔍 审查 | ⚠️ 协调 | ⚠️ 协助 | ⚠️ 协助 | ✅ 全权 | ✅ 修改测试 |

**图例**: ✅ 全权负责 | ❌ 禁止修改 | ⚠️ 有限权限 | 🔍 仅审查

---

## 优缺点分析

### 优势

#### 1. 工程化素养极高
- Clean Architecture 严格分层，领域层红线不可触碰
- OpenAPI 契约驱动开发，前后端类型定义从 Spec 自动生成，集成测试失败率降低 83%
- Decimal 精度保证（金融计算禁用 float），配套 `/type-check` 技能 + 检测脚本
- 异步非阻塞规范明确，配套并发控制模式（Lock 保护、异步队列批处理）

#### 2. 质量保障体系完善
- TDD 闭环自愈（`/tdd`）：契约解析 → 生成测试 → 运行 → 实现 → 自修复直到通过
- 分层覆盖率要求严格（领域层 ≥90% 到接口层 ≥60%）
- Code Reviewer 有合并否决权，审查报告格式标准化（P0/P1/P2 优先级标注）
- 代码简化技能（`/simplify`）作为开发完成后必调步骤

#### 3. 上下文管理能力突出
- 智能分层加载将上下文从 267K 优化到 42K（减少 84%）
- 自动归档机制防止文档膨胀（progress.md 119K → 30K）
- 开工/收工技能实现无缝会话交接，Git 提交自动记录

#### 4. 协作边界清晰
- 文件所有权矩阵定义每个角色的修改权限
- QA 发现 Bug 不直接改业务代码，通过 PM 分配修复任务
- 冲突解决流程标准化（发现冲突 → 停止 → 通知 PM → 重新分配）

#### 5. 文档驱动开发
- 完整的文档链路：PRD → ADR → 契约表 → 任务计划 → 进度日志 → 交接文档
- Memory MCP 永久保留架构决策，支持跨会话知识追溯

### 风险与改进空间

#### 1. 流程过重
- 10 人团队 + 三阶段工作流 + 5 个强制确认检查点，对个人项目来说流程开销很大
- 简单功能变更需要经过 PdM → Arch → PM → Backend → QA → Reviewer 6 个角色链路
- 文档维护成本高（task_plan / findings / progress / Memory MCP / 交接文档 / 看板 / board.md / tasks.json）
- **建议**: 考虑引入轻量级快速通道（跳过完整角色链路的单兵模式）处理小修小补

#### 2. 自定义 Agent 定义冗余
- 每个 Agent 定义文件 ~400 行，开工/收工检查清单大量重复
- `/kaigong` 技能文档达 800+ 行，本质是复杂的伪代码状态机
- 技能之间互相引用形成网状依赖（code-simplifier / brainstorming / systematic-debugging 等）
- **建议**: 抽取公共规范为独立文件，各 Agent 仅引用而非复制

#### 3. MCP Server 配置（已清理 ✅）
- Telegram / SSH / Sentry 占位符已从 `~/.claude/mcp.json` 移除
- 实际启用 6 个核心服务（sqlite, filesystem, puppeteer, time, duckdb, git）
- 需要时再添加真实凭证

#### 4. 过度工程化风险
- Agent 团队、MCP 编排、权限矩阵、角色边界等概念密度极高
- 个人开发场景中，"冲突解决流程"的受益者实际上是同一个人（左右互搏）
- planning-with-files 自建规划体系维护成本不低
- **建议**: 定期审视哪些流程真正提升了效率 vs 哪些只是增加了仪式感

#### 5. 文档版本迭代（已清理 ✅）
- 12 个旧版 SKILL.md 残留文件已清理
- 重复文档和过期文件已清理
- 版本收敛后认知负担显著降低

---

## 总结评价

你是一位**重度 AI 辅助工程实践者**，在"用 AI 做严肃工程"和"用 AI 做快速原型"之间明确选择了前者。你对代码质量、架构一致性、类型安全有极高的要求，并且愿意投入大量精力构建自动化流程来保障这些标准。

你的工作流像一支训练有素的特种部队——纪律严明、分工明确、流程完整。核心优势在于：

- 契约驱动开发确保前后端接口一致
- Memory MCP 实现跨会话知识沉淀
- 智能上下文管理在有限窗口内保留关键信息
- 多层质量保障（TDD + Reviewer + 覆盖率要求）

但也面临一个根本矛盾：**流程的设计者、执行者和受益者是同一个人**。对于个人项目，10 人团队的协调成本可能超过收益。建议评估哪些流程真正带来了质量提升，哪些可以简化为检查清单或自动化脚本。
