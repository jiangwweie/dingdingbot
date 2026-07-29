---
title: Cross-Margin Liquidation Risk Authority Repair Test Cases
status: PROPOSED_OWNER_REVIEW
authority: NOT_CURRENT_AUTHORITY
date: 2026-07-29
revision: 1
design: 2026-07-29-cross-margin-liquidation-risk-authority-repair-design.md
---

# Cross-Margin Liquidation Risk Authority Repair Test Cases

## Purpose

本文档将拟议的 **Cross-margin liquidation authority repair** 转换为可执行
断言。Owner 确认设计后，所有缺失行为必须先观察 RED，再修改生产代码。

本地测试不得连接真实交易所、修改 Tokyo、启用 Entry 或创建真实订单。
生产验收是独立阶段，必须保持 Entry fenced，直到 Owner 明确允许恢复。

## 测试原则

- 使用 `Decimal`、冻结 Pydantic 模型和明确 Side。
- 每个决策同时断言允许的结果和禁止的副作用。
- Domain 测试验证数学与状态，不 mock Domain 内部实现。
- Adapter 测试保留 Binance 原始字段，不把原始字段解释成授权。
- 网络 I/O 在事务外，Event/Aggregate/Incident/Command 在短事务内。
- PostgreSQL 测试使用 disposable 容器和真实迁移。
- Full-chain 必须经过 worker、UoW、reducer 和 durable command。
- 不使用 `xfail`、skip、DML 伪造终态或兼容旧字段。
- 当前正确的 unknown outcome、partial fill、Initial Stop、TP1/runner、
  Settlement/Review 与多仓位语义必须继续通过。

## 拟议测试文件

| 文件 | 测试边界 |
| --- | --- |
| `tests/trading_kernel/unit/test_cross_margin_liquidation.py` | 统一账户级投影数学 |
| `tests/trading_kernel/unit/test_capacity_sizing.py` | Claim 使用统一 projector |
| `tests/trading_kernel/unit/test_entry_dispatch_preflight.py` | Dispatch 复用同一 proof |
| `tests/trading_kernel/unit/test_post_fill_risk.py` | 实际 Stop Risk 与 liquidation proof 分离 |
| `tests/trading_kernel/unit/test_venue_adapter.py` | typed risk snapshot 与原始 observation |
| `tests/trading_kernel/unit/test_reducer.py` | 新状态、Event、Effect 和幂等 |
| `tests/trading_kernel/integration/test_command_dispatch.py` | durable command 与事务边界 |
| `tests/trading_kernel/integration/test_ticket_lifecycle_maintenance.py` | Stop-first 与重试 |
| `tests/trading_kernel/integration/test_schema_baseline.py` | `0003` forward-only schema |
| `tests/trading_kernel/full_chain/test_cross_margin_post_fill_risk.py` | 事故回归与完整生命周期 |
| `tests/trading_kernel/full_chain/test_multi_position_certification.py` | Cross 多仓位与同合约双 Side |
| `tests/trading_kernel/architecture/test_cross_margin_risk_authority.py` | 单一公式、无旧字段与无胶水 |

## A. 纯 Domain 账户投影

