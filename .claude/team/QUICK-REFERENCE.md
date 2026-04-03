# 团队技能与 MCP 调用快速参考

> **创建日期**: 2026-04-01
> **项目**: 盯盘狗 v3.0
> **用途**: 快速查阅各角色的技能和 MCP 调用权限

---

## 角色速查表

| 角色 | 命令 | 核心职责 | 关键技能 |
|------|------|----------|----------|
| **Coordinator** | `/coordinator` | 任务分解、调度 | 并行调度、进度追踪 |
| **Backend Dev** | `/backend` | 后端开发 | `/tdd`, `/type-check` |
| **Frontend Dev** | `/frontend` | 前端开发 | `/ui-ux`, `/webapp-testing` |
| **QA Tester** | `/qa` | 测试专家 | `/tdd`, `/webapp-testing` |
| **Code Reviewer** | `/reviewer` | 代码审查 | `/type-check`, `/simplify` |

---

## MCP 服务器速查

### 已配置服务器

| 服务器 | 用途 | 调用示例 |
|--------|------|----------|
| `filesystem` | 文件操作 | `mcp__filesystem__read_multiple_files` |
| `sqlite` | 数据库查询 | `mcp__sqlite__read_query` |
| `time` | 时区工具 | `mcp__time__now` |
| `duckdb` | OLAP 分析 | `mcp__duckdb__read_query` |
| `puppeteer` | 浏览器自动化 | `mcp__puppeteer__screenshot` |

### 需要填写配置的服务器

| 服务器 | 配置项 | 用途 |
|--------|--------|------|
| `telegram` | BOT_TOKEN, CHAT_ID | 告警通知 |
| `ssh` | HOST, USER, KEY_PATH | 远程部署 |
| `sentry` | ORG, PROJECT, TOKEN | 异常追踪 |

**配置位置**: `~/.claude/mcp.json`

---

## 角色专属技能

### Backend Developer (`/backend`)

**核心技能**:
```bash
/tdd                          # TDD 闭环开发
/type-check                   # 类型精度检查
/simplify                     # 代码简化
/reviewer                     # 代码审查
```

**MCP 调用**:
```python
# 查询数据库表结构
mcp__sqlite__describe_table:
  table_name: signals

# 读取多个源文件
mcp__filesystem__read_multiple_files:
  paths:
    - src/domain/models.py
    - src/application/signal_pipeline.py

# 时区转换
mcp__time__format:
  timestamp: 1712000000000
  timezone: "Asia/Shanghai"
```

**权限边界**:
- ✅ `src/`, `config/`, `tests/` (与 QA 协作)
- ❌ `web-front/`

---

### Frontend Developer (`/frontend`)

**核心技能**:
```bash
/ui-ux-pro-max               # UI 设计
/frontend-design             # 前端设计
/web-artifacts-builder       # Web 构件
/simplify                    # 代码简化
/webapp-testing              # E2E 测试
```

**MCP 调用**:
```python
# 读取多个前端文件
mcp__filesystem__read_multiple_files:
  paths:
    - web-front/src/components/StrategyBuilder.tsx
    - web-front/src/types/strategy.ts

# Puppeteer 截图
mcp__puppeteer__navigate:
  url: "http://localhost:5173"
mcp__puppeteer__screenshot:
  selector: "#strategy-builder"
```

**权限边界**:
- ✅ `web-front/`
- ❌ `src/`

---

### QA Tester (`/qa`)

**核心技能**:
```bash
/tdd                          # TDD 闭环开发
/webapp-testing               # E2E 测试
/simplify                     # 测试代码简化
/reviewer                     # 测试质量审查
```

**MCP 调用**:
```python
# 查询信号尝试统计
mcp__sqlite__read_query: |
  SELECT 
    strategy_name,
    final_result,
    COUNT(*) as count
  FROM signal_attempts
  GROUP BY strategy_name, final_result

# 查询过滤器拒绝原因
mcp__sqlite__read_query: |
  SELECT 
    filter_stage,
    filter_reason,
    COUNT(*) as rejected_count
  FROM signal_attempts
  WHERE final_result = 'FILTERED'
  GROUP BY filter_stage, filter_reason
```

**权限边界**:
- ✅ `tests/`, 读取 `src/`
- ❌ 修改 `src/` 业务代码

