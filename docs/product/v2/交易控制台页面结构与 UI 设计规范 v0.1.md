# 交易控制台页面结构与 UI 设计规范 v0.1

## 0. 文档状态

- 产品名：交易控制台
- 阶段：Gate 2 `PASS_WITH_CONSTRAINT`
- 文档类型：页面结构与 UI 设计规范
- 适用对象：AI Studio 前端工程、前端设计、接入审计
- 唯一事实源：`/api/trading-console/*`
- 当前版本性质：只读版交易控制台
- Gate 3 能力：只允许预设 UI slot，不允许接入真实 action API

------

## 1. 总体设计目标

交易控制台的 UI 不是普通后台，也不是策略测试页。

它的页面目标是：

```text
让 Owner 在真实环境下快速看清：
1. 当前账户是否存在真实风险
2. 当前数据是否连接真实交易所事实
3. 当前订单、仓位、保护单、授权、执行链路是否一致
4. 哪些状态是 warning / blocker / unavailable / not_available
5. 当前哪些动作不可用，为什么不可用
6. 后续 Gate 3 操作能力的 UI 位置在哪里，但当前不能执行
```

本阶段成功标准不是“能操作”，而是：

```text
看得清
不误导
不伪造
不越权
不触发真实交易动作
```

------

## 2. 全局信息架构

### 2.1 一级导航

交易控制台一级导航按如下顺序：

```text
1. 首页
2. 账户总览
3. 订单台账
4. Carrier Shelf
5. 有界实盘授权
6. 实盘执行控制
7. 异常恢复
8. 实盘复盘
9. 技术审计
10. 信号图表预留
```

### 2.2 导航优先级

| 导航          | 优先级 | Gate 2 是否 P0  | 说明                                  |
| ------------- | ------ | --------------- | ------------------------------------- |
| 首页          | P0     | 是              | 真实风险总览                          |
| 账户总览      | P0     | 是              | 全账户事实                            |
| 订单台账      | P0     | 是              | 一级页面                              |
| 有界实盘授权  | P0     | 是              | 只读授权状态                          |
| 实盘执行控制  | P0     | 是              | 只读执行状态                          |
| 异常恢复      | P0     | 是              | 异常解释与 disabled slot              |
| 实盘复盘      | P0     | 是              | 已有事实复盘                          |
| 技术审计      | P0     | 是              | Owner/开发者排障                      |
| Carrier Shelf | P1     | 是，但 v1 scope | BNB-first 当前 Carrier                |
| 信号图表预留  | P2     | 否              | 后续 TradingView / lightweight-charts |

------

## 3. 全局布局

### 3.1 App Shell

推荐布局：

```text
┌──────────────────────────────────────────────┐
│ 顶部全局环境条                                │
├──────────────┬───────────────────────────────┤
│ 左侧导航      │ 页面内容区                     │
│              │                               │
│              │ 页面标题                       │
│              │ 页面状态摘要                   │
│              │ 主内容卡片 / 表格 / 详情区      │
│              │ warnings / blockers / unavailable│
└──────────────┴───────────────────────────────┘
```

### 3.2 顶部全局环境条

全局环境条必须所有页面可见。

内容：

| 字段                  | 来源                           | UI 要求                        |
| --------------------- | ------------------------------ | ------------------------------ |
| 产品名                | 固定                           | 显示“交易控制台”               |
| 当前环境              | `environment.trading_env`      | LIVE / TESTNET / DEV / UNKNOWN |
| profile               | `environment.profile`          | 显示当前 profile               |
| exchange_testnet      | `environment.exchange_testnet` | 明确 true / false / unknown    |
| freshness_status      | envelope                       | 显著显示                       |
| generated_at_ms       | envelope                       | 显示最近生成时间               |
| include_exchange 状态 | query / freshness              | 显示是否读取交易所事实         |
| no_action_guarantee   | envelope                       | 可用图标或技术区展示           |

