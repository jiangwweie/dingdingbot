---
title: DUAL_POSITION_HARD_CAP_ACCOUNT_RISK_MODEL_V0_IMPLEMENTATION_PLAN
status: READY_FOR_EXECUTION_AFTER_DOCUMENT_REVIEW
authority: docs/current/DUAL_POSITION_HARD_CAP_ACCOUNT_RISK_MODEL_V0_IMPLEMENTATION_PLAN.md
design: docs/current/DUAL_POSITION_HARD_CAP_ACCOUNT_RISK_MODEL_V0_DESIGN.md
base_commit: 2001644581cccc968ba695d3ff129960db6a7e84
branch: codex/dual-position-account-risk-v0
---

# Dual-Position Hard-Cap Account Risk Model V0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:executing-plans`
> task-by-task with review checkpoints. Repository constraints prohibit subagent
> dispatch unless the Owner explicitly asks for it. Track every step with the
> checkboxes below.

**Goal:** 在保留一个新 Action-Time Lane、同一 Protected Submit 和 Ticket lifecycle
的前提下，使账户最多顺序建立两个不同 instrument 的受保护仓位，并用 PG current
projection、2.5% 单 Ticket 风险、6% 组合风险、4% 风险簇风险和 90% 保证金上限
完成账户级容量仲裁。

**Architecture:** 完整账户交易所快照在 PG 事务外读取；PG 内由 ownership classifier、
Exposure Current 和 Budget Current 形成唯一账户容量事实。现有 Ticket 原子事务锁定
Account Budget Current 后完成 auto-downsize、reservation、lane 和 Ticket 写入；既有
lifecycle/reconciliation 驱动风险重算和容量释放。

**Tech Stack:** Python 3.14、Pydantic v2、`decimal.Decimal`、SQLAlchemy、Alembic、
PostgreSQL、pytest、Binance USD-M signed GET、现有 Runtime Control State/Action-Time/
Ticket-bound lifecycle。

## Global Constraints

- **目标政策**：`planned_stop_risk_fraction=0.025`、`max_concurrent_positions=2`、
  `max_portfolio_open_risk_fraction=0.06`、`max_cluster_open_risk_fraction=0.04`、
  `max_portfolio_initial_margin_fraction=0.90`、`max_leverage=10`。
- **并发边界**：`max_new_action_time_lanes=1`；保留
  `uq_brc_lane_single_open_real`。
- **同 instrument 边界**：`account_id + exchange_instrument_id` 已有非终态 claim 时，
  第二 Ticket 必须阻断，包括 Hedge Mode。
- **缩量边界**：自动缩量启用；最小有效数量仍超过 risk/margin capacity 才阻断。
- **费用边界**：fee、slippage、funding 不进入开仓 sizing reserve；成交后进入 Outcome。
- **事实边界**：未知/未归属/对账 mismatch/保护缺失/过期 Account Budget Current
  全局阻断新 ENTRY，但不能阻断既有保护、减仓、退出、恢复和 reconciliation。
- **权威边界**：PG/current services 是唯一 runtime authority；不新增 JSON/MD/
  report 文件读写，不新增文件 fallback。
- **性能边界**：交易所读取在 PG 事务外并发且 timeout-bounded；无信号 tick 写 0 个
  JSON/MD 文件；current projection 原地更新，事件只记录语义变化。
- **数值边界**：所有金融计算使用 `Decimal`，禁止 `float`。
- **代码边界**：不建立第二条执行、保护、恢复或对账主链；复用当前 Ticket lifecycle。
- **激活边界**：先 shadow、后 policy activation；migration 不把生产从 1 仓自动改为 2 仓。
- **回滚边界**：`max_concurrent_positions=1` 只停止新 ENTRY，不强平、不撤保护单。

---

## File Responsibility Map

| 文件 | 动作 | 单一职责 |
| --- | --- | --- |
| `src/domain/account_risk.py` | Create | 定义账户风险 typed models、纯风险/容量计算和阻断码 |
| `src/infrastructure/binance_usdm_account_risk_snapshot.py` | Create | 读取并规范化完整 Binance USD-M 账户只读快照 |
| `src/application/action_time/account_exchange_ownership.py` | Create | 账户级普通/Algo 订单和 position 的 Ticket 归属、用途分类 |
| `src/application/action_time/account_exposure_current.py` | Create | 从 typed snapshot + PG lifecycle 投影逐 instrument Exposure Current |
| `src/application/action_time/account_budget_current.py` | Create | 去重汇总 exposure/reservation，生成 Account Budget Current |
| `src/application/action_time/account_capacity_reservation.py` | Create | 锁账户预算行、校验 CAS、计算第二 Ticket 可用容量并预占 |
| `src/application/action_time/account_risk_policy.py` | Create | 追加 Account Risk Policy event 并维护 current projection |
| `src/application/action_time/budget_reservation_transition.py` | Create | 统一 reservation 合法状态转换与事件审计 |
| `src/application/action_time/account_safe_facts.py` | Modify | 从旧 flat boolean 切换为 Account Budget Current 引用和账户容量结论 |
| `src/application/action_time/promotion_action_time_lane.py` | Modify | 消费账户容量决策，保留单 Lane，写 auto-downsize 后 reservation |
| `src/application/action_time/ticket_materialization_sequence.py` | Modify | 把账户预算 row lock/CAS 纳入现有 fact-to-Ticket 原子事务 |
| `src/application/action_time/action_time_ticket.py` | Modify | Ticket 绑定 account risk policy/version 与 capacity projection/version |
| `src/application/action_time/ticket_bound_budget_settlement.py` | Modify | flat + reconciliation matched 后通过统一 transition 释放容量 |
| `src/application/action_time/post_submit_reconciliation_tick.py` | Modify | 每次真实 lifecycle 变化后驱动 exposure/budget current 重投影 |
| `src/infrastructure/runtime_control_state_repository.py` | Modify | 把 account risk policy/current projections 加入 Action-Time PG 读取面 |
| `scripts/run_server_product_state_refresh_sequence.py` | Modify | 使用统一 transition 修复过期 Ticket reservation；刷新 current projection |
| `scripts/ops/set_account_risk_policy.py` | Create | 通过正式 application service 执行 shadow/activate/rollback policy event |
| `migrations/versions/2026-07-14-121_create_account_risk_policy.py` | Create | 建立账户风险 policy event/current 和 versioned cluster mapping |
| `migrations/versions/2026-07-14-122_create_account_risk_current_projections.py` | Create | 建立 exposure/budget current 与 semantic-change event tables |
| `migrations/versions/2026-07-14-123_repair_terminal_budget_reservations.py` | Create | 受约束修复 terminal pre-submit Ticket 的 consumed reservation |
| `tests/unit/test_account_risk.py` | Create | 纯 Decimal 风险、margin、cluster、auto-downsize 单测 |
| `tests/unit/test_binance_usdm_account_risk_snapshot.py` | Create | 完整账户、普通单、Algo 单、timeout/shape 单测 |
| `tests/unit/test_account_exchange_ownership.py` | Create | Ticket owner/purpose/unknown/conflict 分类单测 |
| `tests/unit/test_account_exposure_current.py` | Create | lifecycle 阶段和 held-risk 守恒单测 |
| `tests/unit/test_account_budget_current.py` | Create | reservation/exposure 去重、slot/cluster/margin 汇总单测 |
| `tests/unit/test_budget_reservation_transition.py` | Create | reservation 合法转换和历史泄漏修复单测 |
| `tests/unit/test_account_capacity_reservation.py` | Create | `FOR UPDATE`/CAS/同 instrument/自动缩量单测 |
| `tests/integration/test_dual_position_account_risk_postgres.py` | Create | 真实 PostgreSQL 双事务和两 Ticket 生命周期集成认证 |