---

### Code Reviewer (`/reviewer`)

**核心技能**:
```bash
/type-check                   # 类型精度检查
/simplify                     # 代码简化分析
/code-review                  # 正式审查
```

**MCP 调用**:
```python
# 读取多个文件进行审查
mcp__filesystem__read_multiple_files:
  paths:
    - src/domain/risk_manager.py
    - src/domain/strategy_engine.py

# 运行检查脚本
Bash(python3 scripts/check_float.py)
Bash(python3 scripts/check_quantize.py)
```

**权限边界**:
- ✅ 读取所有代码
- ❌ 直接修改业务代码

---

### Team Coordinator (`/coordinator`)

**核心技能**:
```bash
/planning-with-files          # 任务规划
/brainstorming                # 需求探索
```

**MCP 调用**:
```python
# 读取规划文件
mcp__filesystem__read_multiple_files:
  paths:
    - docs/planning/task_plan.md
    - docs/planning/findings.md
    - docs/planning/progress.md

# 查询任务统计
mcp__sqlite__read_query: |
  SELECT 
    strategy_name,
    COUNT(*) as total_signals,
    SUM(CASE WHEN status = 'SENT' THEN 1 ELSE 0 END) as sent_count
  FROM signal_attempts
  GROUP BY strategy_name
```

**权限边界**:
- ✅ 读取所有规划文件
- ❌ 直接修改业务代码/测试代码

---

## 典型工作流

### 新功能开发 (TDD)

```bash
# 1. Coordinator 分解任务
/coordinator 实现移动止损功能

# 2. Backend 调用 TDD 技能
/backend
/tdd 实现移动止损功能

# 3. 代码完成后检查
/simplify src/domain/risk_manager.py
/type-check src/domain/

# 4. QA 编写测试
/qa
/tdd 编写移动止损测试

# 5. Reviewer 审查
/reviewer 审查移动止损代码

# 6. Coordinator 整合
```

### Bug 修复

```bash
# 1. QA 发现 Bug
/qa
pytest tests/unit/test_xxx.py -v
# 测试失败

# 2. 分析根因
Agent(subagent_type="systematic-debugging", 
      prompt="test_xxx 失败，分析根因")

# 3. Backend 修复
/backend
# 修复业务代码

# 4. QA 回归验证
/qa
pytest tests/unit/test_xxx.py -v

# 5. Reviewer 审查
/reviewer 审查 Bug 修复
```

---

## 检查脚本

### 类型精度检查

```bash
# float 使用检测
python3 scripts/check_float.py

# TickSize/LotSize 格式化检查
python3 scripts/check_quantize.py
```

### 输出示例

```
============================================================
float 使用检测 - 量化系统精度检查
============================================================

检查了 28 个 Python 文件

❌ 发现 34 处 float 使用:
  - models.py: 7 处 (score, pattern_score 等)
  - filter_factory.py: 8 处 (float() 调用)
  ...
```

---

## 文件边界总览

| 目录 | Backend | Frontend | QA | Reviewer |
|------|---------|----------|----|----------|
| `src/` | ✅ 全权 | ❌ 禁止 | ⚠️ 读取 | ✅ 读取 |
| `web-front/` | ❌ 禁止 | ✅ 全权 | ⚠️ 测试 | ✅ 读取 |
| `tests/` | ⚠️ 协作 | ⚠️ 测试 | ✅ 全权 | ✅ 审查 |
| `config/` | ✅ 全权 | ❌ 禁止 | ❌ 禁止 | ✅ 读取 |
| `docs/` | ✅ 读取 | ✅ 读取 | ✅ 读取 | ✅ 读取 |

**图例**: ✅ 全权 | ❌ 禁止 | ⚠️ 有限权限

---

## 相关文档

| 文档 | 路径 |
|------|------|
| MCP 编排配置 | `.claude/MCP-ORCHESTRATION.md` |
| MCP 快速开始 | `.claude/MCP-QUICKSTART.md` |
| MCP 环境变量 | `.claude/MCP-ENV-CONFIG.md` |
| Agentic Workflow | `.claude/skills/agentic-workflow/README.md` |

---

*维护者：AI Builder*
*项目：盯盘狗 v3.0*
*最后更新：2026-04-01*