### 3.3 全局环境条状态规则

| 状态                 | 展示                                 |
| -------------------- | ------------------------------------ |
| `fresh`              | 正常，但仍需看 warnings/blockers     |
| `warning`            | 顶部黄/警示态                        |
| `degraded`           | 顶部橙/危险态                        |
| `not_live_connected` | 顶部中性警示：“未连接实时交易所事实” |
| `unavailable` 非空   | 顶部出现“数据源不可用”提示           |
| `blockers` 非空      | 顶部出现阻断提示                     |

### 3.4 禁止设计

全局环境条不得：

- 把 `not_live_connected` 显示为“安全”
- 把 `unknown` 显示为“正常”
- 隐藏 `unavailable`
- 用绿色表达未核验状态
- 显示“可执行”或“可交易”字样

------

## 4. 全局组件规范

## 4.1 FreshnessBadge

用于显示 envelope `freshness_status`。

| value                | Label                | Severity |
| -------------------- | -------------------- | -------- |
| `fresh`              | 数据已生成           | normal   |
| `warning`            | 有风险提示           | warning  |
| `degraded`           | 数据降级             | danger   |
| `not_live_connected` | 未连接实时交易所事实 | caution  |
| unknown              | 状态未知             | caution  |

规则：

```text
FreshnessBadge 必须出现在：
- 顶部全局环境条
- 页面状态摘要
- 任何依赖 include_exchange 的页面
```

------

## 4.2 WarningPanel

用于展示 envelope `warnings`。

展示字段：

- code
- severity
- message
- count
- order_ids / source ids if available

规则：

```text
warnings 不能折叠到技术审计页才可见。
P0 页面必须主内容区可见。
```

------

## 4.3 BlockerPanel

用于展示 envelope `blockers`。

展示字段：

- code
- message
- affected area
- required action if available

规则：

```text
blockers 必须比 warnings 更显著。
只要 blockers 非空，页面主状态不能显示 clean。
```

------

## 4.4 UnavailablePanel

用于展示 envelope `unavailable`。

展示字段：

- source
- code
- error if available

规则：

```text
unavailable 是数据源缺失，不是空结果。
前端不得把 unavailable 当作“没有风险”。
```

------

## 4.5 NotAvailableValue

用于展示字段级 `not_available`。

展示样式：

```text
不可用
```

或：

```text
当前后端未提供
```

禁止：

- 显示为 0
- 显示为 -
- 前端估算
- 用空白隐藏

------

## 4.6 DeferredActionSlot

用于展示：

- `deferred_actions`
- `future_action_slots`
- `deferred_execute_endpoint`

组件状态：

```text
disabled
future
unavailable
```

展示字段：

- action name
- reason
- requires backend support
- touches exchange? unknown / future
- PG mutation? unknown / future

统一文案：

```text
当前后端未开放此动作。
本阶段仅展示状态，不执行操作。
```

------

## 4.7 ReadOnlyModeBanner

所有涉及执行、恢复、授权、订单操作的页面必须显示。

文案：

```text
当前为只读交易控制台。页面不会下单、撤单、平仓、重试保护或修改 PG 状态。
```

------

## 4.8 SourceBadge

用于展示数据源：

| source            | 显示                 |
| ----------------- | -------------------- |
| `pg`              | 本地 PG              |
| `exchange`        | 交易所               |
| `exchange_normal` | 交易所普通挂单       |
| `exchange_stop`   | 交易所条件 / stop 单 |
| `read_model`      | 后端聚合             |
| `not_available`   | 不可用               |
| `unknown`         | 未知                 |

------

## 4.9 DetailDrawer

表格行点击后打开详情抽屉。

适用页面：

- 订单台账
- 账户总览
- 实盘复盘
- 技术审计
- 异常恢复

详情抽屉必须包含：

- 业务字段
- 技术 ID
- source
- status
- warning / blocker / unavailable
- raw payload policy if applicable

