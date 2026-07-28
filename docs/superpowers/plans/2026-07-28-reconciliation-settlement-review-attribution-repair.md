# Reconciliation Settlement, Order Attribution and BNB Fee Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:test-driven-development` for every task and
> `superpowers:verification-before-completion` before any completion claim.
> Owner 已授权本地 RED/GREEN、recording fake 与 disposable PostgreSQL 验收；
> Tokyo closure-only 发布、系统服务变更与交易所写入仍需独立确认。

**Goal:** Remove cross-Ticket Settlement/Review starvation, attribute Binance
regular and conditional fills by exact `orderId`, close the pending BTC Ticket
through the normal event chain, preserve STOP_MARKET safety exits, make TP1
provably Maker-only, and support auditable USDT/BNB fees without granting the
program any BNB purchase, transfer, margin, or fee-burn mutation authority.

**Architecture:** One age-aware selector remains inside the existing
Reconciliation Worker. A pure order-attribution domain and one Binance
infrastructure resolver serve Lifecycle, unknown recovery, and Review.
Native-fee valuation is a Review-only pure boundary backed by one bounded
read-only BNBUSDT index-price snapshot. Closure-only handover is an exact-ticket deployment
mode with Entry fenced and no schema change. All exchange writes remain durable
Exchange Commands; no fifth worker, compatibility layer, parallel ledger, or
automatic BNB operation is introduced.

**Tech Stack:** Python 3.11+, frozen Pydantic v2 models,
`decimal.Decimal`, SQLAlchemy 2, PostgreSQL 16, pytest/pytest-asyncio, Ruff,
Mypy, CCXT-compatible Binance USD-M adapter, four persistent systemd workers.

## 执行状态

| 工作 | 当前状态 | 权限边界 |
| --- | --- | --- |
| 详细设计 | 已确认 | 本地工程权威，非运行时权威 |
| 实施计划 | 已确认 | 本地实施顺序 |
| 测试用例规格 | 已确认 | 先写 RED |
| 自动化测试代码 | 实施中 | recording fake 与 disposable PostgreSQL |
| 生产代码 | 实施中 | 对应 RED 后才能写 |
| Tokyo closure 部署 | 未授权 | 本计划不执行 |
| BNB 人工转入 | 未执行 | 仅 Owner 在新版本部署后操作 |

## 设计与测试权威

- 设计：
  `docs/superpowers/specs/2026-07-28-reconciliation-settlement-review-attribution-repair-design.md`
- 测试用例：
  `docs/superpowers/specs/2026-07-28-reconciliation-settlement-review-attribution-repair-test-cases.md`
- 当前运行权威：`docs/current/*`、当前代码、action-time PostgreSQL、
  systemd 与交易所只读事实。

若实现细节与设计冲突，停止编码并回到 Owner 确认，不用局部测试通过覆盖
设计。不在本计划中修改 `docs/current/*` 的生产事实。

## 全局工程约束

1. **测试优先**：每个行为先产生缺失能力对应的 RED，再做最小 GREEN，
   最后重构。
2. **不迁移 schema**：本修复必须保持 Alembic `0001`，不得借 P1 修复夹带
   StrategyUniverse `0002`。
3. **单一身份链**：成交归因只允许
   `command -> submitted identity -> actualOrderId -> trade.orderId`。
4. **单一手续费模型**：所有消费者复用 `NativeFee -> ValuedFee`，不各自解析
   USDT/BNB。
5. **单一执行链**：TP1、STOP_MARKET 仍经 durable Exchange Command；Adapter
   不直接创建第二条订单路径。
6. **纯领域**：domain 不依赖 SQLAlchemy、Venue client、系统时钟、文件或
   网络。
7. **明确类型**：核心边界使用 frozen named Pydantic model；raw dict 只能
   存在于 infrastructure parser。
8. **有界查询**：所有 DB/交易所查询按 exact Ticket、symbol、order id 和
   time window 限定。
9. **网络事务分离**：所有 Binance I/O 在 PostgreSQL transaction 外。
10. **Unknown 不重发**：未知结果仍先消歧，不因 resolver 重构改变安全语义。
11. **退出语义固定**：初始止损/runner 是 STOP_MARKET；TP1 是 LIMIT + GTX；
    GTX 拒绝无 taker fallback。