## Task 1: Account Risk Policy And Schema Authority

**Files:**

- Create: `migrations/versions/2026-07-14-121_create_account_risk_policy.py`
- Create: `src/application/action_time/account_risk_policy.py`
- Create: `scripts/ops/set_account_risk_policy.py`
- Create: `tests/unit/test_account_risk_policy_migration.py`
- Create: `tests/unit/test_account_risk_policy.py`

**Interfaces:**

- Produces: `AccountRiskPolicy`, `append_account_risk_policy_event`,
  `load_account_risk_policy_current`, `replace_risk_cluster_memberships`。
- Consumed by: Tasks 2、6、7、9、10。

- [ ] **Step 1: 写 migration RED 测试**

```python
def test_migration_121_keeps_single_position_shadow_defaults(pg_migrated_to_120):
    upgrade_to("121")
    row = conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'brc_account_risk_policy_current'"
    )).all()
    assert {item[0] for item in row} >= {
        "account_id", "runtime_profile_id", "risk_policy_version",
        "planned_stop_risk_fraction", "max_concurrent_positions",
        "max_portfolio_open_risk_fraction", "max_cluster_open_risk_fraction",
        "max_portfolio_initial_margin_fraction", "max_leverage",
        "max_new_action_time_lanes", "automatic_downsize_enabled",
        "unknown_exposure_policy", "activation_state",
    }
```

- [ ] **Step 2: 验证 RED**

Run:

```bash
python3 -m pytest -q tests/unit/test_account_risk_policy_migration.py
```

Expected: FAIL，原因是 migration 121 和目标表尚不存在。

- [ ] **Step 3: 实现 migration 121**

Migration 必须创建：

```text
brc_account_risk_policy_events
brc_account_risk_policy_current
brc_risk_cluster_memberships
```

约束必须包含：

```python
sa.CheckConstraint(
    "planned_stop_risk_fraction > 0 AND planned_stop_risk_fraction <= 1"
)
sa.CheckConstraint("max_concurrent_positions IN (1, 2)")
sa.CheckConstraint("max_new_action_time_lanes = 1")
sa.CheckConstraint(
    "unknown_exposure_policy = 'global_fail_closed'"
)
sa.UniqueConstraint(
    "account_id", "runtime_profile_id",
    name="uq_brc_account_risk_policy_current_scope",
)
```

Migration 只建 schema，不插入 `max_concurrent_positions=2` 的生产 current 行。

- [ ] **Step 4: 写 policy service RED 测试**

```python
def test_activate_policy_records_owner_values_without_mutating_strategy_scope(conn):
    policy = append_account_risk_policy_event(
        conn,
        account_id="binance-subaccount-1",
        runtime_profile_id="runtime-order-capable",
        event_type="activate_dual_position_v0",
        policy=AccountRiskPolicy(
            risk_policy_version="account-risk-v0-owner-20260714",
            planned_stop_risk_fraction=Decimal("0.025"),
            max_concurrent_positions=2,
            max_portfolio_open_risk_fraction=Decimal("0.06"),
            max_cluster_open_risk_fraction=Decimal("0.04"),
            max_portfolio_initial_margin_fraction=Decimal("0.90"),
            max_leverage=10,
            max_new_action_time_lanes=1,
            automatic_downsize_enabled=True,
            unknown_exposure_policy="global_fail_closed",
            activation_state="shadow",
        ),
        created_by="owner_decision_20260714",
        now_ms=1_752_480_000_000,
    )
    assert policy.planned_stop_risk_fraction == Decimal("0.025")
    assert policy.max_concurrent_positions == 2
```

- [ ] **Step 5: 实现 typed policy service 和 ops 入口**

`scripts/ops/set_account_risk_policy.py` 只能接受：

```text
--mode shadow
--mode activate
--mode rollback-single-position
```

三个 mode 都调用 `append_account_risk_policy_event`；脚本不直接执行散落 SQL，不读取或
写入 policy JSON/MD。`activate` 写 2.5%/2/6%/4%/90%/10x；`rollback` 只把
`max_concurrent_positions` 改为 1，其他边界不放宽。

`shadow` 和 `activate` 还必须调用 `replace_risk_cluster_memberships`，把 PG Registry 中
当前 active 且 `asset_class='crypto'` 的 Binance USD-M instrument 以明确
`exchange_instrument_id` 行写入 `crypto_usd_beta`。测试必须证明 symbol 字符串不参与
cluster 推断，未映射的新 instrument 在 live-submit capacity 中 fail-closed。

- [ ] **Step 6: 运行 GREEN 测试并提交**

```bash
python3 -m pytest -q \
  tests/unit/test_account_risk_policy_migration.py \
  tests/unit/test_account_risk_policy.py
git add migrations/versions/2026-07-14-121_create_account_risk_policy.py \
  src/application/action_time/account_risk_policy.py \
  scripts/ops/set_account_risk_policy.py \
  tests/unit/test_account_risk_policy_migration.py \
  tests/unit/test_account_risk_policy.py
git commit -m "feat: add account risk policy authority"
```

