# 盯盘狗项目文档导航

**更新日期**: 2026-03-31

---

## 📚 文档分类索引

### 核心文档

| 文档 | 说明 | 位置 |
|------|------|------|
| 📘 项目README | 项目介绍与快速开始 | [README.md](../README.md) |
| 📋 CLAUDE.md | AI 助手开发指南 | [CLAUDE.md](../CLAUDE.md) |
| 🗺️ 项目计划 | 整体项目规划 | [PROJECT-PLAN.md](PROJECT-PLAN.md) |

---

### v3.0 PMS 系统（当前重点）

#### 设计文档
| 文档 | 说明 |
|------|------|
| [v3 演进路线图](v3/v3-evolution-roadmap.md) | Phase 1-6 详细规划与进度 |
| [系统进度总览](v3/system-progress-summary.md) | 整体进度与里程碑 |
| [v3 迁移分析报告](v3/v3-migration-analysis-report.md) | 技术选型与架构分析 |
| [Phase 1 设计](v3/step1.md) | 核心数据模型设计 |
| [Phase 2 设计](v3/step2.md) | 撮合引擎设计 |
| [Phase 3 设计](v3/step3.md) | 风控状态机设计 |

#### 完成报告
| 文档 | 说明 |
|------|------|
| [Phase 1 完成报告](v3/reports/v3-phase1-complete-report.md) | 模型筑基完成 |
| [Phase 2 完成报告](v3/reports/v3-phase2-complete-report.md) | 撮合引擎完成 |
| [Phase 3 完成报告](v3/reports/v3-phase3-complete-report.md) | 风控状态机完成 |
| [Phase 4 完成报告](v3/reports/v3-phase4-complete-report.md) | 订单编排完成 |
| [Phase 1-4 验证报告](v3/reports/v3-phases-1-4-verification-report.md) | 集成验证 |

#### 审查报告
| 文档 | 说明 |
|------|------|
| [Phase 1-5 系统性审查](reviews/phase1-5-comprehensive-review-report.md) | 57 项 100% 通过 |
| [Phase 5 专项审查](reviews/phase5-code-review.md) | 10 个问题修复 |

---

### Phase 5 实盘集成

| 文档 | 说明 |
|------|------|
| [Phase 5 契约表](designs/phase5-contract.md) | API 接口契约定义 |
| [Phase 5 详细设计](designs/phase5-detailed-design.md) | 实现细节 |
| [Phase 5 开发清单](designs/phase5-development-checklist.md) | 开发任务列表 |
| [Phase 5 环境兼容性](designs/phase5-environment-compatibility-brainstorm.md) | 部署环境分析 |

---

### 架构规范

| 文档 | 说明 |
|------|------|
| [系统开发规范与红线](arch/系统开发规范与红线.md) | 开发约束 |
| [系统重构与架构演进](arch/系统重构与架构演进梳理报告.md) | 架构历史 |
| [Gemini 讨论技术文档](GEMINI_DISCUSSION_DOC.md) | 技术决策记录 |

---

### 工作流与规范

| 文档 | 说明 |
|------|------|
| [全自动交付流水线](workflows/auto-pipeline.md) | 复杂任务工作流 |
| [规划文件使用规范](planning/README.md) | planning-with-files 标准 |

---

### 规划与进度

| 文档 | 说明 |
|------|------|
| [进度日志](planning/progress.md) | 每日开发日志 |
| [研究发现](planning/findings.md) | 技术笔记与决策 |
| [任务计划](planning/task_plan.md) | 当前任务分解 |

---

### 子任务文档

| 目录 | 说明 |
|------|------|
| [tasks/](tasks/) | 子任务详细设计 |
| [tasks/archive/](tasks/archive/) | 已完成任务归档 |

---

### 发布与变更

| 文档 | 说明 |
|------|------|
| [CHANGELOG.md](../CHANGELOG.md) | 版本变更日志 |
| [releases/](releases/) | 发布文档 |

---

## 📁 物理结构

```
docs/
├── README.md                  # 本文件（文档导航）
├── arch/                      # 架构规范
├── designs/                   # 设计文档（Phase 契约表）
├── planning/                  # 规划文档（进度/发现/任务）
├── reviews/                   # 审查报告
├── tasks/                     # 子任务文档
│   └── archive/               # 已完成任务归档
├── v3/                        # v3.0 专项
│   ├── reports/               # Phase 完成报告
│   ├── step1.md, step2.md, step3.md
│   └── v3-evolution-roadmap.md
├── workflows/                 # 工作流规范
├── templates/                 # 文档模板
├── archive/                   # 废弃文档（待清理）
└── reports/                   # 综合报告
    └── file-structure-reorg-plan.md
```

---

## 🔍 快速查找

**我想看...**
- v3 整体规划 → [v3/v3-evolution-roadmap.md](v3/v3-evolution-roadmap.md)
- Phase 完成情况 → [v3/reports/](v3/reports/)
- 审查结果 → [reviews/phase1-5-comprehensive-review-report.md](reviews/phase1-5-comprehensive-review-report.md)
- 今日进度 → [planning/progress.md](planning/progress.md)
- 技术决策 → [planning/findings.md](planning/findings.md)
- 实盘集成 → [designs/phase5-*.md](designs/)

---

## 📝 文档维护

### 文档分类原则
- **设计文档** → `designs/` 或 `v3/`
- **完成报告** → `v3/reports/`
- **审查报告** → `reviews/`
- **进度日志** → `planning/progress.md`
- **技术笔记** → `planning/findings.md`
- **子任务** → `tasks/`（完成后移至 `archive/`）

### 命名规范
- 使用小写字母和连字符：`phase5-contract.md`
- 中文文件名使用 NFC 格式
- 日期前缀：`2026-03-31-*.md`

---

*盯盘狗 🐶 项目组*
*2026-03-31*
