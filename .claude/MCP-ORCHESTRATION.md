# MCP 编排配置 - 团队技能与权限分配

> **创建日期**: 2026-04-01
> **适用项目**: 盯盘狗 v3.0
> **配置目标**: 为不同角色分配合理的 MCP 调用权限，确保安全高效的协作

---

## MCP 服务器总览

### 已配置服务器 (`~/.claude/mcp.json`)

| 服务器 | 用途 | 状态 |
|--------|------|------|
| `sqlite` | 数据库查询 | ✅ 已配置 |
| `filesystem` | 文件操作 | ✅ 已配置 |
| `puppeteer` | 无头浏览器 | ✅ 已配置 |
| `time` | 时区工具 | ✅ 已配置 |
| `duckdb` | OLAP 分析 | ✅ 已配置 |
| `telegram` | 告警通知 | ⚠️ 需 Token |
| `ssh` | 远程部署 | ⚠️ 需主机信息 |
| `sentry` | 异常追踪 | ⚠️ 需 Token |

### 项目技能 (settings.json)

| 技能 | 命令 | 用途 |
|------|------|------|
| `project-manager` | `/pm` | 项目经理（统一协调入口）⭐ |
| `backend-dev` | `/backend` | 后端开发 |
| `frontend-dev` | `/frontend` | 前端开发 |
| `qa-tester` | `/qa` | 测试专家 |
| `code-reviewer` | `/reviewer` | 代码审查 |
| `architect` | `/architect` | 架构师 |
| `product-manager` | `/product-manager` | 产品经理 |
| `diagnostic-analyst` | `/diagnostic` | 诊断分析师 |
| `tdd-self-heal` | `/tdd` | TDD 自愈 |
| `type-precision-enforcer` | `/type-check` | 类型精度检查 |

---

## 角色权限矩阵

### 权限级别定义

| 级别 | 说明 | 示例 |
|------|------|------|
| ✅ **完全权限** | 可独立调用 | 读取文件、运行测试 |
| ⚠️ **受限权限** | 需特定条件或 PM 授权 | 修改生产配置、部署 |
| ❌ **禁止** | 无权调用 | 越权修改其他模块 |

---

## 各角色 MCP 配置

### 1. Team PM (`/pm`)

**核心职责**: 任务分解、角色调度、进度追踪

#### MCP 调用权限

| MCP 服务器 | 权限 | 使用场景 |
|------------|------|----------|
| `filesystem` | ✅ | 读取任务文档、更新进度文件 |
| `sqlite` | ⚠️ | 仅查询任务状态，不修改业务数据 |
| `duckdb` | ⚠️ | 回测数据分析时调用 |

#### 推荐调用的全局技能

| 阶段 | 技能 | 命令 |
|------|------|------|
| 需求分析 | `brainstorming` | `Agent(subagent_type="brainstorming")` |
| 任务规划 | `planning-with-files-zh` | `/planning-with-files` |
| 并行调度 | `dispatching-parallel-agents` | 单消息多 Agent 调用 |
| 代码审查 | `code-review` | `/reviewer` |
| 完成验证 | `verification-before-completion` | `Agent(subagent_type="verification-before-completion")` |

#### 权限边界

```python
# ✅ 允许的操作
- 读取 docs/planning/*.md
- 更新 docs/planning/progress.md
- 查询 v3_dev.db 的 signal_attempts 表
- 创建/更新 Task

# ❌ 禁止的操作
- 直接修改 src/ 业务代码（由 Dev 负责）
- 直接修改 tests/ 测试代码（由 QA 负责）
- 修改 config/user.yaml 生产配置
```

---

### 2. Backend Developer (`/backend`)

**核心职责**: 领域模型、API 接口、异步服务

#### MCP 调用权限

| MCP 服务器 | 权限 | 使用场景 |
|------------|------|----------|
| `filesystem` | ✅ | 读取/修改 src/ 目录 |
| `sqlite` | ✅ | 查询 schema、验证数据模型 |
| `time` | ✅ | 时区转换、时间戳处理 |
| `duckdb` | ⚠️ | 回测引擎开发时调用 |