12. **BNB 非资本**：BNB 不进入 OwnerCapital、margin、Capacity、sizing、
    Initial Stop 或 liquidation truth。
13. **禁止 BNB 写能力**：无 purchase、convert、transfer、fee burn POST、
    Multi-Assets Mode 或 BNB margin API。
14. **正常闭环**：BTC 只经 UoW/Reducer/Event/Review 完成，不做 DML 修复。
15. **部署分层**：先 P1 closure-only，再 BTC 终态/flat 认证，之后才允许
    StrategyUniverse 迁移和正式 Entry 发布。

## 文件结构

| 文件 | 操作 | 单一职责 |
| --- | --- | --- |
| `src/trading_kernel/domain/order_attribution.py` | 新增 | 订单引用、解析和成交归因不变量 |
| `src/trading_kernel/domain/fee_valuation.py` | 新增 | native fee、USDT 估值和证据不变量 |
| `src/trading_kernel/infrastructure/binance_order_attribution.py` | 新增 | Binance regular/algo identity 解析 |
| `src/trading_kernel/infrastructure/binance_fee_valuation.py` | 新增 | BNBUSDT Review snapshot 只读估值 |
| `src/trading_kernel/domain/commands.py` | 修改 | 显式 time-in-force 不变量 |
| `src/trading_kernel/domain/review.py` | 修改 | valued fee 与 attribution evidence |
| `src/trading_kernel/application/ports.py` | 修改 | typed resolver/valuation ports |
| `src/trading_kernel/application/runtime_facts.py` | 修改 | typed request/result 和 BNB 能力事实 |
| `src/trading_kernel/interfaces/reconciliation_worker.py` | 修改 | age-aware work selector 与 closure retry |
| `src/trading_kernel/interfaces/lifecycle_worker.py` | 修改 | exact entry fee facts |
| `src/trading_kernel/infrastructure/pg_repositories.py` | 修改 | 公平选择和 exact command reference |
| `src/trading_kernel/infrastructure/pg_unit_of_work.py` | 修改 | STOP/TP1 command payload TIF |
| `src/trading_kernel/infrastructure/venue_adapter.py` | 修改 | 编排 resolver、GTX 和只读能力读取 |
| `src/trading_kernel/infrastructure/production_runtime.py` | 修改 | resolver/valuation 组装与 BNB 排除 |
| `scripts/trading_kernel/certify_readonly.py` | 修改 | closure-only exact Ticket 认证 |
| `scripts/trading_kernel/deploy_tokyo_release.py` | 修改 | closure-only 切换和 Entry 强制 fence |

## Task 0：冻结实现前事实与分支边界

**Files:**

- Read:
  `docs/current/MAIN_CONTROL_ROADMAP.md`
- Read:
  `docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md`
- Read:
  `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md`
- No production file changes.

- [ ] 确认当前 branch、HEAD、worktree 和 dirty state。
- [ ] 重新读取调度、Review、Lifecycle、unknown、deploy 的当前实现。
- [ ] 用 `rg` 回扫所有 `clientOrderId`、`commissionAsset`、`fee_quote`、
  `stop_market`、`timeInForce` 消费者。
- [ ] 记录实现前 Alembic head；本计划结束时必须不变。
- [ ] 不连接 Tokyo、不修改 PostgreSQL、不调用交易所写接口。

**Stop gate:** 若当前代码已变化到设计证据不成立，先修订设计，不继续写 RED。

## Task 1：建立订单归因与手续费估值领域边界

**Files:**

- Create:
  `src/trading_kernel/domain/order_attribution.py`
- Create:
  `src/trading_kernel/domain/fee_valuation.py`
- Modify:
  `src/trading_kernel/domain/review.py`
- Create:
  `tests/trading_kernel/unit/test_order_attribution.py`
- Create:
  `tests/trading_kernel/unit/test_fee_valuation.py`

**Interfaces:**

```python
def build_ticket_order_reference(...) -> TicketOrderReference: ...

def attribute_trade_fill(
    *,
    reference: TicketOrderReference,
    resolved_identity: ResolvedOrderIdentity,
    trade: ParsedTradeFacts,
    valued_fee: ValuedFee,
) -> AttributedTradeFill: ...

def value_native_fee(
    *,
    native_fee: NativeFee,
    valuation_facts: FeeValuationFacts,
) -> ValuedFee: ...
```