| ID | 场景 | 必须断言 |
| --- | --- | --- |
| CMR-001 | 单一 Long，清算根在 Stop 外且比率高于阈值 | `proved_safe`，价格、距离和 ratio 使用 `Decimal` 精确相等 |
| CMR-002 | 单一 Short，清算根在 Stop 外且比率高于阈值 | `proved_safe`，Short 方向正确 |
| CMR-003 | Long 清算根位于 Stop 与 Entry 之间 | `proved_unsafe` |
| CMR-004 | Short 清算根位于 Entry 与 Stop 之间 | `proved_unsafe` |
| CMR-005 | root 在 Stop 外但 ratio 低于冻结阈值 | `proved_unsafe`；不放宽 `2.0` |
| CMR-006 | root 距离恰好等于阈值 | `proved_safe` |
| CMR-007 | Long adverse 方向不存在清算根 | `proved_safe_no_adverse_root`；price/ratio 为 `None` |
| CMR-008 | Short adverse 方向不存在清算根 | `proved_safe_no_adverse_root` |
| CMR-009 | 当前 margin balance 已不高于 maintenance margin | `facts_contradictory` |
| CMR-010 | 从 total maintenance 扣除该合约当前 maintenance 后为负 | `facts_contradictory` |
| CMR-011 | 同合约 Long 与 Short 同时存在 | 两个 Side 都进入 PnL 和 maintenance 函数 |
| CMR-012 | Long/Short 数量完全对冲 | 不把任一 Side 丢弃或净成一个无身份仓位 |
| CMR-013 | 其他合约仓位存在 | 通过 account base facts 影响 proof，但不扫描其价格函数 |
| CMR-014 | 候选价格跨一个 maintenance bracket | 在正确分段求根 |
| CMR-015 | 候选价格跨多个 bracket | 恰好一个合法根被选择 |
| CMR-016 | root 落在所用 bracket 区间外 | 该根被拒绝并继续检查其他分段 |
| CMR-017 | notional 恰好等于 bracket floor | 使用该 bracket |
| CMR-018 | notional 恰好等于非最终 bracket cap | 使用下一个 bracket |
| CMR-019 | brackets 有 gap、重叠或未排序 | typed snapshot 拒绝 |
| CMR-020 | `maintenance_margin = notional * rate - cum` 为负 | facts 拒绝，不钳制为零 |
| CMR-021 | quantity、entry、mark、balance 或 rate 非有限值 | Pydantic 拒绝 |
| CMR-022 | Position mode 为 one-way 或 margin mode 为 isolated | snapshot 拒绝 |
| CMR-023 | 相同 instrument+side 重复两行 | snapshot 拒绝 |
| CMR-024 | snapshot digest 改变一个金融字段 | digest 必须变化 |
| CMR-025 | 输入顺序变化但语义身份相同 | canonical ordering 后 digest 与 proof 一致 |
| CMR-026 | Long 与 Short 使用相同账户事实分别评估 | 每个 proof 只搜索自己的 adverse 方向 |
| CMR-027 | account risk mode 为 Multi-Assets 或 Portfolio Margin | typed snapshot 拒绝 |
| CMR-028 | settlement asset 不是 USDT | typed snapshot 拒绝 |
| CMR-029 | BNB 手续费余额发生变化，其他 canonical facts 不变 | snapshot digest 和 proof 不变 |
| CMR-030 | 其他合约 mark price 不变，候选合约价格变化 | proof 只解候选合约的单因子根 |

## B. Claim 与 Dispatch 单一权威

| ID | 场景 | 必须断言 |
| --- | --- | --- |
| ENT-001 | Flat instrument 新 Long | Capacity sizing 调用统一 projector 并冻结 proof |
| ENT-002 | Flat instrument 新 Short | 同上，Short 方向正确 |
| ENT-003 | 已有同合约 Short，新 Long | hypothetical snapshot 同时包含旧 Short 和新 Long |
| ENT-004 | 已有同合约 Long，新 Short | hypothetical snapshot 同时包含旧 Long 和新 Short |
| ENT-005 | Claim snapshot 缺 maintenance brackets | `LIQUIDATION_PROOF_FAILED`；无 Claim/Ticket/Command |
| ENT-006 | Claim facts contradictory | `LIQUIDATION_PROOF_FAILED` |
| ENT-007 | Claim proof unsafe | `LIQUIDATION_PROOF_FAILED` |
| ENT-008 | Dispatch action-time facts仍安全 | ENTRY 可以进入 durable dispatch |
| ENT-009 | Dispatch 时余额变化使 proof unsafe | ENTRY 终态拒绝；无 venue create order |
| ENT-010 | Dispatch 时 bracket digest 改变 | ENTRY 终态拒绝 |
| ENT-011 | Dispatch 时 position mode 或 margin mode 改变 | ENTRY 终态拒绝 |
| ENT-012 | Dispatch snapshot stale | ENTRY 终态拒绝 |
| ENT-013 | Claim 与 Dispatch 输入相同 | proof payload 与 digest 完全一致 |
| ENT-014 | 代码静态扫描 | `capacity_sizing.py` 与 `revalidate_entry_dispatch.py` 不再各自实现清算公式 |
| ENT-015 | Universe 或策略不同但风险 facts 相同 | 使用同一 projector；策略不能覆盖风险结果 |
| ENT-016 | action-time account risk mode 改成非标准单资产 | ENTRY 终态拒绝；无 venue create order |