Expected: tests PASS；policy activation 尚未执行。

## Task 2: Pure Decimal Risk And Capacity Domain

**Files:**

- Create: `src/domain/account_risk.py`
- Create: `tests/unit/test_account_risk.py`

**Interfaces:**

- Consumes: `AccountRiskPolicy` from Task 1。
- Produces: `ExposureRiskInput`, `AccountRiskTotals`, `CapacityDecision`,
  `compute_directional_risk`, `decide_account_capacity`。

- [ ] **Step 1: 写 2.5%/6%/4% RED 测试**

```python
def test_second_same_cluster_ticket_downsizes_to_one_point_five_percent():
    result = decide_account_capacity(
        wallet_balance=Decimal("600"),
        available_balance=Decimal("500"),
        exchange_initial_margin=Decimal("100"),
        unreflected_pending_margin=Decimal("0"),
        existing_portfolio_held_risk=Decimal("15"),
        existing_cluster_held_risk=Decimal("15"),
        claimed_position_slots=1,
        instrument_already_claimed=False,
        per_unit_stop_risk=Decimal("3"),
        entry_reference_price=Decimal("150"),
        min_qty=Decimal("0.01"),
        qty_step=Decimal("0.01"),
        min_notional=Decimal("5"),
        exchange_max_leverage=20,
        policy=_policy(),
    )
    assert result.allowed_risk == Decimal("9")
    assert result.intended_qty == Decimal("3.00")
    assert result.blockers == ()
```

600U 下：单 Ticket 2.5%=15U，组合剩余 36-15=21U，cluster 剩余 24-15=9U，
因此第二个同 cluster Ticket 只允许 9U，即 **1.5%**。

- [ ] **Step 2: 写边界 RED 测试**

覆盖以下精确断言：

```text
different cluster second ticket receives min(15, 21, 24) = 15U
same instrument -> account_instrument_already_claimed
two claimed slots -> max_concurrent_positions_reached
minimum qty risk > remaining -> minimum_executable_quantity_exceeds_available_stop_risk_capacity
known portfolio over cap -> portfolio_open_risk_capacity_exhausted
margin min qty > remaining -> minimum_executable_quantity_exceeds_available_margin_capacity
long/short directional risk uses actual-average-entry-to-confirmed-stop and floors locked profit at zero
all outputs are Decimal and finite
```

- [ ] **Step 3: 验证 RED**

```bash
python3 -m pytest -q tests/unit/test_account_risk.py
```

Expected: FAIL，目标 domain module 尚不存在。

- [ ] **Step 4: 实现最小纯 domain**

核心数量决策必须等价于：

```python
ticket_limit = wallet_balance * policy.planned_stop_risk_fraction
portfolio_remaining = max(
    Decimal("0"),
    wallet_balance * policy.max_portfolio_open_risk_fraction
    - existing_portfolio_held_risk,
)
cluster_remaining = max(
    Decimal("0"),
    wallet_balance * policy.max_cluster_open_risk_fraction
    - existing_cluster_held_risk,
)
allowed_risk = min(ticket_limit, portfolio_remaining, cluster_remaining)
```

保证金容量必须使用：

```python
portfolio_margin_remaining = max(
    Decimal("0"),
    wallet_balance * policy.max_portfolio_initial_margin_fraction
    - exchange_initial_margin
    - unreflected_pending_margin,
)
action_time_margin_remaining = min(
    available_balance,
    portfolio_margin_remaining,
)
```

- [ ] **Step 5: 运行 GREEN 测试并提交**

```bash
python3 -m pytest -q tests/unit/test_account_risk.py
git add src/domain/account_risk.py tests/unit/test_account_risk.py
git commit -m "feat: add dual-position account risk domain"
```

## Task 3: Full-Account Binance Read-Only Snapshot

**Files:**

- Create: `src/infrastructure/binance_usdm_account_risk_snapshot.py`
- Create: `tests/unit/test_binance_usdm_account_risk_snapshot.py`
- Modify: `src/application/action_time/account_safe_facts.py`
- Modify: `tests/unit/test_runtime_account_safe_facts.py`

**Interfaces:**

- Produces: `BinanceAccountRiskSnapshotProvider.fetch -> FullAccountRiskSnapshot`。
- Consumed by: Task 5 exposure projector and Task 8 Action-Time refresh。

- [ ] **Step 1: 写完整性 RED 测试**

```python
async def test_snapshot_reads_all_positions_regular_and_algo_orders(fake_http):
    snapshot = await provider.fetch(timeout_seconds=2)
    assert {call.path for call in fake_http.calls} >= {
        "/fapi/v2/account",
        "/fapi/v2/positionRisk",
        "/fapi/v1/openOrders",
        "/fapi/v1/openAlgoOrders",
        "/fapi/v1/positionSide/dual",
    }
    assert snapshot.symbol_filter_applied is False
    assert snapshot.exchange_write_called is False
```

- [ ] **Step 2: 写 fail-closed RED 测试**

覆盖：任一 endpoint timeout、malformed root、缺 account identity、position mode 不一致、
Algo surface unavailable。任何一项失败都返回 `snapshot_ready=False`，且不能把缺失列表
规范化为空列表。

- [ ] **Step 3: 验证 RED**

```bash
python3 -m pytest -q tests/unit/test_binance_usdm_account_risk_snapshot.py
```

- [ ] **Step 4: 实现 typed provider**

provider 必须在单一
`asyncio.wait_for(asyncio.gather(account_call, positions_call, regular_orders_call, algo_orders_call, mode_call))`
边界内完成所有读取，并返回：

```python
class FullAccountRiskSnapshot(BaseModel):
    account_id: str
    exchange_id: str
    total_wallet_balance: Decimal
    available_balance: Decimal
    exchange_total_initial_margin: Decimal
    position_mode: Literal["one_way", "hedge"]
    positions: list[ExchangePositionRow]
    regular_open_orders: list[ExchangeOpenOrderRow]
    algo_open_orders: list[ExchangeOpenOrderRow]
    source_snapshot_id: str
    observed_at_ms: int
    valid_until_ms: int
    symbol_filter_applied: Literal[False] = False
    exchange_write_called: Literal[False] = False
```

禁止从 `scripts/collect_strategy_group_live_facts_readonly.py` 的 symbol-filtered summary
推断完整账户安全。

