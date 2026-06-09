# 交易控制台 API 接入文档 v0.1

> [!CAUTION]
> **SUPERSEDED** — This document describes an earlier Gate 2 read-model product design and no longer represents current product direction or agent instructions.
>
> Current authoritative product semantics:
> - `docs/canon/BRC_TARGET_SEMANTICS.md`
> - `docs/canon/PROJECT_BASELINE_CURRENT.md`
> - `docs/canon/DOCUMENT_GOVERNANCE.md`
>
> This file is preserved only as historical reference.

## 0. 文档状态

- 产品名：交易控制台
- 阶段：Gate 2 `PASS_WITH_CONSTRAINT`
- 文档类型：前端 API 接入文档
- 适用对象：AI Studio 前端工程、前端接入审计、主控验收
- 唯一事实源：`/api/trading-console/*`
- 本文档接口性质：历史 Gate 2 只读 read model
- 本文档禁止接入：真实 action API；此限制不代表当前完整产品边界

------

## 1. 接入总原则

### 1.1 唯一允许 API namespace

交易控制台前端只允许调用：

```text
/api/trading-console/*
```

前端不得把以下 API 作为交易控制台 truth source：

```text
/api/brc/*
/api/runtime/*
/api/dev/testnet/brc/*
```

如页面发现 `/api/trading-console/*` 字段不足、状态语义不清或无法表达页面需求，应输出：

```text
交易控制台后端依赖同步单 v0.2
```

交主控窗口统一处理，不直接派 Codex 后端任务。

------

### 1.2 禁止前端自行推断安全状态

前端不得通过多个旧接口拼接以下状态：

- 当前账户是否安全
- 当前是否可执行
- 授权是否可行动
- 保护是否完整
- 订单是否可归属
- PG 与交易所是否一致
- recovery 是否可操作
- action 是否可点击

这些必须来自 `/api/trading-console/*` read model。

------

### 1.3 禁止接入真实动作

Gate 2 阶段不得接入：

- execute
- cancel order
- replace order
- flatten position
- retry protection
- retry recovery task
- resolve recovery task
- runtime start
- auto-execution enablement
- credential / API key update
- 任何 PG mutation action

如果接口返回：

- `deferred_actions`
- `future_action_slots`
- `deferred_execute_endpoint`

前端只能展示为：

```text
disabled
unavailable
future placeholder
```

不得做成可点击动作。

------

## 2. Shared Envelope

所有 `/api/trading-console/*` endpoint 都应返回统一 envelope。

### 2.1 通用结构

```json
{
  "read_model": "dashboard_state",
  "generated_at_ms": 1780500000000,
  "source": "trading_console_read_model_v1",
  "freshness_status": "not_live_connected",
  "warnings": [],
  "blockers": [],
  "unavailable": [],
  "data": {},
  "no_action_guarantee": {
    "places_order": false,
    "cancels_order": false,
    "replaces_order": false,
    "flattens_position": false,
    "retries_protection": false,
    "starts_runtime": false,
    "grants_auto_execution": false,
    "mutates_pg": false
  },
  "live_ready": false
}
```

### 2.2 前端必须读取的 envelope 字段

| 字段                  | 前端用途                      | 展示规则               |
| --------------------- | ----------------------------- | ---------------------- |
| `read_model`          | 当前返回对象类型              | 可用于调试，不一定主显 |
| `generated_at_ms`     | 生成时间                      | 用于更新时间显示       |
| `source`              | 数据源标识                    | 技术区展示             |
| `freshness_status`    | 数据新鲜度 / 连接语义         | 必须主显或状态显式化   |
| `warnings`            | 风险提示                      | 必须可见               |
| `blockers`            | 阻断项                        | 必须显著展示           |
| `unavailable`         | 不可用事实源                  | 不得隐藏               |
| `data`                | 页面主数据                    | 页面主体               |
| `no_action_guarantee` | 安全保证                      | 技术/审计区可展示      |
| `live_ready`          | read model 层 live-ready 状态 | 不得用于展示可执行     |

------

## 3. Freshness 状态接入规则

### 3.1 状态枚举

