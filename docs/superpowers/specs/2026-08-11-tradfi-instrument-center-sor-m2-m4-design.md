---
title: TRADFI_INSTRUMENT_CENTER_SOR_M2_M4_DESIGN
status: OWNER_APPROVED_FOR_IMPLEMENTATION
date: 2026-08-11
---

# TradFi 标的中心、产品底座与美股 SOR 设计

## Owner 决策

1. Binance 美股永续继续使用 `binance-usdm`，不建设第二 Venue 或执行链。
2. `SOR-US-EQ-PERP-001` 与加密 `SOR-001` 是独立 StrategyGroup。
3. Strategy Registry 不保存标的列表；PostgreSQL StrategyUniverse 是
   Strategy Event 与标的成员关系的唯一权威。
4. 一个标的可以属于多个 StrategyUniverse，但一个 Netting Domain 仍只允许一个
   Active Ticket。
5. 首期 LONG/SHORT 使用相同的八个候选标的、独立 Event 和独立 Universe。
6. M4 只实现美股 SOR；MPG、BRF2、CPM、MI 的 TradFi 适配进入后续待办。
7. M1-M5 不增加真实资本；TradFi RuntimeProfile、Owner Policy 和 Strategy Control
   必须保证新 StrategyGroup 只能 Observation，不能产生真实 Entry。

## 权威边界

```text
Strategy Registry
-> immutable Event semantics and Product Compatibility

Instrument Catalog / Product Current
-> product identity, current Session and bounded market facts

StrategyUniverse
-> versioned Event-to-instrument membership

Owner Policy / Strategy Control
-> Entry authority and capital
```

新增 Product Compatibility 是 Registry 的独立不可变合同，不修改既有六个 Event
合同或 ExitPolicy 的历史 semantic hash。Universe 安装必须同时验证 Event、Runtime
Profile、Owner Policy、Product Compatibility 和 instrument identity。

## M2 产品面

Owner Console 新增 `/instruments`：

- 显示 canonical instrument、Product Family、当前 Session、Product 状态；
- 显示 Active/Warming StrategyUniverse 归属；
- 支持手动刷新、候选详情和策略页路由；
- Universe 修改先生成 Diff，TOTP 后创建新 Warming Universe；
- 不直接修改 Active Universe，不通过浏览器写运行时表。

Strategy 页面增加 Venue、Product Family、RuntimeProfile、Entry Window 和 Active
Universe 摘要，但保留现有按 StrategyVersion 隔离的收益统计。

## M3 产品与运行底座

新增不可变 Product Compatibility 和 PostgreSQL current product projection：

```text
product_family
contract_type
underlying_type
margin_asset
product_status
session_state
regular_session_open_ms
regular_session_close_ms
mark_price
index_price
funding_rate
best_bid / best_ask
corporate_event_status
observed_at_ms / valid_until_ms / source_ref
```

公共网络读取发生在 PostgreSQL transaction 外；成功后使用一个短事务 upsert exact
current projection。缺失、过期或矛盾事实产生显式 unavailable 状态，不生成 Signal。

新增 `tradfi-equity-observe-v1` RuntimeProfile 和 `policy-tradfi-observe`：

- 与现有 USD-M account 共用 Venue/account identity；
- 只允许两个 `SOR-US-EQ-PERP-001` Event；
- `new_entry_submit_enabled=false`；
- Strategy Control 初始状态为 `paused`；
- 现有 Crypto RuntimeProfile、Policy 和 StrategyUniverse 不改变行为。

## M4 SOR-US-EQ-PERP-001 v1

### Event

```text
SOR-US-LONG-15M
SOR-US-SHORT-15M
```

### Session 与触发

- 全时段 Product/Session Observation；
- Signal 只在 `REGULAR` Session 形成；
- Opening Range 为 Regular open 后前两根闭合 15m K 线；
- Entry window 为 Regular open + 30m 至 +150m；
- previous close 在边界内、latest close 首次越界；
- 一个 instrument + side + regular session 最多一个 Episode；
- Signal freshness 为 15m。

### Initial Stop

```text
LONG  = min(opening_range_high, trigger_low) - 0.10 * ATR14_15m
SHORT = max(opening_range_low, trigger_high) + 0.10 * ATR14_15m
```

当 entry-to-stop distance 大于 `1.25 * ATR14_15m` 时不生成 Signal。所有价格按
instrument tick 在 Capacity/Ticket 阶段执行既有规范化。

### ExitPolicy

- TP1 前闭合 15m 回到 Opening Range 内则失败退出；
- TP1 前最多八根闭合 15m bars；
- TP1 为 1R / 50%；
- TP1 后使用 cost-adjusted break-even 与 existing structural ATR runner；
- Regular close 前 15m 是整个 Ticket 的 session exit deadline；
- v1 不隔夜；QQQ/SPY 仅保留后续 context evidence，不作为硬触发条件。

## 失败与性能

- Product/Schedule 缺失、过期或冲突：Observation invalid，不生成 Signal；
- Product Compatibility 不匹配：Universe 安装拒绝；
- Universe 更新：新 Warming 版本，旧 Active 与既有 Ticket 不变；
- 当前 2C4G 继续使用四类 Worker，不按标的新增服务；
- 15m K 线增量读取；Product/Schedule source 使用进程内短 TTL 缓存减少共享请求；
- 前端只手动刷新，列表有界分页。

## 聚焦验收

1. 既有六个 Event semantic hash 和 Crypto detector 行为不变。
2. AAPL 等 Equity instrument 不能加入 Crypto SOR Universe。
3. 新两个 Event 可在 typed Regular Session snapshot 上形成 Live/Replay 相同 Signal。
4. 非 REGULAR、过期 schedule、过宽 Stop、重复 Episode 均不形成 Signal。
5. TradFi Policy 与 Strategy Control 阻止 CapacityClaim/Ticket。
6. Instrument Center 可读取 Product、Session 和 Universe；Universe 写操作需要 TOTP
   且只创建 Warming 版本。
7. 只运行受影响的 domain、Registry、Universe、Owner API、frontend test/build、Ruff、
   Mypy 和 document authority 检查；不运行无关完整 full-chain suite。

## 后续待办

| 策略族 | 拟议 TradFi 身份 | 主要适配 | 优先级 |
| --- | --- | --- | --- |
| MPG | `MPG-US-EQ-PERP-001` | Regular-session 动量和跨标的排名 | SOR M5 后优先评估 |
| BRF2 | `BRF2-US-EQ-PERP-001` | 反弹失败、指数背景、企业事件 | MPG 后 |
| CPM | `CPM-US-EQ-PERP-001` | Session 化回调和 Stop distance | 暂缓 |
| MI | `MI-US-EQ-PERP-001` | 12h impulse 重定义和追价控制 | 暂缓 |
| RSRVCB | `RSRVCB-001` | 多周期排名、VCB、Regime | M7 |

