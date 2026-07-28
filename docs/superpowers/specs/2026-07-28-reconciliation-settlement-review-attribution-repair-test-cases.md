---
title: Reconciliation Settlement, Order Attribution and BNB Fee Repair Test Cases
status: OWNER_REVIEW_REQUIRED
authority: NOT_CURRENT_AUTHORITY
date: 2026-07-28
design: 2026-07-28-reconciliation-settlement-review-attribution-repair-design.md
plan: ../plans/2026-07-28-reconciliation-settlement-review-attribution-repair.md
---

# Reconciliation Settlement, Order Attribution and BNB Fee Repair Test Cases

## 当前状态

本文档只定义 **待实现测试规格**。当前没有创建或修改任何
`tests/**/*.py`，下列用例均未运行、未通过。

Owner 确认设计、实施计划和本测试规格后，实施必须先让相应用例因缺失行为
产生预期 RED，再修改生产代码。不能先写实现，再补一个只覆盖 happy path 的
测试。

## 测试目标

测试共同证明：

1. 多个活跃 Ticket 不能无限阻塞 Settlement/Review。
2. Binance 成交只按 exact `trade.orderId` 归因。
3. 条件订单先解析 `algoId/clientAlgoId -> actualOrderId`。
4. Lifecycle、Unknown recovery、Review 使用同一订单身份组件。
5. BTC-like pending Ticket 通过正常 Event/Reducer/UoW 生成完整 Review。
6. 初始止损和 runner 始终为 STOP_MARKET。
7. TP1 始终为 LIMIT + GTX，Maker 拒绝不退化为 taker。
8. USDT 与 BNB 原生手续费均保留，并使用可复算证据汇总为 USDT。
9. BNB 不进入保证金、仓位预算或风险事实。
10. 程序没有购买、划转、fee burn 变更或 BNB margin 写能力。
11. closure-only handover 只能接管 exact 已平 pending Ticket，且 Entry 保持
    inactive/disabled/fenced。
12. 整个 P1 修复不修改 schema、不引入第五 Worker或平行记账链。

## 测试层级与证据

| 层级 | 主要证明 | 允许替身 | 不足以单独证明 |
| --- | --- | --- | --- |
| **Unit** | frozen model、调度决策、parser、估值、命令不变量 | typed fixture、fake timestamp | PostgreSQL 锁与生产链 |
| **PostgreSQL Integration** | selector、UoW、command lineage、Review 原子性 | recording Venue | Binance 真实字段合同 |
| **Adapter Contract** | Binance request/response namespace 和调用上界 | 官方形状 recording client | Ticket 全生命周期 |
| **Worker Integration** | cadence、重试、Monitor、网络事务边界 | recording adapter | 完整 Producer/Reducer 链 |
| **Full Chain** | 多 Ticket、订单、费用、Settlement、Review 闭环 | fake exchange truth | Tokyo action-time 状态 |
| **Deployment Test** | closure manifest、互斥 CLI、Entry fence、失败恢复 | fake systemd/SSH/process | 实际 Tokyo 部署 |
| **Architecture/Static** | 禁用依赖、无 fallback、无 BTC 特例、无 BNB 写口 | source/AST/import scan | 运行时性能 |
| **Performance Acceptance** | 查询计划、API 数量、page/window 上界 | counting client、EXPLAIN | 策略收益 |

## 测试纪律

1. Financial values 全部使用 `Decimal`。
2. 核心 fixture 使用 frozen named model，不用自由 dict 穿过 application
   boundary。
3. Binance raw fixture 只存在于 infrastructure/adapter contract 测试。
4. Account Trade fixture 默认**不包含 `clientOrderId`**。
5. PostgreSQL 行为使用 disposable PostgreSQL，不以 SQLite 代替。
6. 本地测试禁止真实交易所写；所有 mutation 使用 recording fake。
7. Full-chain 从正式 Command/Event producer 进入，不直写 Signal、Ticket、
   Review 或 terminal status。