同时重排 `account_safe_facts.main` 的事务：第一段短 PG 读取只解析 account/exchange/
runtime identity，随后关闭事务并执行网络快照，最后开启第二段短 PG 事务写 fact/current
projection。当前 `engine.begin()` 包住 signed GET 的结构必须删除，确保交易所延迟不会
持有 PG transaction。

- [ ] **Step 5: 保持旧 flat gate 行为不变并接入 shadow snapshot**

`account_safe_facts.py` 在本任务只生成 shadow projection 输入引用；旧 gate 仍拥有生产
决策权。新增测试断言 shadow snapshot 失败不会伪装成 empty account。

- [ ] **Step 6: 运行 GREEN 与回归并提交**

```bash
python3 -m pytest -q \
  tests/unit/test_binance_usdm_account_risk_snapshot.py \
  tests/unit/test_runtime_account_safe_facts.py
git add src/infrastructure/binance_usdm_account_risk_snapshot.py \
  src/application/action_time/account_safe_facts.py \
  tests/unit/test_binance_usdm_account_risk_snapshot.py \
  tests/unit/test_runtime_account_safe_facts.py
git commit -m "feat: collect full-account risk snapshot"
```

## Task 4: Account-Wide Ownership And Order Purpose

**Files:**

- Create: `src/application/action_time/account_exchange_ownership.py`
- Create: `tests/unit/test_account_exchange_ownership.py`
- Modify: `src/application/action_time/exchange_order_ownership.py`
- Modify: `tests/unit/test_exchange_order_ownership.py`

**Interfaces:**

- Consumes: `FullAccountRiskSnapshot` from Task 3 and existing Ticket command/protection rows。
- Produces: `AccountOrderClassification`, `AccountPositionClassification`,
  `classify_account_exchange_truth`。

- [ ] **Step 1: 写订单用途 RED 矩阵**

```python
@pytest.mark.parametrize(("role", "expected"), [
    ("ENTRY", "working_entry"),
    ("SL", "initial_stop"),
    ("TP1", "take_profit"),
    ("RUNNER_SL", "runner_stop"),
    ("FINAL_EXIT", "final_exit"),
])
def test_owned_order_role_maps_to_purpose(pg, role, expected):
    row = classify_account_exchange_truth(pg, snapshot=_snapshot_with(role))
    assert row.orders[0].purpose == expected
```

- [ ] **Step 2: 写未知/冲突 RED 矩阵**

必须覆盖：

```text
regular order without PG owner -> external_unowned
algo parent owned and actual child matched -> owned_by_ticket
same exchange id and client id point to different Tickets -> identity_conflict
hedge positionSide missing -> mode_or_side_ambiguous
two nonterminal Tickets claim same instrument -> identity_conflict
reduceOnly alone never proves stop/take-profit purpose
```

- [ ] **Step 3: 验证 RED 并实现账户级 classifier**

```bash
python3 -m pytest -q tests/unit/test_account_exchange_ownership.py
```

实现时复用现有 `_pg_order_identities` 证据源，但新增账户级分类不能要求先提供
`current_scope.ticket_id`。旧 `classify_exchange_order_ownership` 改为调用新 classifier
后映射回兼容结果，避免两套归属算法漂移。

- [ ] **Step 4: 运行 GREEN 与旧回归并提交**

```bash
python3 -m pytest -q \
  tests/unit/test_account_exchange_ownership.py \
  tests/unit/test_exchange_order_ownership.py
git add src/application/action_time/account_exchange_ownership.py \
  src/application/action_time/exchange_order_ownership.py \
  tests/unit/test_account_exchange_ownership.py \
  tests/unit/test_exchange_order_ownership.py
git commit -m "feat: classify account-wide exchange ownership"
```

## Task 5: Account Exposure Current Projection

**Files:**

- Create: `migrations/versions/2026-07-14-122_create_account_risk_current_projections.py`
- Create: `src/application/action_time/account_exposure_current.py`
- Create: `tests/unit/test_account_risk_current_migration.py`
- Create: `tests/unit/test_account_exposure_current.py`

**Interfaces:**

- Consumes: `FullAccountRiskSnapshot`、account ownership classification、Ticket lifecycle。
- Produces: `project_account_exposure_current -> AccountExposureProjectionResult`。

- [ ] **Step 1: 写 schema RED 测试**

Migration 122 必须创建：

```text
brc_account_exposure_current
brc_account_budget_current
brc_account_risk_projection_events
brc_budget_reservation_events
```

测试必须验证 exposure current 的唯一键：

```python
("account_id", "exchange_instrument_id", "position_mode", "position_bucket")
```

并验证 budget current 的唯一键：

```python
("account_id", "runtime_profile_id", "risk_policy_version")
```

- [ ] **Step 2: 写 exposure 状态 RED 测试**

覆盖完整守恒矩阵：

```text
reservation only -> reserved
ENTRY working no fill -> working_entry
partial fill + remaining ENTRY -> max(planned, filled risk + remaining risk)
filled without confirmed stop -> open_unprotected + global blocker
filled with exact stop coverage -> open_protected
TP1 filled, runner stop unconfirmed -> keep worst-known held risk
runner stop confirmed -> remaining qty directional risk
flat + matched -> flat, held risk 0, slot false
unknown position owner -> unknown + global blocker
```

- [ ] **Step 3: 验证 RED**

```bash
python3 -m pytest -q \
  tests/unit/test_account_risk_current_migration.py \
  tests/unit/test_account_exposure_current.py
```

- [ ] **Step 4: 实现 current projector**

projector 只接受 typed snapshot，不自行发网络请求。semantic event 的变化判断必须基于：

```python
semantic_fingerprint = sha256(canonical_json({
    "ownership_state": row.ownership_state,
    "exposure_state": row.exposure_state,
    "held_risk": str(row.held_risk),
    "protection_state": row.protection_state,
    "reconciliation_state": row.reconciliation_state,
    "first_blocker": row.first_blocker,
})).hexdigest()
```

相同 fingerprint 只更新 freshness/current，不追加重复业务事件。

- [ ] **Step 5: 运行 GREEN 并提交**

```bash
python3 -m pytest -q \
  tests/unit/test_account_risk_current_migration.py \
  tests/unit/test_account_exposure_current.py
git add migrations/versions/2026-07-14-122_create_account_risk_current_projections.py \
  src/application/action_time/account_exposure_current.py \
  tests/unit/test_account_risk_current_migration.py \
  tests/unit/test_account_exposure_current.py
git commit -m "feat: project account exposure current"
```

