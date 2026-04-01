# 量化开发 MCP 工具整合指南

> **创建日期**: 2026-03-31
> **适用项目**: 盯盘狗 v3.0+
> **目标**: 利用 MCP 工具提升单兵量化开发效率

---

## 已配置工具 ✅

### 项目配置 (`.mcp.json`)

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

### 全局安装状态 ✅ (2026-03-31)

| MCP 服务器 | 安装方式 | 状态 |
|-----------|---------|------|
| `@modelcontextprotocol/server-filesystem` | npm global | ✅ 已安装 |
| `mcp-server-sqlite` | uv tool | ✅ 已安装 |
| `@modelcontextprotocol/server-brave-search` | npm global | ✅ 已安装 |
| `@modelcontextprotocol/server-sequential-thinking` | npm global | ✅ 已安装 |
| `mcp-server-jupyter` | uvx (按需) | ✅ 已安装 |

### Git MCP ✅

**状态**: 已配置

**应用场景**:

| 场景 | 指令示例 |
|------|----------|
| **智能提交** | `检视我对 domain/models.py 和 risk_manager.py 的修改，按领域层/应用层分类生成 commit` |
| **分支管理** | `创建 feature-v3-risk 分支，推送当前进度` |
| **代码审查** | `获取最近 3 个 commit 的 diff，检查是否有违反 Clean Architecture 的导入` |
| **变更溯源** | `谁在什么时候修改了 filter_factory.py 中的 ATR 计算逻辑？` |

### Filesystem MCP ✅

**状态**: 已配置

**应用场景**:

| 场景 | 指令示例 |
|------|----------|
| **项目导航** | `列出 src/domain/目录下所有 Python 文件` |
| **配置检查** | `读取 config/core.yaml 中的 pinbar 默认参数` |
| **日志分析** | `读取 logs/目录中最新的日志文件` |

### SQLite MCP ✅

**状态**: 已配置（signals.db）

**扩展应用场景**:

| 场景 | 指令示例 |
|------|----------|
| **订单状态排查** | `帮我查一下刚刚跑的回测里，所有被打损出局（filter_reason 包含'stop_loss'）的信号` |
| **信号去重验证** | `查询 signals 表中 dedup_key 重复的记录` |
| **MTF 过滤分析** | `统计 signal_attempts 表中 filter_reason='mtf_trend_mismatch' 的次数按周期分组` |
| **止损距离审计** | `找出所有止损距离 < 0.1% 的异常信号记录` |

**常用查询模板**:

```sql
-- 查询最近 24 小时被过滤的信号尝试
SELECT 
    symbol, 
    timeframe, 
    pattern,
    filter_reason,
    metadata,
    created_at
FROM signal_attempts 
WHERE created_at >= datetime('now', '-24 hours')
AND filter_reason IS NOT NULL
ORDER BY created_at DESC
LIMIT 50;

-- 统计各过滤原因的分布
SELECT 
    filter_reason,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as percentage
FROM signal_attempts 
WHERE filter_reason IS NOT NULL
GROUP BY filter_reason
ORDER BY count DESC;

-- 查询止损距离异常小的信号（< 0.1%）
SELECT 
    symbol,
    timeframe,
    entry_price,
    stop_loss_price,
    ROUND(ABS(entry_price - stop_loss_price) * 100.0 / entry_price, 4) as stop_loss_pct
FROM signals
WHERE ABS(entry_price - stop_loss_price) * 100.0 / entry_price < 0.1
ORDER BY stop_loss_pct ASC;
```

---

## 建议扩展工具（可选）

### Jupyter / Python Execution MCP

**状态**: 待配置

**配置方法**:
```json
{
  "mcpServers": {
    "jupyter": {
      "command": "uvx",
      "args": ["mcp-server-jupyter"]
    }
  }
}
```

**应用场景**:

