# MCP 工具调用指南

> **创建日期**: 2026-04-01
> **适用团队**: 盯盘狗 Agent Team
> **目标**: 让每个角色高效、安全地使用 MCP 工具

---

## 📋 已配置 MCP 工具清单

| 工具 | 状态 | 用途 | 调用方式 |
|------|------|------|----------|
| `sqlite` | ✅ 已配置 | 数据库查询、信号分析 | 所有角色可用 |
| `filesystem` | ✅ 已配置 | 文件读写、目录浏览 | 所有角色可用 |
| `brave-search` | ✅ 已配置 | 外部信息检索 | 需 API 密钥 |
| `sequential-thinking` | ✅ 已配置 | 复杂问题链式思考 | 所有角色可用 |
| `jupyter` | ⏸️ 可选 | Python 沙箱执行 | 按需配置 |

---

## 🎭 各角色 MCP 调用规范

### Team Coordinator (`/coordinator`)

**职责**: 任务分解、角色调度、结果整合

#### 推荐调用场景

| 场景 | MCP 工具 | 指令示例 |
|------|---------|----------|
| **任务分解前调研** | `brave-search` | "搜索 2026 年最新的开源量化回测框架架构" |
| **复杂问题推演** | `sequential-thinking` | "一步步推演多角色并行开发可能产生的冲突点" |
| **读取项目文件** | `filesystem` | "读取 docs/planning/task_plan.md 了解当前进度" |
| **数据库状态检查** | `sqlite` | "查询 signals 表最近 1 小时的信号数量" |

#### 调用示例

```python
# 复杂任务分解前进行链式思考
Agent(subagent_type="sequential-thinking", 
      prompt="我需要将'添加止盈跟踪功能'分解为前后端任务，请一步步推演：\n
      1. 需要修改哪些领域模型\n
      2. 后端 API 需要新增哪些端点\n
      3. 前端需要新增哪些组件\n
      4. 可能的并发冲突点在哪里")

# 查询数据库了解当前状态
mcp__sqlite__read_query(query="SELECT source, COUNT(*) FROM signals WHERE created_at >= datetime('now', '-1 hour') GROUP BY source")
```

---

### Backend Developer (`/backend`)

**职责**: Python + FastAPI + asyncio 后端实现

#### 推荐调用场景

| 场景 | MCP 工具 | 指令示例 |
|------|---------|----------|
| **信号数据分析** | `sqlite` | "查询被 ATR 过滤器过滤的信号，统计 filter_reason 分布" |
| **读取配置文件** | `filesystem` | "读取 config/core.yaml 检查 pinbar 默认参数" |
| **日志分析** | `filesystem` | "读取 logs/目录最新日志，分析 WARNING 级别的过滤记录" |
| **外部 API 调研** | `brave-search` | "获取 CCXT Pro 关于 watch_orders 的最新用法" |
| **复杂逻辑推演** | `sequential-thinking` | "推演热重载时 EMA 状态恢复的完整流程" |

#### 调用示例

```python
# 分析信号过滤原因
mcp__sqlite__read_query(query="""
    SELECT filter_reason, COUNT(*) as count 
    FROM signal_attempts 
    WHERE filter_reason IS NOT NULL 
    GROUP BY filter_reason 
    ORDER BY count DESC
""")

# 读取配置文件
config_content = mcp__filesystem__read_text_file(path="config/core.yaml")

# 复杂状态机流转推演
Agent(subagent_type="sequential-thinking",
      prompt="推演 WebSocket 断连重连时的信号去重流程：\n
      1. WS 断开前的最后状态\n
      2. 轮询快照到达时的数据对比\n
      3. 冷却期缓存的更新逻辑\n
      4. 可能出现的竞态条件")
```

#### 常用 SQL 查询模板

```sql
-- 查询最近被过滤的信号及原因
SELECT symbol, timeframe, filter_reason, metadata, created_at
FROM signal_attempts 
WHERE created_at >= datetime('now', '-24 hours')
ORDER BY created_at DESC
LIMIT 50;

-- 查询止损距离异常小的信号
SELECT symbol, timeframe, entry_price, stop_loss_price,
       ROUND(ABS(entry_price - stop_loss_price) * 100.0 / entry_price, 4) as stop_loss_pct
FROM signals
WHERE ABS(entry_price - stop_loss_price) * 100.0 / entry_price < 0.1;

-- 统计各时间周期的信号分布
SELECT timeframe, COUNT(*) as count
FROM signals
GROUP BY timeframe
ORDER BY count DESC;
```

---

### Frontend Developer (`/frontend`)

**职责**: React + TypeScript + TailwindCSS 前端实现

#### 推荐调用场景