8. 每个测试同时断言预期状态和禁止副作用。
9. 网络失败测试断言 transaction 已关闭。
10. 时间边界使用注入的 epoch milliseconds，不依赖 wall clock sleep。
11. 性能使用调用次数、row count 和 query plan，不用抖动的毫秒基准冒充
    结构证明。
12. 所有 closure deploy 测试都断言 Entry 没有被 enable/start。

## 计划测试文件

| 文件 | 层级 | 覆盖范围 |
| --- | --- | --- |
| `unit/test_order_attribution.py` | Unit | reference、resolved identity、fill、digest |
| `unit/test_fee_valuation.py` | Unit | native fee 和纯估值不变量 |
| `unit/test_binance_order_attribution.py` | Adapter | regular/algo/orderId/tradeId |
| `unit/test_binance_fee_valuation.py` | Adapter | BNBUSDT Review index snapshot |
| `unit/test_commands.py` | Unit | order type 与 TIF |
| `unit/test_reconciliation_worker_fairness.py` | Unit | age-aware 调度 |
| `unit/test_reconciliation_worker_review.py` | Unit | Review 请求与失败语义 |
| `unit/test_venue_adapter.py` | Adapter | GTX、exact query、safe payload |
| `integration/test_reconciliation_work_selector.py` | PostgreSQL | 并发选择和索引 |
| `integration/test_order_attribution_repository.py` | PostgreSQL | exact command facts |
| `integration/test_ticket_lifecycle_maintenance.py` | Worker | entry fee 与 runner |
| `integration/test_unknown_outcome_reconciliation.py` | Worker | unknown exact fill |
| `integration/test_bnb_fee_capability_monitor.py` | Worker | feeBurn/balance Monitor |
| `integration/test_closure_only_certification.py` | Deployment | exact flat closure |
| `full_chain/test_multi_ticket_closure_fairness.py` | Full Chain | 多 Ticket 不饥饿 |
| `full_chain/test_binance_actual_order_review.py` | Full Chain | BTC-like complete Review |
| `architecture/test_order_attribution_architecture.py` | Static | 单一 resolver、无旧 filter |
| `architecture/test_bnb_fee_authority.py` | Static | BNB 非资本、无写能力 |
| `architecture/test_closure_handover_architecture.py` | Static | 无第五 Worker、Entry fence |

## A. 调度领域与 Worker 公平性

| ID | 场景 / 动作 | 必须断言 | 禁止副作用 |
| --- | --- | --- | --- |
| SCH-001 | 只有一个 due position | 选择 POSITION | 不查询 Review facts |
| SCH-002 | 只有一个 due Settlement | 选择 SETTLEMENT | 不查询 position |
| SCH-003 | 只有一个 due Review | 选择 REVIEW | 不查询 position |
| SCH-004 | position 与等待 10 秒 closure 同时 due | 选择 position | closure age 不重置 |
| SCH-005 | position 与等待 29,999ms closure 同时 due | 选择 position | 不提前抢占 |
| SCH-006 | position 与等待 30,000ms closure 同时 due | 选择最老 closure | 本轮不再处理 position |
| SCH-007 | position 与等待 31 秒 closure 同时 due | 选择最老 closure | 不按 Ticket id 偏置 |
| SCH-008 | Settlement 与 Review 同时 overdue | 选择 status-entered 最老者 | 不固定 Settlement-first |
| SCH-009 | 两条 closure age 相同 | stable tie-breaker 生效 | 不依赖物理行顺序 |
| SCH-010 | closure 未到 retry due | 忽略 closure | 不发 Binance 请求 |
| SCH-011 | Review retry due | 恢复 eligible 且保留原 age | 不改 Aggregate status |
| SCH-012 | unknown 得到 terminal decision | 只处理 unknown 并返回 | 不同轮写两个 Aggregate |
| SCH-013 | unknown visibility pending + overdue closure | closure 获得选择 | unknown 不被误终态 |
| SCH-014 | position facts timeout | 下轮可重试 | 不推进 Settlement |
| SCH-015 | Review facts timeout | 设置 30 秒 retry | 不每 5 秒忙循环 |
| SCH-016 | 100 次 position 持续 due + 1 closure | closure 在 SLO 内被选择 | closure 不等到 position 清零 |
| SCH-017 | 一个 Review 持续失败 + positions due | positions 仍获得 cadence | Review 不垄断 Worker |
| SCH-018 | no work | 返回 NO_WORK/pending unknown 语义 | 不写 Monitor 噪声 |

