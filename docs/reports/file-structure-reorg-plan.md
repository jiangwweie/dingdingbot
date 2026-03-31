# 项目文件结构重组方案

**创建日期**: 2026-03-31
**状态**: 待审批
**优先级**: 中（不影响功能，提升开发效率）

---

## 一、当前问题分析

### 1.1 根目录杂乱 🔴

**问题**: 根目录散落 20+ 个文件/文件夹，不符合 Python 项目规范

**当前状态**:
```
/
├── .coverage                    # 测试覆盖率（应忽略）
├── .DS_Store                    # macOS 系统文件（应忽略）
├── .env                         # 环境变量（应忽略）
├── .mcp.json                    # MCP 配置
├── alembic.ini                  # 数据库迁移配置
├── backend.log                  # 后端日志（应忽略）
├── CHANGELOG.md                 # 变更日志
├── CLAUDE.md                    # AI 助手指南
├── deploy.sh                    # 部署脚本
├── docker-compose.yml           # Docker 编排
├── Dockerfile.backend           # 后端镜像
├── Dockerfile.frontend          # 前端镜像
├── frontend.log                 # 前端日志（应忽略）
├── pytest.ini                   # 测试配置
├── README.md                    # 项目说明
├── requirements.txt             # Python 依赖
└── venv/                        # Python 虚拟环境
```

### 1.2 docs 目录结构混乱 🔴

**问题**: 106 个 MD 文件分散在 14 个子目录，缺乏统一索引

| 目录 | 文件数 | 状态 | 问题 |
|------|--------|------|------|
| `archive/` | 27+ | ❌ | 已废弃文档未清理 |
| `designs/` | 15+ | ⚠️ | 与 `v3/` 内容重叠 |
| `v3/` | 19+ | ⚠️ | Phase 1-5 完成报告散落 |
| `tasks/` | 10+ | ⚠️ | 已完成任务未归档 |
| `planning/` | 16+ | ⚠️ | 进度日志与计划混放 |
| `arch/` | 9+ | ✅ | 架构规范，相对清晰 |
| `reviews/` | 4+ | ✅ | 审查报告，相对清晰 |

### 1.3 memory 目录冗余 🟡

**问题**: `memory/` 目录与 `.claude/memory/` 系统功能重叠

```
memory/                     # 旧系统（7 个文件）
├── project-phase1-complete.md
├── feedback-workflow.md
├── reference-docs.md
├── project-v3-priority.md
├── feedback-quality.md
└── ...

.claude/memory/             # 新系统（推荐使用）
├── MEMORY.md
└── *.md
```

### 1.4 scripts 目录缺少分类 🟡

**问题**: 13 个脚本混放，用途不清晰

```
scripts/
├── backfill_7days.py          # 数据回补
├── fix_filenames.py           # 文件名修复
├── fix_unicode_paths.py       # Unicode 路径修复
├── read_markdown.py           # MD 读取工具
├── standardize_filenames.py   # 文件名标准化
├── test_send_signal.py        # 测试脚本
├── test_send_styles.py        # 测试脚本
├── start.sh                   # 部署脚本
├── stop.sh                    # 部署脚本
└── deploy-frontend.sh         # 部署脚本
```

---

## 二、重组方案

### 2.1 根目录整理

**目标**: 根目录只保留必要文件，其他移至子目录

| 文件/目录 | 操作 | 新位置/处理方式 |
|-----------|------|----------------|
| `.coverage` | 忽略 | 加入 `.gitignore`（已有） |
| `.DS_Store` | 忽略 | 加入 `.gitignore`（已有） |
| `backend.log` | 忽略 | 加入 `.gitignore` |
| `frontend.log` | 忽略 | 加入 `.gitignore` |
| `data/` | 忽略 | 已在 `.gitignore` |
| `logs/` | 忽略 | 加入 `.gitignore` |
| `alembic.ini` | 保留 | 数据库迁移必需 |
| `pytest.ini` | 保留 | 测试配置必需 |
| `requirements.txt` | 保留 | Python 依赖清单 |
| `deploy.sh` | 移动 | `scripts/deploy.sh` |
| `docker-compose.yml` | 保留 | Docker 标准配置 |
| `Dockerfile.*` | 移动 | `docker/Dockerfile.backend`, `docker/Dockerfile.frontend` |
| `.mcp.json` | 保留 | MCP 配置 |
| `.env` | 忽略 | 加入 `.gitignore` |
| `CHANGELOG.md` | 移动 | `docs/releases/CHANGELOG.md` |
| `MEMORY.md` | 移动 | `.claude/memory/MEMORY.md` |
| `memory/` | 整合 | 内容移至 `.claude/memory/` 后删除 |

### 2.2 docs 目录重构

**目标**: 统一文档索引，归档废弃内容

**新结构**:
```
docs/
├── README.md                    # 文档导航索引（新增）
├── arch/                        # 架构规范（保留）
│   └── ...
├── designs/                     # 设计文档（精简）
│   ├── phase1-models.md
│   ├── phase2-matching.md
│   ├── phase3-risk.md
│   ├── phase4-orchestration.md
│   └── phase5-integration.md
├── v3/                          # v3 专项（保留）
│   ├── step1.md, step2.md, step3.md  # Phase 1-3 设计
│   ├── v3-evolution-roadmap.md       # 演进路线图
│   ├── system-progress-summary.md    # 系统进度总览
│   └── reports/                      # Phase 完成报告
│       ├── phase1-complete.md
│       ├── phase2-complete.md
│       ├── phase3-complete.md
│       ├── phase4-complete.md
│       └── phase5-complete.md
├── reviews/                     # 审查报告（保留）
│   ├── phase1-5-comprehensive-review-report.md
│   └── phase5-code-review.md
├── planning/                    # 规划文档（保留）
│   ├── progress.md              # 进度日志
│   ├── findings.md              # 研究发现
│   └── task_plan.md             # 任务计划
├── workflows/                   # 工作流规范（保留）
│   └── auto-pipeline.md
├── templates/                   # 文档模板（保留）
├── tasks/                       # 子任务文档（归档）
│   └── archive/                 # 已完成任务
├── archive/                     # 废弃文档（清理）
│   └── README.md                # 归档索引
└── reports/                     # 综合报告（新增）
    └── file-structure-reorg-plan.md
```