#### 推荐调用的全局技能

| 场景 | 技能 | 命令 |
|------|------|------|
| 代码简化 | `code-simplifier` | `/simplify` |
| TDD 开发 | `tdd-self-heal` | `/tdd` |
| 类型检查 | `type-precision-enforcer` | `/type-check` |
| Bug 调试 | `systematic-debugging` | `Agent(subagent_type="systematic-debugging")` |

#### 权限边界

```python
# ✅ 允许的操作
- 读取/修改 src/domain/, src/application/, src/infrastructure/
- 读取/修改 tests/unit/, tests/integration/ (与 QA 协作)
- 读取/修改 config/core.yaml, config/user.yaml
- 查询 v3_dev.db 所有表
- 运行 pytest tests/unit/ -v

# ❌ 禁止的操作
- 修改 gemimi-web-front/ 目录（前端代码）
- 修改 tests/conftest.py（需与 QA 协调）
- 修改 .claude/team/ 配置（需 PM 协调）

# ⚠️ 需要协调的操作
- 修改 API 接口 Schema → 通知 PM 分配给 frontend-dev 对接
- 修改数据库 schema → 通知 PM 记录到 findings.md
```

#### 典型工作流

```python
# 1. 接收任务后调用 TDD 技能
/tdd 实现移动止损功能

# 2. 代码完成后调用简化
/simplify src/domain/risk_manager.py

# 3. 调用类型检查
/type-check src/domain/

# 4. 运行测试验证
pytest tests/unit/test_risk_manager.py -v
```

---

### 3. Frontend Developer (`/frontend`)

**核心职责**: React 组件、TypeScript 类型、UI/UX

#### MCP 调用权限

| MCP 服务器 | 权限 | 使用场景 |
|------------|------|----------|
| `filesystem` | ✅ | 读取/修改 gemimi-web-front/ 目录 |
| `puppeteer` | ✅ | UI 自动化测试、页面截图 |
| `time` | ✅ | 时间格式化、时区显示 |

#### 推荐调用的全局技能

| 场景 | 技能 | 命令 |
|------|------|------|
| UI 设计 | `ui-ux-pro-max` | 设计组件样式 |
| 组件构建 | `web-artifacts-builder` | 复杂组件开发 |
| 代码简化 | `code-simplifier` | `/simplify` |
| E2E 测试 | `webapp-testing` | Playwright 测试 |

#### 权限边界

```python
# ✅ 允许的操作
- 读取/修改 gemimi-web-front/ 所有文件
- 读取后端 API Schema (src/domain/models.py)
- 调用 puppeteer 进行页面测试
- 调用 ui-ux-pro-max 设计样式

# ❌ 禁止的操作
- 修改 src/ 目录（后端代码）
- 修改 tests/ 目录（与 QA 协作但不直接修改）
- 修改 config/ 目录

# ⚠️ 需要协调的操作
- 需要 API 字段变更 → 通知 PM 分配给 backend-dev
- 需要修改类型定义 → 与 backend-dev 对齐契约
```

#### 典型工作流

```typescript
// 1. 阅读契约文档
// docs/designs/preview-contract.md

// 2. 调用 UI 设计技能
Agent(subagent_type="ui-ux-pro-max", prompt="设计预览按钮的交互样式")

// 3. 实现组件后调用简化
/simplify gemimi-web-front/src/components/PreviewButton.tsx

// 4. 调用 E2E 测试
Agent(subagent_type="webapp-testing", prompt="为预览功能编写 Playwright 测试")
```

---

### 4. QA Tester (`/qa`)

**核心职责**: 测试策略、单元测试、集成测试、E2E 测试

#### MCP 调用权限

| MCP 服务器 | 权限 | 使用场景 |
|------------|------|----------|
| `filesystem` | ✅ | 读取/修改 tests/ 目录 |
| `sqlite` | ✅ | 查询测试数据、验证结果 |
| `duckdb` | ✅ | 回测数据验证 |

#### 推荐调用的全局技能