## Task 6: Budget Reservation Transition Conservation And Data Repair

**Files:**

- Create: `src/application/action_time/budget_reservation_transition.py`
- Create: `migrations/versions/2026-07-14-123_repair_terminal_budget_reservations.py`
- Create: `tests/unit/test_budget_reservation_transition.py`
- Create: `tests/unit/test_terminal_budget_reservation_repair_migration.py`
- Modify: `src/application/action_time/action_time_ticket.py`
- Modify: `src/application/action_time/ticket_bound_budget_settlement.py`
- Modify: `scripts/run_server_product_state_refresh_sequence.py`

**Interfaces:**

- Produces: `transition_budget_reservation -> BudgetReservationTransitionResult`。
- Consumed by: Ticket creation/expiry、lifecycle settlement、refresh cleanup、Task 7 budget projector。

- [ ] **Step 1: 写状态机 RED 测试**

```python
@pytest.mark.parametrize(("before", "after"), [
    ("active", "consumed"),
    ("active", "expired"),
    ("active", "invalidated"),
    ("consumed", "released"),
])
def test_allowed_reservation_transitions(conn, before, after):
    result = transition_budget_reservation(
        conn,
        budget_reservation_id="budget-1",
        to_status=after,
        reason="unit_test",
        evidence_ref="evidence-1",
        now_ms=1_752_480_000_000,
    )
    assert result.status == after
```

反向转换 `released -> consumed`、`expired -> active`、`consumed -> active` 必须返回
`budget_reservation_transition_invalid`，且不修改行。

- [ ] **Step 2: 写泄漏复现 RED 测试**

```python
def test_expired_presubmit_ticket_releases_consumed_reservation(conn):
    seed_ticket(status="expired", exchange_write_called=False)
    seed_reservation(status="consumed", ticket_id="ticket-expired")
    expire_action_time_objects(conn, now_ms=NOW_MS)
    assert reservation("ticket-expired").status == "released"
    assert reservation("ticket-expired").release_reason == (
        "terminal_presubmit_ticket_capacity_reclaimed"
    )
```

同时写保护测试：submitted Ticket、存在 exchange command write、存在非零 exposure、
reconciliation unknown 中任一成立时，repair 不得释放。

- [ ] **Step 3: 验证 RED**

```bash
python3 -m pytest -q \
  tests/unit/test_budget_reservation_transition.py \
  tests/unit/test_terminal_budget_reservation_repair_migration.py
```

- [ ] **Step 4: 实现统一 transition service**

service 必须在同一事务中：

```text
SELECT reservation FOR UPDATE
-> validate allowed edge and evidence
-> UPDATE brc_budget_reservations
-> INSERT brc_budget_reservation_events
-> return typed result
```

`action_time_ticket._insert_ticket_bundle` 不再直接 `SET status='consumed'`；
`ticket_bound_budget_settlement` 和 server refresh 不再直接散落更新 reservation 状态。

- [ ] **Step 5: 实现 migration 123 的受约束数据修复**

Migration 仅修复同时满足以下条件的行：

```sql
reservation.status = 'consumed'
AND ticket.status IN ('expired', 'finalgate_rejected', 'invalidated', 'superseded')
AND NOT EXISTS (
  SELECT 1 FROM brc_ticket_bound_exchange_commands c
  WHERE c.ticket_id = ticket.ticket_id
    AND c.exchange_write_called = true
)
AND NOT EXISTS (
  SELECT 1 FROM brc_account_exposure_current e
  WHERE e.owner_ticket_id = ticket.ticket_id
    AND e.position_slot_claimed = true
)
```

每一行同时写入 reservation event，`evidence_ref` 指向 migration 123。不能断言固定修复
48 行；测试使用形状断言，生产部署后再只读核对实际数量。

- [ ] **Step 6: GREEN、现有 expiry/settlement 回归并提交**

```bash
python3 -m pytest -q \
  tests/unit/test_budget_reservation_transition.py \
  tests/unit/test_terminal_budget_reservation_repair_migration.py \
  tests/unit/test_action_time_ticket_materialization.py \
  tests/unit/test_action_time_ticket_materialization_sequence.py \
  tests/unit/test_ticket_bound_lifecycle_finalizer.py
git add src/application/action_time/budget_reservation_transition.py \
  migrations/versions/2026-07-14-123_repair_terminal_budget_reservations.py \
  src/application/action_time/action_time_ticket.py \
  src/application/action_time/ticket_bound_budget_settlement.py \
  scripts/run_server_product_state_refresh_sequence.py \
  tests/unit/test_budget_reservation_transition.py \
  tests/unit/test_terminal_budget_reservation_repair_migration.py
git commit -m "fix: conserve ticket budget reservation lifecycle"
```

## Task 7: Account Budget Current And Capacity Arbitration

**Files:**

- Create: `src/application/action_time/account_budget_current.py`
- Create: `src/application/action_time/account_capacity_reservation.py`
- Create: `tests/unit/test_account_budget_current.py`
- Create: `tests/unit/test_account_capacity_reservation.py`

**Interfaces:**

- Consumes: Tasks 1、2、5、6。
- Produces: `project_account_budget_current`、
  `reserve_account_capacity_for_candidate`、内部原子 helper
  `decide_and_persist_locked_account_capacity`。

- [ ] **Step 1: 写风险去重 RED 测试**

```python
def test_consumed_reservation_is_claim_ceiling_not_additive_to_open_exposure(conn):
    seed_consumed_reservation(ticket_id="ticket-1", planned_risk="15")
    seed_exposure(ticket_id="ticket-1", actual_risk="13", state="open_protected")
    budget = project_account_budget_current(conn, snapshot=_snapshot())
    assert budget.portfolio_held_risk == Decimal("13")
    assert budget.reserved_risk == Decimal("0")
```

部分成交 + working remainder 测试必须断言：

```python
held_risk == max(planned_reservation, filled_actual_risk + remaining_entry_risk)
```

- [ ] **Step 2: 写 slot、cluster、margin RED 测试**

覆盖：

```text
one protected position + no pending claim -> claimed_position_slots=1
one position + one pending different instrument -> claimed_position_slots=2
same instrument pending claim -> blocked before risk sizing
unreflected pending margin subtracts once
exchange open-order margin is not subtracted twice
missing cluster mapping -> risk_cluster_membership_missing
stale exposure row -> account_exposure_projection_stale
unknown exposure -> account_exposure_unknown_global_fail_closed
```

