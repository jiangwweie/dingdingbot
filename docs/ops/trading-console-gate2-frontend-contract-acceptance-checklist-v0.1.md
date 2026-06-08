# 交易控制台 Gate 2 前端合同验收清单 v0.1

> [!IMPORTANT]
> 2026-06-08 范围说明：
> 本清单是 Gate 2 read-model / 前端只读接入验收材料，不是当前交易控制台产品边界。
> 当前产品口径见 `docs/ops/knowledge-pack/CURRENT_PRODUCT_OPERATING_MODEL.md`：
> Console 是 Owner bounded-live operations surface，不是单纯只读面板。

## 0. 目的

本清单由前端窗口产出，交给主控窗口判断当前 `/api/trading-console/*` read model 是否已达到“前端文档可启动 / AI Studio 只读版工程可规划”的 Gate 2 标准。

本清单不是 Codex 任务，不要求立即实现。
本清单只判断：当前后端 read model 是否足以支撑交易控制台正式前端文档。

---

## 1. Gate 2 总验收口径

Gate 2 通过后，前端窗口可以开始输出：

* 交易控制台产品说明书
* 交易控制台 API 接入文档
* 交易控制台 UI / 页面设计规范
* AI Studio 前端工程提示词

Gate 2 不要求后端完成：

* 真实执行 action API
* 撤单 / 平仓 / retry protection
* fills 表
* fee / funding / slippage
* 完整多 Carrier shelf
* TradingView 图表组件
* 信号台账完整实现

Gate 2 要求后端完成：

* P0 页面 read model 覆盖
* 字段语义稳定
* 状态语义稳定
* 不可用字段明确表达
* deferred action 明确表达
* 前端不需要自己推断安全状态
* 旧 API / sample data / testnet-only API 不作为交易控制台事实源

---

## 2. 全局接口合同验收

| 检查项                 | Gate 2 要求                                       | 当前判断 | 主控需确认                         |
| ------------------- | ----------------------------------------------- | ---- | ----------------------------- |
| Namespace           | 使用 `/api/trading-console/*`                     | 已有   | 是否作为交易控制台前端唯一允许 namespace     |
| 鉴权                  | operator-authenticated                          | 已有   | 是否满足前端工程接入                    |
| HTTP 方法             | read model 全部 GET-only                          | 已有   | 是否禁止 AI Studio 调用旧 action API |
| Shared envelope     | 所有 endpoint 返回统一 envelope                       | 已有   | 字段是否冻结                        |
| no_action_guarantee | 明确不下单、不撤单、不平仓、不 PG mutation                     | 已有   | 是否作为前端安全依据                    |
| live_ready          | read model 层固定 false                            | 已有   | 前端如何展示                        |
| freshness_status    | fresh / warning / degraded / not_live_connected | 已有   | 语义是否冻结                        |
| warnings            | 非阻断风险                                           | 已有   | warning 与 blocker 是否严格区分      |
| blockers            | 阻断项                                             | 已有   | blocker 是否足够可解释               |
| unavailable         | 数据源不可用                                          | 已有   | unavailable 不得被前端当作 clean     |
| include_exchange    | 默认 false，true 时只读 exchange                      | 已有   | 前端何时允许使用 true                 |

---

## 3. 首页 / 真实风险总览

### 依赖 endpoint

`GET /api/trading-console/dashboard-state`

### 页面需要事实

* 环境 / profile
* GKS / startup guard
* account snapshot summary
* PG positions
* exchange positions
* PG open orders
* exchange open orders
* open intents
* consistency
* authorization
* freshness
* warnings / blockers / unavailable

### Gate 2 必须确认

| 检查项                         | 要求                  | 当前状态      | 主控需确认                          |
| --------------------------- | ------------------- | --------- | ------------------------------ |
| 首页不自行拼接口                    | 后端提供 dashboard 聚合状态 | 已有        | 通过                             |
| 不把 not_live_connected 显示为安全 | 前端必须显著展示            | 需要文档约束    | 确认文案规则                         |
| stale / degraded 语义         | 后端统一返回              | 部分已有      | 是否需要更细状态                       |
| 当前唯一待处理事项                   | 后端是否返回足够依据          | 部分        | 是否需要 `next_required_action` 字段 |
| sample data 禁止              | 不作为首页事实源            | 已有 policy | 是否强制执行                         |

### 是否可进入前端文档

可以，但必须写明：

* `not_live_connected` 不代表账户安全
* `fresh` 才表示已请求交易所只读事实
* `unavailable` 不得当作 clean
* 首页主状态以真实风险为中心，不以发起实盘行动为中心

---

## 4. 账户总览

### 依赖 endpoint

`GET /api/trading-console/account-risk`

### 页面需要事实

* 全账户仓位
* 全账户挂单
* account balance / margin facts
* realized / unrealized PnL where available
* protection ownership
* freshness
* risk_state