### 2.3 memory 目录整合

**目标**: 统一使用 `.claude/memory/` 系统

| 原文件 | 操作 | 新位置 |
|--------|------|--------|
| `memory/project-phase1-complete.md` | 整合 | `.claude/memory/project-milestones.md` |
| `memory/project-v3-priority.md` | 整合 | `.claude/memory/project-priorities.md` |
| `memory/feedback-*.md` | 整合 | `.claude/memory/feedback-guidelines.md` |
| `memory/reference-docs.md` | 保留 | `.claude/memory/reference.md` |

### 2.4 scripts 目录分类

**目标**: 按用途分类脚本

```
scripts/
├── README.md                    # 脚本使用说明（新增）
├── tools/                       # 工具脚本
│   ├── fix_filenames.py
│   ├── fix_unicode_paths.py
│   ├── standardize_filenames.py
│   └── read_markdown.py
├── data/                        # 数据脚本
│   └── backfill_7days.py
├── deploy/                      # 部署脚本
│   ├── deploy.sh
│   ├── start.sh
│   ├── stop.sh
│   └── deploy-frontend.sh
└── test/                        # 测试脚本
    ├── test_send_signal.py
    └── test_send_styles.py
```

---

## 三、执行步骤

### 阶段 1: 清理可忽略文件（5 分钟）

```bash
# 更新 .gitignore
cat >> .gitignore << 'EOF'

# Runtime logs
*.log
logs/

# Coverage
.coverage
htmlcov/

# Local data
data/*.db
data/*.sqlite

# Environment
.env
.local
EOF

# 清理已跟踪的日志文件
git rm --cached backend.log frontend.log .coverage
```

### 阶段 2: 移动脚本和配置文件（10 分钟）

```bash
# 创建 scripts 子目录
mkdir -p scripts/tools scripts/data scripts/deploy scripts/test

# 移动脚本文件
mv scripts/*.sh scripts/deploy/
mv scripts/test_*.py scripts/test/
mv scripts/fix_*.py scripts/tools/
mv scripts/standardize_filenames.py scripts/tools/
mv scripts/read_markdown.py scripts/tools/
mv scripts/backfill_7days.py scripts/data/
mv scripts/deploy-frontend.sh scripts/deploy/

# 移动 Docker 文件
mkdir -p docker
mv Dockerfile.* docker/
mv docker-compose.yml docker/
```

### 阶段 3: 整理 docs 目录（30 分钟）

```bash
# 创建 v3/reports 目录
mkdir -p docs/v3/reports

# 移动 Phase 完成报告
mv docs/v3/v3-phase*-complete-report.md docs/v3/reports/
mv docs/v3/v3-phase*-handoff-report.md docs/v3/reports/
mv docs/v3/v3-phases-*-verification-report.md docs/v3/reports/

# 创建 tasks/archive 目录
mkdir -p docs/tasks/archive

# 移动已完成任务
mv docs/tasks/2026-03-25-*.md docs/tasks/archive/
mv docs/tasks/2026-03-26-*.md docs/tasks/archive/
```

### 阶段 4: 整合 memory 目录（15 分钟）

```bash
# 创建 .claude/memory 目录
mkdir -p .claude/memory

# 移动 memory 内容
cat memory/*.md >> .claude/memory/merged-memory.md
# 手动编辑合并后的文件

# 删除旧 memory 目录
rm -rf memory/
```

### 阶段 5: 创建文档索引（15 分钟）

创建 `docs/README.md` 和 `scripts/README.md` 导航文件。

---

## 四、风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 链接失效 | 高 | 中 | 使用相对路径，更新所有内部链接 |
| Git 历史丢失 | 低 | 高 | 使用 `git mv` 保留历史 |
| 脚本路径失效 | 中 | 中 | 更新脚本中的路径引用 |
| 开发中断 | 低 | 低 | 选择非工作时间执行 |

---

## 五、验收标准

- [ ] 根目录文件减少至 15 个以内
- [ ] `docs/README.md` 包含完整文档索引
- [ ] 所有内部链接有效
- [ ] 脚本可正常运行
- [ ] Git 提交历史保留
- [ ] `.gitignore` 正确忽略运行时文件

---

## 六、时间估算

| 阶段 | 工时 | 负责人 |
|------|------|--------|
| 阶段 1: 清理可忽略文件 | 5 分钟 | 后端 |
| 阶段 2: 移动脚本和配置 | 10 分钟 | 后端 |
| 阶段 3: 整理 docs 目录 | 30 分钟 | 后端 |
| 阶段 4: 整合 memory 目录 | 15 分钟 | 后端 |
| 阶段 5: 创建文档索引 | 15 分钟 | 后端 |
| **总计** | **75 分钟** | |

---

*整理方案完成。等待用户审批后执行。*