- [ ] **Step 3: 写 PostgreSQL row-lock RED 测试**

使用两个独立 connection/transaction：第一个锁定 budget current 并预占，第二个必须等待；
第一个 commit 后，第二个重新读取 `projection_version` 并因剩余容量或 slot 不足而失败。
测试禁止用 SQLite 模拟该并发语义。

- [ ] **Step 4: 验证 RED**

```bash
python3 -m pytest -q \
  tests/unit/test_account_budget_current.py \
  tests/unit/test_account_capacity_reservation.py
```

- [ ] **Step 5: 实现 budget projector**

汇总顺序固定为：

```text
load fresh account risk policy
-> load fresh exposure current rows
-> load active/consumed reservations
-> group by Ticket/instrument
-> apply lifecycle held-risk rule once
-> aggregate portfolio + cluster + margin + slots
-> write one current row with monotonic projection_version
```

禁止以 reservation 状态数量代替 position slot，禁止从 Ticket status 单独推导实际仓位。

- [ ] **Step 6: 实现 capacity reservation**

函数签名固定为：

```python
def reserve_account_capacity_for_candidate(
    conn: sa.engine.Connection,
    *,
    candidate: AccountCapacityCandidate,
    expected_source_snapshot_id: str,
    expected_projection_version: int,
    now_ms: int,
) -> AccountCapacityReservationResult:
    budget_table = sa.Table(
        "brc_account_budget_current", sa.MetaData(), autoload_with=conn
    )
    budget = conn.execute(
        sa.select(budget_table)
        .where(
            budget_table.c.account_id == candidate.account_id,
            budget_table.c.runtime_profile_id == candidate.runtime_profile_id,
        )
        .with_for_update()
    ).mappings().one()
    return decide_and_persist_locked_account_capacity(
        conn=conn,
        candidate=candidate,
        locked_budget=dict(budget),
        expected_source_snapshot_id=expected_source_snapshot_id,
        expected_projection_version=expected_projection_version,
        now_ms=now_ms,
    )
```

内部第一条容量语义 SQL 必须是目标 budget current 行的 `SELECT target_account_budget_row FOR UPDATE`。锁后再次
校验 snapshot、version、validity 和 policy，随后调用 Task 2 pure domain 计算 auto-downsize。

- [ ] **Step 7: GREEN 并提交**

```bash
python3 -m pytest -q \
  tests/unit/test_account_budget_current.py \
  tests/unit/test_account_capacity_reservation.py
git add src/application/action_time/account_budget_current.py \
  src/application/action_time/account_capacity_reservation.py \
  tests/unit/test_account_budget_current.py \
  tests/unit/test_account_capacity_reservation.py
git commit -m "feat: arbitrate account risk capacity atomically"
```

## Task 8: Replace Flat Gate Inside The Existing Action-Time Transaction

**Files:**

- Modify: `src/application/action_time/account_safe_facts.py`
- Modify: `src/application/action_time/promotion_action_time_lane.py`
- Modify: `src/application/action_time/ticket_materialization_sequence.py`
- Modify: `src/application/action_time/action_time_ticket.py`
- Modify: `src/infrastructure/runtime_control_state_repository.py`
- Modify: `tests/unit/test_runtime_account_safe_facts.py`
- Modify: `tests/unit/test_action_time_ticket_materialization.py`
- Modify: `tests/unit/test_action_time_ticket_materialization_sequence.py`
- Create: `tests/integration/test_dual_position_account_risk_postgres.py`

**Interfaces:**

- Consumes: Tasks 1-7。
- Produces: 第二个不同 instrument Ticket 通过原 Action-Time/Ticket 主链创建。

- [ ] **Step 1: 写单仓兼容 RED 测试**

现有 flat 账户用 2.5% policy 创建 Ticket 时，除 risk budget/quantity 改为 2.5% 外，
promotion、lane、Ticket、Runtime Safety State、FinalGate handoff identity 全部保持原结构。

- [ ] **Step 2: 写第二仓 GREEN-path RED 集成测试**

PostgreSQL 场景：

```text
existing ETH Ticket = submitted + open_protected + matched + 15U held risk
new SOL signal = fresh + exact invocation + different instrument + different cluster
wallet = 600U
new ticket target risk = 15U
result = one new lane + one reservation + one Ticket
total planned/held risk <= 30U, below 36U portfolio cap
open real lane count remains 1
exchange write count remains 0 during Ticket materialization
```

- [ ] **Step 3: 写阻断/缩量 RED 矩阵**

| 场景 | 精确期望 |
| --- | --- |
| 同 instrument 第二 Ticket | `account_instrument_already_claimed` |
| 同 cluster 已用 15U、wallet 600U | 第二 Ticket `allocated_risk=9U` 并按 step 自动缩量 |
| 已占两个 slot | `max_concurrent_positions_reached` |
| unknown Algo order | `account_exchange_order_unknown_global_fail_closed` |
| exposure mismatch | `account_exposure_reconciliation_mismatch` |
| Budget Current 过期 | `account_budget_current_stale` |
| CAS 版本变化 | `account_budget_projection_version_changed`，不创建 reservation/lane/Ticket |

- [ ] **Step 4: 验证 RED**

```bash
python3 -m pytest -q \
  tests/unit/test_runtime_account_safe_facts.py \
  tests/unit/test_action_time_ticket_materialization.py \
  tests/unit/test_action_time_ticket_materialization_sequence.py \
  tests/integration/test_dual_position_account_risk_postgres.py
```

- [ ] **Step 5: 接入现有原子事务**

目标顺序必须是：

```python
with conn.begin_nested():
    persist_prefetched_action_time_facts(
        invocation=evidence.invocation,
        prefetched_facts=prefetched_action_time_facts,
        now_ms=now_ms,
    )
    project_account_exposure_current(
        conn, snapshot=full_account_snapshot, now_ms=now_ms
    )
    project_account_budget_current(
        conn,
        account_id=capacity_candidate.account_id,
        runtime_profile_id=capacity_candidate.runtime_profile_id,
        now_ms=now_ms,
    )
    capacity = reserve_account_capacity_for_candidate(
        conn,
        candidate=capacity_candidate,
        expected_source_snapshot_id=full_account_snapshot.source_snapshot_id,
        expected_projection_version=expected_projection_version,
        now_ms=now_ms,
    )
    materialize_action_time_invocation_promotion_action_time_lane(
        conn,
        evidence=evidence,
        capacity_decision=capacity,
    )
    materialize_action_time_ticket(
        conn,
        now_ms=now_ms,
    )
```