### Gate 2 必须确认

| 检查项                  | 要求                           | 当前状态                  | 主控需确认                           |
| -------------------- | ---------------------------- | --------------------- | ------------------------------- |
| 全账户事实                | 不限当前 Carrier                 | 部分依赖 include_exchange | 是否允许账户页默认 include_exchange=true |
| risk_state           | healthy / degraded / unknown | 已有                    | 语义是否冻结                          |
| realized_pnl         | 能展示已有字段                      | 部分                    | API 是否稳定暴露                      |
| protection ownership | 后端给提示                        | 已有基础                  | 是否足够前端展示                        |
| 非当前 Carrier 风险       | 必须可见                         | 需样例验证                 | 需要测试样例                          |

### 是否可进入前端文档

可以，但账户页必须显示数据源和 freshness，不得只显示“安全”。

---

## 5. 订单台账

### 依赖 endpoint

`GET /api/trading-console/order-ledger`

### 页面需要事实

* PG orders
* exchange open orders
* conditional / stop orders
* entry order
* TP / SL protection orders
* parent order grouping
* PG-only
* exchange-only
* matched
* mismatch
* orphan protection
* unknown
* filled_qty
* average_exec_price
* unavailable fields

### Gate 2 必须确认

| 检查项                    | 要求                                                    | 当前状态 | 主控需确认              |
| ---------------------- | ----------------------------------------------------- | ---- | ------------------ |
| 一级页面支撑                 | order-ledger 可独立支撑页面                                  | 已有   | 通过                 |
| 订单分类                   | matched / pg_only / exchange_only / mismatch / orphan | 已有   | 分类语义是否冻结           |
| 保护单组                   | parent_order_id / protection groups                   | 已有   | 前端是否按 group 展示     |
| include_exchange=false | 订单为 pg_unchecked                                      | 已有   | 前端文案确认             |
| include_exchange=true  | 交易所只读 open orders                                     | 已有   | 是否允许订单页默认 true     |
| fills                  | 逐笔成交不可用                                               | 缺失   | 前端显示 not_available |
| fee/funding/slippage   | 不可用                                                   | 缺失   | 前端不得估算             |
| client_order_id        | 不可用                                                   | 缺失   | 不作为 Gate 2 阻塞      |

### 是否可进入前端文档

可以。
订单台账 v1 定位为：订单事实、保护单组、PG/exchange 可见差异。
不定位为：完整成交历史、完整费用、完整 PnL 审计。

---

## 6. 保护状态

### 依赖 endpoint

`GET /api/trading-console/protection-health`

### 页面需要事实

* protected
* partially_protected
* unprotected
* unknown
* orphaned
* protection orders
* TP count
* SL count
* findings
* exposed actions
* deferred actions

### Gate 2 必须确认

| 检查项                | 要求                   | 当前状态 | 主控需确认   |
| ------------------ | -------------------- | ---- | ------- |
| 保护状态枚举             | 可直接用于前端状态展示          | 已有   | 语义冻结    |
| orphaned           | 可识别孤儿保护单             | 已有   | 文案规则    |
| actions_exposed    | v1 应为空               | 已有   | 是否固定为空  |
| deferred_actions   | retry/cancel 等只展示不可用 | 已有   | 前端禁用态规则 |
| partial protection | 可展示                  | 已有基础 | 是否有样例测试 |

### 是否可进入前端文档

可以。
前端只能展示状态和引导，不提供 retry / cancel protection 按钮。

---

## 7. 异常恢复

### 依赖 endpoint

`GET /api/trading-console/recovery-exception-state`

### 页面需要事实

* recovery tasks
* recovery task counts
* mismatches
* manual_action_required
* read_only_actions
* deferred_actions

### Gate 2 必须确认

| 检查项              | 要求           | 当前状态 | 主控需确认      |
| ---------------- | ------------ | ---- | ---------- |
| 异常页可存在           | 有 read model | 已有   | 通过         |
| 手动对账             | 只读动作提示       | 部分   | 是否作为按钮进入前端 |
| retry protection | deferred     | 已有   | 禁用态文案      |
| cancel order     | deferred     | 已有   | 禁用态文案      |
| flatten position | deferred     | 已有   | 禁用态文案      |
| manual required  | 可展示          | 已有   | 是否需要分级     |

### 是否可进入前端文档

可以。
Recovery v1 是“异常可见化 + 引导页”，不是实际恢复操作页。

---

## 8. 有界实盘授权

### 依赖 endpoint

`GET /api/trading-console/authorization-state`

### 页面需要事实

* carrier_id
* authorization_id
* status
* is_actionable
* is_consumed
* is_expired
* is_cancelled
* scope_match
* blocking_reason
* scope
* future_action_slots

### Gate 2 必须确认