- [ ] 写 `OID-DOM-*` 和 `FEE-DOM-*` RED，确认模块缺失。
- [ ] 实现 frozen models、Enum、Decimal 和 extra-forbid。
- [ ] 普通订单只允许 submitted id 等于 actual order id。
- [ ] 条件订单只允许 validated algo resolution 产生 actual order id。
- [ ] USDT 估值固定为 1；BNB 必须携带 Review snapshot evidence。
- [ ] 拒绝未知 fee asset、负 fee、非正 valuation rate 与无效 snapshot time。
- [ ] canonical attribution digest 对输入顺序稳定，对内容变化敏感。
- [ ] focused pytest、Ruff、Mypy 通过。

**Commit:** `feat(kernel): define exact order and fee attribution`

## Task 2：让 OrderCommandPayload 表达真实退出语义

**Files:**

- Modify:
  `src/trading_kernel/domain/commands.py`
- Modify:
  `src/trading_kernel/infrastructure/pg_unit_of_work.py`
- Modify:
  `tests/trading_kernel/unit/test_commands.py`
- Modify:
  `tests/trading_kernel/integration/test_pg_unit_of_work.py`

- [ ] 先写 `ORD-TIF-*` RED。
- [ ] `OrderCommandPayload` 增加显式 `time_in_force`。
- [ ] LIMIT 缺 TIF 必须 validation error。
- [ ] TP1 producer 只生成 LIMIT + GTX。
- [ ] 初始止损与 runner producer 始终生成 STOP_MARKET 且 TIF 为空。
- [ ] MARKET/STOP_MARKET/TAKE_PROFIT_MARKET 携带 TIF 必须拒绝。
- [ ] frozen payload 重试序列化/反序列化保持 TIF，不产生新 generation。
- [ ] 删除任何测试中“TP1 LIMIT 就等于 Maker”的错误断言。

**Commit:** `feat(kernel): make tp1 maker-only order semantics explicit`

## Task 3：建立 age-aware Reconciliation selector

**Files:**

- Modify:
  `src/trading_kernel/interfaces/reconciliation_worker.py`
- Modify:
  `src/trading_kernel/application/ports.py`
- Modify:
  `src/trading_kernel/infrastructure/pg_repositories.py`
- Modify:
  `tests/trading_kernel/unit/test_reconciliation_worker_fairness.py`
- Create:
  `tests/trading_kernel/integration/test_reconciliation_work_selector.py`

**Interfaces:**

```python
async def get_next_reconciliation_work(
    *,
    now_ms: int,
    closure_starvation_limit_ms: int,
) -> ReconciliationWorkItem | None: ...
```

- [ ] 先写 position/settlement/review 竞争矩阵 RED。
- [ ] 保留 unknown terminal decision 的最高安全优先级。
- [ ] overdue closure 达到 30 秒时压过 due position。
- [ ] 未达到 aging 时 position 保持优先。
- [ ] Settlement 和 Review 使用相同 closure age 规则。
- [ ] 单 cadence 最多选择一个 normal work item。
- [ ] Review 失败 30 秒后才重新 eligible，且不改 status-entered age。
- [ ] PostgreSQL 并发使用 `FOR UPDATE SKIP LOCKED`，不会两 Worker 选中同一项。
- [ ] `EXPLAIN` 证明 active status/due path 使用索引并 `LIMIT 1`。

**Commit:** `fix(kernel): prevent settlement and review starvation`

## Task 4：从 PostgreSQL 构建 exact command references

**Files:**

- Modify:
  `src/trading_kernel/application/ports.py`
- Modify:
  `src/trading_kernel/infrastructure/pg_repositories.py`
- Create:
  `tests/trading_kernel/integration/test_order_attribution_repository.py`

- [ ] 先写 accepted、reconciled-accepted、rejected、unknown、cancel command
  矩阵 RED。
- [ ] 只读取 exact Ticket 的 immutable Command rows。
- [ ] 从 typed `ExchangeCommandResult` 提取 submitted exchange id。
- [ ] regular/conditional namespace 只由 frozen order type 决定。
- [ ] Cancel/SetLeverage 不进入 fill attribution 集合。
- [ ] 空、畸形、冲突 result payload fail closed。
- [ ] Repository 不返回 raw dict 给 application/domain。
- [ ] 查询不扫描其他 Ticket 或完整 Command history。