## B. PostgreSQL selector 与并发

| ID | 场景 / 动作 | 必须断言 | 禁止副作用 |
| --- | --- | --- | --- |
| SCH-PG-001 | 两 connection 并发 select | 各自锁定不同 work item | 不重复处理同 Ticket |
| SCH-PG-002 | 最老 closure row 已锁 | SKIP LOCKED 选择下一 eligible | 不阻塞 cadence |
| SCH-PG-003 | terminal Ticket 更老 | 不进入候选 | 不扫描其 events |
| SCH-PG-004 | closure due_at null | 使用 status entered/update time | 不永远遗漏 |
| SCH-PG-005 | schedule next check | retry due 更新，status age 保留 | 不丢 aging |
| SCH-PG-006 | status 在 select 后并发改变 | optimistic version 阻止错误提交 | 不覆盖新状态 |
| SCH-PG-007 | 10,000 terminal + 3 active rows | EXPLAIN 使用 active/due path | 不顺序扫历史 |
| SCH-PG-008 | selector 返回模型 | frozen typed item 完整 | 不返回 ORM/raw tuple |

## C. 订单身份领域不变量

| ID | 场景 / 动作 | 必须断言 | 禁止副作用 |
| --- | --- | --- | --- |
| OID-DOM-001 | accepted regular ENTRY | namespace regular、role entry | 不猜 conditional |
| OID-DOM-002 | accepted LIMIT TP1 | namespace regular、role exit | 不由 trade side 猜 role |
| OID-DOM-003 | accepted STOP_MARKET runner | namespace conditional | 不把 algo id 当 order id |
| OID-DOM-004 | 空 submitted id | validation error | 不产生 reference |
| OID-DOM-005 | Cancel command | 无法构造成 fill reference | 不进入 Review |
| OID-DOM-006 | SetLeverage command | 同上 | 不进入 Review |
| OID-DOM-007 | regular actual id 等于 submitted id | executable identity 成功 | 不调用 algo resolver |
| OID-DOM-008 | regular actual id 不同 | fail closed | 不 fallback 到新 id |
| OID-DOM-009 | conditional 未触发且 terminal canceled | not_triggered | 不生成零值假 fill |
| OID-DOM-010 | conditional triggered + actual id | executable identity 成功 | 不保留歧义 |
| OID-DOM-011 | triggered 但 actual id 空 | validation error | 不查询全账户 trades |
| OID-DOM-012 | fill order id 与 resolved id 一致 | attribution 成功 | 不读 client id |
| OID-DOM-013 | fill order id 不一致 | fail closed | 不模糊匹配 |
| OID-DOM-014 | entry/exit role 不一致 | fail closed | 不重新分类 |
| OID-DOM-015 | same trade id + same content duplicate | 幂等去重 | 不双算数量/费用 |
| OID-DOM-016 | same trade id + conflicting content | fail closed | 不取第一条掩盖冲突 |
| OID-DOM-017 | 同一 fills 不同输入顺序 | digest 相同 | 不把 API 顺序当语义 |
| OID-DOM-018 | price/qty/fee 改变 | digest 改变 | 不产生碰撞式同摘要 |

## D. PostgreSQL Command lineage

| ID | 场景 / 动作 | 必须断言 | 禁止副作用 |
| --- | --- | --- | --- |
| OID-PG-001 | accepted regular command | exact order reference 完整 | 不查其他 Ticket |
| OID-PG-002 | reconciled-accepted unknown command | 同样进入 references | 不要求重新 submit |
| OID-PG-003 | authoritative rejected command | 不进入 executable set | 不查询 trades |
| OID-PG-004 | unresolved unknown command | facts unavailable/阻塞 Review | 不猜 accepted |
| OID-PG-005 | accepted result 缺 exchange id | typed parse failure | 不回退 client id |
| OID-PG-006 | payload/result command id 冲突 | fail closed + Incident path | 不继续 Review |
| OID-PG-007 | Ticket 有多个 exit generations | 只读取合法 immutable lineage | 不把 cancel 当 fill |
| OID-PG-008 | exact Ticket query | bounded command rows | 不全表扫描 |