| 场景 | 技能 | 命令 |
|------|------|------|
| E2E 测试 | `webapp-testing` | Playwright 测试 |
| 测试简化 | `code-simplifier` | `/simplify` |
| 测试失败分析 | `systematic-debugging` | `Agent(subagent_type="systematic-debugging")` |
| 测试质量审查 | `code-review` | `/reviewer` |

#### 权限边界

```python
# ✅ 允许的操作
- 读取/修改 tests/ 所有文件
- 读取 src/ 目录（理解被测代码）
- 查询 v3_dev.db 验证测试结果
- 运行 pytest tests/ -v
- 生成覆盖率报告 pytest --cov=src

# ❌ 禁止的操作
- 直接修改 src/ 业务代码（发现 Bug 时通知对应 Dev 修复）
- 修改 gemimi-web-front/ 业务代码
- 修改 config/ 生产配置

# ⚠️ 需要协调的操作
- 测试发现 Bug → 通知 PM 分配修复任务
- 需要修改测试断言策略 → 通知 PM 确认
```

#### 典型工作流

```python
# 1. 阅读契约文档，设计测试用例
# docs/designs/preview-contract.md

# 2. 编写测试代码
# tests/unit/test_preview_api.py

# 3. 运行测试
pytest tests/unit/test_preview_api.py -v

# 4. 测试失败时调用调试
Agent(subagent_type="systematic-debugging", prompt="test_preview_api 失败，分析根因")

# 5. 生成覆盖率报告
pytest tests/unit/ --cov=src --cov-report=html
```

---

### 5. Code Reviewer (`/reviewer`)

**核心职责**: 独立代码审查、架构一致性检查、安全隐患识别

#### MCP 调用权限

| MCP 服务器 | 权限 | 使用场景 |
|------------|------|----------|
| `filesystem` | ✅ | 读取所有代码文件 |
| `sqlite` | ⚠️ | 仅查询验证特定问题 |

#### 推荐调用的全局技能

| 场景 | 技能 | 命令 |
|------|------|------|
| 类型精度审查 | `type-precision-enforcer` | `/type-check` |
| 并发审查 | `concurrency-audit` | (待实现) |
| 契约同步检查 | `contract-sync` | (待实现) |

#### 权限边界

```python
# ✅ 允许的操作
- 读取所有源代码文件
- 读取测试文件
- 读取架构文档
- 运行检查脚本 (scripts/check_*.py)
- 批准/拒绝代码合并

# ❌ 禁止的操作
- 直接修改业务代码（发现问题通知对应角色修复）
- 修改测试断言
- 修改配置文件

# ⚠️ 需要协调的操作
- 发现严重架构问题 → 通知 PM 重新规划
```

#### 审查清单

```markdown
## 审查检查清单

### 类型安全
- [ ] 无 float 污染 (domain 层)
- [ ] Pydantic 模型有 discriminator
- [ ] 金额计算使用 Decimal

### 并发安全
- [ ] 无持锁时的网络 I/O
- [ ] asyncio.Lock 正确释放
- [ ] 数据库事务正确处理

### 架构一致性
- [ ] domain 层无 I/O 依赖
- [ ] Clean Architecture 分层正确
- [ ] 日志脱敏正确

### 测试质量
- [ ] 测试覆盖率 ≥ 80%
- [ ] 边界条件已测试
- [ ] 回归测试通过
```

---

## MCP 调用最佳实践

### 1. 数据库查询 (SQLite MCP)

```python
# ✅ 推荐：只读查询
mcp__sqlite__read_query: |
  SELECT * FROM signal_attempts 
  WHERE final_result = 'FILTERED'
  LIMIT 10

# ❌ 避免：直接修改生产数据
mcp__sqlite__write_query: |
  DELETE FROM signals WHERE ...  # 除非是测试清理

# ✅ 允许：测试数据清理
mcp__sqlite__write_query: |
  DELETE FROM test_cache WHERE created_at < datetime('now', '-1 hour')
```

### 2. 文件操作 (FileSystem MCP)