| 值                   | 含义                             | UI 展示                                  |
| -------------------- | -------------------------------- | ---------------------------------------- |
| `fresh`              | 请求源可用，未出现 degraded 事实 | 可以正常展示，但仍需看 warnings/blockers |
| `warning`            | 数据可用但存在 warning facts     | 显示“需关注”                             |
| `degraded`           | 一个或多个数据源失败 / 不可用    | 显示“数据降级 / 不完整”                  |
| `not_live_connected` | 默认未请求交易所事实             | 显示“未连接实时交易所事实”               |

### 3.2 禁止展示

| 状态                 | 禁止展示为              |
| -------------------- | ----------------------- |
| `not_live_connected` | 账户安全 / 已确认无风险 |
| `degraded`           | clean / healthy         |
| `warning`            | 完全正常                |
| `unknown`            | 正常                    |
| `unavailable`        | 可忽略                  |

------

## 4. include_exchange 接入规则

部分 endpoint 支持：

```text
include_exchange=false | true
```

### 4.1 默认值

```text
include_exchange=false
```

含义：

- 不调用交易所
- 不调用 account snapshot reader
- 返回本地 / PG / cached / read-model facts
- freshness 通常为 `not_live_connected`

前端不得把该状态展示为真实账户安全。

### 4.2 启用交易所只读事实

```text
include_exchange=true
```

含义：

- 允许后端调用只读 exchange 方法
- 可读取 positions
- 可读取 open orders
- 可读取 conditional / stop open orders
- 不允许下单、撤单、改单、平仓

### 4.3 页面建议

| 页面                | 默认 include_exchange               | 说明                           |
| ------------------- | ----------------------------------- | ------------------------------ |
| 首页 / 真实风险总览 | `false` 初始，允许手动刷新为 `true` | 避免默认频繁读交易所           |
| 账户总览            | 建议支持 `true`                     | 账户页需要真实事实             |
| 订单台账            | 建议支持 `true`                     | 订单对账需要交易所 open orders |
| 保护状态            | 建议支持 `true`                     | 判断保护单是否真实存在         |
| 异常恢复            | 建议支持 `true`                     | 异常页需要真实风险事实         |
| 授权状态            | `false`                             | 授权状态来自后端               |
| 执行控制            | `false` 或 `true` 由主控确认        | 只读显示，不执行               |
| 复盘                | `false`                             | 使用已存事实                   |
| 技术审计            | `false`                             | 查询链路，不读交易所           |
| Carrier Shelf       | `false`                             | v1 展示当前 scope              |
| Signal marker feed  | `false`                             | 后置图表 feed                  |

------

## 5. 页面到 API 映射

| 页面                | Endpoint                                            | 说明                          |
| ------------------- | --------------------------------------------------- | ----------------------------- |
| 首页 / 真实风险总览 | `GET /api/trading-console/dashboard-state`          | 首页聚合状态                  |
| 账户总览            | `GET /api/trading-console/account-risk`             | 全账户风险事实                |
| 订单台账            | `GET /api/trading-console/order-ledger`             | 订单分类、保护单组、对账事实  |
| 保护状态            | `GET /api/trading-console/protection-health`        | 保护完整性                    |
| 异常恢复            | `GET /api/trading-console/recovery-exception-state` | 异常、mismatch、recovery task |
| 有界实盘授权        | `GET /api/trading-console/authorization-state`      | 授权生命周期                  |
| 实盘执行控制        | `GET /api/trading-console/execution-control-state`  | 执行控制只读状态              |
| 实盘复盘            | `GET /api/trading-console/review-state`             | 复盘事实                      |
| 技术审计            | `GET /api/trading-console/audit-chain`              | 技术链路                      |
| Carrier Shelf       | `GET /api/trading-console/carrier-availability`     | v1 Carrier 可用性             |
| 信号图表预留        | `GET /api/trading-console/signal-marker-feed`       | 后续 marker feed              |
| API 治理            | `GET /api/trading-console/api-classification`       | API 白名单 / 旧 API 分类      |

------

# 6. Endpoint 接入说明

## 6.1 `GET /api/trading-console/dashboard-state`