## E. Binance regular、algo 与 trade 归因

| ID | 场景 / 动作 | 必须断言 | 禁止副作用 |
| --- | --- | --- | --- |
| BIN-OID-001 | regular order accepted | 使用 symbol+orderId 查 trades | 不要求 clientOrderId |
| BIN-OID-002 | trade row 无 clientOrderId | 正常解析 | 不丢弃真实 fill |
| BIN-OID-003 | trade row orderId 不同 | fail closed | 不接纳同 symbol 其他成交 |
| BIN-OID-004 | trade row symbol 不同 | fail closed | 不跨标的归因 |
| BIN-OID-005 | trade row positionSide 不同 | fail closed | 不跨 Netting Domain |
| BIN-OID-006 | trade time 在 exposure window 外 | fail closed | 不吸收历史成交 |
| BIN-OID-007 | algo query 按 algoId 返回 clientAlgoId | 两者均核对 | 不做字符串 contains |
| BIN-OID-008 | BTC-like algo 返回 actualOrderId | 用 1085699838084 查 trade | 不用 algoId 查 trade |
| BIN-OID-009 | algo terminal canceled、actual id 空 | not_triggered | 不查 Account Trade |
| BIN-OID-010 | algo open、actual id 空 | facts pending | 不声明 not-triggered terminal |
| BIN-OID-011 | algo actualQty>0、actual id 空 | contradiction | 不构造合成 order id |
| BIN-OID-012 | algo symbol/side/positionSide 冲突 | fail closed | 不接受 payload 漂移 |
| BIN-OID-013 | userTrades 多个 partial fills | 全部累加并保留各 tradeId | 不只取最后一条 |
| BIN-OID-014 | API 返回重复同 row | 去重后数量不变 | 不双算 |
| BIN-OID-015 | 恰好 1000 rows 但数量已证明完整 | 接受完整集 | 不继续无界翻页 |
| BIN-OID-016 | 恰好 1000 rows 且数量不完整 | facts unavailable | 不静默截断 |
| BIN-OID-017 | safe accepted response | 保留 allowlist 字段 | 不落未知/敏感字段 |
| BIN-OID-018 | Binance timeout | typed temporary unavailable | DB transaction 已关闭 |

## F. 原生手续费与 BNBUSDT 估值

| ID | 场景 / 动作 | 必须断言 | 禁止副作用 |
| --- | --- | --- | --- |
| FEE-DOM-001 | USDT fee 0.25 | native 保存 USDT/0.25；USDT value 0.25 | 不查价格 |
| FEE-DOM-002 | BNB fee 0.001 + valid rate 600 | USDT value 0.600 | 不改变 native amount |
| FEE-DOM-003 | fee amount 0 | 合法零 native fee 且有 asset | 不把缺失解析成 0 |
| FEE-DOM-004 | fee amount 负数 | validation error | 不取绝对值 |
| FEE-DOM-005 | 未知 asset | facts unavailable/unsupported | 不按 USDT 处理 |
| FEE-DOM-006 | rate 0/负数 | validation error | 不生成 ValuedFee |
| FEE-DOM-007 | evidence 缺 pair/observed time | BNB valuation 拒绝 | 不只保存 rate |
| FEE-DOM-008 | USDT evidence 带 BNB snapshot fields | validation error | 不混用方法 |
| FEE-BNB-001 | Review 含一个或多个 BNB fill | 只读一次 BNBUSDT index snapshot | 不逐 fill 请求 |
| FEE-BNB-002 | Review 没有 BNB fill | 不调用 BNBUSDT API | 不制造无关网络 I/O |
| FEE-BNB-003 | snapshot price 非正数 | facts unavailable | 不按 0 计价 |
| FEE-BNB-004 | snapshot observed time 无效 | facts unavailable | 不伪造时间 |
| FEE-BNB-005 | snapshot API 空/失败 | Review economics unavailable | 不以 fee=0 完成 |
| FEE-BNB-006 | Ticket 混合 USDT/BNB fees | USDT 固定 1，BNB 共用快照后汇总 | 不统一假成一种 asset |
| FEE-BNB-007 | 冻结 Review evidence | 保存 method/rate/pair/observed time | 不声称成交时刻历史汇率 |

