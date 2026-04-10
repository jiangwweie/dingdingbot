# MCP Servers 完全配置指南 - 盯盘狗量化项目

> **最后更新**: 2026-04-01
> **适用场景**: 量化交易系统开发、回测引擎验证、订单状态机调试、实盘监控

---

## 当前已配置的 MCP 服务器

查看 `settings.local.json` 中的 `enabledMcpjsonServers`:

```json
{
  "enabledMcpjsonServers": [
    "filesystem",  // 文件读写、目录操作
    "git",         // Git 版本控制
    "sqlite"       // SQLite 数据库查询
  ]
}
```

**全局配置文件位置**: `~/.claude/mcp.json`

**当前配置状态** (已更新为当前项目路径):
```json
{
  "mcpServers": {
    "sqlite": {
      "command": "uvx",
      "args": ["mcp-server-sqlite", "--db-path", "/Users/jiangwei/Documents/final/data/v3_dev.db"]
    },
    "filesystem": {
      "command": "node",
      "args": ["/opt/homebrew/lib/node_modules/@modelcontextprotocol/server-filesystem/dist/index.js", "/Users/jiangwei/Documents/final"]
    },
    "puppeteer": {
      "command": "node",
      "args": ["/opt/homebrew/lib/node_modules/@modelcontextprotocol/server-puppeteer/dist/index.js"]
    },
    "time": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-time"]
    },
    "duckdb": {
      "command": "uvx",
      "args": ["mcp-server-duckdb", "--db-path", "/Users/jiangwei/Documents/final/data/backtest.db"]
    },
    "git": {
      "command": "uvx",
      "args": ["mcp-server-git", "--repository", "/Users/jiangwei/Documents/final"]
    }
  }
}
```

> 注：telegram / ssh / sentry 占位符已移除，需要时再添加。详见 [MCP-ENV-CONFIG.md](MCP-ENV-CONFIG.md)。

---

## MCP 服务器分类与使用场景

### 一、增强系统架构与记忆 (Architecture & Context)

#### 1. Memory MCP (知识图谱与长期记忆) 🧠

**应用场景**: v3.0 架构非常庞大（包含 Signal、Order、Position 状态机和 OCO 逻辑），需要在多次会话间保持架构一致性。

**实战效果**:
```
用户：记住 DynamicRiskManager 的职责是只改价格不改数量

→ 下一次对话中:
AI 会自动遵循这条架构红线，不会把数量计算逻辑错误地放入 RiskManager
```

**配置文件**:
```json
{
  "mcpServers": {
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"]
    }
  }
}
```

**相关技能**:
- 项目已有的 `memory/` 目录 (`.claude/memory/`)
- 使用 `mcp__sqlite__append_insight` 添加业务洞察

---

#### 2. File System / Ripgrep MCP (全量代码库极速检索) 🔍

**应用场景**: 当系统膨胀到几十个文件时，查找特定的 CCXT 调用或错误码。

**实战效果**:
```
用户：找出所有包含 Decimal 强转逻辑的代码块

→ AI 瞬间定位并完成批量重构
```

**当前配置**: 已启用 `filesystem` MCP

**可用命令**:
- `mcp__filesystem__search_files` - 递归搜索文件
- `mcp__filesystem__read_text_file` - 读取文件
- `mcp__filesystem__read_multiple_files` - 批量读取
- `Grep` 工具 - 正则内容搜索

---

### 二、极速数据处理与回测引擎 (Data & Backtesting)

#### 3. DuckDB MCP (海量时序数据极速分析) 🦆

**应用场景**: 分析过去三年、精确到分钟的 Binance 历史 K 线，SQLite 性能不足时。

**优势对比**:
| 特性 | SQLite | DuckDB |
|------|--------|---------|
| OLTP | ✅ | ❌ |
| OLAP | ⚠️ 慢 | ✅ 秒级 |
| Parquet 支持 | ❌ | ✅ |
| 时序聚合 | 基础 | 原生优化 |

**安装**:
```bash
# 添加 DuckDB MCP 到 ~/.claude/mcp.json
{
  "mcpServers": {
    "duckdb": {
      "command": "uvx",
      "args": ["mcp-server-duckdb", "--db-path", "/Users/jiangwei/Documents/final/data/backtest.db"]
    }
  }
}
```