### 页面

首页 / 真实风险总览

### 用途

提供首页唯一聚合状态，避免前端自行拼接安全状态。

### Query

| 参数               | 类型    | 默认  | 说明                   |
| ------------------ | ------- | ----- | ---------------------- |
| `symbol`           | string? | null  | 可选 symbol 过滤       |
| `include_exchange` | boolean | false | 是否读取交易所只读事实 |

### `data` 主要字段

| 字段                       | 含义                                             |
| -------------------------- | ------------------------------------------------ |
| `environment`              | 运行环境、profile、trading_env、exchange_testnet |
| `guards`                   | GKS / startup guard                              |
| `account_snapshot_summary` | 账户摘要                                         |
| `positions.pg`             | PG 仓位                                          |
| `positions.exchange`       | 交易所仓位                                       |
| `orders.pg_open`           | PG open orders                                   |
| `orders.exchange_open`     | 交易所 open orders                               |
| `orders.open_intents`      | 未终态 execution intents                         |
| `consistency`              | 一致性摘要                                       |
| `authorization`            | 授权摘要                                         |
| `freshness`                | 数据新鲜度                                       |

### 前端展示规则

- 首页主状态来自该 endpoint。
- `freshness_status=not_live_connected` 时，显示“未连接实时交易所事实”。
- `warnings` 必须展示。
- `blockers` 必须主显。
- `unavailable` 必须显示为数据源缺失。
- 不展示“发起实盘行动”作为默认主按钮。

------

## 6.2 `GET /api/trading-console/account-risk`

### 页面

账户总览

### 用途

展示全账户风险、仓位、挂单、资金事实和保护归属。

### Query

| 参数               | 类型    | 默认  | 说明                   |
| ------------------ | ------- | ----- | ---------------------- |
| `symbol`           | string? | null  | 可选 symbol 过滤       |
| `include_exchange` | boolean | false | 是否读取交易所只读事实 |

### `data` 主要字段

| 字段                   | 含义                                  |
| ---------------------- | ------------------------------------- |
| `risk_state`           | `healthy` / `degraded` / `unknown` 等 |
| `account`              | 账户摘要                              |
| `positions`            | 仓位列表                              |
| `open_orders`          | open orders                           |
| `margin_facts`         | margin / equity / unrealized_pnl      |
| `protection_ownership` | 保护归属摘要                          |
| `freshness`            | 数据新鲜度                            |

### 前端展示规则

- `risk_state=unknown` 不得展示为 healthy。
- 仓位和订单需显示 source：PG / exchange。
- 不得估算不可用 PnL / margin。
- 账户页可提供“读取交易所只读事实”刷新入口，但该入口只触发 include_exchange=true 的 GET 请求，不是 action API。

------

## 6.3 `GET /api/trading-console/order-ledger`

### 页面

订单台账

### 用途

展示 PG / 交易所订单、保护单组、分类统计和不可用字段。

### Query

| 参数               | 类型    | 默认  | 说明                       |
| ------------------ | ------- | ----- | -------------------------- |
| `symbol`           | string? | null  | 可选 symbol 过滤           |
| `include_exchange` | boolean | false | 是否读取交易所 open orders |
| `limit`            | number  | 100   | 1-500                      |

### `data` 主要字段

| 字段                    | 含义                    |
| ----------------------- | ----------------------- |
| `orders`                | 分类后的订单行          |
| `groups`                | entry/protection groups |
| `classification_counts` | 分类计数                |
| `unavailable_fields`    | 不可用字段              |

### 订单分类

| classification      | 含义                  | UI 规则            |
| ------------------- | --------------------- | ------------------ |
| `matched`           | PG 与交易所可匹配     | 正常展示           |
| `pg_unchecked`      | 未请求交易所事实      | 显示“未核验交易所” |
| `pg_only`           | PG 有，交易所未见     | 警示               |
| `exchange_only`     | 交易所有，PG 无       | 警示               |
| `mismatch`          | PG 与交易所状态不一致 | 警示 / 异常        |
| `orphan_protection` | 孤儿保护单            | 显著警示           |
| `unknown`           | 无法归类              | 显示未知           |

