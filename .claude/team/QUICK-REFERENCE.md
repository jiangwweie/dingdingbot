# 盯盘狗 Agent Team 快速参考

> **用途**: 快速查阅 MCP 调用权限、文件边界、验证命令
> **完整角色说明**: 见 `.claude/team/README.md` 和各角色 `SKILL.md`

---

## MCP 服务器速查

| 服务器 | 用途 | 调用示例 |
|--------|------|----------|
| `filesystem` | 文件操作 | `mcp__filesystem__read_multiple_files` |
| `sqlite` | 数据库查询 | `mcp__sqlite__read_query` |
| `duckdb` | OLAP 分析 | `mcp__duckdb__read_query` |
| `puppeteer` | 浏览器自动化 | `mcp__puppeteer__screenshot` |

### 需要填写配置的服务器

| 服务器 | 配置项 | 用途 |
|--------|--------|------|
| `telegram` | BOT_TOKEN, CHAT_ID | 告警通知 |
| `ssh` | HOST, USER, KEY_PATH | 远程部署 |
| `sentry` | ORG, PROJECT, TOKEN | 异常追踪 |

配置位置：`~/.claude/mcp.json`

---

## 文件边界速查

| 目录 | Backend | Frontend | QA | Architect |
|------|---------|----------|----|-----------|
| `src/` | ✅ 全权 | ❌ 禁止 | ⚠️ 读取 | 🔍 审查 |
| `gemimi-web-front/` | ❌ 禁止 | ✅ 全权 | ⚠️ 测试 | ❌ 禁止 |
| `tests/` | ⚠️ 协作 | ⚠️ 测试 | ✅ 全权 | 🔍 审查 |
| `config/` | ✅ 全权 | ❌ 禁止 | ❌ 禁止 | 🔍 审查 |
| `docs/` | ✅ 读取 | ✅ 读取 | ✅ 读取 | ✅ 全权 |

**图例**: ✅ 全权 | ❌ 禁止 | ⚠️ 有限权限 | 🔍 仅审查

---

## 验证命令速查

### 后端
```bash
pytest tests/unit/ -v --tb=short
mypy src/
flake8 src/
```

### 前端
```bash
cd gemimi-web-front && npm run type-check
cd gemimi-web-front && npm run build
cd gemimi-web-front && npm run lint
```

### 数据库查询
```sql
-- 信号尝试统计
SELECT strategy_name, final_result, COUNT(*) as count
FROM signal_attempts
GROUP BY strategy_name, final_result;

-- 过滤器拒绝原因
SELECT filter_stage, filter_reason, COUNT(*) as rejected_count
FROM signal_attempts
WHERE final_result = 'FILTERED'
GROUP BY filter_stage, filter_reason;
```

---

*维护者：PM*
*项目：盯盘狗 v3.0*