| 场景 | 指令示例 |
|------|----------|
| **ATR 阈值验证** | `生成 1000 根虚拟 K 线，测试 ATR 过滤器在不同 min_atr_ratio 阈值下的信号通过率` |
| **Pinbar 参数优化** | `回测过去 30 天数据，对比 min_wick_ratio=0.5 vs 0.6 的信号质量和盈亏比` |
| **仓位公式验证** | `用 100 组随机数据验证方案 B 的风险头寸计算是否会出现超仓` |
| **滑点敏感性分析** | `模拟 0.01%~0.1% 滑点区间，对最终收益的影响曲线` |

**示例工作流**:
```
1. 让 MCP 启动 Jupyter 内核
2. 生成测试数据（随机 K 线 / 历史数据采样）
3. 运行待验证逻辑（如 DynamicRiskManager）
4. 输出统计结果（通过率、盈亏比、最大回撤）
5. 可选：用字符画打印资金曲线
```

---

### Brave Search MCP ✅

**状态**: 已全局安装并配置

**配置方法**:
```json
{
  "mcpServers": {
    "brave-search": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-brave-search"]
    }
  }
}
```

**应用场景**:

| 场景 | 指令示例 |
|------|----------|
| **交易所规则更新** | `获取 2026 年币安合约 API 最新的限频规则和 ReduceOnly 要求` |
| **CCXT 文档查询** | `获取 CCXT Pro 关于 watch_orders 和 watch_balance 的最新用法` |
| **竞品分析** | `搜索 2026 年最新的开源加密货币回测框架，分析它们的订单状态机设计` |
| **文献调研** | `查找关于 Pinbar 形态成功率的最新量化研究论文` |

**示例工作流**:
```
1. 用户：需要处理 Binance 的 ReduceOnly 规则
2. MCP: 搜索 Binance Futures API 最新文档
3. MCP: 提取 reduceOnly 参数的合法场景
4. MCP: 检查当前代码中的下单逻辑
5. MCP: 生成符合最新规范的修复方案
```

---

### Sequential Thinking MCP ✅

**状态**: 已全局安装并配置

**配置方法**:
```json
{
  "mcpServers": {
    "sequential-thinking": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
    }
  }
}
```

**应用场景**:

| 场景 | 指令示例 |
|------|----------|
| **并发边界推演** | `推演 500 并发 K 线到达时，信号去重锁的获取顺序和可能的死锁场景` |
| **状态机流转** | `一步步推演 TP1 成交后，OCO 订单取消 + 移动止损激活的完整状态变迁` |
| **竞态条件分析** | `分析 WebSocket 断连瞬间，重连回调与轮询快照同时到达时的数据覆盖逻辑` |
| **异常恢复沙盘** | `推演数据库锁超时后，事务回滚 + 状态恢复的完整流程` |

**示例工作流**:
```
1. 修改核心逻辑前（如撮合引擎）
2. 启动 Sequential Thinking MCP
3. 强制输出：
   - T0: 初始状态（订单簿、持仓、余额）
   - T1: 触发条件（价格穿越 TP1）
   - T2: 并发事件（WS 断连 / 新 K 线到达）
   - T3: 锁获取顺序（DB 行锁 → 内存锁）
   - T4: 最终状态（成交、取消、更新）
4. 识别潜在 Race Condition
5. 修改代码 + 添加防御性断言
```

---

### Jupyter / Python Execution MCP

**状态**: 已安装（uvx 按需调用），可选配置

**配置方法**:
```json
{
  "mcpServers": {
    "jupyter": {
      "command": "uvx",
      "args": ["mcp-server-jupyter"]
    }
  }
}
```

**应用场景**:

| 场景 | 指令示例 |
|------|----------|
| **ATR 阈值验证** | `生成 1000 根虚拟 K 线，测试 ATR 过滤器在不同 min_atr_ratio 阈值下的信号通过率` |
| **Pinbar 参数优化** | `回测过去 30 天数据，对比 min_wick_ratio=0.5 vs 0.6 的信号质量和盈亏比` |
| **仓位公式验证** | `用 100 组随机数据验证方案 B 的风险头寸计算是否会出现超仓` |
| **滑点敏感性分析** | `模拟 0.01%~0.1% 滑点区间，对最终收益的影响曲线` |