------

## 5. 页面模板规范

每个页面统一结构：

```text
页面标题
页面说明
页面级状态摘要
Warnings / Blockers / Unavailable
主内容
详情区域
Future action slots
技术信息折叠区
```

每个页面必须处理：

- loading
- empty
- warning
- degraded
- unavailable
- not_available
- disabled action
- no data
- not_live_connected

------

# 6. 页面设计规范

## 6.1 首页 / 真实风险总览

### 6.1.1 目标

首页回答：

```text
当前真实账户是否存在风险？
当前数据是否连接真实交易所事实？
当前有没有仓位、挂单、授权、执行意图、异常？
```

### 6.1.2 Endpoint

```text
GET /api/trading-console/dashboard-state
```

### 6.1.3 页面布局

```text
┌────────────────────────────────────┐
│ 页面标题：首页                       │
│ 状态摘要：真实风险总览               │
├────────────────────────────────────┤
│ 核心状态卡                          │
├────────────┬────────────┬──────────┤
│ 仓位摘要    │ 挂单摘要    │ 授权摘要  │
├────────────┴────────────┴──────────┤
│ 执行意图 / open intents 摘要         │
├────────────────────────────────────┤
│ Warnings / Blockers / Unavailable   │
├────────────────────────────────────┤
│ 最近复盘 / 快捷入口                  │
└────────────────────────────────────┘
```

### 6.1.4 核心状态卡

状态优先级：

1. blockers 非空
2. unavailable 非空
3. freshness_status = degraded
4. freshness_status = not_live_connected
5. warnings 非空
6. open positions / open orders / open intents 非空
7. 空闲状态

空闲状态文案：

```text
当前无真实敞口，暂无待处理事项。
```

如果 `not_live_connected`：

```text
当前未连接实时交易所事实，不能确认真实账户是否完全安全。
```

### 6.1.5 禁止

首页不得：

- 默认显示“发起实盘行动”
- 显示可执行按钮
- 把未连接交易所显示为安全
- 隐藏 open intents
- 隐藏 unavailable

------

## 6.2 账户总览

### 6.2.1 目标

展示全账户事实，不限当前 Carrier。

### 6.2.2 Endpoint

```text
GET /api/trading-console/account-risk
```

### 6.2.3 页面布局

```text
┌────────────────────────────────────┐
│ 页面标题：账户总览                   │
│ 风险状态：risk_state                 │
├────────────────────────────────────┤
│ 账户资金摘要                         │
├────────────────────────────────────┤
│ 仓位表                               │
├────────────────────────────────────┤
│ Open Orders 摘要                     │
├────────────────────────────────────┤
│ Protection Ownership                 │
├────────────────────────────────────┤
│ Freshness / Unavailable              │
└────────────────────────────────────┘
```

### 6.2.4 仓位表列

建议列：

- source
- symbol
- side
- quantity
- entry_price
- mark_price
- unrealized_pnl
- realized_pnl
- leverage
- margin_mode
- system_owned
- protection_status
- updated_at

### 6.2.5 展示规则

- `risk_state=unknown` 不得展示为 healthy。
- `source=exchange` 和 `source=pg` 必须区分。
- `not_available` 字段必须显示为不可用。
- 如果未 include exchange，显示“未读取交易所仓位事实”。

------

## 6.3 订单台账

### 6.3.1 目标

订单台账是一级页面。

它回答：

```text
系统记录了什么订单？
交易所有什么订单？
哪些匹配？
哪些不一致？
哪些是保护单？
哪些是孤儿保护单？
```

### 6.3.2 Endpoint

```text
GET /api/trading-console/order-ledger
```

### 6.3.3 页面布局