| 检查项                 | 要求                               | 当前状态 | 主控需确认         |
| ------------------- | -------------------------------- | ---- | ------------- |
| 授权状态显式化             | 前端不自行推断                          | 已有   | 通过            |
| consumed 不可执行       | 后端返回 is_consumed / is_actionable | 已有   | 语义冻结          |
| expired             | 后端返回                             | 已有基础 | TTL 是否真实可用    |
| cancelled           | 当前 false / future slot           | 部分   | 是否后续补 void    |
| scope_match         | 当前可能 not_checked                 | 部分   | Gate 2 是否接受   |
| profile/environment | 当前可能 not_available               | 部分   | 是否要 Gate 2 前补 |

### 是否可进入前端文档

可以，但需标注：

* `void_authorization` 是 future action slot
* `scope_match=not_checked` 不能被显示为通过
* profile/environment 缺失时必须显示 not_available

---

## 9. 实盘执行控制

### 依赖 endpoint

`GET /api/trading-console/execution-control-state`

### 页面需要事实

* hard_gate.status
* hard_gate.gates
* blockers
* warnings
* execution_preview
* deferred_execute_endpoint

### Gate 2 必须确认

| 检查项              | 要求                                       | 当前状态 | 主控需确认              |
| ---------------- | ---------------------------------------- | ---- | ------------------ |
| 执行控制只读           | 不创建 intent、不下单                           | 已有   | 通过                 |
| execute endpoint | deferred / absent                        | 已有   | 前端不得显示可点击执行        |
| hard gate        | 只读摘要                                     | 已有   | 是否足够表达             |
| per-gate 状态      | 至少 authorization/protection/open_intents | 已有基础 | 是否需要补完整 final gate |
| blockers         | 可展示                                      | 已有   | 文案规则               |

### 是否可进入前端文档

可以，但前端必须写死：

* Gate 2 版本不显示真实执行按钮
* 只显示执行控制状态
* `deferred_execute_endpoint=true` 时按钮只能 disabled / unavailable
* 不得调用旧 `/owner-trial-flow/.../execute`

---

## 10. 实盘复盘

### 依赖 endpoint

`GET /api/trading-console/review-state`

### 页面需要事实

* reviews
* filled_order_facts
* positions
* unavailable fields
* entry / protection / recovery 关系
* PnL where available

### Gate 2 必须确认

| 检查项                | 要求            | 当前状态 | 主控需确认  |
| ------------------ | ------------- | ---- | ------ |
| review records     | 可展示           | 已有   | 通过     |
| filled order facts | 可展示           | 已有   | 通过     |
| positions          | 可展示           | 已有   | 通过     |
| fee                | not_available | 已有   | 前端不得估算 |
| fee_asset          | not_available | 已有   | 前端不得估算 |
| funding            | not_available | 已有   | 前端不得估算 |
| slippage           | not_available | 已有   | 前端不得估算 |
| 完整 PnL             | 不作为 Gate 2 要求 | 缺失   | 主控确认   |

### 是否可进入前端文档

可以。
复盘 v1 必须区分：

* 已有交易事实
* 不可用成本字段
* 系统链路结果
* 后续 PnL 增强项

---

## 11. 技术审计

### 依赖 endpoint

`GET /api/trading-console/audit-chain`

### 查询参数

* authorization_id
* intent_id
* order_id
* exchange_order_id
* symbol
* limit

### 页面需要事实

* query
* authorization
* intents
* orders
* positions
* reviews
* audit_events
* raw_payload_policy

### Gate 2 必须确认

| 检查项         | 要求                      | 当前状态 | 主控需确认     |
| ----------- | ----------------------- | ---- | --------- |
| ID 查询       | 支持核心 ID                 | 已有   | 通过        |
| raw payload | masked_or_omitted       | 已有   | 是否满足排障    |
| 敏感字段        | 不暴露 api_key/secret/totp | 已有测试 | 通过        |
| unavailable | 缺 repo 时明确返回            | 已有   | 前端展示规则    |
| 完整链路        | v0.1 聚合                 | 部分   | 是否接受 v0.1 |

### 是否可进入前端文档

可以。
技术审计页给 Owner/开发者排障使用，不面向普通用户简化。

---

## 12. Carrier Shelf

### 依赖 endpoint

`GET /api/trading-console/carrier-availability`

### 页面需要事实

* carriers
* carrier_id
* strategy_family_id
* symbol
* side
* status
* blocked_reasons
* authorization
* protection
* sample_data_policy

### Gate 2 必须确认

| 检查项             | 要求                          | 当前状态 | 主控需确认         |
| --------------- | --------------------------- | ---- | ------------- |
| 不使用 sample_data | sample_data_policy=not_used | 已有   | 通过            |
| Carrier list    | v1 仅当前 BNB carrier          | 部分   | 是否接受 v1 scope |
| 多 Carrier       | 不作为 Gate 2 要求               | 缺失   | 后置            |
| blocked reasons | 可展示                         | 已有基础 | 语义是否足够        |
| BNB hardcode    | 需要明确临时性                     | 存在   | 主控必须确认        |