| 场景 | MCP 工具 | 指令示例 |
|------|---------|----------|
| **读取组件文件** | `filesystem` | "读取 web-front/src/pages/Backtest.tsx 了解当前实现" |
| **API 接口调研** | `brave-search` | "搜索 lightweight-charts 时区配置最佳实践" |
| **复杂交互推演** | `sequential-thinking` | "推演用户点击预览按钮后的完整数据流" |
| **读取后端 Schema** | `filesystem` | "读取 src/interfaces/api.py 确认 API 返回结构" |

#### 调用示例

```python
# 读取当前组件实现
component = mcp__filesystem__read_text_file(path="web-front/src/pages/Backtest.tsx")

# 读取后端 API 定义，确认接口契约
api = mcp__filesystem__read_text_file(path="src/interfaces/api.py")

# 复杂用户交互流程推演
Agent(subagent_type="sequential-thinking",
      prompt="推演用户从策略工作台导入策略到回测沙箱的完整流程：\n
      1. 用户点击'导入策略'按钮\n
      2. 前端发送什么请求\n
      3. 后端返回什么数据\n
      4. 前端如何渲染结果\n
      5. 可能的错误场景")
```

---

### QA Tester (`/qa`)

**职责**: 测试策略、单元测试、集成测试

#### 推荐调用场景

| 场景 | MCP 工具 | 指令示例 |
|------|---------|----------|
| **测试数据验证** | `sqlite` | "查询最新 10 个信号的入场价和止损价，验证计算逻辑" |
| **读取测试文件** | `filesystem` | "读取 tests/unit/test_risk_calculator.py 了解现有测试" |
| **测试失败分析** | `sequential-thinking` | "一步步分析测试失败的可能原因" |
| **外部测试框架** | `brave-search` | "搜索 pytest-asyncio 最新用法" |

#### 调用示例

```python
# 查询信号数据验证业务逻辑
signals = mcp__sqlite__read_query(query="""
    SELECT symbol, entry_price, stop_loss_price, 
           (entry_price - stop_loss_price) * 100.0 / entry_price as loss_pct
    FROM signals
    ORDER BY created_at DESC
    LIMIT 10
""")

# 读取现有测试
test = mcp__filesystem__read_text_file(path="tests/unit/test_risk_calculator.py")

# 测试失败根因分析
Agent(subagent_type="sequential-thinking",
      prompt="测试 test_risk_calculator.py::test_position_size_with_open_positions 失败了。\n
      请一步步分析：\n
      1. 测试期望的行为是什么\n
      2. 实际输出了什么\n
      3. 风险计算公式中哪里可能出问题\n
      4. 如何修复")
```

---

### Code Reviewer (`/reviewer`)

**职责**: 代码审查、架构一致性检查、安全隐患识别

#### 推荐调用场景

| 场景 | MCP 工具 | 指令示例 |
|------|---------|----------|
| **读取修改文件** | `filesystem` | "读取 src/domain/risk_calculator.py 检查修改" |
| **架构规范对照** | `filesystem` | "读取 docs/arch/系统开发规范与红线.md" |
| **Git 变更审查** | `filesystem` | "读取 git diff 检查最近提交" |
| **安全问题排查** | `sequential-thinking` | "分析这段代码是否有 SQL 注入风险" |

#### 调用示例

```python
# 读取修改的代码
code = mcp__filesystem__read_text_file(path="src/domain/risk_calculator.py")

# 读取架构规范
arch = mcp__filesystem__read_text_file(path="docs/arch/系统开发规范与红线.md")

# 架构一致性审查推演
Agent(subagent_type="sequential-thinking",
      prompt="审查这段代码的架构一致性：\n
      1. 是否导入了 ccxt/aiohttp/fastapi 到 domain 层\n
      2. 是否使用了 Dict[str, Any] 而不是具名 Pydantic 类\n
      3. 金额计算是否使用了 Decimal\n
      4. 异步代码中是否有同步阻塞调用")
```

---

### Diagnostic Analyst (`/diagnostic`)

**职责**: 问题根因分析、共性问题排查、技术债识别

#### 推荐调用场景

| 场景 | MCP 工具 | 指令示例 |
|------|---------|----------|
| **数据库分析** | `sqlite` | "分析 signal_attempts 表中各过滤原因的分布" |
| **日志分析** | `filesystem` | "读取 logs/最新日志，筛选 ERROR 级别记录" |
| **问题推演** | `sequential-thinking` | "一步步推演 MTF 过滤器失效的 5 个可能原因" |
| **外部信息检索** | `brave-search` | "搜索 SQLite 锁超时问题的常见原因" |

#### 调用示例