### 订单字段展示建议

前端应优先展示：

- order_id
- exchange_order_id
- symbol
- direction / side
- order_type
- order_role
- status
- price
- trigger_price
- requested_qty
- filled_qty
- average_exec_price
- reduce_only
- parent_order_id
- oco_group_id
- classification
- source
- exchange_match / pg_match

### unavailable_fields

当前 v1 明确不可用：

- client_order_id
- fees
- funding
- slippage

前端不得估算。

------

## 6.4 `GET /api/trading-console/protection-health`

### 页面

保护状态 / 订单台账 / 异常恢复

### 用途

展示前端安全可用的保护状态。

### Query

| 参数               | 类型    | 默认  | 说明                   |
| ------------------ | ------- | ----- | ---------------------- |
| `symbol`           | string? | null  | 可选 symbol            |
| `include_exchange` | boolean | false | 是否读取交易所只读事实 |

### `data` 主要字段

| 字段                | 含义                 |
| ------------------- | -------------------- |
| `status`            | 保护状态             |
| `protection_orders` | 保护单列表           |
| `tp_count`          | TP 数量              |
| `sl_count`          | SL 数量              |
| `findings`          | 检测发现             |
| `actions_exposed`   | 当前开放动作，应为空 |
| `deferred_actions`  | 后续动作槽位         |

### status 枚举

| status                | 含义           | UI 规则               |
| --------------------- | -------------- | --------------------- |
| `protected`           | TP/SL 保护完整 | 正常                  |
| `partially_protected` | 部分保护       | warning               |
| `unprotected`         | 有仓位但无保护 | blocker / danger      |
| `unknown`             | 无法确认       | warning / unavailable |
| `orphaned`            | 孤儿保护单     | warning / danger      |

### 前端展示规则

- `actions_exposed` 不应生成操作按钮。
- `deferred_actions` 只展示 disabled placeholder。
- `unprotected` / `orphaned` 必须进入异常提示。

------

## 6.5 `GET /api/trading-console/recovery-exception-state`

### 页面

异常恢复

### 用途

展示 recovery task、mismatch、manual action required 和 future action slot。

### Query

| 参数               | 类型    | 默认  | 说明                   |
| ------------------ | ------- | ----- | ---------------------- |
| `symbol`           | string? | null  | 可选 symbol            |
| `include_exchange` | boolean | false | 是否读取交易所只读事实 |

### `data` 主要字段

| 字段                     | 含义                                        |
| ------------------------ | ------------------------------------------- |
| `recovery_tasks`         | recovery task 列表                          |
| `recovery_task_counts`   | recovery task 计数                          |
| `mismatches`             | mismatch / orphan / PG-only / exchange-only |
| `manual_action_required` | 是否需要人工处理                            |
| `read_only_actions`      | 只读动作提示                                |
| `deferred_actions`       | 后续动作槽位                                |

### 前端展示规则

- `manual_action_required=true` 必须显著展示。
- `deferred_actions` 不可点击。
- 可以预留 Gate 3 操作区，但所有动作 disabled。
- 如果只有 `read_only_actions.manual_reconciliation`，也必须确认该动作是否属于 `/api/trading-console/*`；若不是，不得直接接入旧 API。

------

## 6.6 `GET /api/trading-console/authorization-state`

### 页面

有界实盘授权

### 用途

展示授权生命周期和是否可行动。

### Query

| 参数     | 类型    | 默认 | 说明        |
| -------- | ------- | ---- | ----------- |
| `symbol` | string? | null | 可选 symbol |

### `data` 主要字段

| 字段                  | 含义           |
| --------------------- | -------------- |
| `carrier_id`          | Carrier ID     |
| `authorization_id`    | 授权 ID        |
| `status`              | 授权状态       |
| `is_actionable`       | 是否可行动     |
| `is_consumed`         | 是否已消费     |
| `is_expired`          | 是否过期       |
| `is_cancelled`        | 是否取消       |
| `scope_match`         | scope 是否匹配 |
| `blocking_reason`     | 不可行动原因   |
| `scope`               | 授权范围       |
| `future_action_slots` | 后续动作槽位   |