```text
┌────────────────────────────────────┐
│ 页面标题：订单台账                   │
│ 分类统计 classification_counts       │
├────────────────────────────────────┤
│ 筛选区                               │
├────────────────────────────────────┤
│ 订单表                               │
├────────────────────────────────────┤
│ 保护单组 groups                      │
├────────────────────────────────────┤
│ 对账 / 异常分类视图                   │
├────────────────────────────────────┤
│ unavailable_fields                   │
└────────────────────────────────────┘
```

### 6.3.4 筛选项

前端应预设筛选：

- symbol
- source
- classification
- order_role
- status
- only protection orders
- only mismatch
- only orphan protection
- only PG-only
- only exchange-only

如果后端暂不支持筛选，前端可在当前响应内本地筛选，但不得跨 API 推断安全状态。

### 6.3.5 订单表列

建议列：

- classification
- source
- order_id
- exchange_order_id
- symbol
- side
- order_role
- order_type
- status
- price
- trigger_price
- requested_qty
- filled_qty
- average_exec_price
- reduce_only
- parent_order_id
- oco_group_id
- created_at
- updated_at

### 6.3.6 分类 Badge

| classification    | UI     |
| ----------------- | ------ |
| matched           | 普通   |
| pg_unchecked      | 未核验 |
| pg_only           | 警示   |
| exchange_only     | 警示   |
| mismatch          | 危险   |
| orphan_protection | 危险   |
| unknown           | 未知   |

### 6.3.7 保护单组视图

每个 group 展示：

```text
Entry Order
├─ TP Orders
└─ SL / Algo Orders
```

如果没有 entry 但有 protection：

```text
孤儿保护单组
```

### 6.3.8 禁止

订单台账不得：

- 把 pg_unchecked 当作 matched
- 隐藏 orphan_protection
- 估算 fee / funding / slippage
- 假造 fills
- 把 exchange_only 当作系统订单

------

## 6.4 Carrier Shelf

### 6.4.1 目标

展示当前 v1 Carrier 可用性。

### 6.4.2 Endpoint

```text
GET /api/trading-console/carrier-availability
```

### 6.4.3 页面布局

```text
┌────────────────────────────────────┐
│ 页面标题：Carrier Shelf             │
│ v1 scope 说明                       │
├────────────────────────────────────┤
│ Carrier 卡片                        │
├────────────────────────────────────┤
│ blocked reasons                     │
├────────────────────────────────────┤
│ authorization 摘要                  │
├────────────────────────────────────┤
│ protection 摘要                     │
├────────────────────────────────────┤
│ sample_data_policy                  │
└────────────────────────────────────┘
```

### 6.4.4 Carrier 卡片字段

- carrier_id
- strategy_family_id
- symbol
- side
- status
- blocked_reasons
- authorization
- protection

### 6.4.5 v1 scope 提示

必须显示：

```text
当前 Carrier Shelf 为 BNB-first v1 scope，不代表最终多策略货架。
```

### 6.4.6 禁止

- 不得使用 sample_data。
- 不得显示完整多 Carrier 货架假象。
- 不得出现“测试候选”。

------

## 6.5 有界实盘授权

### 6.5.1 目标

展示授权状态，不创建、不作废、不修改授权。

### 6.5.2 Endpoint

```text
GET /api/trading-console/authorization-state
```

### 6.5.3 页面布局

```text
┌────────────────────────────────────┐
│ 页面标题：有界实盘授权               │
│ 授权状态摘要                         │
├────────────────────────────────────┤
│ 授权 ID / Carrier / Scope            │
├────────────────────────────────────┤
│ 状态字段                             │
├────────────────────────────────────┤
│ blocking_reason                      │
├────────────────────────────────────┤
│ future_action_slots                  │
└────────────────────────────────────┘
```

### 6.5.4 状态字段

- status
- is_actionable
- is_consumed
- is_expired
- is_cancelled
- scope_match
- blocking_reason

### 6.5.5 显示规则

| 字段                    | UI       |
| ----------------------- | -------- |
| is_actionable=false     | 不可行动 |
| is_consumed=true        | 已消费   |
| is_expired=true         | 已过期   |
| is_cancelled=true       | 已取消   |
| scope_match=not_checked | 未核验   |
| blocking_reason 非空    | 显著展示 |