```python
# ✅ 推荐：读取多个文件
mcp__filesystem__read_multiple_files:
  paths:
    - src/domain/models.py
    - src/application/signal_pipeline.py

# ✅ 推荐：搜索文件
mcp__filesystem__search_files:
  path: src/domain
  pattern: "**/*.py

# ❌ 避免：越权修改
mcp__filesystem__write_file:
  path: gemimi-web-front/src/components/...  # 后端角色禁止
```

### 3. Python 执行 (Bash 权限)

```bash
# ✅ 允许的运行测试命令
Bash(pytest tests/unit/ -v)
Bash(python3 scripts/check_float.py)
Bash(python3 -c "import decimal; ...")

# ⚠️ 需要授权的命令
Bash(python3 src/main.py)  # 启动生产服务
Bash(git push origin main)  # 推送到主分支
```

---

## 技能调用流程图

```
                    ┌─────────────────┐
                    │  用户需求输入    │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  PM    │
                    │  任务分解        │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
     ┌────────────┐ ┌────────────┐ ┌────────────┐
     │ Backend    │ │ Frontend   │ │ QA         │
     │ /backend   │ │ /frontend  │ │ /qa        │
     └─────┬──────┘ └─────┬──────┘ └─────┬──────┘
           │              │              │
           │ 调用技能      │ 调用技能      │ 调用技能
           ▼              ▼              ▼
     ┌────────────┐ ┌────────────┐ ┌────────────┐
     │ /tdd       │ │ /ui-ux     │ │ /webapp    │
     │ /simplify  │ │ /simplify  │ │ /debug     │
     │ /type-check│ │            │ │            │
     └─────┬──────┘ └─────┬──────┘ └─────┬──────┘
           │              │              │
           └──────────────┼──────────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │  Reviewer       │
                 │  /reviewer      │
                 │  /type-check    │
                 └────────┬────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │  PM    │
                 │  整合输出        │
                 └─────────────────┘
```

---

## 权限配置文件

### settings.local.json 权限配置

```json
{
  "permissions": {
    "allow": [
      "Bash(python3 -c \"import json; json.load\\(open\\(''/Users/jiangwei/Documents/final/.claude/settings.json''\\)\\)\")",
      "Bash(ls -la /Users/jiangwei/Documents/final/.claude/*.json)",
      "Bash(CLAUDE_DEBUG=1 claude --version)",
      "Bash(grep -v \"^team$\")",
      "Bash(grep -v \"^\\\\.$\")",
      "Bash(grep -v \"^\\\\.\\\\.$\")",
      "Bash(tmux ls:*)",
      "Bash(python3:*)",
      "Bash(python:*)",
      "Bash(git add:*)",
      "Bash(git reset:*)",
      "Bash(git commit:*)",
      "mcp__filesystem__write_file",
      "mcp__filesystem__read_text_file",
      "mcp__filesystem__read_multiple_files",
      "mcp__filesystem__create_directory",
      "mcp__filesystem__search_files",
      "mcp__filesystem__move_file",
      "mcp__sqlite__read_query",
      "mcp__sqlite__describe_table",
      "mcp__sqlite__list_tables",
      "mcp__sqlite__append_insight",
      "Read(//Users/jiangwei/Documents/final/**)",
      "Grep(**.py)",
      "Glob(**/*.py)",
      "Bash(pytest:*)",
      "Bash(python3 scripts/check_float.py)",
      "Bash(python3 scripts/check_quantize.py)"
    ]
  },
  "enabledMcpjsonServers": [
    "filesystem",
    "sqlite",
    "time",
    "duckdb",
    "puppeteer"
  ]
}
```

---

## 故障排查

### MCP 工具调用失败

```bash
# 1. 检查 MCP 服务器是否加载
cat ~/.claude/mcp.json

# 2. 检查 permissions.allow 是否包含对应权限
cat .claude/settings.local.json | jq '.permissions.allow'

# 3. 重启 Claude Code
/exit
claude
```

### 技能未加载

```bash
# 检查 settings.json 配置
cat .claude/settings.json | jq '.skills.local'

# 确认技能文件存在
ls -la .claude/skills/*/SKILL.md
ls -la .claude/team/*/SKILL.md
```

---

*维护者：AI Builder*
*项目：盯盘狗 v3.0*
*最后更新：2026-04-01*