**使用示例**:
```sql
-- 加载 Parquet 历史 K 线数据
SELECT 
    symbol,
    timeframe,
    date_trunc('hour', timestamp) as hour,
    avg(close) as avg_close,
    max(high) - min(low) as range
FROM read_parquet('data/klines/*.parquet')
WHERE symbol = 'BTC/USDT:USDT'
GROUP BY 1, 2, 3
ORDER BY 3 DESC;
```

---

#### 4. Time / Timezone MCP (时区与时间戳工具) ⏰

**应用场景**: 加密货币 24/7 交易，处理 UTC 时间、本地时间、MTF 多周期对齐。

**典型问题**:
```python
# 错误示范 - 离一错误
assert htf_open_time + duration <= current_time  # ❌ 时区不一致

# 正确做法
from datetime import timezone, timedelta
utc_now = datetime.now(timezone.utc)
cn_time = utc_now + timedelta(hours=8)
```

**安装**:
```json
{
  "mcpServers": {
    "time": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-time"]
    }
  }
}
```

**使用示例**:
```
用户：现在 Binance 的 4 小时 K 线闭合时间是什么？当前时间距离下一根 K 线还有多久？

→ AI 调用 Time MCP 计算精确的 UTC 时间边界
```

---

### 三、外部交互与通知 (API & Notification)

#### 5. REST API Client / cURL Skill (端点直接调试) 🔌

**应用场景**: 对接交易所 API 前，调试参数验签规则。

**实战效果**:
```
用户：向 https://testnet.binancefuture.com 发送一个创建 0.1 BTC 测试订单的 POST 请求

→ AI 自动生成 HMAC SHA256 签名并发送请求
```

**当前权限**: 已配置 `Bash(curl:*)` 权限

**使用示例**:
```bash
# 币安测试网创建订单
curl -X POST "https://testnet.binancefuture.com/fapi/v1/order" \
  -H "X-MBX-APIKEY: $API_KEY" \
  -d "symbol=BTCUSDT" \
  -d "side=BUY" \
  -d "type=LIMIT" \
  -d "quantity=0.1" \
  -d "price=50000" \
  --data-urlencode "signature=$SIGNATURE"
```

---

#### 6. Telegram MCP (实时告警模块集成) 📢

> ⚠️ 待启用：需要真实 Bot Token 和 Chat ID。详见 [MCP-ENV-CONFIG.md](MCP-ENV-CONFIG.md)。

**应用场景**: 测试 Notifier 模块，验证信号通知的 Markdown 格式。

---

### 四、投研与外部数据源 (Research & Alpha)

#### 7. Puppeteer / Browser Automation MCP (无头浏览器自动化) 🤖

**应用场景**: 抓取非 API 数据源（推特情绪、贪婪恐慌指数、链上数据面板）。

**当前配置**: 已启用 `puppeteer` MCP

**使用示例**:
```
用户：抓取 coinmarketcap.com 的贪婪恐慌指数，并保存为 JSON

→ AI 控制无头浏览器 → 截取数据 → 返回结构化结果
```

**代码示例**:
```javascript
// Puppeteer 抓取示例
const page = await browser.newPage();
await page.goto('https://alternative.me/crypto/fear-and-greed-index/');
const score = await page.$eval('.fng-circular-value', el => el.innerText);
console.log(`Fear & Greed Index: ${score}`);
```

---

#### 8. Brave Search MCP (实时量化文献与 API 检索) 🔎

**应用场景**: 检索"2026 年最新的币安合约 API 限频规则"或量化论文。

**安装**:
```json
{
  "mcpServers": {
    "brave-search": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-brave-search"],
      "env": {
        "BRAVE_API_KEY": "your_api_key"
      }
    }
  }
}
```

**使用示例**:
```
用户：搜索 2025-2026 年关于 Pinbar 形态的最新变种统计论文

→ AI 返回最新论文列表和关键结论
```

**当前 Web 能力**:
- `WebSearch` - 通用搜索
- `WebFetch(domain:docs.ccxt.com)` - CCXT 文档
- `WebFetch(domain:github.com)` - GitHub
- `WebFetch(domain:ccxt.com)` - ccxt.com

---

### 五、部署运维与监控 (DevOps & Monitoring)

#### 9. SSH MCP (云节点直接调度) 🖥️