网络 snapshot 必须在进入 `begin_nested()` 前完成。任一步失败，reservation、lane、Ticket
全部回滚；snapshot/current semantic event 可在独立短事务持久化，但不能授予旧版本容量。

- [ ] **Step 6: 删除旧 flat boolean 的 live-submit authority**

在 `activation_state='active'` 时：

```text
account_safe = account_budget_current.new_entry_allowed
account_capacity_projection_ref = account_budget_current_id
account_capacity_projection_version = projection_version
```

`active_position_clear`、`open_orders_clear`、`active_position_or_open_order_clear` 不再进入
promotion/Ticket blocker。shadow 时仍计算旧结论用于对比，但 shadow 不能授权第二 Ticket。

- [ ] **Step 7: GREEN、核心回归并提交**

```bash
python3 -m pytest -q \
  tests/unit/test_runtime_account_safe_facts.py \
  tests/unit/test_action_time_ticket_materialization.py \
  tests/unit/test_action_time_ticket_materialization_sequence.py \
  tests/unit/test_strategy_runtime_safety_readiness.py \
  tests/unit/test_action_time_finalgate_preflight_materialization.py \
  tests/integration/test_dual_position_account_risk_postgres.py
git add src/application/action_time/account_safe_facts.py \
  src/application/action_time/promotion_action_time_lane.py \
  src/application/action_time/ticket_materialization_sequence.py \
  src/application/action_time/action_time_ticket.py \
  src/infrastructure/runtime_control_state_repository.py \
  tests/unit/test_runtime_account_safe_facts.py \
  tests/unit/test_action_time_ticket_materialization.py \
  tests/unit/test_action_time_ticket_materialization_sequence.py \
  tests/integration/test_dual_position_account_risk_postgres.py
git commit -m "feat: allow bounded second-position ticket materialization"
```

## Task 9: Lifecycle Reprojection, Capacity Release And Owner State

**Files:**

- Modify: `src/application/action_time/post_submit_reconciliation_tick.py`
- Modify: `src/application/action_time/ticket_bound_budget_settlement.py`
- Modify: `src/application/action_time/ticket_bound_lifecycle_finalizer.py`
- Modify: `src/application/readmodels/runtime_safety_truth.py`
- Modify: `scripts/ops/check_tokyo_runtime_ops_health_once.py`
- Create: `tests/unit/test_account_risk_lifecycle_reprojection.py`
- Modify: `tests/unit/test_tokyo_runtime_ops_health_lifecycle.py`

**Interfaces:**

- Consumes: current lifecycle reconciliation result。
- Produces: exposure/budget refresh、精确容量释放、Owner 可读账户状态。

- [ ] **Step 1: 写 lifecycle 守恒 RED 测试**

```text
protected fill -> exposure open_protected and reservation not additive
TP1 fill + runner unconfirmed -> no risk release
runner confirmed -> recompute remaining qty risk
manual exact close + matched -> flat and release exactly once
duplicate reconciliation tick -> no duplicate reservation event
unknown outcome -> worst-known hold and new-entry global fail-closed
```

- [ ] **Step 2: 写 Owner 语言 RED 测试**

健康场景只输出产品语言：

```text
当前 1/2 个仓位正在运行；仍可接收一个不同品种机会
当前 2/2 个仓位正在运行；新机会暂不入场
账户事实需要重新对账；系统已停止新开仓，现有保护继续运行
```

默认 Owner card 不暴露 `FOR UPDATE`、CAS、RequiredFacts、FinalGate、projection row id。

- [ ] **Step 3: 验证 RED 并实现事件驱动重投影**

每次 post-submit reconciliation 产生以下任一变化时调用 projector：position qty、ENTRY
working qty、confirmed stop、TP1、Runner Stop、flat、ownership、reconciliation。相同语义
tick 不重复写业务 event。

- [ ] **Step 4: 运行 GREEN 与生命周期回归并提交**

```bash
python3 -m pytest -q \
  tests/unit/test_account_risk_lifecycle_reprojection.py \
  tests/unit/test_ticket_bound_lifecycle_finalizer.py \
  tests/unit/test_ticket_bound_lifecycle_scheduler.py \
  tests/unit/test_tokyo_runtime_ops_health_lifecycle.py
git add src/application/action_time/post_submit_reconciliation_tick.py \
  src/application/action_time/ticket_bound_budget_settlement.py \
  src/application/action_time/ticket_bound_lifecycle_finalizer.py \
  src/application/readmodels/runtime_safety_truth.py \
  scripts/ops/check_tokyo_runtime_ops_health_once.py \
  tests/unit/test_account_risk_lifecycle_reprojection.py \
  tests/unit/test_tokyo_runtime_ops_health_lifecycle.py
git commit -m "feat: reconcile account risk through ticket lifecycle"
```

## Task 10: Shadow Certification, Release Gate, Activation And Rollback Proof

**Files:**

- Modify: `docs/current/DUAL_POSITION_HARD_CAP_ACCOUNT_RISK_MODEL_V0_DESIGN.md`
- Modify: `docs/current/DUAL_POSITION_HARD_CAP_ACCOUNT_RISK_MODEL_V0_IMPLEMENTATION_PLAN.md`
- Modify: `docs/current/MAIN_CONTROL_ROADMAP.md`
- Modify: `docs/current/MAINLINE_ENGINEERING_PROGRAM_PLAN.md`
- Modify: `docs/current/RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md`
- Create: `tests/unit/test_dual_position_account_risk_release_acceptance.py`

**Interfaces:**

- Consumes: Tasks 1-9 complete implementation。
- Produces: shadow acceptance evidence、active policy event、rollback proof、current planning truth。

- [ ] **Step 1: 运行完整本地分层测试**

Fast lane：

```bash
python3 -m pytest -q \
  tests/unit/test_account_risk.py \
  tests/unit/test_binance_usdm_account_risk_snapshot.py \
  tests/unit/test_account_exchange_ownership.py \
  tests/unit/test_account_exposure_current.py \
  tests/unit/test_account_budget_current.py \
  tests/unit/test_account_capacity_reservation.py \
  tests/unit/test_budget_reservation_transition.py
```