**示例工作流**:
```
1. 让 MCP 启动 Jupyter 内核
2. 生成测试数据（随机 K 线 / 历史数据采样）
3. 运行待验证逻辑（如 DynamicRiskManager）
4. 输出统计结果（通过率、盈亏比、最大回撤）
5. 可选：用字符画打印资金曲线
```

---

### GitHub MCP（可选）

**状态**: 未配置（可使用 Bash 工具替代）

**说明**: 官方的 `@modelcontextprotocol/server-github` 不存在于 npm。Git 操作可通过以下方式完成：
- 使用内置的 Bash 工具执行 `git` 命令
- 使用 `gh` CLI 工具（如 `gh pr create`）

---

## 整合配置

### 项目配置 (`.mcp.json`)

项目级别的 MCP 配置已经完成，位于项目根目录的 `.mcp.json` 文件。

**注意**: Claude Code 的 `settings.json` 不支持直接配置 `mcpServers` 字段。MCP 服务器需要通过以下方式配置：

1. **项目级别**: `.mcp.json` 文件（推荐）
2. **用户级别**: `~/.claude/settings.json` 不支持 MCP 配置
3. **插件级别**: 通过插件的 `pluginConfigs` 配置

### 完整配置模板

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
    },
    "jupyter": {
      "command": "uvx",
      "args": ["mcp-server-jupyter"]
    }
  }
}
```

---

## 开发工作流升级

### 传统工作流 vs MCP 增强工作流

| 阶段 | 传统方式 | MCP 增强方式 |
|------|----------|--------------|
| **需求分析** | 人工查阅文档 | Web Search MCP 实时获取最新 API 规范 |
| **原型验证** | 写临时 Python 脚本 | Jupyter MCP 秒级运行 + 可视化 |
| **核心开发** | 人工推演边界 | Sequential Thinking MCP 沙盘推演 |
| **数据验证** | 打开 DB 浏览器 | SQLite MCP 直接查询 + 分析 |
| **代码提交** | 手动 git add/commit | Git MCP 智能分层提交 |
| **Code Review** | 人工检查 | 自动对照架构规范审查 |

---

## 优先级与状态

### ✅ 已完成（2026-03-31）

| MCP 服务器 | 安装方式 | 项目配置 | 状态 |
|-----------|---------|---------|------|
| Filesystem | npm global | ✅ | 已安装并配置 |
| SQLite | uv tool | ✅ | 已安装并配置 |
| Brave Search | npm global | ✅ | 已安装并配置 |
| Sequential Thinking | npm global | ✅ | 已安装并配置 |
| Jupyter | uvx (按需) | 可选 | 已安装 |

### 🟡 无需配置

| 工具 | 说明 | 替代方案 |
|------|------|----------|
| Git MCP | 官方包不存在 | 使用内置 Bash + `git`/`gh` CLI |
| GitHub MCP | 官方包不存在 | 使用 `gh` CLI 工具 |

---

## 实战案例

### 案例：ATR 过滤器调试

**传统方式**:
```
1. 修改 filter_factory.py
2. 运行 pytest tests/unit/test_filter_factory.py
3. 查看失败用例
4. 打开数据库查实际数据
5. 写 Python 脚本模拟边界场景
6. 重复 1-5 多次
```

**MCP 增强方式**:
```
1. 修改 filter_factory.py
2. 运行 pytest（失败）
3. SQLite MCP: 查询实际被过滤的信号 metadata
4. Jupyter MCP: 加载真实数据，运行 ATR 计算逻辑
5. Sequential Thinking: 推演边界场景（ATR=0 时？）
6. 修复代码
7. SQLite MCP: 验证修复后查询
```

**效率提升**: 从 30 分钟 → 8 分钟

---

## 注意事项

1. **数据库安全**: SQLite MCP 仅配置只读权限，避免误删改
2. **API 限频**: Web Search 注意请求频率，避免被封禁
3. **本地优先**: 敏感数据（API Key）不通过外部 MCP 传输
4. **版本锁定**: MCP Server 使用固定版本，避免 breaking changes

---

*本指南持续更新，每次配置新 MCP 工具后补充实战案例*