**Commit:** `feat(kernel): expose typed ticket order references`

## Task 5：实现 Binance exact order resolver

**Files:**

- Create:
  `src/trading_kernel/infrastructure/binance_order_attribution.py`
- Modify:
  `src/trading_kernel/application/ports.py`
- Modify:
  `src/trading_kernel/infrastructure/venue_adapter.py`
- Create:
  `tests/trading_kernel/unit/test_binance_order_attribution.py`
- Modify:
  `tests/trading_kernel/unit/test_venue_adapter.py`

- [ ] fixture 的 Account Trade row 刻意不包含 `clientOrderId`。
- [ ] 普通订单按 `symbol + orderId` 读取并核对每条 row。
- [ ] 条件订单按 exact `algoId` 查询并核对 `clientAlgoId`。
- [ ] `actualOrderId` 为空且 terminal not-triggered 时返回零 fill 语义。
- [ ] triggered/filled 状态缺 actual order id 时 fail closed。
- [ ] 用 actual order id 查询 trades，禁止把 algo id 当 order id。
- [ ] BTC runner 示例仅作为 fixture，生产代码无 BTC 常量/分支。
- [ ] trade 按 `tradeId` 幂等去重；冲突 duplicate fail closed。
- [ ] page-limit 不能证明完整时返回 facts unavailable。
- [ ] `_safe_response_payload()` 只扩大必要 allowlist，不落未知原始响应。

**Commit:** `fix(kernel): resolve Binance fills by actual order id`

## Task 6：实现 BNB 原生手续费与 USDT 估值

**Files:**

- Create:
  `src/trading_kernel/infrastructure/binance_fee_valuation.py`
- Modify:
  `src/trading_kernel/application/ports.py`
- Modify:
  `src/trading_kernel/infrastructure/venue_adapter.py`
- Modify:
  `src/trading_kernel/infrastructure/production_runtime.py`
- Create:
  `tests/trading_kernel/unit/test_binance_fee_valuation.py`
- Modify:
  `tests/trading_kernel/unit/test_production_runtime.py`

- [ ] 先写 `FEE-BNB-*` RED。
- [ ] 保存真实 `commission` 和 `commissionAsset`。
- [ ] USDT 不做 market lookup，rate 固定为 1。
- [ ] BNB 仅在最终 Review 读取一次 BNBUSDT public index-price snapshot。
- [ ] 覆盖空响应、无效 observed time 与非正价格；保存 method/rate/observed time。
- [ ] 同一 Ticket Review 有任意 BNB fill 时最多调用一次；无 BNB fill 时零调用。
- [ ] 混合 USDT/BNB fills 分别估值后汇总。
- [ ] 未知 asset 与 missing/invalid snapshot 返回 facts unavailable，不回退 0。
- [ ] 证明 BNB balance 不进入 Owner capital/sizing/margin facts。
- [ ] 生产 client 只暴露 index-kline readonly method，不暴露 purchase/transfer。

**Commit:** `feat(kernel): value native BNB fees with readonly evidence`

## Task 7：迁移 Lifecycle、Unknown 和 Review 三个消费者

**Files:**

- Modify:
  `src/trading_kernel/application/runtime_facts.py`
- Modify:
  `src/trading_kernel/interfaces/lifecycle_worker.py`
- Modify:
  `src/trading_kernel/interfaces/reconciliation_worker.py`
- Modify:
  `src/trading_kernel/infrastructure/venue_adapter.py`
- Modify:
  `src/trading_kernel/domain/review.py`
- Modify:
  `tests/trading_kernel/integration/test_ticket_lifecycle_maintenance.py`
- Modify:
  `tests/trading_kernel/integration/test_unknown_outcome_reconciliation.py`
- Modify:
  `tests/trading_kernel/unit/test_reconciliation_worker_review.py`
- Modify:
  `tests/trading_kernel/unit/test_review_economics.py`

- [ ] Lifecycle entry fee 只来自 exact entry order fills，执行风险计算仍使用非折扣
  taker fee 上界。
- [ ] Lifecycle 不读取 BNB valuation facts，也不因 BNB snapshot 不可得阻塞 runner。
- [ ] runner future fee 保持非折扣 taker 上界。
- [ ] Unknown regular/conditional 都先解析 order identity，再累计 exact fills。
- [ ] Unknown visibility deadline、no-resend、Incident 语义保持。
- [ ] Review 使用 typed references/resolved identities/valued fills。
- [ ] Review 保存 native fees、valuation evidence 和 attribution digest。
- [ ] quantity completeness 在写 Review 前严格校验。
- [ ] 三个消费者不再读取 `trade.clientOrderId`。
- [ ] 使用 AST/source gate 阻止相同假设重新出现。

