# MCP 工具配置总结

> **配置日期**: 2026-04-01
> **状态**: ✅ 已完成

---

## 📦 已安装的 MCP 工具

| 工具 | 安装方式 | 配置位置 | 状态 |
|------|---------|---------|------|
| Filesystem | `npm install -g` | `.mcp.json` | ✅ 就绪 |
| SQLite | `uv tool install` | `.mcp.json` | ✅ 就绪 |
| Brave Search | `npm install -g` | `.mcp.json` | ✅ 就绪 |
| Sequential Thinking | `npm install -g` | `.mcp.json` | ✅ 就绪 |
| Jupyter | `uvx` (按需) | 可选 | ✅ 可用 |

---

## 📁 项目配置文件

### .mcp.json
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]
    },
    "sqlite": {
      "command": "uvx",
      "args": ["mcp-server-sqlite", "--db-path", "./signals.db"]
    },
    "brave-search": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-brave-search"]
    },
    "sequential-thinking": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
    }
  }
}
```

---

## 📚 团队文档

| 文档 | 路径 | 用途 |
|------|------|------|
| **MCP 工具整合指南** | `docs/mcp-integration/量化开发 MCP 工具整合指南.md` | 完整使用指南 |
| **角色调用规范** | `.claude/team/MCP-INTEGRATION.md` | 各角色调用示例 |
| **快速调用卡片** | `.claude/commands/mcp.md` | 速查手册 |
| **工作流规范** | `.claude/team/WORKFLOW.md` | 开工/收工规范 (已更新 v1.1) |
| **团队说明** | `.claude/team/README.md` | 团队结构说明 |

---

## 🎭 角色调用示例

### Backend Dev
```python
# 查询信号过滤原因分布
mcp__sqlite__read_query(query="""
    SELECT filter_reason, COUNT(*) as count 
    FROM signal_attempts 
    GROUP BY filter_reason 
    ORDER BY count DESC
""")
```

### Frontend Dev
```python
# 读取组件和 API 契约
mcp__filesystem__read_text_file(path="web-front/src/pages/Backtest.tsx")
mcp__filesystem__read_text_file(path="src/interfaces/api.py")
```

### QA Tester
```python
# 验证信号数据
mcp__sqlite__read_query(query="""
    SELECT symbol, entry_price, stop_loss_price,
           (entry_price - stop_loss_price) * 100.0 / entry_price
    FROM signals ORDER BY created_at DESC LIMIT 10
""")
```

### Diagnostic Analyst
```python
# 分析过滤分布
mcp__sqlite__read_query(query="""
    SELECT filter_reason, COUNT(*), 
           ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2)
    FROM signal_attempts 
    WHERE filter_reason IS NOT NULL 
    GROUP BY filter_reason
""")
```

### Coordinator
```python
# 任务分解前推演
Agent(subagent_type="sequential-thinking",
      prompt="推演多角色并行开发可能的冲突点...")
```

---

## 🔧 测试命令

```bash
# 查看配置
cat .mcp.json

# 测试 SQLite MCP
uvx mcp-server-sqlite --db-path ./signals.db --help

# 测试 Brave Search MCP (需 API 密钥)
npx -y @modelcontextprotocol/server-brave-search --help

# 测试 Sequential Thinking MCP
npx -y @modelcontextprotocol/server-sequential-thinking --help

# 测试 Filesystem MCP
npx -y @modelcontextprotocol/server-filesystem --help
```

---

## ⚠️ 注意事项

1. **Brave Search API 密钥**: 需要配置 `BRAVE_API_KEY` 环境变量才能使用搜索功能
2. **数据库路径**: SQLite 配置使用 `./signals.db`，确保文件存在
3. **文件权限**: Filesystem MCP 只能访问项目根目录及其子目录
4. **Git MCP**: 官方包不存在，使用内置 Bash + `git`/`gh` CLI 替代

---

## 📖 使用流程

```
1. 阅读需求
   ↓
2. 根据需要调用 MCP 工具：
   - 查询数据库 → sqlite
   - 读取文件 → filesystem
   - 复杂分析 → sequential-thinking
   - 外部信息 → brave-search
   ↓
3. 执行任务
   ↓
4. 验证输出
   ↓
5. 提交结果
```

---

## 🚀 下一步

团队成员可以：

1. **使用 `/mcp` 命令** 查看快速调用卡片
2. **阅读角色规范** 了解各自角色的调用示例
3. **开始使用 MCP 工具** 提升开发效率

---

*配置完成 | 2026-04-01*
