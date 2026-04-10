# 技能版本清单

> 最后更新：2026-04-10
> 维护者：AI Builder

---

## 命令技能（`.claude/commands/`）

| 技能 | 版本 | 最后更新 | 说明 |
|------|------|----------|------|
| `kaigong.md` | v8.0 | 2026-04-04 | 开工技能（Memory MCP 混合方案版） |
| `shougong.md` | v5.0 | 2026-04-10 | 收工技能（Memory MCP 混合版） |

## 团队技能（`.claude/team/*/SKILL.md`）

| 技能 | 版本 | 说明 |
|------|------|------|
| `architect/SKILL.md` | - | 架构师 - 架构设计、契约设计、技术选型 |
| `backend-dev/SKILL.md` | - | 后端开发专家 - Python + FastAPI + asyncio |
| `code-reviewer/SKILL.md` | - | 代码审查员 - 架构一致性、安全隐患识别 |
| `diagnostic-analyst/SKILL.md` | - | 诊断分析师 |
| `frontend-dev/SKILL.md` | - | 前端开发专家 - React + TypeScript + TailwindCSS |
| `product-manager/SKILL.md` | - | 产品经理 - 需求过滤、优先级排序、用户故事 |
| `project-manager/SKILL.md` | - | 项目经理 - 任务调度、Agent调度、进度追踪 |
| `qa-tester/SKILL.md` | - | 质量保障专家 - pytest + pytest-asyncio |

## 独立技能（`.claude/skills/`）

| 技能 | 说明 |
|------|------|
| `agentic-workflow/tdd-self-heal/` | TDD 闭环自愈 |
| `agentic-workflow/type-precision-enforcer/` | 类型精度强制 |
| `prd/` | 产品需求文档生成 |
| `pua-skill/` | 提示词优化助手 |
| `ralph/` | PRD → prd.json 转换 |

---

## 版本更新规范

1. 更新技能版本时，**直接覆盖当前文件**，不要创建 `.v2` / `.backup` 等备份
2. 如需保留历史版本，移至 `docs/archive/skills/` 目录
3. 更新本表格中的版本号和日期

## 清理历史

- 2026-04-10：清理 12 个旧版 SKILL.md 残留文件（`.backup.*` / `.v2` / `.v3`）
