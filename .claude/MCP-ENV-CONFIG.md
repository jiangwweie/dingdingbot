# MCP 服务器环境变量配置指南

> **配置日期**: 2026-04-01
> **文件位置**: `~/.claude/mcp.json`

---

## 已配置的 MCP 服务器清单

| 服务器 | 状态 | 用途 | 配置项 |
|--------|------|------|--------|
| **sqlite** | ✅ 已配置 | 本地数据库查询 | `--db-path` 已指向 v3_dev.db |
| **filesystem** | ✅ 已配置 | 文件操作/代码检索 | 路径已指向 final 项目 |
| **puppeteer** | ✅ 已配置 | 无头浏览器自动化 | 无需额外配置 |
| **time** | ✅ 已添加 | 时区/时间戳处理 | 无需额外配置 |
| **telegram** | ⚠️ 需填写 Token | 告警通知 | TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID |
| **ssh** | ⚠️ 需填写主机信息 | 远程部署 | SSH_HOST, SSH_USER, SSH_KEY_PATH |
| **sentry** | ⚠️ 需填写 Token | 异常追踪 | SENTRY_ORG, SENTRY_PROJECT, SENTRY_AUTH_TOKEN |
| **duckdb** | ✅ 已添加 | OLAP 数据分析 | --db-path 已配置 |
| **openclaw** | ⚠️ 需验证 | 内部网关 | 已有配置，需验证 connectivity |

---

## 需要填写的真实配置

### 1. Telegram 通知 (实盘告警)

**获取步骤**:
1. 在 Telegram 搜索 `@BotFather`
2. 发送 `/newbot` 创建机器人
3. 复制 Token (格式如：`123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)
4. 创建频道或群组，添加机器人为管理员
5. 获取频道 ID (格式如：`-1001234567890`)

**更新位置**: `~/.claude/mcp.json`
```json
"telegram": {
  "env": {
    "TELEGRAM_BOT_TOKEN": "123456789:ABCdefGHIjklMNOpqrsTUVwxyz",
    "TELEGRAM_CHAT_ID": "-1001234567890"
  }
}
```

---

### 2. SSH 远程服务器 (新加坡节点)

**更新位置**: `~/.claude/mcp.json`
```json
"ssh": {
  "env": {
    "SSH_HOST": "你的服务器 IP 或域名",
    "SSH_USER": "用户名 (如 ubuntu/deploy)",
    "SSH_KEY_PATH": "~/.ssh/id_ed25519"
  }
}
```

**安全建议**:
- 使用专用的 SSH 密钥（不要使用个人主密钥）
- 在服务器上限制该密钥的权限（`~/.ssh/authorized_keys` 中添加 `command="..."` 限制）
- 仅授予只读命令权限

---

### 3. Sentry 错误监控

**获取步骤**:
1. 访问 https://sentry.io
2. 创建项目 (选择 Python)
3. 进入 Settings → API Keys 创建 Auth Token
4. 获取 Organization Slug

**更新位置**: `~/.claude/mcp.json`
```json
"sentry": {
  "env": {
    "SENTRY_ORG": "你的组织名称",
    "SENTRY_PROJECT": "dingpingbot",
    "SENTRY_AUTH_TOKEN": "sntrys_xxx..."
  }
}
```

---

### 4. OpenClaw 内部网关 (如使用)

**当前配置**:
```json
"openclaw": {
  "args": [
    "acp",
    "--url", "ws://127.0.0.1:18789",
    "--token-file", "~/.openclaw/gateway.token",
    "--session", "agent:main:main"
  ]
}
```

**验证连接**:
```bash
# 检查网关是否运行
curl http://127.0.0.1:18789/health

# 检查 token 文件是否存在
cat ~/.openclaw/gateway.token
```

---

## 快速测试命令

### Telegram 测试
```bash
# 手动测试 bot token 是否有效
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getMe"
```

### SSH 测试
```bash
# 测试 SSH 连接
ssh -i ~/.ssh/id_ed25519 deploy@your-server.com
```

### Sentry 测试
```bash
# 验证 Token 是否有效
curl -H "Authorization: Bearer <YOUR_TOKEN>" \
  https://sentry.io/api/0/organizations/
```

---

## 配置验证清单

- [ ] Telegram Bot Token 已填写并验证
- [ ] Telegram Chat ID 已填写
- [ ] SSH 主机地址已填写
- [ ] SSH 用户名已填写
- [ ] SSH 密钥路径正确
- [ ] Sentry Org 已填写
- [ ] Sentry Project 已填写
- [ ] Sentry Auth Token 已填写
- [ ] OpenClaw 网关运行正常
- [ ] 所有配置保存后重启 Claude Code

---

## 重启 Claude Code 使配置生效

```bash
# 退出当前 Claude 会话
/exit

# 重新启动
claude
```

或者在桌面应用中：
1. 关闭 Claude Code 窗口
2. 重新打开应用
3. 验证新 MCP 服务器是否加载：`/help mcp`

---

*维护者：AI Builder*
*项目：盯盘狗 v3.0*