## C. Adapter 与原始交易所观测

| ID | 场景 | 必须断言 |
| --- | --- | --- |
| VEN-001 | Binance Long `liquidationPrice = "0"` | 保留 `Decimal("0")` observation |
| VEN-002 | Binance Short `liquidationPrice = 0` | 保留 `Decimal("0")` observation |
| VEN-003 | AVAX Long 返回高于 Entry 的正数 | 原样保留并标记 direction-invalid monitor；不改变 proof |
| VEN-004 | raw field 缺失 | observation unavailable；不伪造 `0` |
| VEN-005 | raw field 非数字 | snapshot 采集失败或显式 unsupported；不吞错 |
| VEN-006 | 同合约 Long/Short 两行 | 按精确 `positionSide` 生成两个 position facts |
| VEN-007 | 返回 BOTH row | independent-sides snapshot 拒绝 |
| VEN-008 | 账户 position mode 不是 Hedge | snapshot 拒绝 |
| VEN-009 | 任一开放 position 缺 average entry | snapshot 拒绝 |
| VEN-010 | balance 缺 totalMarginBalance | snapshot unavailable |
| VEN-011 | balance 缺 totalMaintMargin | snapshot unavailable |
| VEN-012 | mark price 缺失或非正 | snapshot unavailable |
| VEN-013 | leverage bracket 缺精确 symbol | snapshot unavailable |
| VEN-014 | bracket `cum` 被解析 | `maintenance_amount` 精确等于原始 `cum` |
| VEN-015 | bracket 存在不能表达的调整系数 | snapshot 拒绝，不忽略 |
| VEN-016 | 网络超时 | worker 返回 facts unavailable，无数据库事务悬挂 |
| VEN-017 | 一次正常 snapshot | 只调用有界账户、精确合约 positions/mark/mode/bracket 端点 |
| VEN-018 | Adapter 完成 snapshot | 零 exchange mutation、零文件输出 |
| VEN-019 | raw reported price 改变，账户 canonical facts 不变 | canonical snapshot digest 和 proof 不变，仅独立 observation 审计变化 |
| VEN-020 | Multi-Assets Mode 开启 | snapshot 拒绝；不得套用单资产公式 |
| VEN-021 | Portfolio Margin 账户 | snapshot 拒绝；不得套用标准 Futures 公式 |
| VEN-022 | BNB 余额或手续费折扣事实变化 | 不进入 canonical risk snapshot |

## D. Stop-First 生命周期

| ID | 场景 | 必须断言 |
| --- | --- | --- |
| PFR-001 | 完整 Entry Fill | `EntryFilled` 记录实际 qty/price/stop risk，不声称已有 liquidation proof |
| PFR-002 | Entry Fill 后 risk source 暂不可用 | Initial Stop 仍必须先准备和提交 |
| PFR-003 | Initial Stop 尚未确认 | 不读取或不提交 TP1，不释放 Entry Lane |
| PFR-004 | Initial Stop 确认且 Stop Risk 正常 | 进入 `post_fill_risk_recheck_pending` |
| PFR-005 | Stop 方向错误 | 保留 `FLATTEN_IMMEDIATELY`，不创建无效 Stop |
| PFR-006 | actual Stop Risk 超硬上限 | Initial Stop 后 durable Controlled Flatten |
| PFR-007 | actual Stop Risk 恰好等于硬上限 | 不因 Stop Risk 单独平仓，继续 liquidation proof |
| PFR-008 | proof `proved_safe` | 提交 `PostFillLiquidationRiskConfirmed`、释放 lane、准备 TP1 |
| PFR-009 | proof `proved_safe_no_adverse_root` | 与安全 proof 相同地继续 TP1，但状态可审计 |
| PFR-010 | proof `proved_unsafe` | `PostFillLiquidationRiskDegraded`、无 TP1、准备 Controlled Flatten |
| PFR-011 | proof `facts_contradictory` | 保持 Stop、无 TP1、account-capacity Incident、无 Flatten |
| PFR-012 | snapshot timeout | 保持 Stop、无 TP1、account-capacity Incident、安排重试 |
| PFR-013 | timeout 重复十次 | 只有一个 unavailable Event/Incident；无 append-only spam |
| PFR-014 | timeout 后恢复并 proof safe | 解决 Incident、释放 lane、准备一个 TP1 |
| PFR-015 | timeout 后恢复并 proof unsafe | 解决 unavailable Incident、准备一个 Controlled Flatten |
| PFR-016 | 同一 safe proof 重复到达 | 无重复 Event、TP1 generation 或 lane release |
| PFR-017 | 同一 unsafe proof 重复到达 | 无重复 Controlled Flatten generation |
| PFR-018 | process 在 unavailable 后重启 | Aggregate 重载后仍保持 Stop、lane 和重试身份 |
| PFR-019 | process 在 proof commit 前崩溃 | 重试由 expected version 保证最多提交一次 |
| PFR-020 | process 在 proof commit 后、dispatch 前崩溃 | durable command 恢复，不重新计算第二个 command |

