---
title: TRADFI_SOR_M5_OBSERVATION_DESIGN
status: OWNER_APPROVED_FOR_IMPLEMENTATION
date: 2026-08-11
---

# TradFi SOR M5 Observation / Shadow 设计

## 2026-08-12 M6 决策补充

Owner 已明确 **M6 上线即开启小额真实交易**，不以 Observation 天数、样本数或人工
go/hold/stop 结论作为 Entry 解锁门槛。本文件继续拥有 M5 Observation 的数据、路径和
展示语义；M6 上线状态机、StrategyGroup pause 和真实资金边界由
`docs/superpowers/specs/2026-08-12-tradfi-sor-m6-live-entry-design.md` 取代此前可能被理解为
“先观察后交易”的阶段解释。

## Owner 解释与设计结论

Owner 对 M5 的解释被采纳：Observation 不舍弃实盘交易能力，只暂停新
TradFi Ticket 的生产准入。`SOR-US-EQ-PERP-001` 继续使用同一条正式链：

```text
Product / Session readonly facts
-> StrategySignal
-> Observation Outcome
-> M6 时恢复 Readiness / Authority
-> CapacityClaim
-> immutable Ticket
-> durable Exchange Command
-> protected lifecycle
```

Observation Outcome 是 Signal 的只读市场路径证据，不是模拟 Ticket、虚拟订单、
CapacityClaim 或第二执行链。未来真实 Ticket 可以与同一 Signal 的 Observation
Outcome 并存，二者分别表达“当时可观察到的策略路径”和“真实执行结果”。

## 问题

M2-M4 已能表达 TradFi Product、Universe、Regular Session 和标准 Signal，但当前
Shadow Outcome 只覆盖少数已进入 Admission 后被组合容量拒绝的 Signal。TradFi
Policy 关闭 Entry 时不会进入 Admission，因此不能形成 M5 路径证据。

当前 Product/Session 投影也只由 Owner API 手动刷新。正式 Observation 若依赖该
手动动作，将无法稳定在每个闭合 15m Bar 上获得 Session 与报价事实。

## 用户价值

1. Owner 可按 StrategyVersion、方向、标的和 Session 时间观察美股 SOR 的路径质量；
2. 不用真实资金即可判断 TP1、Initial Stop、Opening Range Failure 和 Time Stop；
3. M6 开放真实 Entry 后，可直接比较观察路径与真实 Ticket/成交质量；
4. 2C4G 主机只处理闭合 Bar 和有界当前投影，不建设高频行情仓库。

## 权威与身份

| 事实 | 唯一权威 |
| --- | --- |
| StrategyVersion、Event、ExitPolicy | Strategy Registry |
| 标的成员与版本 | PostgreSQL StrategyUniverse |
| Signal 与冻结 Fact | PostgreSQL Signal/Event authority |
| Product、Session、Spread、Top-of-book | PostgreSQL current projection，来源为 Binance readonly public facts |
| Observation Outcome | PostgreSQL Shadow Outcome current projection |
| Ticket、Command 和真实成交 | 正式 Kernel 与 Exchange truth |

每个 Signal 最多拥有一个 Shadow Outcome。既有 Crypto portfolio-rejection Shadow
保留原语义；M5 新增 `strategy_observation` 来源，使 Shadow 由 `signal_event_id`
直接拥有，`admission_decision_id` 仅在 portfolio-rejection 情况下存在。

## Observation 生成

1. Observation Worker 在网络 I/O 阶段按完整 TradFi Universe 批量读取 Product、
   Trading Schedule、Premium Index 和 Top-of-book；
2. 同一闭合 Bar 的相同成员集使用进程内有界缓存，避免 LONG/SHORT Scope 重复读取；
3. 网络读取结束后用短 PostgreSQL 事务更新 current Product projection；
4. Detector 使用同一批冻结 Product/Session 事实形成 StrategySignal；
5. Signal 成功持久化时，同事务幂等创建一个 `strategy_observation` Shadow Spec；
6. Observation Worker 在 Horizon 到期后读取精确闭合 K 线并完成路径投影。

## 冻结观察计划

M5 对每个美股 SOR Signal 冻结：

- Signal、StrategyVersion、Universe、Event、instrument 和 side；
- Trigger quote：LONG 使用 best ask，SHORT 使用 best bid；
- Initial Stop；
- TP1 = 1R；
- Opening Range failure boundary；
- Regular Session open、exit deadline；
- Mark、Index、Funding、best bid/ask 与 Top-of-book quantity；
- Horizon：最多 8 根闭合 15m Bar，且不超过 Session exit deadline。