**Commit:** `fix(kernel): unify lifecycle recovery and review attribution`

## Task 8：提交 TP1 GTX 并处理 Maker rejection

**Files:**

- Modify:
  `src/trading_kernel/infrastructure/venue_adapter.py`
- Modify:
  `tests/trading_kernel/unit/test_venue_adapter.py`
- Modify:
  `tests/trading_kernel/integration/test_command_dispatch.py`
- Modify:
  `tests/trading_kernel/full_chain/test_ticket_lifecycle.py`

- [ ] Adapter 把 TP1 映射为 `type=limit + timeInForce=GTX`。
- [ ] accepted/readback facts 核对 type/origType/timeInForce。
- [ ] GTX rejected 命令进入唯一 terminal rejection 路径。
- [ ] 断言没有 GTC、MARKET、调价或第二 generation command。
- [ ] 初始 STOP_MARKET 仍可见、数量正确、身份精确。
- [ ] runner STOP_MARKET 创建/替换语义不携带 GTX。
- [ ] unknown GTX outcome 仍进入 unknown recovery，不能误当 authoritative reject。

**Commit:** `feat(kernel): enforce maker-only tp1 dispatch`

## Task 9：增加 BNB fee capability 只读观察

**Files:**

- Modify:
  `src/trading_kernel/application/runtime_facts.py`
- Modify:
  `src/trading_kernel/infrastructure/venue_adapter.py`
- Modify:
  `src/trading_kernel/infrastructure/production_runtime.py`
- Modify:
  `src/trading_kernel/interfaces/reconciliation_worker.py`
- Create:
  `tests/trading_kernel/integration/test_bnb_fee_capability_monitor.py`
- Create:
  `tests/trading_kernel/architecture/test_bnb_fee_authority.py`

- [ ] 读取 feeBurn status、BNB Futures wallet balance 和 observed time。
- [ ] `available/unavailable/low_balance/unknown` 使用稳定 Monitor 语义。
- [ ] BNB 余额阈值只影响 warning，不影响 Entry/exit/Settlement/Review。
- [ ] Monitor cadence 幂等，不每 5 秒追加噪声事件。
- [ ] 静态 gate 禁止 fee burn POST、purchase、convert、transfer、multi-assets
  mutation。
- [ ] recording client 证明所有新增调用是 GET/public readonly。
- [ ] BNB 为 0 时 USDT fee 仍能完整闭环。

**Commit:** `feat(kernel): report readonly BNB fee capability`

## Task 10：实现 exact closure-only handover

**Files:**

- Modify:
  `scripts/trading_kernel/certify_readonly.py`
- Modify:
  `scripts/trading_kernel/deploy_tokyo_release.py`
- Modify:
  `tests/trading_kernel/unit/test_deploy_tokyo_release.py`
- Create:
  `tests/trading_kernel/integration/test_closure_only_certification.py`
- Create:
  `tests/trading_kernel/architecture/test_closure_handover_architecture.py`

- [ ] `--closure-ticket-id` 必须 exact、非空、唯一。
- [ ] closure/protected/flat 三模式互斥。
- [ ] closure 与 `--enable-entry` 互斥。
- [ ] closure 禁止 schema revision 变化。
- [ ] 认证 status 只允许 Settlement/Review pending。
- [ ] exact Ticket 必须 flat、无单、无 unresolved、无 Incident、已释放全部权威。
- [ ] 停 Worker 后第二次读取 action-time facts，防止 preflight 竞态。
- [ ] identity rotation 后只允许 target safety workers。
- [ ] postflight 证明 Entry inactive、disabled、fenced。
- [ ] 任一矛盾 fail closed，不 DML 修复 Ticket。

**Commit:** `feat(kernel): add fenced closure-only handover`

## Task 11：BTC 正常事件回放与多 Ticket Full Chain

**Files:**

- Create:
  `tests/trading_kernel/full_chain/test_multi_ticket_closure_fairness.py`
- Create:
  `tests/trading_kernel/full_chain/test_binance_actual_order_review.py`