## E. ETH 与 AVAX 事故回归

| ID | 事故夹具 | 必须断言 |
| --- | --- | --- |
| INC-001 | ETH Long，venue report=`0`，canonical account proof safe | Initial Stop -> TP1；无 Controlled Flatten |
| INC-002 | ETH Long，venue report=`0`，canonical proof unavailable | Initial Stop 保留；Entry blocked；无 TP1、无 Flatten |
| INC-003 | AVAX Long，entry=`6.60`、stop=`6.383`、venue report=`14.076`，canonical proof safe | 原始值被审计但不能影响 proof；无 Flatten |
| INC-004 | AVAX Long，entry=`6.58`、stop=`6.383`、venue report=`14.17`，canonical proof safe | 同上 |
| INC-005 | AVAX Long，entry=`6.62`、stop=`6.383`、venue report=`13.90`，canonical proof safe | 同上 |
| INC-006 | AVAX Long，同样 raw report，但 canonical root 侵入 Stop | 证明是 canonical risk 触发保护后平仓 |
| INC-007 | 将 venue report 从 `0` 改成任意方向错误正数 | canonical proof 与 lifecycle decision 不变 |
| INC-008 | 将账户 balance/maintenance 改成不安全，同时 raw report 保持正常 | lifecycle 必须按 canonical proof 平仓 |

事故测试使用经过脱敏的数值夹具，不依赖 Ticket ID、API credential、生产
数据库导出文件或当前交易所状态。它们证明已观察到的错误输入类别，不声称
重建当时完整账户的历史清算根。

## F. 多仓位 Cross 场景

| ID | 场景 | 必须断言 |
| --- | --- | --- |
| MUL-001 | BTC Long 已保护，新增 ETH Long | ETH proof 使用全账户 balance/maintenance |
| MUL-002 | BTC Long 已保护，新增 ETH Short | Side 不影响账户级事实归属 |
| MUL-003 | AVAX Short 已保护，新增 AVAX Long | 两个 Side 同时进入 exact-instrument 价格函数 |
| MUL-004 | AVAX Long 已保护，新增 AVAX Short | 同上 |
| MUL-005 | 同合约相反 Side 降低 adverse exposure | proof 可变安全，但两个 Ticket 身份保持独立 |
| MUL-006 | 同合约相反 Side 增加另一方向风险 | 当前 Ticket proof 只搜索自身 adverse 方向 |
| MUL-007 | 不同 Ticket 同时等待 Reconciliation | 每 tick 只处理一个 bounded work item，无相互改写 |
| MUL-008 | 一个 Ticket proof unavailable | account-capacity scope 阻止新 ENTRY，其他已保护 Ticket 继续 Lifecycle |
| MUL-009 | 一个 Ticket canonical proof unsafe | 只为该 Ticket 创建 Flatten command |
| MUL-010 | 另一个 Ticket 已在 runner | risk recheck 不替换或取消其 runner Stop |
| MUL-011 | 同 Netting Domain 已有 Ticket | 仍由原有 domain rule 拒绝，不进入 projector |
| MUL-012 | 三个活跃 Ticket | projection 复杂度只与当前账户 positions 和 brackets 有界相关 |

