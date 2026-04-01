# MCP 工具快速调用卡片

> **速查手册** | 更新日期：2026-04-01

---

## 🔧 已配置工具

| 工具 | 状态 | 用途 |
|------|------|------|
| `sqlite` | ✅ | 数据库查询 |
| `filesystem` | ✅ | 文件操作 |
| `brave-search` | ✅ | 网络搜索 |
| `sequential-thinking` | ✅ | 链式思考 |

---

## 📞 调用语法

### SQLite 查询
```python
mcp__sqlite__read_query(query="SELECT * FROM signals LIMIT 10")
```

### 文件读取
```python
mcp__filesystem__read_text_file(path="src/domain/models.py")
```

### 目录浏览
```python
mcp__filesystem__list_directory(path="logs/")
```

### 链式思考
```python
Agent(subagent_type="sequential-thinking", 
      prompt="一步步分析...")
```

### 网络搜索
```python
WebSearch(query="CCXT Pro watch_orders example 2026")
```

---

## 🎭 角色快捷指令

### Backend Dev
```python
# 查询过滤原因分布
mcp__sqlite__read_query(query="""
    SELECT filter_reason, COUNT(*) 
    FROM signal_attempts 
    GROUP BY filter_reason 
    ORDER BY count DESC
""")

# 读取配置文件
mcp__filesystem__read_text_file(path="config/core.yaml")

# 复杂逻辑推演
Agent(subagent_type="sequential-thinking",
      prompt="推演热重载时 EMA 状态恢复流程...")
```

### Frontend Dev
```python
# 读取组件文件
mcp__filesystem__read_text_file(path="web-front/src/pages/Backtest.tsx")

# 读取 API 契约
mcp__filesystem__read_text_file(path="src/interfaces/api.py")
```

### QA Tester
```python
# 验证信号数据
mcp__sqlite__read_query(query="""
    SELECT symbol, entry_price, stop_loss_price,
           (entry_price - stop_loss_price) * 100.0 / entry_price as loss_pct
    FROM signals ORDER BY created_at DESC LIMIT 10
""")
```

### Diagnostic Analyst
```python
# 分析过滤分布
mcp__sqlite__read_query(query="""
    SELECT filter_reason, 
           COUNT(*) as count,
           ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as percentage
    FROM signal_attempts 
    WHERE filter_reason IS NOT NULL 
    GROUP BY filter_reason
""")

# 读取日志
mcp__filesystem__read_text_file(path="logs/app.log", tail=100)
```

### DevOps
```python
# 检查数据库状态
mcp__sqlite__read_query(query="""
    SELECT COUNT(*) as total, 
           datetime(MAX(created_at)) as last_signal
    FROM signals
""")
```

### Coordinator
```python
# 任务分解前推演
Agent(subagent_type="sequential-thinking",
      prompt="推演多角色并行开发可能的冲突点...")

# 查询项目进度
mcp__filesystem__read_text_file(path="docs/planning/progress.md")
```

---

## ⚠️ 边界与限制

| 角色 | SQLite 写入 | 文件写入范围 |
|------|-----------|-------------|
| Backend | ✅ 业务表 | `src/`, `config/`, `tests/` |
| Frontend | ❌ | `web-front/` |
| QA | ⚠️ 测试数据 | `tests/` |
| Reviewer | ❌ | ❌ 仅读 |
| Diagnostic | ❌ | `docs/` |
| DevOps | ✅ 运维 | `logs/`, `data/` |

---

## 📖 完整文档

- [MCP 工具整合指南](../../docs/mcp-integration/量化开发 MCP 工具整合指南.md)
- [角色调用规范](./MCP-INTEGRATION.md)

---

**快捷命令**:
```bash
# 查看 MCP 配置
cat .mcp.json

# 测试 SQLite MCP
uvx mcp-server-sqlite --db-path ./signals.db --help
```