缺失有效报价、Stop、Opening Range 或 Session deadline 时，Signal 仍保留，但
Observation Outcome 明确进入 `unavailable`，不得用 Trigger close 静默替代报价。

## 路径评价

路径按闭合 15m K 线计算，不推断同一根 K 线内部的未知先后顺序：

| Path | 定义 |
| --- | --- |
| `tp1_first` | TP1 在 Initial Stop 前首次触达 |
| `initial_stop_first` | Initial Stop 在 TP1 前首次触达 |
| `ambiguous_same_bar` | 同一根 K 线同时覆盖 TP1 与 Initial Stop |
| `opening_range_failure` | TP1/Stop 均未触发，闭合价回到 Opening Range 内 |
| `time_stop` | TP1 前完成 8 根闭合 Bar |
| `session_exit` | 先到 Regular Session exit deadline |
| `horizon_complete` | Horizon 完整但没有更具体路径 |

每个完成 Outcome 同时记录固定 Horizon 的 MFE R、MAE R、路径首次发生时间、
Spread bps 和 Mark/Index deviation bps。M5 不计算净收益、不模拟手续费、不把报价
摩擦称为真实 Slippage。真实 Entry/Exit Slippage 只由 M6 Ticket 和成交事实拥有。

## Owner Console

StrategyVersion 摘要增加 Observation 样本数、完成数、TP1-first、Stop-first、
Failure、Ambiguous、Median MFE/MAE 与 Median Spread。

策略页的 Observation 按钮打开有界弹窗：

- 支持按 Path 读取当前 StrategyVersion 样本；
- 每行显示 instrument、side、Signal time、Path、MFE/MAE 和 Spread；
- 点击样本打开完整观察详情，展示 15m K 线与 Entry、Stop、TP1、Opening Range；
- 浏览器路由保存 StrategyVersion、时间范围、Path、cursor 和返回位置；
- 若同一 Signal 已形成真实 Ticket，显示 Ticket 链接；否则明确标记 Observation only。

Signal 页面允许 `not_evaluated`：它表示 Signal 已形成但 Entry Admission 因 M5
观察模式未运行，不得伪造 AdmissionDecision。

## 性能

- 不新增 Worker 或 systemd service；
- 每个闭合 15m Bar 最多一次相同 Universe Product 批量读取；
- Depth 只保留 Top-of-book price/quantity，不保存完整订单簿；
- Shadow due selector、StrategyVersion 列表和样本详情全部使用有界 keyset 查询；
- 无 Signal/无 due Shadow 的 cadence 不创建文件；
- 前端继续手动刷新。

## 实盘演进

M6 不删除或替换 M5：

1. Owner 在 M6 R4 部署包中批准方向和 Universe；资本完整复用统一的
   `policy-main / Policy v4`，不增加 TradFi 专属参数；
2. `new_entry_submit_enabled` 与 Strategy Control 恢复后，同一 StrategySignal 进入
   正式 Admission；
3. CapacityClaim、Ticket 和 Command 仍由既有 Kernel 生成；
4. Observation Outcome 继续完成，只作为真实 Ticket 的对照证据；
5. 真实成交、Fees、Funding、Slippage、Settlement 和 Review 只来自 Ticket 链。

M6 认证完成后不增加 Observation 等待期；StrategyGroup resume 即允许后续新鲜 Signal
参与正式准入。

## 验收标准

1. TradFi SOR Signal 在 Entry 禁用时创建一个 Signal-owned Observation Outcome；
2. Outcome 创建不产生 AdmissionDecision、CapacityClaim、Ticket 或 Exchange Command；
3. 同一 Signal 重放不会创建第二个 Outcome；
4. TP1、Stop、同 Bar 歧义、Opening Range failure、Time Stop 和 Session exit 的
   纯领域评价有直接测试；
5. Product facts 由 Observation Worker 自动批量刷新，网络 I/O 不在事务内；
6. Existing portfolio-rejection Shadow 数据在 `0004 -> 0005` 后保留并能继续完成；
7. StrategyVersion 摘要和样本列表不混合版本；
8. Owner Console 可从策略页进入 Observation 样本并正确返回；
9. TradFi Policy 和 Strategy Control 继续阻止真实 Ticket；
10. 只运行受影响的领域、Observation、Migration、Owner API、前端测试/build、
    Ruff、Mypy 和文档检查，部署前再执行一次 R4 必需认证。

## 非目标

- 不开放 TradFi 真实 Entry；
- 不增加资本、杠杆、并发容量或凭证；
- 不构造模拟 Ticket、模拟订单或模拟 PnL；
- 不持续保存完整 Depth；
- 不实现 MPG、BRF2、CPM、MI 或 RSRVCB TradFi 版本；
- 不部署生产或改变 Nginx/systemd。
