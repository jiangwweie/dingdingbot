# 技术发现

> **说明**: 仅保留当前活跃的技术发现，已归档的见 `archive/completed-tasks/findings-history-20260407-and-earlier.md`。
> **最后更新**: 2026-04-10

---

## 2026-04-08 P0 WebSocket K 线选择逻辑修复

### 核心修复：交易所 x 字段优先 + 多层防御

**问题**: WebSocket K 线选择逻辑错误，系统处理 `ohlcv[-1]`（未收盘 K 线）进行形态检测。

**技术发现**:
1. `candle[6]` 可能包含 `info` 字典，`info['x']` 表示收盘状态
2. 无 `x` 字段时，使用 `ohlcv[-2]` + 时间戳推断作为后备
3. `KlineData` 新增 `info` 字段保留交易所原始数据

### Pinbar 最小波幅检查

| 方案 | 选择 |
|------|------|
| 固定值 (0.5 USDT) | ❌ 过滤低价格币种 |
| **动态百分比 (0.1%)** | ✅ 适配所有价格级别 |

**公式**: 有 ATR → `atr * 0.1`，无 ATR → `close * 0.001`

---

## 2026-04-08 系统优先级重新分析 - 用户场景驱动

### 核心发现：并发问题不存在

**用户约束**: 单人使用 + 1h/4h 中长线 + 不存在多人并发

| 原并发问题 | 原优先级 | 新优先级 |
|----------|---------|---------|
| 全局状态依赖注入 | P1 | P3 |
| 仓位同步竞态修复 | P1 | P3 |
| 多锁管理简化 | P2 | P3 |

**节省 10h 工时**

### MVP 范围调整

| 维度 | 完整版本 | 最小交付版本 |
|------|---------|-------------|
| 支持策略 | 全部 4 种 | **仅 Pinbar** |
| 总工时 | 55.5h | **33h** |

---

## 2026-04-07 P1-5 Provider 注册模式架构决策

**决策**: 外观模式 + Provider 注册实现（用户核心需求：零修改扩展）

| 决策项 | 结论 |
|--------|------|
| 扩展方式 | Protocol 接口 + Registry 注册中心 |
| 缓存机制 | CachedProvider 基类 + TTL 惰性清理 |
| 并发安全 | asyncio.Lock + 双重检查锁定 |
| 时钟注入 | ClockProtocol 抽象（测试可控） |
| 向后兼容 | 57 个调用方零修改 |

**成果**: 135 单元测试 + 50 集成测试，覆盖率 92%，代码审查 A+

---

## P1-5 Repository 层实现技术要点

- `ConfigRepository` 扩展：`update_risk_config_item()` / `update_user_config_item()` KV 模式更新
- Decimal 精度：`Decimal(str(value))` 转换，YAML 导出时 `str()` 序列化
- TTLCache: `time.monotonic()` 计算 TTL，惰性清理 + LRU 淘汰

---

## 工作流重构 v3.0

### 核心设计

1. **规划会话强制交互式头脑风暴**: PM ≥3 澄清问题 → Arch ≥2 方案 → PM 任务分解
2. **开发会话强制 Agent 调用**: `Agent(subagent_type="team-backend-dev", prompt="...")`
3. **状态看板实时更新**: `docs/planning/board.md` 每次调度后更新
4. **暂停关键词触发**: 用户输入"暂停"/"午休"自动更新 progress.md + findings.md

### 技能配置

| 技能 | 职责 |
|------|------|
| `/coordinator` | 兼任 PdM/Arch/PM |
| `/backend` | 后端开发 |
| `/frontend` | 前端开发 |
| `/qa` | 测试专家 |
| `/reviewer` | 代码审查 |

---

## DEBT-3 API 依赖注入架构决策

**问题**: API 端点硬编码 `OrderRepository()`，测试 fixture 临时数据库无法被使用。

**方案**: 全局变量 + `_get_order_repo()` 辅助函数 + 扩展 `set_dependencies()`

```python
_order_repo: Optional[OrderRepository] = None

def _get_order_repo() -> OrderRepository:
    if _order_repo is None:
        return OrderRepository()
    return _order_repo
```

---

## 2026-04-10 MCP 占位符清理 + 文档版本收敛