### 前端展示规则

- `is_actionable=false` 时不得展示执行入口。
- `is_consumed=true` 必须显示“已消费”。
- `is_expired=true` 必须显示“已过期”。
- `scope_match=not_checked` 不得展示为通过。
- `future_action_slots.void_authorization` 只能 disabled。
- `future_action_slots.cancel_authorization` 只能 disabled。

------

## 6.7 `GET /api/trading-console/execution-control-state`

### 页面

实盘执行控制

### 用途

展示执行控制状态，不执行任何真实动作。

### Query

| 参数               | 类型    | 默认  | 说明                   |
| ------------------ | ------- | ----- | ---------------------- |
| `symbol`           | string? | null  | 可选 symbol            |
| `include_exchange` | boolean | false | 是否读取交易所只读事实 |

### `data` 主要字段

| 字段                        | 含义                  |
| --------------------------- | --------------------- |
| `hard_gate.status`          | hard gate 总状态      |
| `hard_gate.gates`           | gate 列表             |
| `execution_preview`         | 执行预览状态          |
| `deferred_execute_endpoint` | 执行接口是否 deferred |

### 前端展示规则

- 不显示可点击执行按钮。
- `deferred_execute_endpoint=true` 显示 disabled slot。
- `execution_preview.status=not_available` 不得补写。
- `hard_gate.status=blocked` 必须显著展示。
- 不得调用旧 execute endpoint。
- 可预设 Gate 3 执行按钮组件，但必须 disabled。

------

## 6.8 `GET /api/trading-console/review-state`

### 页面

实盘复盘

### 用途

展示 review records、filled order facts、positions 和不可用字段。

### Query

| 参数     | 类型    | 默认 | 说明        |
| -------- | ------- | ---- | ----------- |
| `symbol` | string? | null | 可选 symbol |
| `limit`  | number  | 100  | 1-500       |

### `data` 主要字段

| 字段                 | 含义           |
| -------------------- | -------------- |
| `reviews`            | 复盘记录       |
| `filled_order_facts` | 已成交订单事实 |
| `positions`          | 仓位           |
| `unavailable_fields` | 不可用字段     |

### 当前 unavailable_fields

- fills_table
- fee
- fee_asset
- funding
- slippage

### 前端展示规则

- 不估算 fee。
- 不估算 fee_asset。
- 不估算 funding。
- 不估算 slippage。
- 不构造完整 PnL。
- 如果只展示已有 realized_pnl / average_exec_price / filled_qty，必须标明“基于已存事实”。

------

## 6.9 `GET /api/trading-console/audit-chain`

### 页面

技术审计

### 用途

按核心 ID 查询技术链路。

### Query

| 参数                | 类型    | 默认 | 说明               |
| ------------------- | ------- | ---- | ------------------ |
| `authorization_id`  | string? | null | 授权 ID            |
| `intent_id`         | string? | null | ExecutionIntent ID |
| `order_id`          | string? | null | 本地订单 ID        |
| `exchange_order_id` | string? | null | 交易所订单 ID      |
| `symbol`            | string? | null | symbol             |
| `limit`             | number  | 100  | 1-500              |

### `data` 主要字段

| 字段                 | 含义             |
| -------------------- | ---------------- |
| `query`              | 查询条件         |
| `authorization`      | 授权状态         |
| `intents`            | 执行意图         |
| `orders`             | 订单             |
| `positions`          | 仓位             |
| `reviews`            | 复盘             |
| `audit_events`       | 审计事件         |
| `raw_payload_policy` | raw payload 策略 |

### 前端展示规则

- raw payload 只展示策略，不展示敏感内容。
- `raw_payload_policy=masked_or_omitted` 必须可见。
- 该页面可以显示技术 ID。
- `unavailable` 必须显示数据源缺失。

------

## 6.10 `GET /api/trading-console/carrier-availability`

### 页面

Carrier Shelf

### 用途

展示当前 v1 Carrier 可用性。

### Query

| 参数               | 类型    | 默认  | 说明                   |
| ------------------ | ------- | ----- | ---------------------- |
| `include_exchange` | boolean | false | 是否读取交易所只读事实 |