### 6.5.6 future_action_slots

显示为 disabled：

- void_authorization
- cancel_authorization

文案：

```text
后端暂未开放授权作废动作。
```

------

## 6.6 实盘执行控制

### 6.6.1 目标

展示执行控制状态，不执行真实动作。

### 6.6.2 Endpoint

```text
GET /api/trading-console/execution-control-state
```

### 6.6.3 页面布局

```text
┌────────────────────────────────────┐
│ 页面标题：实盘执行控制               │
│ ReadOnlyModeBanner                  │
├────────────────────────────────────┤
│ hard_gate.status                    │
├────────────────────────────────────┤
│ Gate 列表                           │
├────────────────────────────────────┤
│ Blockers / Warnings                 │
├────────────────────────────────────┤
│ execution_preview                   │
├────────────────────────────────────┤
│ disabled execute slot               │
└────────────────────────────────────┘
```

### 6.6.4 Gate 列表字段

- code
- status
- message if available

### 6.6.5 Disabled execute slot

显示一个不可点击区域：

```text
实盘执行动作未开放
```

说明：

```text
当前 Gate 2 版本仅展示执行状态，不提交订单。
```

### 6.6.6 禁止

- 不得出现可点击“执行”按钮。
- 不得调用旧 execute endpoint。
- 不得根据 `is_actionable=true` 启用按钮。
- 不得把 `deferred_execute_endpoint=true` 变成 action。

------

## 6.7 异常恢复

### 6.7.1 目标

展示异常与恢复引导，不执行恢复动作。

### 6.7.2 Endpoint

```text
GET /api/trading-console/recovery-exception-state
```

### 6.7.3 页面布局

```text
┌────────────────────────────────────┐
│ 页面标题：异常恢复                   │
│ 当前异常摘要                         │
├────────────────────────────────────┤
│ manual_action_required              │
├────────────────────────────────────┤
│ recovery_tasks                      │
├────────────────────────────────────┤
│ mismatches                          │
├────────────────────────────────────┤
│ read_only_actions                   │
├────────────────────────────────────┤
│ deferred_actions disabled slots     │
└────────────────────────────────────┘
```

### 6.7.4 deferred_actions

可能包括：

- retry_protection
- cancel_order
- flatten_position
- resolve_recovery_task

全部 disabled。

### 6.7.5 禁止

- 不得接 cancel。
- 不得接 flatten。
- 不得接 retry protection。
- 不得接 resolve recovery task。
- 不得前端拼旧 API。

------

## 6.8 实盘复盘

### 6.8.1 目标

展示已有复盘事实、交易事实和系统链路事实。

### 6.8.2 Endpoint

```text
GET /api/trading-console/review-state
```

### 6.8.3 页面布局

```text
┌────────────────────────────────────┐
│ 页面标题：实盘复盘                   │
│ 复盘摘要                             │
├────────────────────────────────────┤
│ reviews 列表                         │
├────────────────────────────────────┤
│ filled_order_facts                   │
├────────────────────────────────────┤
│ positions                            │
├────────────────────────────────────┤
│ unavailable_fields                   │
└────────────────────────────────────┘
```

### 6.8.4 复盘卡片字段

建议展示：

- review_id
- decision / status
- authorization_id if present
- campaign_id if present
- created_at
- metadata summary

### 6.8.5 不可用字段展示

必须显示：

- fills_table: not_available
- fee: not_available
- fee_asset: not_available
- funding: not_available
- slippage: not_available

### 6.8.6 禁止

- 不得估算完整 PnL。
- 不得估算 fee。
- 不得估算 funding。
- 不得估算 slippage。
- 不得隐藏不可用成本字段。

------

## 6.9 技术审计

### 6.9.1 目标

给 Owner / 开发者排障。