## G. Incident、Monitor 与 Entry Fence

| ID | 场景 | 必须断言 |
| --- | --- | --- |
| MON-001 | post-fill facts unavailable | 一个 open Incident，scope=`account_capacity`，key 精确 |
| MON-002 | facts contradictory | 不与 unavailable 混为同一 kind |
| MON-003 | proof 恢复 safe | unavailable Incident 原子解决 |
| MON-004 | proof 恢复 unsafe | unavailable Incident 解决，unsafe Monitor 保留 |
| MON-005 | venue report=`0` | Monitor code 为 observation warning，不打开安全 Incident |
| MON-006 | venue report direction-invalid | Monitor warning 不创建 Flatten command |
| MON-007 | account-capacity Incident 开放 | Entry readiness 拒绝所有该账户新 Ticket |
| MON-008 | 已有 Ticket | Incident 不移除 Stop、Lifecycle 或 Reconciliation authority |
| MON-009 | Runtime Fence 同时存在 | runtime scope 优先阻断，proof worker 不越权 mutation |
| MON-010 | Owner Policy 仍允许 Entry 但 systemd write fence 存在 | Entry service 无法启动 |

## H. PostgreSQL 与 Event 持久化

| ID | 场景 | 必须断言 |
| --- | --- | --- |
| DB-001 | 从空数据库迁移到 `0003` | schema head、metadata 和 table allowlist 一致 |
| DB-002 | 迁移前存在活跃 Ticket | migration 拒绝且 DDL 全部回滚 |
| DB-003 | 存在非平 position 或开放订单 | migration 拒绝 |
| DB-004 | 存在 unresolved command/Incident | migration 拒绝 |
| DB-005 | 存在 pending Settlement/Review | migration 拒绝 |
| DB-006 | 只剩 terminal Ticket、历史 Event 或 Review | migration 仍拒绝；无历史 backfill |
| DB-007 | 官方 reset 后 runtime/trade tables 全空 | migration 成功 |
| DB-008 | Aggregate schema | 旧 `actual_liquidation_*` 列不存在 |
| DB-009 | Aggregate schema | 新 proof/model/snapshot 字段完整 |
| DB-010 | `EntryFilled` round-trip | raw venue `0` 原样保存 |
| DB-011 | Safe proof Event round-trip | 类型与 payload 完全一致 |
| DB-012 | Unsafe proof Event round-trip | 类型与 payload 完全一致 |
| DB-013 | Unavailable Event round-trip | Incident effect 可重建 |
| DB-014 | Event registry parity | Domain TradeEvent union 与 PostgreSQL registry 完全一致 |
| DB-015 | proof commit fault injection | Event、Aggregate、Incident/resolve 和 Command 全部回滚 |
| DB-016 | successful proof commit | 上述事实单事务提交 |
| DB-017 | reload Aggregate | snapshot/model/bracket/proof identities 不丢失 |

## I. Full-Chain 验收

| ID | 完整场景 | 必须链路 |
| --- | --- | --- |
| CHN-001 | 正常 Long | Signal -> Claim proof -> Ticket -> ENTRY -> Fill -> Stop -> post-fill proof -> TP1 -> runner -> flat -> Settlement -> Review |
| CHN-002 | 正常 Short | 同上，Short 方向和 rounding 正确 |
| CHN-003 | ETH raw zero | 正常链路完成，无误 Flatten |
| CHN-004 | AVAX raw wrong-side | 正常链路完成，无误 Flatten |
| CHN-005 | canonical unsafe | ENTRY -> Fill -> Stop -> proof unsafe -> Controlled Flatten -> closure |
| CHN-006 | post-fill facts unavailable then recover safe | Stop 全程存在；无 TP1 早发；恢复后正常闭环 |
| CHN-007 | post-fill facts unavailable then recover unsafe | Stop 全程存在；恢复后一个 Flatten；正常闭环 |
| CHN-008 | adapter timeout and restart | 无重复 Event/Command，Entry 仍阻断 |
| CHN-009 | 两个不同 Netting Domain | 生命周期并发、Entry 串行、proof 不串 Ticket |
| CHN-010 | 同合约 Long/Short | 两张 Ticket、两套保护和 proof lineage，账户事实共享 |
| CHN-011 | proof 后 TP1/runner | P1 actualOrderId、GTX 和 BNB fee Review 继续工作 |
| CHN-012 | 两个活跃 Ticket 加一个 closure Ticket | Settlement/Review 公平调度不回归 |