### `data` 主要字段

| 字段                 | 含义             |
| -------------------- | ---------------- |
| `carriers`           | Carrier 列表     |
| `sample_data_policy` | sample data 策略 |

### carrier 字段

建议展示：

- carrier_id
- strategy_family_id
- symbol
- side
- status
- blocked_reasons
- authorization
- protection

### 前端展示规则

- v1 只展示当前 BNB-first Carrier scope。
- 不展示成最终多策略货架。
- `sample_data_policy=not_used` 必须作为产品约束。
- blocked_reasons 必须可见。
- 不出现“测试候选”文案。

------

## 6.11 `GET /api/trading-console/signal-marker-feed`

### 页面

信号图表预留，不进入 Gate 2 P0。

### 用途

为后续 TradingView / lightweight-charts 图表 marker 提供后端 feed。

### Query

| 参数     | 类型    | 默认 | 说明        |
| -------- | ------- | ---- | ----------- |
| `symbol` | string? | null | 可选 symbol |
| `limit`  | number  | 100  | 1-500       |

### `data` 主要字段

| 字段            | 含义         |
| --------------- | ------------ |
| `markers`       | marker 列表  |
| `chart_adapter` | 图表适配状态 |

### 前端展示规则

- Gate 2 不做 P0 页面。
- 不做外部 TradingView 跳转。
- 后续目标是内嵌图表组件。
- 当前可在技术区或后续章节标为“预留”。

------

## 6.12 `GET /api/trading-console/api-classification`

### 页面

不一定独立成页，可用于前端接入约束、技术审计或开发检查。

### 用途

明确交易控制台允许 API、旧 API 分类和 action 策略。

### `data` 主要字段

| 字段                         | 含义             |
| ---------------------------- | ---------------- |
| `trading_console_v1_allowed` | 允许接入 API     |
| `internal_or_legacy`         | 内部 / 旧 API    |
| `action_api_policy`          | action API 策略  |
| `sample_data_policy`         | sample data 策略 |

### 前端展示规则

- AI Studio 工程必须遵守 allowed list。
- `internal_or_legacy` 里的 API 不可作为 truth source。
- `action_api_policy=deferred_not_exposed_in_trading_console_v1` 必须遵守。
- `sample_data_policy=not_allowed_as_trading_console_truth_source` 必须遵守。

------

## 7. 状态展示规范

### 7.1 Severity 映射

| 后端事实                        | UI severity       |
| ------------------------------- | ----------------- |
| no warnings, no blockers, fresh | normal            |
| warnings non-empty              | warning           |
| blockers non-empty              | blocker           |
| unavailable non-empty           | degraded          |
| not_live_connected              | neutral / caution |
| unknown                         | caution           |
| not_available                   | muted unavailable |
| deferred action                 | disabled          |
| future action slot              | disabled / future |

### 7.2 订单分类视觉建议

| classification      | 显示             |
| ------------------- | ---------------- |
| `matched`           | 正常             |
| `pg_unchecked`      | 中性提示         |
| `pg_only`           | warning          |
| `exchange_only`     | warning          |
| `mismatch`          | blocker / danger |
| `orphan_protection` | danger           |
| `unknown`           | caution          |

### 7.3 保护状态视觉建议

| status                | 显示    |
| --------------------- | ------- |
| `protected`           | normal  |
| `partially_protected` | warning |
| `unprotected`         | danger  |
| `unknown`             | caution |
| `orphaned`            | danger  |

### 7.4 授权状态视觉建议

| 状态                      | 显示                      |
| ------------------------- | ------------------------- |
| `is_actionable=true`      | 注意：Gate 2 仍不开放执行 |
| `is_consumed=true`        | 已消费，不可执行          |
| `is_expired=true`         | 已过期                    |
| `is_cancelled=true`       | 已取消                    |
| `scope_match=not_checked` | 未核验，不可展示为通过    |
| `blocking_reason` 非空    | 显著展示                  |

------

## 8. 错误、空态、加载态

### 8.1 Loading