## G. 退出订单与 TP1 Maker-only

| ID | 场景 / 动作 | 必须断言 | 禁止副作用 |
| --- | --- | --- | --- |
| ORD-TIF-001 | 生成初始止损 | STOP_MARKET、TIF null | 不生成 LIMIT |
| ORD-TIF-002 | 生成 TP1 | LIMIT、GTX、price/qty 完整 | 不用 GTC |
| ORD-TIF-003 | 生成 runner replacement | STOP_MARKET、TIF null | 不携带 GTX |
| ORD-TIF-004 | LIMIT 缺 TIF | validation error | 不默认 GTC |
| ORD-TIF-005 | STOP_MARKET 带 GTX | validation error | 不吞掉字段 |
| ORD-TIF-006 | TP1 payload round-trip | GTX 保持且 digest 稳定 | 不丢语义 |
| ORD-TIF-007 | Adapter 提交 TP1 | Binance params 含 timeInForce=GTX | 不含 post-only 猜测参数 |
| ORD-TIF-008 | accepted readback | type/origType/TIF 全部匹配 | 不只看 status |
| ORD-TIF-009 | GTX 因 marketable rejected | command terminal rejected + Incident | 不重发 GTC |
| ORD-TIF-010 | GTX rejected 后检查 commands | 只有原 generation | 不生成 MARKET |
| ORD-TIF-011 | GTX rejected 后检查保护 | 初始 STOP_MARKET 仍存在且精确 | 不取消保护 |
| ORD-TIF-012 | GTX outcome unknown | 进入 exact unknown recovery | 不按 rejected 处理 |
| ORD-TIF-013 | runner replacement | 先确认新 STOP 再撤旧语义保持 | 不受 GTX 分支影响 |
| ORD-TIF-014 | scan 所有 TP1 producer | 全部 LIMIT+GTX | 不存在第二 producer |

## H. Lifecycle、Unknown 与 Review 消费者

| ID | 场景 / 动作 | 必须断言 | 禁止副作用 |
| --- | --- | --- | --- |
| CON-LIF-001 | entry regular fills + USDT fee | exact entry fee 进入 facts | 不按 client id filter |
| CON-LIF-002 | entry fills + BNB fee | Lifecycle 不读取 BNB price，runner 仍用非折扣 taker 上界 | 不把 BNB 数量当 USDT |
| CON-LIF-003 | BNB snapshot 不可用 | Lifecycle 仍可按风险上界推进 | 不以 BNB 估值阻塞保护 |
| CON-LIF-004 | 未来 runner fee | 使用非折扣 taker 上界 | 不依赖 BNB balance |
| CON-LIF-005 | TP1 GTX rejected | 保留初始 stop + Incident | 不提前创建 runner |
| CON-UNK-001 | regular unknown 可见 | 解析 exact orderId 和 fills | 不重发 entry |
| CON-UNK-002 | conditional unknown 可见 | algo -> actualOrderId -> fills | 不以 algoId 累计 |
| CON-UNK-003 | same symbol 其他 order fill | matching qty 不增加 | 不误判 accepted |
| CON-UNK-004 | visibility deadline 未到 | pending | 不 terminal reject |
| CON-UNK-005 | identity contradiction | Incident/fail closed | 不释放 lane |
| CON-REV-001 | regular entry + TP1 + runner | roles 来自 commands | 不由 trade side 猜测 |
| CON-REV-002 | Account Trade 无 clientOrderId | 完整 Review | 不丢 fills |
| CON-REV-003 | entry quantity 不完整 | economics unavailable | 不写 complete Review |
| CON-REV-004 | exit quantity 不完整 | economics unavailable | 不写 terminal |
| CON-REV-005 | funding unavailable 但 fills 完整 | 使用既有 funding 语义 | 不伪造 funding=0 |
| CON-REV-006 | attribution digest 重试 | 同 facts 同 digest | 不重复 Review |
| CON-REV-007 | Review insert 与 ReviewRecorded | 同一事务原子完成 | 不留 orphan Review |
| CON-REV-008 | 并发两次 Review | optimistic/unique 收敛一次 | 不双写 |