每个 full-chain case 必须断言：

```text
one Exposure Episode -> one Ticket
one ENTRY command generation
Initial Stop before TP1 or post-fill flatten
every exchange mutation has one durable command
raw venue liquidation observation cannot create a command
proof snapshot/model/bracket/policy identities are frozen
no unknown outcome is blindly resent
terminal external flatness and no residual order
budget and Netting Domain released
Settlement and Review complete
no unresolved Ticket Incident
```

## J. 架构与性能门

| ID | 边界 | 必须断言 |
| --- | --- | --- |
| ARC-001 | Source scan | 只有 `cross_margin_liquidation.py` 实现清算方程 |
| ARC-002 | Source scan | `current_liquidation_price` 不再进入风险决策 |
| ARC-003 | Source scan | 旧 `actual_liquidation_*` model/repository/schema 字段消失 |
| ARC-004 | Source scan | 测试 helper `safe_liquidation_price()` 消失 |
| ARC-005 | Domain | 无 SQLAlchemy、venue、filesystem、subprocess 或 web import |
| ARC-006 | Transactions | 风险 snapshot 网络读取发生在数据库事务外 |
| ARC-007 | Commands | Stop、TP1、Flatten 均 durable-before-dispatch |
| ARC-008 | Runtime | 不新增 worker、timer 或第二条 execution chain |
| ARC-009 | File I/O | no-op 和 retry cadence 创建零 JSON/Markdown |
| ARC-010 | Compatibility | 无 legacy/compat module、alias、dual read/write 或 schema fallback |
| ARC-011 | Query | 每次只锁精确 Ticket；无 history scan |
| ARC-012 | Venue calls | 正常 post-fill proof 只执行一次有界 snapshot |
| ARC-013 | Retry | unavailable retry 遵守 timeout 和 poll interval，不 busy-loop |
| ARC-014 | Complexity | root solver 工作量受两个 Side 和 bracket 数量限制 |
| ARC-015 | Existing P1 | Settlement/Review fairness、order attribution、GTX、BNB 测试保持绿色 |
| ARC-016 | Account mode | 只有标准单资产 USDT Futures 可以调用该 projector |
| ARC-017 | Fee boundary | BNB 只出现在 fee valuation，不进入 liquidation Domain |
| ARC-018 | Model identity | 组合压力测试不得悄悄改变 `cross-margin-liquidation-v1` 语义 |

## Required RED Sequence

Owner 确认并开始实施后，先按以下顺序观察 RED：

1. `INC-001` 和 `INC-003`：证明 raw `0` 与 wrong-side 值当前会误触发
   Flatten。
2. `PFR-002` 和 `PFR-004`：证明现有 Fill Event 尚未与 liquidation proof
   分离。
3. `ENT-013` 和 `ARC-001`：证明 Claim 与 Dispatch 当前存在重复公式。
4. `CMR-011` 和 `CMR-014`：证明同合约双 Side 与跨 bracket 投影尚未被统一
   模型覆盖。
5. `MON-001` 和 `PFR-013`：证明 unavailable 还没有稳定的 Incident、lane
   和幂等重试语义。
6. `DB-008`、`DB-009` 和 `DB-014`：证明旧 projection 与新 Event registry
   尚未迁移。
7. `CHN-003` 至 `CHN-010`：证明事故回归、失败恢复和多仓位完整链尚未闭合。

不得通过修改期望值、删除 safety assertion、标记 `xfail` 或绕过真实
Application/UoW 边界制造绿色。

## 本地验证命令

### 纯 Domain 与 Adapter