### 6.9.2 Endpoint

```text
GET /api/trading-console/audit-chain
```

### 6.9.3 页面布局

```text
┌────────────────────────────────────┐
│ 页面标题：技术审计                   │
│ 查询区                               │
├────────────────────────────────────┤
│ authorization                       │
├────────────────────────────────────┤
│ intents                             │
├────────────────────────────────────┤
│ orders                              │
├────────────────────────────────────┤
│ positions                           │
├────────────────────────────────────┤
│ reviews                             │
├────────────────────────────────────┤
│ audit_events                        │
├────────────────────────────────────┤
│ raw_payload_policy                  │
└────────────────────────────────────┘
```

### 6.9.4 查询区字段

- authorization_id
- intent_id
- order_id
- exchange_order_id
- symbol
- limit

### 6.9.5 展示规则

- 技术 ID 可直接展示。
- raw payload 不直接展示敏感内容。
- `raw_payload_policy=masked_or_omitted` 必须显示。
- unavailable 必须显示。
- 该页允许偏工程化。

------

## 6.10 信号图表预留

### 6.10.1 目标

后续图表复盘预留，不进入 P0。

### 6.10.2 Endpoint

```text
GET /api/trading-console/signal-marker-feed
```

### 6.10.3 页面状态

Gate 2 中显示为：

```text
后续功能预留
```

或不放入主导航。

### 6.10.4 后续目标

```text
信号列表
+ TradingView / lightweight-charts 图表组件
+ signal / entry / TP / SL / recovery markers
```

### 6.10.5 禁止

- 不做外部 TradingView 跳转页。
- 不作为 Gate 2 P0 页面。
- 不从旧 signal API 直接拼页面。

------

## 7. 表格规范

### 7.1 通用表格能力

表格应支持：

- 搜索框
- 本地筛选
- 状态 filter
- source filter
- 分类 filter
- 分页或 limit 展示
- 行详情抽屉
- 空态
- loading
- unavailable 提示

### 7.2 表格不得做

- 不得跨旧 API 拉数据拼表
- 不得隐藏 unknown
- 不得把 not_available 显示为空
- 不得把 pg_unchecked 显示成 matched

------

## 8. 卡片规范

### 8.1 状态卡

状态卡结构：

```text
标题
主状态
辅助说明
更新时间
source
warnings/blockers count
```

### 8.2 风险卡

风险卡结构：

```text
风险级别
风险原因
影响范围
需要关注的事实
可跳转页面
```

### 8.3 Future Action 卡

future action 卡结构：

```text
动作名称
当前状态：未开放
原因
需要后端 action API
是否可能触达交易：未来确认
```

------

## 9. 颜色 / 状态语义建议

不强制具体色值，但语义必须固定：

| 语义        | 用途            |
| ----------- | --------------- |
| normal      | 已知正常事实    |
| neutral     | 未连接 / 未核验 |
| warning     | 需关注          |
| danger      | 阻断 / 高风险   |
| unavailable | 数据不可用      |
| disabled    | 动作不可用      |
| future      | 后续能力槽位    |

禁止：

- 用 normal/green 表示 `not_live_connected`
- 用 normal/green 表示 `unknown`
- 用 normal/green 表示 `unavailable`
- 用 normal/green 表示 `pg_unchecked`

------

## 10. 文案规范

### 10.1 推荐用语

- 交易控制台
- 实盘行动
- 有界实盘授权
- 实盘执行
- 实盘复盘
- 账户总览
- 订单台账
- 异常恢复
- 技术审计
- 未连接实时交易所事实
- 数据不可用
- 当前后端未提供
- 后续能力槽位

### 10.2 禁止用户可见主文案

- trial
- test authorization
- mock
- demo
- simulation
- 测试授权
- 发起测试
- 测试页面
- 模拟页面

### 10.3 Disabled action 文案

统一使用：

```text
当前未开放
```

补充说明：

