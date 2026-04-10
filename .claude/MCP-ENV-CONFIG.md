# MCP 服务器环境变量配置指南

> **配置日期**: 2026-04-01
> **最后更新**: 2026-04-10
> **文件位置**: `~/.claude/mcp.json`

---

## 已配置的 MCP 服务器清单

| 服务器 | 状态 | 用途 | 配置项 |
|--------|------|------|--------|
| **sqlite** | ✅ 已配置 | 本地数据库查询 | `--db-path` 已指向 v3_dev.db |
| **filesystem** | ✅ 已配置 | 文件操作/代码检索 | 路径已指向 final 项目 |
| **puppeteer** | ✅ 已配置 | 无头浏览器自动化 | 无需额外配置 |
| **time** | ✅ 已配置 | 时区/时间戳处理 | 无需额外配置 |
| **duckdb** | ✅ 已配置 | OLAP 数据分析 | `--db-path` 已配置 backtest.db |
| **git** | ✅ 已配置 | Git 版本控制 | 路径已指向 final 项目 |

---

## 待启用服务器（需真实凭证）

以下服务器已不在 `~/.claude/mcp.json` 中，需要时再添加：

| 服务器 | 用途 | 需要的凭证 |
|--------|------|-----------|
| **telegram** | 告警通知 | BOT_TOKEN, CHAT_ID |
| **ssh** | 远程部署 | HOST, USER, KEY_PATH |
| **sentry** | 异常追踪 | ORG, PROJECT, AUTH_TOKEN |

---

## 如何启用新服务器

### 1. Telegram 通知 (实盘告警)

**获取步骤**:
1. 在 Telegram 搜索 `@BotFather`
2. 发送 `/newbot` 创建机器人
3. 复制 Token
4. 创建频道，添加机器人为管理员
5. 获取频道 ID

**添加到 `~/.claude/mcp.json`**:
```json
"telegram": {
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-telegram"],
  "env": {
    "TELEGRAM_BOT_TOKEN": "你的真实 Token",
    "TELEGRAM_CHAT_ID": "你的频道 ID"
  }
}
```

**同时在项目的 `.claude/settings.local.json` 中启用**:
```json
"enabledMcpjsonServers": ["filesystem", "sqlite", "time", "duckdb", "puppeteer", "git", "telegram"]
```

---

### 2. SSH 远程服务器

**添加到 `~/.claude/mcp.json`**:
```json
"ssh": {
  "command": "uvx",
  "args": ["mcp-server-ssh"],
  "env": {
    "SSH_HOST": "你的服务器 IP",
    "SSH_USER": "用户名",
    "SSH_KEY_PATH": "~/.ssh/id_ed25519"
  }
}
```

**安全建议**:
- 使用专用的 SSH 密钥
- 仅授予只读命令权限

---

### 3. Sentry 错误监控

**添加到 `~/.claude/mcp.json`**:
```json
"sentry": {
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-sentry"],
  "env": {
    "SENTRY_ORG": "你的组织名称",
    "SENTRY_PROJECT": "dingpingbot",
    "SENTRY_AUTH_TOKEN": "你的 Auth Token"
  }
}
```

---

*维护者：AI Builder*
*项目：盯盘狗 v3.0*