每个页面应有 loading 状态：

```text
正在读取交易控制台只读事实
```

如果 `include_exchange=true`：

```text
正在读取交易所只读事实
```

### 8.2 Empty

空态必须区分：

| 场景            | 文案                     |
| --------------- | ------------------------ |
| 无订单          | 当前没有可展示订单事实   |
| 未读取交易所    | 当前未读取交易所订单事实 |
| 无复盘          | 当前没有复盘记录         |
| 无 audit events | 当前没有匹配审计事件     |
| 无 carrier      | 当前无可展示 Carrier     |
| 无 markers      | 当前无 marker feed       |

### 8.3 Error / unavailable

如果 `unavailable` 非空，展示：

```text
部分数据源不可用，当前页面不代表完整真实状态。
```

不能静默失败。

------

## 9. 禁止行为清单

AI Studio / 前端工程禁止：

1. 调用 `/api/brc/*` 作为交易控制台事实源。
2. 调用 `/api/runtime/*` 作为交易控制台事实源。
3. 调用 `/api/dev/testnet/brc/*`。
4. 接入 execute action。
5. 接入 cancel / replace / flatten / retry protection。
6. 根据前端判断启用按钮。
7. 把 `deferred_actions` 变成可点击按钮。
8. 把 `future_action_slots` 变成可点击按钮。
9. 把 `deferred_execute_endpoint` 变成执行入口。
10. 估算 fee / funding / slippage。
11. 伪造 fills。
12. 隐藏 not_available。
13. 隐藏 unavailable。
14. 把 not_live_connected 当 clean。
15. 把 BNB-first Carrier Shelf 做成最终多策略货架。
16. 把 signal-marker-feed 做成 Gate 2 P0 页面。
17. 使用 trial / 测试授权 等用户可见主语言。

------

## 10. 前端接入验收标准

前端接入通过标准：

1. 所有 API 请求均来自 `/api/trading-console/*`。
2. 所有页面都读取 shared envelope。
3. 所有页面都处理 `freshness_status`。
4. 所有页面都展示 `warnings`。
5. 所有页面都展示 `blockers`。
6. 所有页面都展示或汇总 `unavailable`。
7. `not_available` 字段不被估算。
8. `deferred_actions` 全部 disabled。
9. `future_action_slots` 全部 disabled。
10. `deferred_execute_endpoint` 不产生执行按钮。
11. 订单台账正确区分分类。
12. 保护状态正确映射 severity。
13. 授权状态不会误导为可执行。
14. 执行控制页不出现真实执行动作。
15. Recovery 页不出现真实恢复动作。
16. 复盘页不伪造完整 PnL。
17. 技术审计页不泄露敏感 payload。
18. Carrier Shelf 明确 v1 scope。
19. Signal marker feed 后置。
20. 不出现 sample_data 作为 truth source。

------

## 11. 后端缺口反馈规则

如果前端接入过程中发现以下情况：

- 页面无法表达关键状态
- endpoint 缺字段
- 状态枚举不清
- warnings / blockers / unavailable 无法映射
- order classification 不够
- protection status 不够
- authorization state 不够
- execution-control 不够
- review 数据不足
- audit query 不够
- BNB-first scope 影响产品表达

前端窗口输出：

```text
交易控制台后端依赖同步单 v0.2
```

不要直接要求 Codex 修改后端。

------

## 12. 当前 API 接入结论

Gate 2 阶段可接入：

- dashboard-state
- account-risk
- order-ledger
- protection-health
- recovery-exception-state
- authorization-state
- execution-control-state
- review-state
- audit-chain
- carrier-availability
- api-classification

Gate 2 阶段可预留但不作为 P0：

- signal-marker-feed

Gate 2 阶段不可接入：

- execute
- cancel
- replace
- flatten
- retry protection
- runtime start
- auto-execution
- 任何 PG mutation action

本阶段前端目标是：

```text
Gate 2 read-model 交易控制台
+ 风险状态清晰
+ 订单事实可见
+ 授权执行链路可见
+ 异常可解释
+ 复盘可读
+ 审计可查
+ 未来操作槽位预设但全部禁用
```