```text
该动作需要后端安全 action API，并经主控确认后才能启用。
```

------

## 11. Gate 3 操作组件预设

AI Studio 可以预设以下组件，但必须 disabled：

### 11.1 危险动作按钮

用于未来：

- 执行实盘行动
- 撤单
- 平仓
- retry protection
- resolve recovery

当前全部 disabled。

### 11.2 二次确认弹窗

可设计但不触发。

弹窗结构：

```text
动作名称
是否触达交易所
是否修改 PG
symbol
side
quantity
notional
authorization_id
风险说明
取消
确认
```

当前确认按钮 disabled。

### 11.3 订单操作菜单

可预设：

- 查看审计
- 查看关联复盘
- 取消订单
- 标记异常

当前只有查看类可以作为只读导航；交易动作 disabled。

### 11.4 Recovery 操作区

可预设：

- 手动对账
- 作废授权
- retry protection
- cancel order
- flatten position
- mark manual review required

当前全部按后端可用性展示；未在 `/api/trading-console/*` 暴露的动作不得接入。

------

## 12. 响应式布局建议

### 桌面优先

交易控制台主要面向桌面端。

推荐：

- 左侧导航固定
- 顶部环境条固定
- 内容区宽屏表格
- 详情抽屉右侧滑出
- 审计页支持大表格 / JSON-like 区块

### 移动端

移动端可降级：

- 导航折叠
- 表格变卡片
- 审计页只读
- 不优化复杂操作

Gate 2 不要求移动端完整体验。

------

## 13. AI Studio 设计红线

AI Studio 不得：

1. 自行增加真实动作按钮。
2. 自行接旧 API。
3. 自行生成 mock 数据作为 truth source。
4. 把 sample data 展示为真实数据。
5. 把 not_available 估算成数值。
6. 把 unavailable 隐藏。
7. 把 not_live_connected 画成安全。
8. 把 BNB-first Carrier Shelf 画成最终多策略货架。
9. 把 signal-marker-feed 做成 P0 页面。
10. 把 disabled slot 变成可点击。
11. 使用 trial / 测试授权 作为主语言。
12. 把执行控制页做成交易终端。

------

## 14. 页面验收标准

### 首页

- 能显示 freshness。
- 能显示 not_live_connected。
- 能显示 warning / blocker / unavailable。
- 不显示执行按钮。
- 不以发起实盘行动为中心。

### 账户总览

- 能展示全账户事实。
- 能区分 PG / exchange。
- 能展示 risk_state。
- 不估算 not_available 字段。

### 订单台账

- 是一级页面。
- 能展示分类统计。
- 能展示订单表。
- 能展示保护单组。
- 能展示 pg_only / exchange_only / mismatch / orphan。
- 不估算 fee / funding / slippage。

### Carrier Shelf

- 明确 BNB-first v1 scope。
- 不使用 sample data。
- 不伪装成完整货架。

### 授权页

- 能展示 is_actionable / consumed / expired / cancelled。
- future action slot disabled。
- 不展示执行入口。

### 执行控制

- hard gate 可见。
- blockers 可见。
- deferred execute slot disabled。
- 没有真实执行按钮。

### 异常恢复

- manual_action_required 可见。
- recovery tasks 可见。
- deferred actions disabled。
- 不接 cancel / flatten / retry。

### 复盘

- review records 可见。
- filled_order_facts 可见。
- unavailable_fields 可见。
- 不伪造完整 PnL。

### 技术审计

- 支持核心 ID 查询。
- 展示 audit chain。
- raw payload policy 可见。
- 技术字段可复制。

------

## 15. 结论

交易控制台 Gate 2 UI 的核心是：

```text
只读真实事实
清楚表达风险
清楚表达不可用
清楚表达 deferred
预设未来操作组件
但不开放任何真实交易动作
```

AI Studio 的任务是把这些状态、页面和组件做成可用工程，而不是重新解释交易语义或安全边界。