- Modify:
  `tests/trading_kernel/full_chain/test_fault_matrix.py`
- Modify:
  `tests/trading_kernel/full_chain/test_ticket_lifecycle.py`

- [ ] 构造至少两个持续 due active positions 和一个 BTC-like
  `SETTLEMENT_PENDING` Ticket。
- [ ] 证明 closure 在 30 秒 + poll bound 内被选择。
- [ ] 通过正式 `BudgetSettled -> ReviewRecorded` 事件推进。
- [ ] runner fixture 使用已知 algo/clientAlgo/actualOrderId 形状。
- [ ] Account Trade rows 只有 tradeId/orderId，不带 clientOrderId。
- [ ] entry/exit quantity、native fee、USDT fee、gross/net PnL、R 和 digest
  全部可复算。
- [ ] 覆盖 USDT-only、BNB-only、mixed-fee 三种 Ticket。
- [ ] 证明已有 SOL/AVAX-like positions 的 STOP/runner cadence 未失去保护。
- [ ] 禁止直接 INSERT Review、UPDATE terminal 或 BTC 专用 branch。

**Commit:** `test(kernel): certify fair closure and exact Binance review`

## Task 12：同类缺陷回扫、性能与本地总验收

**Files:**

- Modify/create focused architecture tests as required.
- Do not modify Tokyo state.

- [ ] `rg`/AST 证明 production 不再按 `trade.clientOrderId` 过滤成交。
- [ ] 证明所有实际 fee 都保存 native asset/amount，所有汇总都有估值证据。
- [ ] 证明 production 无 fee burn mutation、BNB transfer/purchase 和 BNB margin
  dependency。
- [ ] 证明 TP1 没有非 GTX producer 或 Adapter fallback。
- [ ] 证明 initial stop/runner 没有被改成 LIMIT。
- [ ] 证明 BNB balance 不影响 sizing/capital/capacity query。
- [ ] PostgreSQL `EXPLAIN`、Binance call-count 和 bounded page tests 通过。
- [ ] 运行 focused unit/integration/full-chain/architecture tests。
- [ ] 运行完整 Trading Kernel suite。
- [ ] 运行 Ruff、Mypy、runtime file-I/O audit 和 `git diff --check`。
- [ ] 确认 Alembic head 未改变，未新增 migration。
- [ ] 生成本地证据摘要，明确 **DEPLOYMENT_BLOCKED / OWNER_CONFIRMATION_REQUIRED**。

**Commit:** `test(kernel): close attribution and fee regression matrix`

## 实施完成后的生产顺序

以下是未来操作顺序，不由本计划自动执行：

```text
本地完整验收
-> SOL/AVAX 与其他交易所持仓和订单自然全平
-> Owner 独立确认 P1 closure-only 发布
-> action-time PostgreSQL/exchange/systemd/identity 认证
-> P1 无 migration、Entry fenced 发布
-> BTC 正常 Settlement/Review terminal
-> 全平认证
-> StrategyUniverse 代码与 migration 独立发布
-> 最终生产 Universe 播种和预热
-> 正式发布显式 --enable-entry
-> Owner 人工转入少量 BNB
-> Agent 只读复核 feeBurn/BNB balance 并写 PostgreSQL Monitor
```

## 本地完成门

只有以下全部满足才可向 Owner 汇报“实现已完成，等待部署确认”：

1. **调度**：多 Ticket closure 选择延迟满足设计边界。
2. **身份**：普通单与条件单都由 exact actual order id 归因。
3. **消费者**：Lifecycle、Unknown、Review 已统一迁移。
4. **订单**：STOP_MARKET/GTX 退出矩阵及拒绝恢复全部通过。
5. **手续费**：USDT、BNB、混合资产和不可用估值矩阵通过。
6. **资本隔离**：BNB 不影响 margin/sizing/capacity/risk。
7. **BTC 回放**：正常事件链生成唯一完整 Review。
8. **发布安全**：closure-only 不能启用 Entry、不能迁移 schema。
9. **静态边界**：没有 BTC 特例、clientOrderId trade filter、BNB 写 API、
   fallback 或平行账本。
10. **总验收**：完整测试、Ruff、Mypy、I/O audit、diff check 全绿。
11. **生产边界**：未部署、未写 Tokyo、未写交易所、未转入 BNB。