### 是否可进入前端文档

可以，但必须写明：

* Carrier Shelf v1 是当前 active/configured carrier surface
* 不是完整多策略货架
* BNB first carrier 是当前 v1 scope，不是最终产品结构

---

## 13. 信号 marker feed

### 依赖 endpoint

`GET /api/trading-console/signal-marker-feed`

### 页面需要事实

* markers
* marker_type
* timestamp_ms
* symbol
* side
* price
* source_id
* payload
* chart_adapter

### Gate 2 必须确认

| 检查项                     | 要求             | 当前状态 | 主控需确认   |
| ----------------------- | -------------- | ---- | ------- |
| 后端 marker feed          | 有              | 已有   | 可作为后续预留 |
| TradingView 组件          | 不在后端 sprint 范围 | 缺失   | 后置      |
| lightweight chart ready | false          | 已有   | 后置      |
| 信号台账                    | 不作为 P0         | 后置   | 主控确认    |

### 是否可进入前端文档

只作为后续扩展章节进入。
不进入 Gate 2 P0 页面工程范围。

---

## 14. API 分类 / 旧 API 隔离

### 依赖 endpoint

`GET /api/trading-console/api-classification`

### 页面需要事实

* trading_console_v1_allowed
* internal_or_legacy
* action_api_policy
* sample_data_policy

### Gate 2 必须确认

| 检查项             | 要求                          | 当前状态 | 主控需确认  |
| --------------- | --------------------------- | ---- | ------ |
| allowed API 白名单 | 有                           | 已有   | 通过     |
| 旧 API           | 标记 internal_or_legacy       | 已有   | 前端禁止调用 |
| action API      | deferred_not_exposed        | 已有   | 通过     |
| sample data     | not_allowed_as_truth_source | 已有   | 通过     |

### 是否可进入前端文档

必须进入。
这是 AI Studio 工程约束的一部分。

---

## 15. Gate 2 通过条件汇总

主控确认以下条件后，前端窗口可以开始正式文档：

1. `/api/trading-console/*` read model namespace 已挂载并稳定。
2. 所有 read model 仍为 GET-only。
3. 默认 `include_exchange=false` 不调用交易所。
4. `include_exchange=true` 只调用只读 exchange 方法。
5. shared envelope 字段冻结。
6. `freshness_status` 语义冻结。
7. `warnings / blockers / unavailable` 语义冻结。
8. `no_action_guarantee` 作为前端安全约束。
9. P0 页面均有对应 endpoint。
10. 订单台账分类语义冻结。
11. 保护状态枚举语义冻结。
12. Recovery deferred action 语义冻结。
13. Authorization `is_actionable / is_consumed / is_expired / is_cancelled / scope_match` 语义冻结。
14. Execution-control 明确不提供真实执行。
15. Review 不可用成本字段明确返回 `not_available`。
16. Audit raw payload policy 固定为 `masked_or_omitted`。
17. Carrier Shelf v1 的 BNB scope 被主控接受或后端已去硬编码。
18. Signal marker feed 后置，不阻塞 P0。
19. 旧 `/api/brc/*`、`/api/runtime/*`、testnet/dev-only API 不作为交易控制台事实源。
20. sample_data 不作为交易控制台 truth source。

---

## 16. Gate 2 未通过时的阻塞点

若以下任一项未确认，不应开始正式前端文档：

* 后端 contract 字段仍频繁变动。
* `warnings / blockers / unavailable` 语义不稳定。
* `include_exchange` 页面语义不清。
* 前端仍需要拼旧 API 判断安全状态。
* `execution-control-state` 被误认为真实执行入口。
* 订单台账分类不稳定。
* BNB hardcode 未被主控接受为 v1 scope。
* sample_data 仍可能进入真实页面。
* 旧执行按钮仍可能被新前端复用。
* P0 页面缺代表性响应样例。

---

## 17. Gate 2 通过后的前端工作范围

Gate 2 通过后，前端窗口输出：

* 交易控制台产品说明书
* 交易控制台 API 接入文档
* 交易控制台 UI / 页面设计规范
* AI Studio 工程提示词

AI Studio 工程范围：

* Gate 2 read-model 交易控制台
* 首页 / 账户总览 / 订单台账 / 授权状态 / 执行控制状态 / 异常恢复 / 复盘 / 审计
* Gate 3 操作组件预设
* disabled / deferred 状态
* 不接真实 action API

AI Studio 不得实现：

* 真实执行
* 撤单
* 平仓
* retry protection
* runtime start
* auto execution
* 修改 PG 状态
* 自行调用旧 action API