```python
# 分析过滤原因分布
distribution = mcp__sqlite__read_query(query="""
    SELECT filter_reason, 
           COUNT(*) as count,
           ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as percentage
    FROM signal_attempts 
    WHERE filter_reason IS NOT NULL 
    GROUP BY filter_reason 
    ORDER BY count DESC
""")

# 读取日志分析
logs = mcp__filesystem__read_text_file(path="logs/app.log", tail=100)

# 根因分析推演
Agent(subagent_type="sequential-thinking",
      prompt="用户反馈'回测结果为 0 个信号'，请一步步推演可能原因：\n
      1. K 线数据是否正确加载\n
      2. 策略是否正确配置\n
      3. 过滤器是否过于严格\n
      4. 时间范围参数是否生效\n
      5. 每个原因的验证方法")
```

---

### DevOps Engineer (`/devops`)

**职责**: 服务器运维、Docker 部署、配置管理、故障排查

#### 推荐调用场景

| 场景 | MCP 工具 | 指令示例 |
|------|---------|----------|
| **数据库检查** | `sqlite` | "查询 signals 表大小和最近写入时间" |
| **配置文件检查** | `filesystem` | "读取 docker-compose.yml 检查配置" |
| **日志分析** | `filesystem` | "读取 logs/最新日志，分析启动失败原因" |
| **运维知识检索** | `brave-search` | "搜索 Docker 容器 SQLite 锁超时的解决方案" |
| **故障推演** | `sequential-thinking` | "推演容器重启后数据恢复的完整流程" |

#### 调用示例

```python
# 检查数据库状态
status = mcp__sqlite__read_query(query="""
    SELECT 
        datetime('now') as check_time,
        COUNT(*) as total_signals,
        datetime(MAX(created_at)) as last_signal_time
    FROM signals
""")

# 读取部署配置
config = mcp__filesystem__read_text_file(path="docker-compose.yml")

# 部署问题推演
Agent(subagent_type="sequential-thinking",
      prompt="推演生产环境配置热重载的完整流程：\n
      1. 配置文件如何下发\n
      2. ConfigManager 如何检测变更\n
      3. SignalPipeline 如何重建\n
      4. EMA 等状态指标如何恢复\n
      5. 可能的故障点")
```

---

## 🔒 安全与边界

### 数据写入限制

| 角色 | SQLite 写入权限 | Filesystem 写入范围 |
|------|----------------|---------------------|
| Backend | ✅ 允许 (业务表) | ✅ src/, config/, tests/ |
| Frontend | ❌ 禁止 | ✅ web-front/ |
| QA | ⚠️ 测试数据 | ✅ tests/ |
| Reviewer | ❌ 禁止 | ❌ 仅读 |
| Diagnostic | ❌ 禁止 | ✅ docs/ (诊断报告) |
| DevOps | ✅ 运维数据 | ✅ logs/, data/ |
| Coordinator | ❌ 禁止 | ✅ docs/, .claude/ |

### 敏感操作提醒

- **数据库删除操作**: 必须二次确认
- **生产配置文件**: 禁止修改 `*-prod.yaml`（除非 DevOps）
- **外部 API 密钥**: 禁止在日志中暴露 `BRAVE_API_KEY`

---

## 🚀 最佳实践

### ✅ 推荐做法

1. **查询先行**: 修改代码前先用 SQLite MCP 查询当前数据状态
2. **链式思考**: 复杂修改前用 Sequential Thinking MCP 推演影响
3. **信息检索**: 不确定时用 Brave Search MCP 检索最新文档
4. **文件浏览**: 使用 Filesystem MCP 的 `list_directory` 而非 Bash `ls`

### ❌ 避免做法

1. **绕过 MCP**: 能用 MCP 工具完成的，不要用 Bash 脚本
2. **盲目修改**: 未查询数据库就直接修改业务逻辑
3. **过度检索**: 简单问题不要调用外部搜索
4. **权限越界**: 不要修改非负责范围的文件

---

## 📚 快速参考

### MCP 调用语法

```python
# SQLite 查询
mcp__sqlite__read_query(query="SELECT ...")

# 文件读取
mcp__filesystem__read_text_file(path="...")

# 目录浏览
mcp__filesystem__list_directory(path="...")

# 文件写入（需权限）
mcp__filesystem__write_file(path="...", content="...")

# Sequential Thinking（通过 Agent）
Agent(subagent_type="sequential-thinking", prompt="...")

# Brave Search（通过 WebSearch 工具）
WebSearch(query="...")
```

### 常用命令

```bash
# 检查 MCP 配置
cat .mcp.json

# 测试 SQLite MCP
uvx mcp-server-sqlite --db-path ./signals.db

# 测试 Sequential Thinking MCP
npx -y @modelcontextprotocol/server-sequential-thinking --help
```

---

## 📖 相关文档

- [MCP 工具整合指南](./docs/mcp-integration/量化开发 MCP 工具整合指南.md)
- [团队角色配置](./.claude/team/README.md)
- [系统开发规范](./docs/arch/系统开发规范与红线.md)

---

*本指南持续更新，每次添加新 MCP 工具后补充调用规范*
