# 团队技能与 MCP 配置完成总结

> **配置日期**: 2026-04-01
> **项目**: 盯盘狗 v3.0
> **状态**: ✅ 配置完成

---

## 完成的配置工作

### 1. MCP 服务器配置 (全局 `~/.claude/mcp.json`)

已配置 8 个 MCP 服务器：

| 服务器 | 状态 | 用途 |
|--------|------|------|
| `sqlite` | ✅ | 查询 v3_dev.db |
| `filesystem` | ✅ | 文件操作 |
| `puppeteer` | ✅ | 无头浏览器 |
| `time` | ✅ | 时区工具 |
| `duckdb` | ✅ | OLAP 分析 |
| `telegram` | ⚠️ | 需填写 Token |
| `ssh` | ⚠️ | 需填写主机信息 |
| `sentry` | ⚠️ | 需填写 Token |

### 2. 项目技能注册 (`.claude/settings.json`)

已注册 7 个技能：

| 技能 | 命令 | 用途 |
|------|------|------|
| `team-coordinator` | `/coordinator` | 任务分解与调度 |
| `backend-dev` | `/backend` | 后端开发 |
| `frontend-dev` | `/frontend` | 前端开发 |
| `qa-tester` | `/qa` | 测试专家 |
| `code-reviewer` | `/reviewer` | 代码审查 |
| `tdd-self-heal` | `/tdd` | TDD 闭环自愈 ⭐ |
| `type-precision-enforcer` | `/type-check` | 类型精度检查 ⭐ |

### 3. 团队角色技能更新

已为以下角色添加 MCP 调用指南：

| 角色 | 文件 | 更新内容 |
|------|------|----------|
| Coordinator | `team/team-coordinator/SKILL.md` | MCP 查询权限、调度指南 |
| Backend Dev | `team/backend-dev/SKILL.md` | TDD、类型检查、MCP 查询 |
| Frontend Dev | `team/frontend-dev/SKILL.md` | UI 设计、E2E 测试、Puppeteer |
| QA Tester | `team/qa-tester/SKILL.md` | 测试技能、数据库查询 |
| Code Reviewer | `team/code-reviewer/SKILL.md` | 类型检查、审查脚本 |

### 4. 创建的文档

| 文档 | 路径 | 用途 |
|------|------|------|
| MCP 编排配置 | `.claude/MCP-ORCHESTRATION.md` | 角色权限矩阵 |
| MCP 快速参考 | `.claude/team/QUICK-REFERENCE.md` | 速查表 |
| Agentic Workflow | `.claude/skills/agentic-workflow/README.md` | 高阶技能设计 |
| TDD 自愈技能 | `.claude/skills/agentic-workflow/tdd-self-heal/SKILL.md` | TDD 工作流 |
| 类型精度技能 | `.claude/skills/agentic-workflow/type-precision-enforcer/SKILL.md` | 精度检查 |

### 5. 创建的检查脚本

| 脚本 | 用途 | 状态 |
|------|------|------|
| `scripts/check_float.py` | 检测 float 污染 | ✅ 可运行 |
| `scripts/check_quantize.py` | 检测 TickSize 格式化 | ✅ 可运行 |

---

## 角色权限总览

### 文件修改权限

| 目录 | Backend | Frontend | QA | Reviewer | Coordinator |
|------|---------|----------|----|----------|-------------|
| `src/` | ✅ | ❌ | ⚠️ | ✅ | ✅ |
| `web-front/` | ❌ | ✅ | ⚠️ | ✅ | ✅ |
| `tests/` | ⚠️ | ⚠️ | ✅ | ✅ | ⚠️ |
| `config/` | ✅ | ❌ | ❌ | ✅ | ✅ |

**图例**: ✅ 全权 | ❌ 禁止 | ⚠️ 有限权限

### MCP 调用权限

| 角色 | SQLite | FileSystem | DuckDB | Puppeteer | Time |
|------|--------|------------|--------|-----------|------|
| Backend | ✅ | ✅ | ⚠️ | ❌ | ✅ |
| Frontend | ❌ | ✅ | ❌ | ✅ | ✅ |
| QA | ✅ | ✅ | ✅ | ⚠️ | ❌ |
| Reviewer | ⚠️ | ✅ | ❌ | ❌ | ❌ |
| Coordinator | ⚠️ | ✅ | ⚠️ | ❌ | ❌ |

---

## 典型工作流

### 新功能开发 (TDD + 类型检查)

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

# 6. Coordinator 整合交付
```

### Bug 修复流程

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

# 6. Coordinator 交付
```

---

## 待完成的配置

### 需要填写真实信息的 MCP 服务器

编辑 `~/.claude/mcp.json`：

```json
"telegram": {
  "env": {
    "TELEGRAM_BOT_TOKEN": "你的 Bot Token",
    "TELEGRAM_CHAT_ID": "你的频道 ID"
  }
},
"ssh": {
  "env": {
    "SSH_HOST": "你的服务器 IP",
    "SSH_USER": "用户名",
    "SSH_KEY_PATH": "~/.ssh/id_ed25519"
  }
},
"sentry": {
  "env": {
    "SENTRY_ORG": "组织名",
    "SENTRY_PROJECT": "dingpingbot",
    "SENTRY_AUTH_TOKEN": "Token"
  }
}
```

### 待实现的技能

| 技能 | 用途 | 状态 |
|------|------|------|
| 契约双向同步 | 代码↔文档同步 | 📋 设计完成 |
| 并发幽灵猎手 | 并发代码审查 | 📋 设计完成 |
| 沙箱时间旅行 | 回测时间伪造 | 📋 设计完成 |

---

## 快速入门

### 使用 TDD 技能

```bash
# 调用 TDD 自愈技能
/tdd 实现移动止损功能
契约文档：docs/v3/phase3-risk-state-machine-contract.md
测试用例：UT-005 ~ UT-008
```

### 运行类型检查

```bash
# 使用技能
/type-check src/domain/

# 或直接运行脚本
python3 scripts/check_float.py
python3 scripts/check_quantize.py
```

### 查询数据库

```python
# 查询信号统计
mcp__sqlite__read_query: |
  SELECT 
    strategy_name,
    COUNT(*) as total_signals,
    SUM(CASE WHEN status = 'SENT' THEN 1 ELSE 0 END) as sent_count
  FROM signal_attempts
  GROUP BY strategy_name
```

---

## 相关文档索引

| 文档 | 路径 |
|------|------|
| MCP 编排配置 | `.claude/MCP-ORCHESTRATION.md` |
| MCP 快速开始 | `.claude/MCP-QUICKSTART.md` |
| MCP 环境变量 | `.claude/MCP-ENV-CONFIG.md` |
| 团队快速参考 | `.claude/team/QUICK-REFERENCE.md` |
| Agentic Workflow | `.claude/skills/agentic-workflow/README.md` |

---

## 配置验证清单

- [x] MCP 服务器配置 (`~/.claude/mcp.json`)
- [x] 项目技能注册 (`.claude/settings.json`)
- [x] 团队角色技能更新 (5 个 SKILL.md)
- [x] 检查脚本创建 (`scripts/check_*.py`)
- [x] 文档创建 (4 个新文档)
- [ ] Telegram 配置 (需填写)
- [ ] SSH 配置 (需填写)
- [ ] Sentry 配置 (需填写)

---

*配置完成日期：2026-04-01*
*维护者：AI Builder*
*项目：盯盘狗 v3.0*