Integration lane：

```bash
python3 -m pytest -q tests/integration/test_dual_position_account_risk_postgres.py
```

Release lane：

```bash
python3 -m pytest -q
```

Expected: 0 failures；全量耗时作为 release certification 记录，不要求回到 fast lane 速度。

- [ ] **Step 2: 运行 PG migration 和文件 I/O gate**

```bash
alembic upgrade head
python3 scripts/audit_production_runtime_file_io.py
python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
```

Expected：migration head 123；`performance_risk.status=clear`；无 tracked output 改动；
无新增生产 JSON/MD reader/writer。

- [ ] **Step 3: 部署 shadow，不改变生产交易容量**

```bash
python3 scripts/ops/set_account_risk_policy.py \
  --mode shadow \
  --database-url "$PG_DATABASE_URL"
```

部署后必须只读证明：

```text
production max_concurrent_positions remains 1 for live authority
shadow policy carries 0.025 / 2 / 0.06 / 0.04 / 0.90 / 10
current ETH position has one owner_ticket_id
regular TP1 and Algo SL are both classified and non-conflicting
exposure_state=open_protected
reconciliation_state=matched
position_slot_claimed=true
unknown order count=0
unknown position count=0
terminal reservation leakage count=0
```

- [ ] **Step 4: 运行影子差异与故障注入认证**

认证矩阵：

| 注入 | 期望 |
| --- | --- |
| 删除 Algo stop 可见性 | shadow 全局阻断新 ENTRY |
| 制造 unowned regular order | shadow 全局阻断新 ENTRY |
| 令 exposure snapshot 过期 | shadow 全局阻断新 ENTRY |
| 两事务同时申请第二 slot | 只有一个事务取得容量 |
| 同 instrument 第二候选 | 精确 instrument blocker |
| 同 cluster 容量只剩 1.5% | 自动缩量，不放大别的上限 |
| TP1 后 Runner 未确认 | 不释放风险 |
| rollback policy=1 | 不强平、不撤保护、停止新 ENTRY |

- [ ] **Step 5: 激活 2.5% 双仓位 policy**

只有 Step 1-4 全部通过才执行：

```bash
python3 scripts/ops/set_account_risk_policy.py \
  --mode activate \
  --database-url "$PG_DATABASE_URL"
```

激活后 read-only acceptance 必须证明 active current policy 精确为：

```text
planned_stop_risk_fraction=0.025
max_concurrent_positions=2
max_portfolio_open_risk_fraction=0.06
max_cluster_open_risk_fraction=0.04
max_portfolio_initial_margin_fraction=0.90
max_leverage=10
max_new_action_time_lanes=1
automatic_downsize_enabled=true
unknown_exposure_policy=global_fail_closed
```

- [ ] **Step 6: 激活后非交易验收**

不插入生产 synthetic signal/Ticket。只读核对 watcher、monitor、lifecycle timer、PG
projection freshness、现有 ETH 保护和 account budget current；自然新信号出现时，按 P0
interrupt 记录其第二 Ticket chain，不绕过当前官方路径。

- [ ] **Step 7: 回滚演练**

在 disposable PostgreSQL 和非 exchange-write 环境执行：

```bash
python3 scripts/ops/set_account_risk_policy.py \
  --mode rollback-single-position \
  --database-url "$TEST_PG_DATABASE_URL"
```

断言已有两个 exposure 不被关闭/删除，所有 protection/lifecycle 行保持，新的 ENTRY
capacity=false。演练完成后不把测试 policy 写入生产。

- [ ] **Step 8: 更新 current docs、最终验证并提交**

```bash
python3 scripts/audit_production_runtime_file_io.py
python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
git diff --check
git add docs/current/DUAL_POSITION_HARD_CAP_ACCOUNT_RISK_MODEL_V0_DESIGN.md \
  docs/current/DUAL_POSITION_HARD_CAP_ACCOUNT_RISK_MODEL_V0_IMPLEMENTATION_PLAN.md \
  docs/current/MAIN_CONTROL_ROADMAP.md \
  docs/current/MAINLINE_ENGINEERING_PROGRAM_PLAN.md \
  docs/current/RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md \
  tests/unit/test_dual_position_account_risk_release_acceptance.py
git commit -m "docs: accept dual-position account risk v0"
```

## Review Checkpoints

| Checkpoint | Tasks | 可继续条件 | Hard Stop |
| --- | --- | --- | --- |
| **A Policy + Domain** | 1-2 | Owner 数值、Decimal 公式、账户级 policy authority 全部固定 | 任何策略 scope policy 与账户 policy 双 authority |
| **B Facts + Ownership** | 3-4 | 全账户 position/regular/algo 完整，归属与用途唯一 | 缺任一 exchange surface 或使用 symbol-filtered empty 代替 |
| **C Projection + Conservation** | 5-7 | exposure/budget 去重、reservation 泄漏修复、row lock/CAS 成立 | risk/margin 双计数、未知事实被当作 0 |
| **D Action-Time + Lifecycle** | 8-9 | 第二 Ticket 复用现有主链，容量随 lifecycle 恰好释放一次 | 新执行路径、FinalGate/Operation Layer/保护绕过 |
| **E Shadow + Activation** | 10 | 当前真实 ETH 样本和故障矩阵通过，production I/O audit clear | shadow 未过即改 active，或 activation 隐式扩大到第三仓 |

## Final Capability Acceptance

实施完成后必须能够用一个 production-shaped PostgreSQL 测试证明：

```text
Ticket A: ETH, protected, 2.5% planned risk
Ticket B: SOL, different instrument, bounded by remaining account capacity

one account
-> two owned positions at most
-> one new Action-Time Lane at a time
-> no duplicate instrument claim
-> portfolio held risk <= 6%
-> cluster held risk <= 4%
-> initial margin <= 90%
-> each new Ticket planned risk <= 2.5%
-> leverage <= 10x
-> each position protected and reconciled
-> flat releases reservation/risk/slot exactly once
```

## Execution Stop Rule

本计划在 **Task 10 shadow acceptance** 前不改变生产双仓位权限。任一 checkpoint 发现
完整账户事实、归属、保护、风险去重、原子预占或生命周期释放无法唯一证明时，停止
activation，保留单仓位生产能力，并把 first blocker 固化到 PG/current truth。