```bash
uv run pytest -q \
  tests/trading_kernel/unit/test_cross_margin_liquidation.py \
  tests/trading_kernel/unit/test_capacity_sizing.py \
  tests/trading_kernel/unit/test_entry_dispatch_preflight.py \
  tests/trading_kernel/unit/test_post_fill_risk.py \
  tests/trading_kernel/unit/test_venue_adapter.py \
  tests/trading_kernel/unit/test_reducer.py
```

### PostgreSQL 与生命周期

```bash
uv run pytest -q \
  tests/trading_kernel/integration/test_command_dispatch.py \
  tests/trading_kernel/integration/test_ticket_lifecycle_maintenance.py \
  tests/trading_kernel/integration/test_schema_baseline.py
```

### Full-Chain 与多仓位

```bash
uv run pytest -q \
  tests/trading_kernel/full_chain/test_cross_margin_post_fill_risk.py \
  tests/trading_kernel/full_chain/test_multi_position_certification.py \
  tests/trading_kernel/full_chain/test_multi_ticket_closure_fairness.py \
  tests/trading_kernel/full_chain/test_ticket_lifecycle.py
```

### 最终本地认证

```bash
uv run pytest -q \
  tests/trading_kernel/unit \
  tests/trading_kernel/integration \
  tests/trading_kernel/full_chain \
  tests/trading_kernel/architecture

uv run ruff check \
  src/trading_kernel \
  tests/trading_kernel \
  scripts/trading_kernel

uv run --with mypy mypy \
  --config-file mypy.ini \
  src/trading_kernel \
  scripts/trading_kernel

uv run python scripts/audit_production_runtime_file_io.py
git diff --check
```

Disposable PostgreSQL 必须从空库迁移到新 schema head，验证约束和
forward-only refusal，并在测试完成后删除测试容器资源。禁止连接 Tokyo
PostgreSQL 代替本地集成测试。

## 生产发布验收

生产验收不属于本地测试自动执行范围。Owner 确认部署后，按以下阶段执行：

### Entry 继续 fenced

1. 确认 systemd Entry 为 `inactive/disabled`；
2. 确认 write-fence 文件存在；
3. 确认 Observation、Lifecycle、Reconciliation active；
4. 确认无新 ENTRY Command；
5. 确认旧持仓、订单、Incident、Settlement 和 Review 已闭环。

### Flat-only 发布

1. 认证交易所 flat 且无 residual order；
2. 认证 PostgreSQL 满足 `0002` 与 `0003` migration preflight；
3. 停止旧 writer，迁移并切换唯一目标 commit/schema；
4. 启动三个安全 worker；
5. 只读认证账户 identity、independent sides、Cross、固定 `5x`、Universe、
   Owner Policy、instrument rules、标准单资产模式和 USDT settlement；
6. Entry 继续 fenced。

### Owner 恢复 Entry 后的首笔验收

1. 新 Ticket 的 Claim 和 dispatch proof identities 一致；
2. Entry Fill 后 Initial Stop 优先确认；
3. post-fill proof Event 包含 snapshot/model/bracket/policy/fill/stop 身份；
4. venue raw liquidation observation 不拥有 command authority；
5. safe proof 才准备 TP1；
6. unsafe proof 才准备 Controlled Flatten；
7. facts unavailable 自动阻止下一笔 Entry；
8. Ticket 最终完成 Reconciliation、Settlement 和 Review。

## 完成证据

实现只有同时满足以下条件才可声明本地完成：

- 每个缺失行为族有可保存的 RED 证据；
- 所有目标测试 GREEN，报告精确通过数和零新增 skip；
- ETH `0` 与 AVAX wrong-side 回归完整通过；
- canonical unsafe 与 facts unavailable 分支完整通过；
- 同合约 Long/Short、多合约、多 Ticket 和 closure fairness 完整通过；
- Multi-Assets、Portfolio Margin、非 USDT settlement 和 BNB 边界测试通过；
- 迁移从空库成功、非 flat 失败并完整回滚；
- Event registry、Aggregate reload 和 Incident blocking 可重建；
- Ruff、source Mypy、架构、文件 I/O 和 `git diff --check` 通过；
- diff 证明无旧 liquidation authority、无兼容胶水、无第二执行链；
- Tokyo 仍保持 Entry fenced，部署和恢复 Entry 分别等待 Owner 确认。