> ⚠️ 待启用：需要真实服务器信息。详见 [MCP-ENV-CONFIG.md](MCP-ENV-CONFIG.md)。

**应用场景**: 新加坡节点服务器部署，远程更新代码、查看日志。

---

#### 10. Sentry MCP (实盘异常追踪) 🚨

> ⚠️ 待启用：需要真实 Sentry 凭证。详见 [MCP-ENV-CONFIG.md](MCP-ENV-CONFIG.md).

**应用场景**: 实盘系统异常时，快速拉取错误堆栈并定位问题。

---

## 推荐配置清单 (按优先级)

### 🔥 立即配置 (当前开发阶段必需)

| MCP 服务器 | 用途 | 状态 |
|------------|------|------|
| SQLite | 订单/信号数据库查询 | ✅ 已配置 |
| FileSystem | 文件操作/代码检索 | ✅ 已配置 |
| Git | 版本控制 | ✅ 已配置 |
| Time | 时区/时间戳处理 | ✅ 已配置 |
| DuckDB | 海量数据回测 | ✅ 已配置 |
| Puppeteer | 无头浏览器 | ✅ 已配置 |

### 📋 实盘前配置

| MCP 服务器 | 用途 | 优先级 |
|------------|------|--------|
| Telegram | 告警通知测试 | 高 (待启用) |
| SSH | 远程部署监控 | 高 (待启用) |
| Sentry | 异常追踪 | 中 (待启用) |

---

## 权限管理最佳实践

### 安全原则

1. **最小权限**: 仅授予必要操作的权限
2. **分类授权**:  destructive 操作（删除、强制推送）单独审批
3. **审计日志**: 记录所有 MCP 调用历史

### 当前权限配置示例

查看 `settings.local.json` 的 `permissions.allow`:

```json
{
  "permissions": {
    "allow": [
      "mcp__filesystem__*",     // 文件系统操作
      "mcp__sqlite__*",          // 数据库查询
      "Bash(git:*)",             // Git 操作
      "Bash(python3:*)",         // Python 执行
      "Bash(curl:*)",            // API 调试
      "WebSearch",               // 网络搜索
      "WebFetch(domain:*)"       // 网页读取
    ]
  }
}
```

---

## 故障排查

### 问题：MCP 工具返回错误

**排查步骤**:
1. 检查 `~/.claude/mcp.json` 配置是否正确
2. 检查 `settings.local.json` 中 `enabledMcpjsonServers` 是否包含该服务器
3. 检查 `permissions.allow` 是否有对应权限
4. 检查文件/数据库路径是否在允许目录内

### 问题：数据库查询返回空表

**可能原因**: SQLite MCP 指向错误的数据库文件

**解决**:
```bash
# 验证数据库路径
sqlite3 /Users/jiangwei/Documents/final/data/v3_dev.db ".tables"

# 更新 ~/.claude/mcp.json 中的 --db-path 参数
```

### 问题：File System MCP 无法访问某些目录

**解决**: 更新 `~/.claude/mcp.json` 中的路径参数：
```json
"filesystem": {
  "args": [".../server-filesystem/dist/index.js", "/Users/jiangwei/Documents/final"]
}
```

---

## 快捷命令参考

### SQLite 常用查询

```sql
-- 查询最新 10 条信号
SELECT * FROM signals ORDER BY created_at DESC LIMIT 10;

-- 查询所有未处理的信号
SELECT * FROM signals WHERE status = 'PENDING';

-- 统计各策略表现
SELECT 
    strategy_name,
    COUNT(*) as signals,
    AVG(score) as avg_score
FROM signals 
GROUP BY strategy_name;

-- 查询订单执行统计
SELECT 
    exit_reason,
    COUNT(*) as count,
    AVG(pnl) as avg_pnl,
    SUM(pnl) as total_pnl
FROM orders
WHERE status = 'CLOSED'
GROUP BY exit_reason;
```

### Git 工作流

```bash
# 查看当前会话的所有修改
git diff HEAD

# 按模块分类提交
git add src/domain/     # 领域层
git commit -m "feat(domain): xxx"

git add src/infrastructure/  # 基础设施层
git commit -m "feat(infra): xxx"

# 推送到远程分支
git push origin feature-v3-xxx
```

---

*配置日期：2026-04-01*  
*项目：盯盘狗 v3.0*  
*维护者：AI Builder*