## I. BNB 能力、资本隔离与禁用 API

| ID | 场景 / 动作 | 必须断言 | 禁止副作用 |
| --- | --- | --- | --- |
| BNB-CAP-001 | feeBurn true + balance positive | Monitor available | 不修改 feeBurn |
| BNB-CAP-002 | feeBurn false | warning/owner intervention | 不 POST 开启 |
| BNB-CAP-003 | balance 0 | unavailable/low balance warning | 不购买或划转 |
| BNB-CAP-004 | balance 低于阈值 | low_balance | 不阻止 Entry |
| BNB-CAP-005 | 阈值未配置 | unknown/无 low 判定 | 不使用代码默认金额 |
| BNB-CAP-006 | feeBurn API timeout | unknown + bounded retry | 不变成 safety failure |
| BNB-CAP-007 | 相同 facts 重复 cadence | Monitor 幂等 | 不追加噪声行 |
| BNB-CAP-008 | BNB 余额增加 | Monitor 更新 observation | 不推断转入来源 |
| BNB-CAP-009 | BNB 余额下降 | Monitor 更新/提醒 | 不自动补充 |
| BNB-CAP-010 | BNB 不足后 Binance 扣 USDT | Review 正常支持混合 asset | 不阻塞结算 |
| BNB-ISO-001 | OwnerCapitalFacts 构造 | 只含 USDT 资本权威 | 不加 BNB USDT value |
| BNB-ISO-002 | sizing 输入有 BNB balance | position qty 与无 BNB 时相同 | 不扩大仓位 |
| BNB-ISO-003 | CapacityClaim | 不读取 BNB | 不增加容量 |
| BNB-ISO-004 | liquidation evidence | 保持现有 positionRisk/account 语义 | 不用 BNB 补证据 |
| BNB-ISO-005 | dependency/source scan | 无 transfer/purchase/convert/feeBurn POST | 不存在隐藏 client method |
| BNB-ISO-006 | recording Venue 调用审计 | 新能力调用全为 readonly | exchange write count 为 0 |

## J. Closure-only handover

| ID | 场景 / 动作 | 必须断言 | 禁止副作用 |
| --- | --- | --- | --- |
| HND-001 | exact Settlement pending、flat、全释放 | certification pass | 不改 Ticket |
| HND-002 | exact Review pending、flat、全释放 | certification pass | 不写 Review |
| HND-003 | Ticket id 缺失/通配 | CLI 拒绝 | 不选择所有 pending |
| HND-004 | 重复 Ticket id | CLI 拒绝 | 不自动去重后继续 |
| HND-005 | closure + protected mode | 参数互斥拒绝 | 不猜模式 |
| HND-006 | closure + enable-entry | 参数互斥拒绝 | Entry 不 start |
| HND-007 | schema revision 变化 | fail closed | 不迁移 |
| HND-008 | active position 非零 | fail closed | 不走 closure |
| HND-009 | regular/conditional order residue | fail closed | 不取消订单 |
| HND-010 | unresolved command | fail closed | 不重发 |
| HND-011 | open Incident | fail closed | 不自动 close |
| HND-012 | budget/capacity/netting 未释放 | fail closed | 不强制 release |
| HND-013 | Ticket 已 terminal complete | no-op/不符合 closure | 不重开 |
| HND-014 | Ticket 已 terminal incomplete | fail closed + correction required | 不覆盖 Review |
| HND-015 | preflight 后状态漂移 | stop-workers 后 recheck 捕获 | 不 rotate identity |
| HND-016 | identity rotation 前失败 | 旧 identity 可恢复 safety workers | Entry 仍 fenced |
| HND-017 | identity rotation 后失败 | 只允许 target identity workers | 不启动旧 writer |
| HND-018 | postflight | safety workers active，Entry inactive/disabled/fenced | 不自动恢复 Entry |
| HND-019 | 全部 Ticket 后续 terminal/flat | 仍不自动 enable Entry | policy true 不启动服务 |
| HND-020 | BNB capability unavailable | closure certification 仍可通过 | 不把成本 warning 当安全门 |