### 清理决策
- MCP 占位符（telegram/ssh/sentry）使用 dummy 值，不在项目 enabled 列表中，直接删除
- 12 个旧版 SKILL.md 残留文件（.backup / .v2 / .v3）全部删除，保留当前活跃版本
- 重复的 phase-contracts 目录（docs/designs/archive/ 和 docs/v3/ 各 14 个相同文件）删除 archive 副本
- 创建 SKILL_VERSIONS.md 版本追踪清单，避免未来再次积累残留文件

### 用户画像洞察
- 流程过重：10 人团队 + 三阶段工作流 + 5 个强制检查点，个人项目开销大
- 建议引入"快速通道"模式（light mode）处理小修小补
- Agent 定义去重：抽取公共规范为独立文件，各 Agent 仅引用而非复制

---

## 2026-04-10 策略系统架构分析

### 两套策略 API 并存

| 旧 API `/api/strategies` | 新 API `/api/v1/config/strategies` |
|---|---|
| id: number | id: string UUID |
| strategy_json: JSON 字符串 | trigger_config/filter_configs 扁平字段 |
| StrategyWorkbench 使用 | StrategyConfig / StrategiesTab 使用 |
| 有 Dry Run 预览 + 下发实盘 | 无预览、无下发功能 |

### 策略下发断裂根因

```
用户点"下发到实盘" → StrategyWorkbench 直接 PUT /api/config
→ 写了配置文件但 ConfigManager 内存未更新（未触发热重载）
→ 仪表盘 GET /api/config 读内存 → 显示空策略
```

**正确流程**: `POST /api/strategies/{id}/apply` 会写入 + 触发热重载 observer。

### MTF 映射是固定规则，无需用户配置

后端三处硬编码固定映射：
```python
MTF_MAPPING = {"15m": "1h", "1h": "4h", "4h": "1d", "1d": "1w"}
```
运行时根据 K 线自身的 timeframe 自动查找对应高一级周期。前端 MTF mapping 单选下拉框选了也不生效——"前端能选但后端不读"。

### 回测页面策略数组初始为空

Backtest.tsx 和 PMSBacktest.tsx 的 strategies 数组初始为空，用户必须手动组装或从工作台导入。没有"一键使用已保存策略"的快捷路径。

### 配置管理审计报告（2026-04-10）

#### P0 问题（阻断性）

| # | 问题 | 文件 | 行号 |
|---|------|------|------|
| 1 | RiskConfig 类型与后端不匹配（前端有 default_leverage，后端没有） | web-front/src/api/config.ts | 95-99 |
| 2 | BackupTab 导入/导出调用不存在的旧 API 路径 | web-front/src/pages/config/BackupTab.tsx | 184, 214 |
| 3 | BackupTab preview 数据结构与后端 ImportPreview 类型不匹配 | web-front/src/pages/config/BackupTab.tsx | 133-143 |
| 4 | YAML 全局 string 构造器被劫持为 Decimal，影响所有 YAML 解析 | src/interfaces/api_v1_config.py | 72 |

#### P1 问题（重要）

| # | 问题 | 文件 |
|---|------|------|
| 5 | 热重载通知只发给 Observer，ConfigManager 缓存未刷新 | api_v1_config.py:640-644 |
| 6 | 两个 SystemTab 组件功能重复（SystemTab.tsx vs SystemSettings.tsx） | 两个文件 |
| 7 | StrategyForm 提交 trigger_config.params 永远为空 | StrategyForm.tsx:116-118 |
| 8 | lib/api.ts 包含大量死代码/过时接口 | lib/api.ts |
| 9 | 多个 Repository 各自独立创建 DB 连接 | config_repositories.py |
| 10 | ConfigSnapshotService 每次创建快照新建/关闭临时连接 | config_snapshot_service.py:157-162 |

> 注：并发安全问题用户明确表示不考虑，已跳过 P1-3 (upsert 竞态)。

### 旧 API 死代码清理策略

**决定**: 渐进式清理，不是本轮目标。
- `lib/api.ts` 被 30+ 个文件引用，不能整体删除
- StrategyWorkbench 删除后，清理仅被其引用的旧函数
- 其余旧函数标记 `@deprecated`，后续逐步迁移

---

## 归档

2026-04-07 及更早的技术发现已归档至:
`docs/planning/archive/completed-tasks/findings-history-20260407-and-earlier.md`

---

*最后更新：2026-04-10 10:15 - 文档精简完成*