## K. BTC-like 正常事件回放与多 Ticket Full Chain

| ID | 场景 / 动作 | 必须断言 | 禁止副作用 |
| --- | --- | --- | --- |
| BTC-FC-001 | BTC-like 从 Settlement pending 开始 | 唯一 BudgetSettled | 不跳过 Reducer |
| BTC-FC-002 | 随后进入 Review | exact commands/references 完整 | 不手工输入 order id |
| BTC-FC-003 | runner algo fixture | 解析 actualOrderId 1085699838084 | 不产生 BTC 代码分支 |
| BTC-FC-004 | runner Account Trade 无 clientOrderId | exit fill 被精确接受 | 不丢真实成交 |
| BTC-FC-005 | Review 计算 | gross/net/R/native fees 可复算 | 不以 exchange realized PnL 替代公式 |
| BTC-FC-006 | Review 写入 | 唯一 ReviewRecorded -> terminal | 不 UPDATE terminal |
| BTC-FC-007 | 同时有 SOL-like/AVAX-like due positions | BTC closure 在边界内推进 | 不停止保护 cadence |
| BTC-FC-008 | BTC Review 一次临时超时 | 30 秒后正常重试完成 | 不阻塞其他 Ticket |
| BTC-FC-009 | BTC fee 是 BNB | 保存 native + index evidence | 不以 BNB amount 当 USDT |
| BTC-FC-010 | BTC fee facts 缺失 | 保持 Review pending/unavailable | 不伪造完整 Review |
| BTC-FC-011 | terminal projections | ticket/command/incident/budget/capacity/netting 全闭合 | 不留占用 |
| BTC-FC-012 | 重新运行 worker | 幂等 no-op | 不产生第二 Review |

## L. Entry 启动、发布顺序与人工 BNB 边界

| ID | 场景 / 动作 | 必须断言 | 禁止副作用 |
| --- | --- | --- | --- |
| SVC-001 | P1 closure deploy 成功 | Entry inactive/disabled/fenced | policy true 不启动 |
| SVC-002 | BTC terminal/全平 | Entry 仍不启动 | Settlement 不触发 systemd |
| SVC-003 | 无 `--enable-entry` 正式部署 | Entry 保持 disabled | 不隐式恢复 |
| SVC-004 | 所有正式门通过且显式 enable | safety services 先、Entry 最后 | 不提前接收信号 |
| SVC-005 | BNB 支持版本部署前 balance=0 | 部署不自动转入 | exchange transfer writes=0 |
| SVC-006 | 模拟 Owner 部署后外部转入 | 只读 facts/Monitor 更新 | 程序不归因谁转入 |
| SVC-007 | feeBurn false | 代理汇报 Owner intervention | 程序不自动开启 |
| SVC-008 | BNB low balance | warning only | 不影响 STOP/runner/Entry |

## M. 性能、架构与静态门

| ID | 场景 / 动作 | 必须断言 | 禁止副作用 |
| --- | --- | --- | --- |
| PERF-001 | 单 cadence | 最多 1 normal work item | 不做 position+Review 双网络链 |
| PERF-002 | exact Ticket 20 commands | 只读该 Ticket rows | 不扫全 command 表 |
| PERF-003 | 10 fills 同一分钟 | 1 index-kline request | 不逐 fill 重复 |
| PERF-004 | 3 order ids | 每 id 有界 trade query | 不抓全账户历史 |
| PERF-005 | Review retry failure | 30 秒调用上界 | 不按 5 秒 busy loop |
| PERF-006 | closure selector EXPLAIN | index/limit 路径 | 不扫 terminal history |
| ARCH-001 | production source scan | 无 `trade.clientOrderId` fill filter | 不保留旧 helper |
| ARCH-002 | import graph | 三消费者依赖同一 resolver port | 不复制 parser |
| ARCH-003 | fee source scan | native fee model 为唯一入口 | 不散落 BNB if 分支 |
| ARCH-004 | command producer scan | TP1 全部 GTX | 不存在 GTC fallback |
| ARCH-005 | protection scan | stop/runner 全部 STOP_MARKET | 不转 LIMIT |
| ARCH-006 | API capability scan | 无 BNB 写接口 | 不以未调用为借口保留能力 |
| ARCH-007 | runtime dependency scan | BNB 不流入 capital/sizing | 不做隐式换算 |
| ARCH-008 | service inventory | 仍为四个 Worker | 不新增 Settlement daemon |
| ARCH-009 | migration inventory | Alembic head 未改变 | 不夹带 0002 |
| ARCH-010 | source scan | 无 BTC id/symbol 常量 | 不建特殊恢复分支 |
| ARCH-011 | runtime file audit | no-signal cadence 零 JSON/Markdown | 不写 proof file |
| ARCH-012 | transaction recording | Binance I/O 时 DB transaction 关闭 | 不持锁联网 |

## N. 故障恢复矩阵

| 故障点 | 预期恢复 | 数据不变量 | 交易安全不变量 |
| --- | --- | --- | --- |
| selector transaction rollback | 下轮重新选择 | Aggregate version 不变 | 无 exchange write |
| regular order lookup timeout | facts unavailable/retry | command 不改写 | unknown 不重发 |
| algo query timeout | facts unavailable/retry | algo identity 保留 | 不猜 actual order |
| trade query partial page | Review pending | 无 partial complete Review | 不影响保护单 |
| BNB index timeout | valuation unavailable | native fee 保留 | 不降低 runner cost |
| GTX authoritative reject | terminal reject + Incident | 只有一个 generation | STOP_MARKET 保留 |
| GTX unknown outcome | unknown recovery | command outcome 未伪造 | 不重发 |
| Review insert crash | UoW rollback | 无 orphan Review/event | Ticket 可重试 |
| closure preflight 后漂移 | second check 拒绝 | runtime identity 不旋转 | Entry fenced |
| closure rotation 后 service fail | target-only recovery | 不启旧 writer | Entry fenced |

## O. 本地总验收命令类别

实现阶段应按当前仓库工具链填写并执行 exact commands，至少覆盖：

1. focused Unit；
2. disposable PostgreSQL Integration；
3. Worker Integration；
4. Full Chain；
5. Deployment script Unit/Integration；
6. Architecture/Static；
7. 完整 Trading Kernel pytest；
8. Ruff；
9. Mypy；
10. runtime file-I/O audit；
11. migration head identity；
12. `git diff --check`。

最终验收报告必须列出每个命令、exit code、通过/失败数量和未运行项。不能只写
“测试通过”。

## 测试完成门

以下任一项未证明，都不得声明实现完成：

1. **调度边界**：活跃 positions 存在时 closure 仍有界推进。
2. **真实协议**：userTrades fixture 不含 clientOrderId。
3. **条件订单**：actualOrderId 是唯一 trade.orderId 桥。
4. **三消费者**：Lifecycle、Unknown、Review 同时迁移。
5. **退出语义**：STOP_MARKET/GTX 矩阵和拒绝恢复完整。
6. **费用语义**：USDT、BNB、mixed、Review snapshot missing/invalid 全覆盖。
7. **资本隔离**：BNB 不改变仓位数量和风险预算。
8. **禁止能力**：自动购买、划转、fee burn 变更和 BNB margin 不存在。
9. **BTC 回放**：正常事件链产生唯一完整 Review。
10. **发布门**：closure-only 不迁移 schema、不启用 Entry。
11. **回归范围**：完整套件、静态门和性能边界全部通过。
12. **生产边界**：测试未写 Tokyo、未写真实交易所、未转入 BNB。
