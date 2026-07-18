---
title: DUAL_POSITION_ACCOUNT_RISK_V0_RELEASE_BLOCKER_REMEDIATION_IMPLEMENTATION_PLAN
status: LOCAL_REMEDIATION_CERTIFICATION_REOPENED
authority: docs/current/DUAL_POSITION_ACCOUNT_RISK_V0_RELEASE_BLOCKER_REMEDIATION_IMPLEMENTATION_PLAN.md
implements: docs/current/DUAL_POSITION_ACCOUNT_RISK_V0_RELEASE_BLOCKER_REMEDIATION_DESIGN.md
last_verified: 2026-07-18
implementation_state: T01_T12_COMPLETE_LOCAL_ONLY
integration_state: LOCAL_REMEDIATION_CERTIFICATION_REOPENED
component_certification: T01_T12_EVIDENCE_RETAINED
release_gate_blocker: docs/current/P0_RUNTIME_OBSERVATION_TRUTH_AND_FORENSICS_REMEDIATION_IMPLEMENTATION_PLAN.md
certified_source_commit: e4f49dcfa77932f6ec440b3a869943eb2ade73a1
repair_baseline: 60bb7fedcd2b9bd300cef900c6bbb304c5a34770
repair_branch: codex/dual-position-account-risk-remediation-v1
repair_worktree: /Users/jiangwei/Documents/final/.worktrees/dual-position-account-risk-remediation-v1
production_state: UNCHANGED
deployment_state: NOT_AUTHORIZED
policy_activation: NOT_PERFORMED
exchange_write: 0
current_migration_head: 136_LOCAL_ONLY
planned_migration_head: 136
---

# Dual-Position Account Risk V0 Unified Remediation Implementation Plan

> **For implementation agents:** execute this plan with
> `superpowers:executing-plans`, `superpowers:test-driven-development` and
> `superpowers:verification-before-completion`. The main Codex controller owns every core-file
> edit and final integration decision. A bounded non-core task may be delegated only through
> a task card containing all fields in section 2.3; shared-worktree writers must remain
> serialized.

**Goal:** turn merge baseline `60bb7fedcd2b9bd300cef900c6bbb304c5a34770`
into one locally certified repair branch that conserves account slot, stop risk, cluster risk
and margin from capacity fact through Claim, Ticket, FinalGate, lifecycle release, runner
recovery and deploy identity.

**Architecture:** preserve Ticket as the sole trade-lifecycle owner; use one immutable
Capacity Claim plus one mutable Reservation lifecycle; derive Account Exposure Current and
one Account Budget Current row from complete exchange snapshots and effective Claims; keep
all current authority in PostgreSQL; repair release lifecycle and deployment gates in the
existing production path rather than adding parallel engines.

**Tech stack:** Python 3.10, Pydantic, `decimal.Decimal`, SQLAlchemy, Alembic,
PostgreSQL, pytest, Binance USD-M signed GET readers, hashed runtime dependency lock and the
Tokyo immutable-release state machine.

## 1. Execution Authorization And Frozen Topology

### 1.1 Current authorization

**本计划的 T01-T12 组件工作已经完成，但整分支状态因 P0 Runtime Observation Truth
缺陷重新打开为 `LOCAL_REMEDIATION_CERTIFICATION_REOPENED`，部署状态为
`DEPLOYMENT_NO_GO`。**
PostgreSQL、消费者、部署状态机、审计、完整仓库回归与 clean Linux/amd64 CPython 3.10
hash-lock 安装/导入门禁均已通过。最终 lock gate 使用官方 PyPI、只读 worktree、
`--require-hashes`、禁用受污染缓存，完成四个要求导入及 `pip check`，退出码为 `0`；lock、
版本和 hash 无修改。上述结果继续作为组件证据，但必须与
`P0_RUNTIME_OBSERVATION_TRUTH_AND_FORENSICS_REMEDIATION_IMPLEMENTATION_PLAN.md`
在同一 exact HEAD 重新认证后，才能恢复整分支部署候选状态。批准范围仍仅为本地修复、
本地认证与预部署审查。以下事项仍在本计划之外：

- push or pull-request publication;
- Tokyo staging, deploy or service mutation;
- production migration apply;
- account-risk policy activation or live-profile expansion;
- exchange write, withdrawal, transfer or credential mutation.

### 1.2 Required worktree

| Property | Required value | Verification |
| --- | --- | --- |
| **Worktree** | `/Users/jiangwei/Documents/final/.worktrees/dual-position-account-risk-remediation-v1` | `pwd` |
| **Branch** | `codex/dual-position-account-risk-remediation-v1` | `git branch --show-current` |
| **Repair ancestor** | `60bb7fedcd2b9bd300cef900c6bbb304c5a34770` | `git merge-base --is-ancestor 60bb7fed HEAD` |
| **Release parent** | `6aad77ea4c67609ceed9b545d392de4ff1eaab3b` | `git rev-list --parents -n 1 60bb7fed` |
| **Budget parent** | `5b67181e2d287fb306bae953075c89e2c6be32ab` | `git rev-list --parents -n 1 60bb7fed` |
| **Migration head before repair** | `133` | sorted migration inventory |
| **Migration head after repair** | `136` | migration and deploy-default tests |

The docs-only plan commit may be a descendant of `60bb7fed`; it does not replace the frozen
code ancestry. The source release and budget worktrees are read-only references. Their
working-tree changes, especially the release worktree's pre-existing
`requirements-runtime.lock` modification, must never be copied, staged, restored or edited.

### 1.3 Start gate

Run before the first implementation edit:

```bash
pwd
git status --short --branch
git branch --show-current
git merge-base --is-ancestor 60bb7fedcd2b9bd300cef900c6bbb304c5a34770 HEAD
git rev-list --parents -n 1 60bb7fedcd2b9bd300cef900c6bbb304c5a34770
python3 scripts/validate_current_docs_authority.py
git diff --check
```

Expected outcome: exact worktree and branch, correct two merge parents, only approved local
changes, current-doc authority valid and no whitespace error. Any mismatch is a **hard stop**.

## 2. Program Control Packet

### 2.1 Global authority model

```text
Owner controls policy.
System executes process.
Tradeability Decision answers can-trade.
Runtime Safety State answers live-submit safety.
Review updates strategy governance.
```

### 2.2 Chain position and state transition

| Field | Before implementation | After all local gates |
| --- | --- | --- |
| **Chain Position** | Local two-parent merge; deep-review NO-GO | Local production-shape capability certified |
| **Live Enablement State** | Account-capacity chain not conserved | Shadow/deploy review candidate only |
| **First Blocker** | CAP-01 capacity-base fact cannot bind | Separate deployment authorization remains |
| **Runtime Safety State** | No new authority | No new authority |
| **Production State** | Unchanged | Unchanged |
| **Policy Activation** | Not performed | Not performed |
| **Exchange Writes** | `0` | `0` |

### 2.3 Mandatory task-card fields

Every delegated or resumed task must carry these exact fields:

1. **Task ID**
2. **Goal**
3. **Why**
4. **Allowed files**
5. **Forbidden files**
6. **Requirements**
7. **Global Authority Model**
8. **Chain Position**
9. **Live Enablement State Before**
10. **Live Enablement State After**
11. **Blocker Removed Or Reclassified**
12. **Per-Symbol / Per-Fact Acceptance**
13. **Stop Condition**
14. **Capability Unlocked**
15. **Next Engineering Bottleneck**
16. **Rehearsal/Simulation Boundary**
17. **Tests**
18. **Done When**
19. **Hard Stop**

### 2.4 Global implementation constraints

The following inherited fields are copied verbatim into every T01-T12 execution card:

- **Global Authority Model:** section 2.1, without modification.
- **Chain Position:** the task's position in section 3; no task may skip its dependencies.
- **Live Enablement State Before:** local deep-review NO-GO, production unchanged.
- **Live Enablement State After:** only the named local capability is unlocked; runtime submit
  authority and production state remain unchanged.
- **Stop Condition:** stop at the task's named Done When boundary and commit only that task.
- **Tests:** the task's TDD steps and commands are mandatory, not examples.

- Use `Decimal` for every quantity, price, risk, margin and multiplier calculation.
- Add no PG + file dual authority, current JSON/Markdown/YAML/JSONL reader or recurring
  report writer.
- Keep full-account network I/O outside the Account Budget `FOR UPDATE` transaction.
- Do not edit migrations `086` or `121 -> 133`; use only forward migrations `134 -> 136`.
- Do not make fixtures seed Exposure or Budget in the final production-shape test.
- Preserve existing exit, protection, reconciliation and settlement during rollback.
- Fail closed for unknown ownership, unknown exchange outcome, unsupported calculation kind,
  stale facts, cross-account identity and ambiguous migration mapping.
- Do not widen StrategyGroup, account, instrument, side, leverage, notional or runtime scope.
- The following core file remains main-controller-only even when a task is delegated:
  `src/infrastructure/exchange_gateway.py`.
- Full-suite green does not override a failing PostgreSQL production-shape, migration,
  runtime-lock, file-I/O or performance gate.

## 3. Execution Graph And Commit Boundaries

| Order | Task | Depends on | Repairs | Local commit subject |
| ---: | --- | --- | --- | --- |
| **1** | **T01 Snapshot truth** | Start gate | SNAP-01/02/03 | `fix: preserve complete account snapshot truth` |
| **2** | **T02 Ownership identity** | T01 | OWN-01/02; OWN-03 contract | `fix: enforce account instrument and hedge ownership identity` |
| **3** | **T03 Capacity-base fact producer** | T01 | CAP-01 producer only | `fix: produce independent account capacity base fact` |
| **4** | **T04 Fact binding and current authority** | T02, T03 | CAP-01 binding, CAP-03/04/05/06, CUR-01/03, OWN-03, migration 134 | `fix: conserve account risk current authority` |
| **5** | **T05 Atomic Claim-to-Ticket** | T04 | CAP-02 | `fix: atomically project account capacity claims` |
| **6** | **T06 Lifecycle release** | T05 | CUR-02 | `fix: release and reproject terminal capacity` |
| **7** | **T07 Runner recovery** | T01 | RUN-01/02/04 | `fix: restore runner trailing and exact fill recovery` |
| **8** | **T08 Adoption lifecycle** | T06, T07 | RUN-03/05, migration 135 | `fix: serialize effective exit policy adoption` |
| **9** | **T09 Instrument calculation** | T08 | EXT-01/02, migration 136 | `fix: price linear contracts with explicit multiplier` |
| **10** | **T10 Release identity** | T09 | DEP-01..07 | `fix: bind runtime and release deployment identity` |
| **11** | **T11 Integrated certification** | T01-T10 | QA-01 and cross-unit | `test: certify dual position remediation chain` |
| **12** | **T12 Authority closure** | T11 | Documentation state | `docs: certify dual position remediation readiness` |

Tasks are serial at shared mutation boundaries. T07 may be researched in parallel with
T03-T06, but it is merged only after T06 is green. T08 must precede migration 136 so the
Alembic chain remains `134 -> 135 -> 136`.

### 3.1 Inherited-invariant task and test map

| Invariant ID | Owning tasks | Required integrated tests |
| --- | --- | --- |
| **INV-01 rounded stop risk** | T05, T09, T11 | `test_account_capacity_materialization.py`, `test_account_capacity_reservation.py`, `test_account_capacity_finalgate_guard.py` |
| **INV-02 immutable policy epoch** | T04, T05, T11 | `test_account_budget_current.py`, `test_account_capacity_claim_persistence.py`, `test_account_capacity_postgres.py` |
| **INV-03 quantity-specific protection segments** | T02, T04, T11 | `test_account_exposure_current.py`, `test_account_risk_lifecycle_reprojection.py`, remediation full-chain |
| **INV-04 nonterminal ownership** | T02, T11 | `test_account_exposure_current.py`, `test_ticket_exit_execution_binding.py`, full-chain identity negatives |
| **INV-05 lock-first PG arbitration** | T04, T05, T11 | two concurrent first Claims with no Budget Current row in `test_account_capacity_postgres.py` |

T11 must rerun every direct test above; a complete-suite pass without the direct invariant
assertions does not recertify the inherited behavior.

## 4. T01 — Preserve Complete Account Snapshot Truth

### 4.1 Task packet

**Task ID:** `DPR-REMED-T01`

**Goal:** normalize zero positions, Algo client identity and partial-fill quantities without
dropping or inventing exchange truth.

**Why:** an invalid zero row can remove the entire account fact; missing `clientAlgoId` and
executed quantity can misclassify protection or overstate remaining working risk.

**Allowed files:**

- `src/infrastructure/binance_usdm_account_risk_snapshot.py`
- `src/infrastructure/binance_usdm_streaming_signed_reader.py`
- `src/infrastructure/streaming_http_json.py` only if the common stream adapter cannot retain
  the required scalar fields
- `tests/unit/test_binance_usdm_account_risk_snapshot.py`
- `tests/unit/test_streaming_http_json.py`

**Forbidden files:** risk models, Ticket/FinalGate services, gateway mutation methods,
migrations and deploy scripts.

**Requirements:**

1. Parse symbol, `positionAmt` and position bucket before validating entry price.
2. Accept and discard `positionAmt=0, entryPrice=0`; require a positive entry price only for
   nonzero positions.
3. Preserve `orig_qty`, `executed_qty` and `remaining_qty=max(orig-executed, 0)` as Decimal.
4. Preserve `orderId`, `algoId`, `clientOrderId` and `clientAlgoId` under typed fields.
5. Reject negative remaining quantity, malformed nonzero positions and wrong-symbol rows.
6. Keep the signed reader GET-only and bounded by its existing total timeout.

**Blocker Removed Or Reclassified:** SNAP-01, SNAP-02 and SNAP-03 become closed.

**Per-Symbol / Per-Fact Acceptance:** one raw payload containing zero BTC row, nonzero ETH
row, partially filled normal order and Algo stop produces one complete account fact with
exact ETH quantity and both client identities.

**Capability Unlocked:** U1 typed snapshot truth.

**Next Engineering Bottleneck:** ownership classification.

**Rehearsal/Simulation Boundary:** fixture-only signed GET payload; zero exchange writes.

### 4.2 TDD steps

1. Add RED tests:
   - `test_zero_position_with_zero_entry_price_is_filtered_before_validation`;
   - `test_algo_order_preserves_client_algo_id`;
   - `test_partial_fill_preserves_orig_executed_and_remaining_qty`;
   - streaming and non-streaming normalized snapshots are identical.
2. Run:

   ```bash
   python3 -m pytest -q \
     tests/unit/test_binance_usdm_account_risk_snapshot.py \
     tests/unit/test_streaming_http_json.py
   ```

   Expected RED: zero-entry validation, missing client identity and missing executed/remaining
   fields fail the new assertions.
3. Implement the smallest shared typed contract and parsers.
4. Rerun the same command green, then run `git diff --check`.
5. Commit only T01 files with subject `fix: preserve complete account snapshot truth`.

**Done When:** both readers produce the same complete typed snapshot and all malformed
nonzero/negative cases fail closed.

**Hard Stop:** any proposed fix silently substitutes original quantity for remaining
quantity or weakens symbol/account validation.

## 5. T02 — Enforce Account, Instrument And Hedge-Bucket Ownership

### 5.1 Task packet

**Task ID:** `DPR-REMED-T02`

**Goal:** make position and order identity collision-safe across accounts, instruments,
one-way mode and hedge mode; define deterministic historical-overlap preflight for migration
134.

**Why:** the current tree can collapse hedge buckets to `BOTH`, match an ID from another
instrument and choose an arbitrary overlapping historical mapping.

**Allowed files:**

- `src/application/action_time/account_exchange_ownership.py`
- `src/application/action_time/account_exposure_current.py`
- `src/infrastructure/account_capacity_hot_path_repository.py`
- `tests/unit/test_account_exchange_ownership.py`
- `tests/unit/test_account_exposure_current.py`
- `tests/unit/test_account_capacity_hot_path_repository.py`

**Forbidden files:** migrations through 133, policy values, runner/deploy code and exchange
write paths.

**Requirements:**

1. Use order key `(account_id, exchange_instrument_id, id_kind, id_value)`.
2. Validate side, `position_bucket` and lifecycle role after an ID match.
3. Use Exposure netting key
   `(account_id, exchange_instrument_id, position_mode, position_bucket)`.
4. Keep V0 slot key `(account_id, exchange_instrument_id)`; an opposite nonzero hedge bucket
   cannot create a second system Ticket.
5. Treat cross-instrument ID collision, duplicate ownership evidence and bucket contradiction
   as new-ENTRY hard holds.
6. Define migration preflight as exactly one mapping valid at the row's recorded timestamp;
   zero or multiple matches abort instead of selecting `LIMIT 1`.

**Blocker Removed Or Reclassified:** OWN-01 and OWN-02 close; OWN-03 has an executable RED
contract for T04 migration 134.

**Per-Symbol / Per-Fact Acceptance:** BTC/LONG and BTC/SHORT remain distinct Exposure rows;
an ETH order sharing a numeric order ID with BTC cannot own BTC; same-instrument second
Ticket is blocked in one-way and hedge modes.

**Capability Unlocked:** U1 ownership truth.

**Next Engineering Bottleneck:** current projection conservation.

**Rehearsal/Simulation Boundary:** in-memory typed snapshots and disposable DB fixtures only.

### 5.2 TDD steps

1. Add RED tests for hedge LONG/SHORT separation, opposite-bucket external exposure and
   cross-instrument `order_id` / `client_algo_id` collisions. Record the exact zero/multi-match
   historical mapping cases in T04; do not commit an expected-failure marker.
2. Run:

   ```bash
   python3 -m pytest -q \
     tests/unit/test_account_exchange_ownership.py \
     tests/unit/test_account_exposure_current.py \
     tests/unit/test_account_capacity_hot_path_repository.py
   ```

   Expected RED: bucket collapse, ID-only ownership and overlap selection violate assertions.
3. Implement composite identities and bounded repository queries. Do not create migration 134
   yet.
4. Rerun all T02 focused tests green; add no skip or xfail.
5. Commit T02 production/tests. OWN-03 remains explicitly open until T04 adds migration 134 and
   its RED/GREEN migration tests.

**Done When:** runtime identity tests are green and OWN-03 remains a named T04 dependency rather
than a hidden passing claim.

**Hard Stop:** any identity key omits account or instrument, or maps hedge LONG/SHORT to
`BOTH` after normalization.

## 6. T03 — Produce An Independent Account Capacity Base Fact

### 6.1 Task packet

**Task ID:** `DPR-REMED-T03`

**Goal:** produce and persist a complete, tradable, non-flat account-capacity fact without
weakening the legacy flat `account_safe` fact or changing downstream binding yet.

**Why:** CAP-01 currently blocks a valid second position before the new budget model can run.

**Allowed files:**

- `src/application/action_time/account_safe_facts.py`
- `src/application/action_time/runtime_pg_fact_snapshots.py`
- `scripts/runtime_pg_fact_snapshots.py`
- `scripts/build_runtime_account_safe_facts.py`
- `tests/unit/test_runtime_account_safe_facts.py`
- `tests/unit/test_runtime_pg_fact_snapshots.py`

**Forbidden files:** legacy `account_safe` meaning, policy numeric values, FinalGate bypass,
Invocation/Lane/Ticket consumers, migrations and exchange-write code.

**Requirements:**

1. Emit `account_capacity_base.v1` from the same complete signed snapshot used by
   the capacity path, using `BinanceUsdmAccountRiskSnapshotProvider` over all five account
   endpoints including `openAlgoOrders`; do not derive it from the legacy candidate-symbol
   summaries.
2. Satisfy only when snapshot is fresh/complete, account/profile exact, `can_trade=true` and
   mode is `one_way` or `hedge`.
3. Keep legacy `account_safe` satisfied only for its existing flat-account contract.
4. Persist `fact_surface="account_capacity_base"` and
   `fact_values.schema_version="account_capacity_base.v1"` in the existing JSON fact payload;
   T03 adds no schema column or migration. Do not store a decision-bearing boolean only inside
   the legacy `account_safe` payload.
5. Persist unsatisfied facts for audit; T03 deliberately does not bind either new/old fact into
   a new consumer path.
6. Give both facts the same source snapshot identity and bounded validity window.
7. The active-policy collector reads PG account/profile/exchange identity in one short
   transaction, closes it, fetches the full snapshot outside PG, then persists the independent
   fact in a second short transaction. The no-policy collector remains unchanged.
8. T03 may consume the T01 provider/reader contract but must not create a second writer or
   duplicate snapshot-provider path.

**Blocker Removed Or Reclassified:** CAP-01 producer half closes; CAP-01 remains open until T04
adds physical references and migrates every consumer.

**Per-Symbol / Per-Fact Acceptance:** with one protected BTC position and a complete account
snapshot, an independently queryable satisfied `account_capacity_base.v1` row exists for the
exact account/profile/snapshot; the legacy `account_safe` row remains unsatisfied.

**Capability Unlocked:** a producer surface that T04 can bind without legacy relaxation.

**Next Engineering Bottleneck:** Account Current authority.

**Rehearsal/Simulation Boundary:** PG fact production only; no Invocation, Ticket or exchange
write.

### 6.2 TDD steps

1. Add RED tests for independent active-policy/non-flat production, no-policy legacy behavior,
   stale snapshot, wrong account, incomplete Algo-order page and unsatisfied-fact persistence.
2. Run:

   ```bash
   python3 -m pytest -q \
     tests/unit/test_runtime_account_safe_facts.py \
     tests/unit/test_runtime_pg_fact_snapshots.py
   ```

   Expected RED: no independent `account_capacity_base` fact row exists.
3. Implement the typed fact producer/writer only.
4. Rerun green and prove existing legacy-flat tests are unchanged.
5. Commit with subject `fix: produce independent account capacity base fact`.

**Done When:** capacity-base is independently produced/persisted while `account_safe` retains
exact legacy semantics; CAP-01 remains explicitly open for T04 binding.

**Hard Stop:** reinterpreting `account_safe=true` to mean “capacity may exist”.

## 7. T04 — Conserve Account Current Authority And Add Migration 134

### 7.1 Task packet

**Task ID:** `DPR-REMED-T04`

**Goal:** bind the independent capacity fact end-to-end, then make one Account Budget Current
row and bounded Exposure Current projection account for each episode's risk, slot and margin
exactly once.

**Why:** reserved margin disappears, policy-version rows can split current authority, current
refresh ignores quantitative changes, and flat history is loaded on each tick.

**Allowed files:**

- `src/application/action_time/account_exposure_current.py`
- `src/application/action_time/account_budget_current.py`
- `src/application/action_time/account_risk_reprojection.py`
- `src/application/action_time/account_capacity_materialization.py`
- `src/application/action_time/post_submit_reconciliation_tick.py`
- `src/domain/action_time_invocation.py`
- `src/application/action_time/action_time_invocation.py`
- `src/application/action_time/fact_snapshots.py`
- `src/application/action_time/promotion_action_time_lane.py`
- `src/application/action_time/action_time_ticket.py`
- `src/application/action_time/finalgate_preflight.py`
- `src/application/action_time/operation_layer_handoff.py`
- `src/application/action_time/runtime_safety_state.py`
- `src/application/action_time/full_chain_simulation_harness.py`
- `src/application/readmodels/canary_mutation_sentinel.py`
- `src/application/readmodels/runtime_safety_truth.py`
- `src/application/readmodels/strategy_group_live_facts_readiness.py`
- `src/application/readmodels/strategy_live_candidate_pool.py`
- `src/infrastructure/account_capacity_hot_path_repository.py`
- `src/infrastructure/runtime_control_state_repository.py` only for the new fact-reference columns
- `src/infrastructure/canary_mutation_sentinel_repository.py`
- `src/infrastructure/canary_mutation_sentinel_queries.py`
- `scripts/run_runtime_control_state_retention.py`
- `scripts/build_strategy_fresh_signal_action_time_boundary.py`
- `scripts/ops/set_account_risk_policy.py`
- `migrations/versions/2026-07-17-134_repair_account_risk_current_authority.py`
- focused tests named below

**Forbidden files:** migrations through 133, policy caps, Ticket lifecycle behavior outside
fact selection, runner, deploy scripts and exchange-write paths.

**Requirements:**

1. Migration 134 adds nullable `account_capacity_base_fact_snapshot_id` to
   ActionTimeInvocation, Action-Time Lane and Ticket, makes Ticket's legacy
   `account_safe_fact_snapshot_id` nullable and backfills valid legacy rows. Invocation permits
   neither reference while still collecting facts but forbids both; its evidence loader requires
   exactly one before capacity arbitration. Bound Lane and materialized Ticket enforce exactly
   one selected reference.
2. No-policy paths bind only `account_safe`; active-policy paths bind only
   `account_capacity_base`. Invocation, Lane, Ticket, FinalGate, Operation Layer handoff and
   Runtime Safety State validate the exact selected fact surface, account/profile/exchange,
   freshness and snapshot identity. Delete Runtime Safety State's legacy
   `account_capacity_base_safe` relaxation as an authority path.
3. Every downstream consumer derives and equality-checks
   `(account_capacity_fact_surface, account_capacity_fact_snapshot_id)` from the exactly-one
   physical pair. Fresh-signal boundary, readiness, candidate pool, Runtime Safety Truth,
   canary repository/digest and full-chain simulation must consume that pair; unknown schema,
   both/neither at an authority boundary or canonical/physical mismatch fails closed.
4. Before editing, run a whole-repository `rg` inventory for
   `account_safe_fact_snapshot_id`, `account_capacity_base_safe`, trusted fact refs, canary
   column sets and fact-retention joins. The design's minimum inventory is mandatory but not a
   whitelist. Every hit is either migrated in T04 or, only for the deploy state machine,
   recorded as a T10 dependency.
5. Migration 134 adds `trusted_fact_refs_schema_version`, plus V2 trusted-reference columns
   `account_capacity_fact_surface` and `account_capacity_fact_snapshot_id` to
   `brc_runtime_safety_state_snapshots`. Existing rows are labeled
   `runtime_safety_trusted_refs.v1` without inventing a digest; new materializations use
   `runtime_safety_trusted_refs.v2`. It also adds indexes for every new/legacy capacity-fact
   reference on Invocation, Lane, Ticket and Runtime Safety. Runtime-control retention preserves
   every directly referenced fact, including non-expired V2 Runtime Safety rows, through
   set-based `NOT EXISTS` joins and must not materialize unbounded fact history in Python.
   `runtime_safety_submit_authorized` dispatches on this schema before status/freshness: V1
   remains audit-readable but always returns `false`, including an unexpired stored
   `live_submit_ready` row. Only V2 with the exact canonical pair, V2 Ticket hash schema,
   current identity and fresh satisfied facts may authorize submit. Migration 134 preserves
   historical V1 status rather than rewriting it to manufacture this behavior.
6. Migration 134 adds `ticket_hash_schema_version`, marks existing Tickets
   `action_time_ticket_hash.v1` without recomputing or updating their hash and requires all new
   Tickets to use `action_time_ticket_hash.v2`. Before labeling, it verifies every stored Ticket
   hash through the frozen V1 field tuple in stable-key batches of at most 1000 rows; blank or
   mismatch aborts before UPDATE with `ticket_hash_v1_preflight_failed`. Migration 134 embeds a
   migration-local frozen V1 tuple/canonicalizer and does not import a mutable current-model
   hash function; a golden fixture proves it equals the pre-134 production verifier. V2 hashes
   the frozen V1 field set plus canonical capacity surface/ID, `exposure_episode_id` and
   `capacity_claim_hash`; unknown versions fail closed.
7. Add `brc.canary_mutation_sentinel.v2` for new canary captures and dispatch Runtime Safety
   Truth by `runtime_safety_trusted_refs.v1/v2`. Preserve the byte-identical V1 **canary digest**
   and the frozen V1 Runtime Safety trusted-ref key/interpretation; Runtime Safety Truth has no
   historical digest and the implementation must not fabricate one. Implement separate frozen
   field/model constants and dispatch by explicit schema; do not append fields to the V1 tuple or
   hash a V1 canary row through the current V2 Pydantic model. No historical sentinel,
   trusted-ref interpretation or Ticket digest is rewritten.
   Downgrade 134 aborts before DDL with
   `capacity_fact_history_not_legacy_compatible` if V2 Ticket/reference history exists.
8. Budget Current unique scope is exactly `(account_id, runtime_profile_id)`; policy version
   and `account_risk_policy_event_id` are row values.
9. The exact Account Risk Policy Current row is the always-present serialization/bootstrap
   anchor for the active-policy path. Lock it first, validate `source_event_id`, upsert the
   first Budget Current row from the complete snapshot/current Exposure, then hold the Budget
   row for the remaining Claim transaction.
10. Migration 134 aborts if duplicate Budget Current rows exist for one scope; it does not pick
   a winner.
11. Migration 134 adds `account_risk_policy_event_id` to Budget Current, joins each row to the
   exact `(account_id, runtime_profile_id)` policy current, verifies matching
   `risk_policy_version`, backfills `source_event_id`, then enforces non-null. Zero, multiple or
   version-mismatched policy authority aborts.
12. Migration 134 revalidates identity at each recorded timestamp. Active/current/live-eligible/
   nonterminal rows require exactly one match; zero or multiple matches abort. Terminal rows
   already classified `legacy_audit_only_identity_unresolved` may retain zero/multiple matches,
   remain excluded from current/hot/runtime authority and preserve all evidence; exactly one
   match may correct their stored identity.
13. Reservation-only Exposure stores Claim stop risk, one slot and reserved margin under
   `(reservation_id, exposure_episode_id)`.
14. Margin states are `reserved_unreflected`, `partially_reflected`, `exchange_reflected`,
   `unknown`, `released`. Exact owned position quantity plus exact owned remaining Entry-order
   quantity determines reflected quantity; local pending margin covers only the planned
   unreflected remainder. Unknown lineage uses the conservative upper bound and blocks entry;
   elapsed time never changes reflection state.
15. Every fresh complete snapshot refreshes quantitative current and validity; only semantic
   fingerprint change appends an audit event.
16. Current refresh queries only non-flat/working/unknown/blocked rows, effective Reservations
   bounded by `max_positions+1`, and snapshot instruments.
17. A 100000-row flat history fixture transfers zero flat rows to application memory.
18. `account_capacity_materialization` loads one
    `AccountRiskPolicyCurrentProjection`; both pre/post-Claim Budget projection receive its
    immutable `source_event_id` instead of re-querying or inferring an epoch.
19. `set_account_risk_policy.py` removes both account/profile technical defaults, requires
    explicit values, validates the exact current runtime scope binding and creates no event on
    mismatch. Tests only; this plan does not activate policy.

**Blocker Removed Or Reclassified:** CAP-01, CAP-03, CAP-04, CAP-05, CAP-06, CUR-01,
CUR-03 and OWN-03 close.

**Per-Symbol / Per-Fact Acceptance:** active-policy ETH flows capacity fact through Invocation,
Lane, Ticket, FinalGate, handoff and Runtime Safety State without legacy relaxation; first BTC
Ticket plus ETH Claim yields two slots and one pending ETH margin exactly once; wallet/margin
changes refresh Budget Current even when Ticket enum is unchanged.

**Capability Unlocked:** U2 current account capacity authority.

**Next Engineering Bottleneck:** post-Claim Ticket transaction.

**Rehearsal/Simulation Boundary:** disposable PostgreSQL only; no live DB and no exchange write.

### 7.2 TDD steps

1. Add/activate RED tests in:
   - `tests/unit/test_account_exposure_current.py`;
   - `tests/unit/test_account_budget_current.py`;
   - `tests/unit/test_account_risk_lifecycle_reprojection.py`;
   - `tests/unit/test_account_capacity_hot_path_repository.py`;
   - `tests/unit/test_asset_neutral_account_risk_migrations.py`;
   - `tests/unit/test_action_time_invocation.py`;
   - `tests/unit/test_pg_promotion_action_time_lane_materialization.py`;
   - `tests/unit/test_action_time_ticket_materialization.py`;
   - `tests/unit/test_account_capacity_gate_replacement.py`;
   - `tests/unit/test_action_time_operation_layer_handoff_materialization.py`;
   - `tests/unit/test_ticket_bound_runtime_safety_state_materialization.py`;
   - `tests/unit/test_runtime_control_state_retention.py`;
   - `tests/unit/test_strategy_fresh_signal_action_time_boundary.py`;
   - `tests/unit/test_canary_mutation_sentinel.py`;
   - `tests/unit/test_canary_mutation_sentinel_queries.py`;
   - `tests/unit/test_canary_mutation_sentinel_repository.py`;
   - `tests/unit/test_ticket_bound_runtime_safety_state_materialization.py`.
   - `tests/unit/test_strategy_group_live_facts_readiness_artifact.py`;
   - `tests/unit/test_strategy_live_candidate_pool.py`;
   - `tests/unit/test_action_time_full_chain_impact.py`;
   - `tests/unit/test_set_account_risk_policy.py`;
   - `tests/integration/test_account_capacity_hot_path_scale.py`.
2. Required test names include:
   - `test_active_unreflected_claim_holds_risk_slot_and_margin_once`;
   - `test_partial_reflection_counts_exchange_and_unreflected_margin_once`;
   - `test_fresh_wallet_change_refreshes_current_without_new_audit_event`;
   - `test_budget_current_is_one_row_across_policy_versions`;
   - `test_migration_134_aborts_duplicate_budget_current_scope`;
   - `test_migration_134_adds_capacity_fact_references_and_exactly_one_ticket_binding`;
   - `test_migration_134_aborts_zero_or_multiple_active_mapping`;
   - `test_migration_134_preserves_terminal_audit_only_unresolved_mapping`;
   - `test_capacity_fact_reference_flows_invocation_lane_ticket_finalgate_handoff_runtime_safety`;
   - `test_capacity_fact_reference_is_preserved_by_retention_for_invocation_lane_ticket_and_runtime_safety`;
   - `test_capacity_fact_retention_plan_uses_reference_indexes_and_does_not_scan_python_history`;
   - `test_capacity_fact_canonical_pair_flows_through_readiness_candidate_canary_and_simulation`;
   - `test_ticket_hash_v1_is_byte_identical_after_migration_134`;
   - `test_ticket_hash_v2_binds_capacity_pair_episode_and_claim_hash`;
   - `test_unknown_ticket_canary_or_runtime_trusted_refs_schema_fails_closed`;
   - `test_runtime_safety_v1_trusted_refs_remain_readable_without_fabricated_digest`;
   - `test_runtime_safety_v1_live_submit_ready_is_readable_but_never_submit_authorized`;
   - `test_runtime_safety_submit_authorized_requires_v2_pair_and_v2_ticket_hash_schema`;
   - `test_migration_134_never_recomputes_historical_hashes`;
   - `test_migration_134_aborts_before_update_on_invalid_v1_ticket_hash`;
   - `test_migration_134_downgrade_aborts_v2_history_before_ddl`;
   - `test_policy_tool_requires_exact_account_and_runtime_profile_binding`;
   - `test_flat_history_is_not_materialized_by_current_refresh`.
3. Add one table-driven state-conservation test covering all stages below. Each row separately
   asserts portfolio risk, primary-cluster risk, slot, local pending margin, exchange initial/
   portfolio margin and new-entry authority:

   | Stage | Required assertion |
   | --- | --- |
   | **Reservation-only active/consumed** | Claim risk, cluster risk, one slot and local reserved margin appear once |
   | **Partial fill + partially reflected remainder** | Filled directional plus remaining working risk is conservative; exchange margin plus only the unreflected local remainder appears once |
   | **Exact exchange-reflected** | Local margin is zero and exchange margin is counted once |
   | **Unknown/mismatch** | Last-known/Claim upper bound remains and all new entry is blocked |
   | **Flat/released** | Episode risk, cluster risk, slot and local margin are zero |

4. Run focused RED:

   ```bash
   python3 -m pytest -q \
     tests/unit/test_account_exposure_current.py \
     tests/unit/test_account_budget_current.py \
     tests/unit/test_account_risk_lifecycle_reprojection.py \
     tests/unit/test_account_capacity_hot_path_repository.py \
     tests/unit/test_asset_neutral_account_risk_migrations.py \
     tests/unit/test_action_time_invocation.py \
     tests/unit/test_pg_promotion_action_time_lane_materialization.py \
     tests/unit/test_action_time_ticket_materialization.py \
     tests/unit/test_account_capacity_gate_replacement.py \
     tests/unit/test_action_time_operation_layer_handoff_materialization.py \
     tests/unit/test_ticket_bound_runtime_safety_state_materialization.py \
     tests/unit/test_runtime_control_state_retention.py \
     tests/unit/test_strategy_fresh_signal_action_time_boundary.py \
     tests/unit/test_canary_mutation_sentinel.py \
     tests/unit/test_canary_mutation_sentinel_queries.py \
     tests/unit/test_canary_mutation_sentinel_repository.py \
     tests/unit/test_ticket_bound_runtime_safety_state_materialization.py \
     tests/unit/test_strategy_group_live_facts_readiness_artifact.py \
     tests/unit/test_strategy_live_candidate_pool.py \
     tests/unit/test_action_time_full_chain_impact.py \
     tests/unit/test_set_account_risk_policy.py \
     tests/integration/test_account_capacity_hot_path_scale.py
   ```

5. Capture the consumer inventory in the implementation review record and prove every hit is
   covered by T04 or the named T10 deploy dependency; an unexplained consumer keeps CAP-01 open.
6. Implement current projectors/repository bounds, then migration 134 with revision `134` and
   `down_revision="133"`.
7. Rerun green; confirm the new CAP-01/OWN-03 tests fail before migration 134 and pass after it, with
   no skip or xfail.
8. Run the immutable migration source check against the frozen code baseline, not only the
   current uncommitted diff:

   ```bash
   git diff --exit-code 60bb7fedcd2b9bd300cef900c6bbb304c5a34770 -- \
     migrations/versions \
     ':(exclude)migrations/versions/2026-07-17-134_repair_account_risk_current_authority.py' \
     ':(exclude)migrations/versions/2026-07-17-135_repair_exit_policy_adoption_effective_uniqueness.py' \
     ':(exclude)migrations/versions/2026-07-17-136_add_instrument_risk_calculation_kind.py'
   ```

   Expected: no output.
9. Commit with subject `fix: conserve account risk current authority`.

**Done When:** migration 134, current refresh, margin conservation and scale tests pass with
bounded queries and no older migration diff.

**Hard Stop:** collapsing duplicate current rows automatically, elapsed-time margin reflection
or application-side scan of flat history.

## 8. T05 — Make Claim, Post-Claim Projection And Ticket Atomic

### 8.1 Task packet

**Task ID:** `DPR-REMED-T05`

**Goal:** implement the 13-step Claim-to-Ticket transaction in the design and make FinalGate
consume its exact persisted post-Claim lineage.

**Why:** projection-before-Claim leaves the Ticket's own slot/risk absent and causes FinalGate
to fail or count capacity inconsistently.

**Allowed files:**

- `src/application/action_time/account_capacity_materialization.py`
- `src/application/action_time/account_capacity_claim.py`
- `src/application/action_time/account_capacity_reservation.py`
- `src/application/action_time/budget_reservation_transition.py`
- `src/application/action_time/promotion_action_time_lane.py`
- `src/application/action_time/ticket_materialization_sequence.py`
- `src/application/action_time/action_time_ticket.py`
- `src/application/action_time/finalgate_preflight.py`
- related unit and PostgreSQL integration tests

**Forbidden files:** exchange I/O under DB lock, policy values, alternate Ticket service,
migrations and live submit code.

**Requirements:**

1. Fetch the full account snapshot before beginning the mutation transaction.
2. Lock the exact Account Risk Policy Current row first and validate its immutable event;
   insert-or-update the first Budget Current row, then hold that row `FOR UPDATE`. All remaining
   capacity calculation happens only after the Budget lock is held. A missing Budget row is
   therefore bootstrapable, while two concurrent first Claims serialize on the policy row.
3. Pre-generate immutable `ticket_id` and `exposure_episode_id`; insert them and the final
   `capacity_claim_hash` with the active Claim. The consumed transition may update only status,
   transition time/reason and event metadata; `budget_reservation_transition.py` itself verifies
   exact Ticket ID, exposure episode ID and Claim hash under the same row lock, never delegates
   those checks only to its caller and never mutates Claim identity.
4. In one transaction: locked policy bootstrap -> pre-claim refresh -> Budget Current upsert/
   lock -> capacity calculation -> active Claim ->
   reservation-only Exposure -> post-claim Budget -> Ticket -> Reservation `consumed`.
5. Roll back all seven mutation classes on any failure.
6. FinalGate requires `consumed`, exact Ticket/episode/claim hash, policy event, source snapshot
   and post-Claim projection version.
7. FinalGate excludes only the exact Ticket's Claim from “new incremental capacity”; it still
   counts that Claim once in total held capacity.
8. Claim replay is idempotent only when every immutable field/hash matches.

**Blocker Removed Or Reclassified:** CAP-02 closes.

**Per-Symbol / Per-Fact Acceptance:** one existing BTC Ticket plus an ETH candidate creates an
ETH Claim, post-Claim current, Ticket and consumed Reservation atomically; FinalGate passes
with exactly two slots and fails on any lineage mismatch.

**Capability Unlocked:** U3 second-position Ticket materialization without exchange authority.

**Next Engineering Bottleneck:** terminal release and reprojection.

**Rehearsal/Simulation Boundary:** Ticket and FinalGate PG materialization only; Operation Layer
and exchange writes are not invoked.

### 8.2 TDD steps

1. Add RED tests in:
   - `tests/unit/test_account_capacity_materialization.py`;
   - `tests/unit/test_account_capacity_claim.py`;
   - `tests/unit/test_account_capacity_claim_persistence.py`;
   - `tests/unit/test_budget_reservation_transition.py`;
   - `tests/unit/test_action_time_ticket_materialization_sequence.py`;
   - `tests/unit/test_account_capacity_finalgate_guard.py`;
   - `tests/integration/test_account_capacity_postgres.py`.
2. Required RED cases: post-Claim version observed by Ticket; Reservation active before Ticket
   and consumed after; injected failure at each mutation boundary leaves zero partial rows;
   two concurrent first candidates with no Budget Current row serialize to one remaining slot;
   own Claim counted once; direct consumed-transition calls with wrong Ticket, episode or Claim
   hash each fail before status/event mutation.
3. Run:

   ```bash
   python3 -m pytest -q \
     tests/unit/test_account_capacity_materialization.py \
     tests/unit/test_account_capacity_claim.py \
     tests/unit/test_account_capacity_claim_persistence.py \
     tests/unit/test_budget_reservation_transition.py \
     tests/unit/test_action_time_ticket_materialization_sequence.py \
     tests/unit/test_account_capacity_finalgate_guard.py \
     tests/integration/test_account_capacity_postgres.py
   ```

4. Implement the transaction without network/subprocess calls inside the lock.
5. Rerun green and inspect SQL-call recording to prove exact Policy Current lock -> Budget
   upsert/lock -> capacity calculation -> mutation ordering.
6. Commit with subject `fix: atomically project account capacity claims`.

**Done When:** rollback, concurrency, idempotency and own-Claim FinalGate tests pass on real
PostgreSQL.

**Hard Stop:** a helper commits independently, Ticket is created outside the transaction, or
FinalGate accepts an `active` unbound Reservation.

## 9. T06 — Release And Reproject Terminal Capacity

### 9.1 Task packet

**Task ID:** `DPR-REMED-T06`

**Goal:** release pre-submit and post-submit capacity only from exact terminal evidence, and
refresh Exposure/Budget in the same closure.

**Why:** current code can let a reservation-only slot block its own release and can leave
released capacity stale until another event.

**Allowed files:**

- `src/application/action_time/budget_reservation_transition.py`
- `src/application/action_time/account_risk_reprojection.py`
- `src/application/action_time/post_submit_reconciliation_tick.py`
- `src/application/action_time/ticket_bound_budget_settlement.py`
- `src/application/action_time/ticket_bound_lifecycle_finalizer.py`
- `src/application/action_time/lifecycle_maintenance_service.py`
- `src/application/action_time/lifecycle_maintenance_scheduler.py`
- focused lifecycle/reprojection tests

**Forbidden files:** force-close logic, protection cancellation, policy changes and file-backed
recovery.

**Requirements:**

1. Pre-submit release requires terminal Ticket, no dispatch/write/unknown outcome, no real
   position and no real open order.
2. Ignore only the exact reservation-only Exposure derived from the Claim when deciding whether
   real exchange exposure exists.
3. Post-submit release requires terminal lifecycle, exact flat account snapshot, matched
   reconciliation and residual protection handled.
4. Reservation status event, Exposure flat transition and Budget refresh commit together.
5. The budget-settlement authority itself validates exact Ticket/reservation/episode lineage,
   flat position truth, matched reconciliation and handled residual protection. Callers cannot
   bypass those predicates by presenting only a settlement evidence ID.
6. Settlement evidence alone never releases capacity.
7. Repeated scheduler ticks are idempotent and append no duplicate release/audit event.

**Blocker Removed Or Reclassified:** CUR-02 closes.

**Per-Symbol / Per-Fact Acceptance:** FinalGate-rejected ETH Ticket immediately returns one slot
while BTC remains protected; flat/matched submitted ETH releases once; unknown outcome remains
held.

**Capability Unlocked:** next eligible different-instrument Claim regains capacity exactly once.

**Next Engineering Bottleneck:** release lifecycle recovery defects.

**Rehearsal/Simulation Boundary:** simulated lifecycle and read-only account truth; no order
cancel, amend, close or submit.

### 9.2 TDD steps

1. Add RED cases to:
   - `tests/unit/test_budget_reservation_transition.py`;
   - `tests/unit/test_account_risk_lifecycle_reprojection.py`;
   - `tests/unit/test_ticket_bound_budget_settlement.py`;
   - `tests/unit/test_ticket_bound_post_submit_reconciliation_tick.py`;
   - `tests/integration/test_asset_neutral_account_risk_full_chain.py`.
2. Run focused RED:

   ```bash
   python3 -m pytest -q \
     tests/unit/test_budget_reservation_transition.py \
     tests/unit/test_account_risk_lifecycle_reprojection.py \
     tests/unit/test_ticket_bound_budget_settlement.py \
     tests/unit/test_ticket_bound_post_submit_reconciliation_tick.py \
     tests/integration/test_asset_neutral_account_risk_full_chain.py
   ```

3. Implement exact pre/post-submit predicates and same-transaction reprojection.
4. Rerun green, including repeated release tick and unknown-outcome negatives.
5. Commit with subject `fix: release and reproject terminal capacity`.

**Done When:** the full-chain test proves Claim -> Ticket -> reject/flat -> release -> next
Claim without manual projection seeding.

**Hard Stop:** release on settlement ID alone, release under unknown outcome, force close or
protection cancellation.

## 10. T07 — Restore Runner Trailing And Exact Entry-Fill Recovery

### 10.1 Task packet

**Task ID:** `DPR-REMED-T07`

**Goal:** make post-TP1 structural/reference trailing reachable and restore restart state from
exact Entry order fills beyond the latest-50 window.

**Why:** the runner currently returns the break-even floor before evaluating later trailing,
and recovery may misclassify an old or split Entry as contradictory.

**Allowed files:**

- `src/domain/ticket_exit_policy.py`
- `src/application/action_time/ticket_exit_policy_service.py`
- `src/application/action_time/exchange_snapshot_provider.py`
- `src/application/action_time/ticket_exit_execution_binding.py`
- `src/application/action_time/lifecycle_maintenance_scheduler.py`
- `scripts/run_ticket_bound_lifecycle_maintenance_once.py`
- `src/infrastructure/exchange_gateway.py` — **main Codex controller only**
- runner, snapshot-provider, binding and scheduler tests

**Forbidden files:** exchange mutation methods, policy parameter changes, unbounded pagination,
report files and file-backed fill caches.

**Requirements:**

1. Treat the break-even floor as a long lower bound / short upper bound and as the minimum
   target for an emitted post-TP1 mutation, not an immediate state rewrite. A floor-only move
   emits only when its own `minimum_improvement_ticks` is reached. If it is sub-threshold, a
   separately eligible structural/reference candidate may still emit after being clamped by
   the floor and evaluated under its own rule threshold.
2. Evaluate only the immutable policy's mutually exclusive
   `runner_rule`: `structural_atr`, `reference_trail` or `no_runner`. Ignore every unconfigured
   candidate, clamp the configured candidate by the floor, apply that rule's own improvement
   threshold and emit at most one strict improvement per newer closed watermark.
3. Prefer durable PG fills; if incomplete, query the exact venue `exchange_market_id` and use
   the immutable Entry exchange order ID only as a local equality filter.
4. Add the read-only gateway interface
   `fetch_order_trades_exact(exchange_market_id, exchange_order_id,
   entry_order_created_at_ms, entry_order_terminal_at_ms=None,
   first_durable_trade_id=None, *, page_limit=1000, max_pages=20,
   timeout_seconds=8)` and return typed complete/incomplete/timeout/identity outcomes.
5. Bound fallback to 1000 fills/page, 20 pages and 8 seconds total; dedupe by exchange trade ID.
6. Never send `orderId` to Binance USD-M `/fapi/v1/userTrades`. If a durable first trade ID
   exists, query `symbol + fromId + limit`; otherwise query bounded
   `symbol + startTime + endTime + limit` windows derived from the durable order lifetime, each
   no longer than seven days. Iterate every chronological window even when the prior window is
   not full; each request counts against `max_pages`. A full time-window page continues with
   `symbol + fromId(last_trade_id + 1)` because time parameters and `fromId` cannot be combined.
7. Pagination is ascending by exchange trade ID, including same-timestamp fills. Rows belonging
   to other orders advance the cursor but are excluded by exact local `exchange_order_id`.
   Display symbol is never substituted for the raw venue market ID.
8. Implement explicit `TIME_WINDOW` and `FROM_ID_WITH_WINDOW_END_GUARD` states. Windows are
   closed `[start,end]`; next start is `end+1ms`. A non-full time page advances to the next
   window. A full page uses `fromId=last_trade_id+1`; the first row beyond the current end is not
   consumed for that window and transitions to the next window. A non-full fromId page that did
   not cross the end also advances to the next window. Page/deadline counters never reset.
9. Completion requires lifecycle quantity equality, average price within one rule tick and
   complete fee asset/amount.
10. Old history outside retrievable bounds, empty/incomplete pages, seven-day window exhaustion,
   cursor non-monotonicity and page/deadline exhaustion return
   `entry_fill_history_incomplete`, not contradiction or success.
11. Gateway extension is read-only and scoped; no existing write capability changes. The
    official endpoint contract used by this task is the
    [Binance USD-M Account Trade List implementation](https://github.com/binance/binance-futures-connector-python/blob/main/binance/um_futures/account.py#L3280-L3322).

**Blocker Removed Or Reclassified:** RUN-01, RUN-02 and RUN-04 close.

**Per-Symbol / Per-Fact Acceptance:** TP1-complete long and short runners advance from floor to
strictly better structural/reference stops; an Entry older than 50 newer fills and split over
multiple pages restores the exact immutable execution snapshot.

**Capability Unlocked:** release lifecycle can resume runner state after restart/deploy.

**Next Engineering Bottleneck:** adoption lifecycle uniqueness.

**Rehearsal/Simulation Boundary:** fake/read-only gateway only; assertions require
`exchange_write_called=false`.

### 10.2 TDD steps

1. Add RED tests:
   - `test_tp1_floor_does_not_hide_newer_structural_trailing_candidate`;
   - long/short one-tick-outside-floor with a two-tick floor threshold is a no-op, while a
     three-tick-beyond-floor configured candidate emits one clamped mutation;
   - long/short structural and reference rules, unconfigured-candidate ignore, per-rule
     threshold and repeated-watermark idempotency;
   - `test_restart_recovers_entry_fill_after_more_than_fifty_newer_fills`;
   - real narrow-gateway request never contains `orderId`, starts from durable `fromId` or a
     bounded order-lifetime window, and continues in ascending trade-ID order;
   - entries older than seven days, order lifetime spanning more than one seven-day window,
     multiple-order row mixing, display/raw symbol mismatch, same-timestamp fills, duplicate
     trade IDs, non-full-window `end+1ms` transition, full-page fromId crossing the window end,
     timeout, non-monotonic cursor and incomplete fee truth.
2. Run:

   ```bash
   python3 -m pytest -q \
     tests/unit/test_ticket_exit_policy.py \
     tests/unit/test_ticket_exit_policy_service.py \
     tests/unit/test_ticket_bound_exchange_snapshot_provider.py \
     tests/unit/test_ticket_bound_exchange_snapshot_narrow_gateway.py \
     tests/unit/test_ticket_exit_execution_binding.py \
     tests/unit/test_ticket_exit_policy_binding.py \
     tests/unit/test_ticket_bound_lifecycle_scheduler.py
   ```

3. Implement evaluator ordering first and rerun domain/service tests.
4. Add the exact-order read method in the gateway under main-controller ownership; then wire
   provider/binding bounded-window pagination, local exact-order filtering and total deadline.
5. Rerun all T07 tests green and assert zero gateway mutation calls.
6. Commit with subject `fix: restore runner trailing and exact fill recovery`.

**Done When:** trailing and restart recovery pass deterministic long/short, pagination,
deadline and incomplete-history negatives.

**Hard Stop:** unbounded history scan, symbol-only fill acceptance, average/fee tolerance
weakening or any exchange-write call.

## 11. T08 — Serialize Effective Exit-Policy Adoption And Add Migration 135

### 11.1 Task packet

**Task ID:** `DPR-REMED-T08`

**Goal:** support `accepted -> revoked -> accepted` while guaranteeing at most one effective
acceptance per Ticket.

**Why:** migration 125's lifetime accepted-event unique index prevents valid recovery after an
explicit revoke.

**Allowed files:**

- `src/application/action_time/ticket_exit_policy_adoption_service.py`
- `src/application/action_time/ticket_exit_policy_binding.py`
- `src/application/action_time/ticket_exit_policy_service.py`
- `src/application/action_time/ticket_bound_fill_projector.py`
- `src/application/action_time/ticket_exit_execution_binding.py`
- `src/application/action_time/lifecycle_maintenance_scheduler.py`
- `src/application/action_time/ticket_exit_policy_projection.py`
- `src/application/action_time/lifecycle_exchange_command_completion.py`
- `migrations/versions/2026-07-17-135_repair_exit_policy_adoption_effective_uniqueness.py`
- `tests/unit/test_ticket_exit_policy_adoption_service.py`
- `tests/unit/test_ticket_exit_policy_adoption.py`
- `tests/unit/test_ticket_exit_policy_binding.py`
- `tests/unit/test_ticket_exit_policy_service.py`
- `tests/unit/test_ticket_bound_fill_projector.py`
- `tests/unit/test_ticket_exit_execution_binding.py`
- `tests/unit/test_ticket_bound_lifecycle_scheduler.py`
- `tests/unit/test_ticket_exit_policy_projection.py`
- `tests/unit/test_ticket_exit_policy_tp1_reprice.py`
- `tests/unit/test_ticket_exit_policy_adoption_migration.py`
- new `tests/integration/test_ticket_exit_policy_adoption_postgres.py`
- new `tests/integration/test_postgres_certification_environment.py`
- new `tests/fail_on_skip_plugin.py`
- new `tests/unit/test_required_gate_no_skip_plugin.py`

**Forbidden files:** migration 125, Ticket immutable policy snapshot, policy parameter values
and exchange mutation paths.

**Requirements:**

1. Migration 135 has `revision="135"`, `down_revision="134"` and drops only the lifetime
   accepted unique index identified by migration 125. It also adds adoption-owned
   `adoption_state`, `mutation_allowed` and monotonic `adoption_projection_version` to
   `brc_ticket_exit_policy_current`; the general execution `state` remains a separate lifecycle
   projection field.
2. Adoption events remain append-only; revoke points to the exact superseded accepted event.
3. Lock the Ticket row before accepted/revoked conflict evaluation and event append.
4. Effective acceptance means accepted and not superseded by a later valid revoke.
5. At most one effective acceptance; concurrent double acceptance serializes to one success
   and one idempotent/conflict result.
6. Duplicate revoke, revoke wrong event and acceptance while another effective acceptance
   exists fail closed.
7. Only the adoption service writes the three adoption-owned columns. Legacy
   `binding_source='ticket'` rows backfill to `ticket_bound/true`; an adoption-bound row backfills
   to `accepted/true` only when its exact accepted event is valid and non-superseded. Missing or
   ambiguous binding aborts migration before mutation. A check constraint permits
   `mutation_allowed=false` exactly when `adoption_state='revoked'`.
8. `revoke_ticket_exit_policy_adoption` appends the revoke and CAS-transitions the one current
   projection by exact `ticket_id + adoption_event_id=A + adoption_state=accepted + expected
   adoption_projection_version`, then writes `revoked/false` and increments that version under
   the same Ticket lock. It does not use general execution `state` or `first_blocker` as a CAS
   predicate.
9. Binding is capability-specific while revoked: read-only protection, reconciliation,
   fill-projector and recovery paths may read the last accepted snapshot only with
   `mutation_allowed=false`; the runner mutation resolver fails closed and emits no new stop
   generation. The fill projector may update TP1/protection truth but may not create a runner
   mutation.
10. Accept B CAS-replaces only the exact `adoption_event_id=A + adoption_state=revoked + expected
    adoption_projection_version` authority with B's complete execution projection,
    restores `mutation_allowed=true` and makes only B available to the mutation resolver;
    it preserves durable Entry fill, TP1 quantity, active protection and last emitted stop
    generation, never re-enables an already emitted exchange command, inserts no duplicate
    current row and deletes no A/revoke history.
11. Fill projector, market-fact projection and lifecycle command completion may update execution,
    TP1, protection and blocker fields while revoked, but never the adoption-owned columns. Their
    updates cannot prevent the later exact Accept B CAS.
12. Downgrade preflights lifetime uniqueness and aborts when post-135 history contains multiple
   accepted events for one Ticket; it never deletes or rewrites events to recreate the old index.
13. A real PostgreSQL two-connection test serializes concurrent accept/accept and
    accept/revoke/accept under the Ticket row lock. At every commit boundary, at most one
    effective current acceptance exists.

**Blocker Removed Or Reclassified:** RUN-03 and RUN-05 close.

**Per-Symbol / Per-Fact Acceptance:** one Ticket can accept A, revoke A and accept B; binding
resolves B only; two concurrent B accepts do not create two effective events.

**Capability Unlocked:** recoverable append-only adoption authority.

**Next Engineering Bottleneck:** explicit instrument risk calculation kind.

**Rehearsal/Simulation Boundary:** disposable PostgreSQL and service calls only; no exchange
read or write is required.

### 11.2 TDD steps

1. Add the reusable required-gate infrastructure before any PostgreSQL acceptance claim:
   `tests/fail_on_skip_plugin.py` records every skip and xfail report and forces a nonzero
   session result; its unit test proves pass remains zero and skip/xfail each fail. Add the
   disposable-environment identity test that requires the generated test database, user and
   schema contract. These files are owned by T08 because its task-level PG gate is their first
   consumer; T11 reuses them and does not defer their creation.
2. Add RED service and migration tests for accepted A -> current A -> revoke A -> revoked
   current -> accept B -> current B, effective binding, runner mutation block while revoked,
   protection/reconciliation/fill projection continuation with `mutation_allowed=false`,
   concurrent acceptance, invalid revoke and downgrade/upgrade behavior. Reaccept B preserves
   A-era durable execution/protection progress and proves zero duplicate runner/protection
   command eligibility.
3. Run the plugin self-test first, then the focused service suite:

   ```bash
   python3 -m pytest -q tests/unit/test_required_gate_no_skip_plugin.py

   python3 -m pytest -q \
     tests/unit/test_ticket_exit_policy_adoption.py \
     tests/unit/test_ticket_exit_policy_adoption_service.py \
     tests/unit/test_ticket_exit_policy_binding.py \
     tests/unit/test_ticket_exit_policy_service.py \
     tests/unit/test_ticket_bound_fill_projector.py \
     tests/unit/test_ticket_exit_execution_binding.py \
     tests/unit/test_ticket_bound_lifecycle_scheduler.py \
     tests/unit/test_ticket_exit_policy_projection.py \
     tests/unit/test_ticket_exit_policy_tp1_reprice.py \
     tests/unit/test_ticket_exit_policy_adoption_migration.py
   ```

4. Implement Ticket-row serialization, adoption-owned CAS fields, capability-specific binding
   and effective-event resolver;
   then add migration 135.
5. Before claiming RUN-03/RUN-05 closed or committing T08, run section 14.2 gate 1's exact
   self-contained Docker PostgreSQL block, but replace its two pytest commands with this one
   required command inside the same block:

   ```bash
   python3 -m pytest -q -ra -p tests.fail_on_skip_plugin \
     tests/integration/test_postgres_certification_environment.py \
     tests/integration/test_ticket_exit_policy_adoption_postgres.py
   ```

   Docker/container setup, generated DSN/schema, identity checks and cleanup behavior remain
   byte-for-byte the same as gate 1; an ambient DSN or skipped/xfail test is not accepted.
6. Rerun green; prove a legacy-compatible fixture completes `135 -> 134 -> 135`, a post-135
   multi-accepted fixture aborts `135 -> 134` atomically, and migration 125 has no diff from
   the frozen baseline. The real PostgreSQL test must use two independent connections and prove
   only one effective current row after each race. It also runs fill, market-fact and TP1
   command-completion projection between revoke A and accept B, then proves B still accepts and
   no prior command becomes eligible twice. T11 alone owns the later full
   `136 -> 133 -> 136` round trip.
7. Commit with subject `fix: serialize effective exit policy adoption`.

**Done When:** full event sequence and race tests pass and historical accepted rows remain
queryable.

**Hard Stop:** deleting historical events, mutating migration 125 or using application-only
checks without a Ticket row lock.

## 12. T09 — Price Linear Contracts With Explicit Multiplier And Add Migration 136

### 12.1 Task packet

**Task ID:** `DPR-REMED-T09`

**Goal:** remove the hidden unit-multiplier assumption while explicitly limiting V0 to linear
quote-settled contracts.

**Why:** non-unit linear contracts otherwise receive incorrect notional, stop risk, margin and
quantity.

**Allowed files:**

- `src/domain/instrument_risk_identity.py`
- `src/domain/account_risk.py`
- `src/domain/account_capacity_claim.py`
- `src/application/action_time/instrument_risk_facts.py`
- `src/application/action_time/account_capacity_claim.py`
- `src/application/action_time/account_exposure_current.py`
- `src/application/action_time/account_capacity_reservation.py`
- `src/application/action_time/promotion_action_time_lane.py`
- `src/application/action_time/finalgate_preflight.py`
- `migrations/versions/2026-07-17-136_add_instrument_risk_calculation_kind.py`
- instrument/risk/capacity/FinalGate/migration tests

**Forbidden files:** inverse/quanto execution adapter, asset-specific strategy patch, policy
caps and migration 131.

**Requirements:**

1. Introduce `InstrumentRuleSnapshotRefV2` and verifier contract
   `account_capacity_claim.v2`; persist the existing `capacity_claim_schema_version` column as
   exact value `'v2'`, then load and persist `risk_calculation_kind="linear_quote_settled"` and
   positive `contract_multiplier` plus the recomputable V2 rule `semantic_hash` through the
   versioned rule snapshot, immutable Claim V2 hash/round-trip, Exposure Current and
   Ticket/FinalGate lineage.
2. Preserve exact stored value `'v1'`, the V1 Claim model/field set and verifier for historical
   rows. Migration 136
   never deserializes a V1 row into V2, never recomputes a V1 hash and rejects unknown schema
   versions. New Claims after 136 are V2; Ticket V2 binds their `capacity_claim_hash`.
3. Use:
   `notional=abs(qty)*price*multiplier`,
   `stop_risk=abs(entry-stop)*abs(qty)*multiplier`,
   `reserved_margin=notional/leverage`.
4. Apply the multiplier before step-size rounding and recompute actual rounded stop risk after
   rounding.
5. FinalGate recomputes legality against the same calculation kind and current rule snapshot.
6. Exposure Current applies the same multiplier to filled directional risk and remaining
   working-order risk; portfolio and primary-cluster aggregates therefore cannot fall back to
   unit-multiplier math after exchange exposure appears.
7. Unknown, inverse, quanto and nonlinear kinds fail before Claim creation.
8. Migration 136 has `revision="136"`, `down_revision="135"`. It adds nullable
   `risk_calculation_kind` and `supersedes_instrument_rule_snapshot_id` with no server defaults;
   the calculation-kind check permits only null or `linear_quote_settled`. Before any rule-row
   mutation it materializes
   the exact target set: all current rule snapshots, every snapshot referenced by an active or
   consumed Reservation, and the exactly-one current snapshot for every non-flat/non-closed
   Exposure instrument.
9. Every target joins exactly one active instrument and is eligible only if
   `exchange_id='binance_usdm'`, `asset_class='crypto'`,
   `instrument_type IN ('perpetual','future')`, settlement and margin assets are equal/nonblank,
   and `contract_multiplier > 0`. Anything else aborts the whole migration before mutation with
   the stable design failure code; no default, partial UPDATE or row-by-row best effort is
   allowed.
10. Never add the new kind to a V1 row, alter its `rule_schema_version`, or recompute its opaque
    historical `semantic_hash`. Precompute every eligible **current V1** row's deterministic V2
    clone, ID and canonical hash and reject all collisions before mutation. Because migration
    133 enforces immediate uniqueness for one current rule per instrument, lock target V1 rows
    in stable key order, mark those exact rows `superseded`, bulk-insert the precomputed V2 rows
    as `current`, then assert exactly one current V2 and zero current V1 for every target—all in
    one migration transaction under the writer fence. Any failure rolls back every status
    change and insert. Referenced V1 rows remain exact historical Claim V1 authority and cannot
    create new Claims.
11. `InstrumentRuleSnapshotRefV2` contains `semantic_hash`, kind and multiplier. New-Claim/current
    loaders require exactly one current V2, recompute that hash and reject V1 current, null,
    mismatch or unknown schema. Superseded/unreferenced V1 stays audit-only. Positive fixtures
    cover exact V1-to-V2 cloning; negatives cover ID/hash collision, missing/duplicate joins,
    wrong venue, inactive instrument, wrong asset/instrument type, unequal assets and invalid
    multiplier.
12. Downgrade 136 aborts before mutation with
    `instrument_risk_history_not_legacy_compatible` unless there is no stored Claim `'v2'` and
    every V2 row is an unchanged deterministic migration clone with its exact V1 predecessor. A
    compatible downgrade, after complete preflight, deletes only those current clones, restores
    each predecessor's current status in the same transaction, and asserts one current V1/zero
    current V2 per instrument; runtime-created V2, missing predecessor, changed V1 hash/status
    lineage or V2 Claim aborts. It never rewrites V1 or V2 hashes to force compatibility.

**Blocker Removed Or Reclassified:** EXT-01 and EXT-02 close.

**Per-Symbol / Per-Fact Acceptance:** a synthetic linear contract with multiplier `10` holds
exactly 10x the unit-contract notional/risk for the same quantity; an unsupported kind creates
no Claim.

**Capability Unlocked:** asset-neutral core correctness for known linear contracts without
granting new asset-class live scope.

**Next Engineering Bottleneck:** runtime package and deployment identity.

**Rehearsal/Simulation Boundary:** domain, PG and FinalGate tests only; no new live instrument
is authorized.

### 12.2 TDD steps

1. Add RED tests to:
   - `tests/unit/test_instrument_risk_identity.py`;
   - `tests/unit/test_instrument_risk_facts.py`;
   - `tests/unit/test_account_risk.py`;
   - `tests/unit/test_account_capacity_claim.py`;
   - `tests/unit/test_account_capacity_claim_persistence.py`;
   - `tests/unit/test_account_exposure_current.py`;
   - `tests/unit/test_account_capacity_reservation.py`;
   - `tests/unit/test_account_capacity_finalgate_guard.py`;
   - `tests/integration/test_instrument_risk_calculation_postgres.py`.
2. Run focused RED:

   ```bash
   python3 -m pytest -q \
     tests/unit/test_instrument_risk_identity.py \
     tests/unit/test_instrument_risk_facts.py \
     tests/unit/test_account_risk.py \
     tests/unit/test_account_capacity_claim.py \
     tests/unit/test_account_capacity_claim_persistence.py \
     tests/unit/test_account_exposure_current.py \
     tests/unit/test_account_capacity_reservation.py \
     tests/unit/test_account_capacity_finalgate_guard.py \
     tests/integration/test_instrument_risk_calculation_postgres.py
   ```

3. Required compatibility and migration tests include:
   - frozen Claim V1 hash, Rule V1 fields and opaque Rule V1 `semantic_hash` remain byte-identical
     through `135 -> 136` and all V2 code imports;
   - a current V1 becomes one deterministic current V2 plus an exact superseded V1 predecessor;
   - real PostgreSQL has migration 133's immediate partial unique index in place; the 136 switch
     succeeds without disabling it and ends with one current V2/zero current V1 per instrument;
   - an injected V2 INSERT or postcondition failure rolls back all predecessor status changes,
     leaving the complete current V1 authority visible;
   - mutating V2 `risk_calculation_kind`, multiplier or any canonical economic field invalidates
     Rule V2 semantic hash, Claim hash and therefore Ticket V2 lineage;
   - unknown Claim/hash schema fails closed;
   - migration 136 preflight produces the exact target count before UPDATE and performs zero
     UPDATEs on every negative fixture;
   - active Binance USD-M linear positive rows clone to V2, while current active non-Binance,
     precious-metal/future fixture, ambiguous current rule and non-positive multiplier abort;
   - legacy-only `136 -> 135 -> 136` succeeds, while Claim V2 downgrade aborts atomically.
4. Implement version-dispatched Rule/Claim loaders and hashes, domain math, filled/remaining
   Exposure propagation, FinalGate and migration 136 as one matrix.
5. Rerun green and use an explicit Decimal fixture to assert no float enters serialized Claim
   or Ticket facts. Inspect the migration statement count to prove preflight precedes UPDATE.
6. Commit with subject `fix: price linear contracts with explicit multiplier`.

**Done When:** unit/non-unit linear, rounding, unsupported-kind, deterministic Rule V1-to-V2
clone/hash, frozen V1 and migration/downgrade tests pass.

**Hard Stop:** defaulting unknown kinds to linear, prebuilding inverse/quanto support or using
`float`.

## 13. T10 — Bind Runtime Dependency, Certification Pair And Exact Release Tree

### 13.1 Task packet

**Task ID:** `DPR-REMED-T10`

**Goal:** make an immutable release prove its runtime imports, renewed certification identity,
exact tracked tree and migration head 136 before it can be considered deployable.

**Why:** missing `ijson`, mixed old/new certification, mutable release reuse and stale deploy
defaults can invalidate an otherwise green local tree.

**Allowed files:**

- `requirements-runtime.lock`
- `scripts/prepare_tokyo_runtime_governance_release.py`
- `scripts/plan_tokyo_runtime_governance_git_deploy.py`
- `scripts/execute_tokyo_runtime_governance_git_deploy.py`
- `scripts/tokyo_runtime_deploy_remote_state_machine.py`
- `scripts/set_production_writer_fence.py`
- `scripts/verify_tokyo_runtime_governance_postdeploy.py`
- corresponding deploy/release tests
- `tests/unit/test_production_writer_fence.py`

**Forbidden files:** source-worktree lockfile, server filesystem, production service config,
unhashed dependency installation and deployment execution.

**Requirements:**

1. Regenerate the integrated lock in a clean Linux/Python 3.10 resolver; keep
   `ccxt==4.5.56`; include `ijson>=3.5.1,<4.0.0` and hashes.
2. Validate a clean venv with `pip install --require-hashes` and imports named in the design.
3. Production `build_immutable_venv` runs the same four imports after hashed install and before
   writing `.complete`; any import failure leaves no complete marker and cannot advance to
   writer quiescence/schema/pointer mutation.
4. `release_activation_recorded` remains the existing pair-free **provisional
   code/schema/pointer activation record** because certification consumes it. Do not force the
   renewed pair into that pre-certification phase and do not modify
   `record_runtime_release_activation` or capability-certification semantics merely to do so.
5. Represent post-certification identity as one typed `cert_pair(ref, payload)` object; renewal
   replaces the whole object before lifecycle restore or final activation mutation. Only that
   object may feed lifecycle restore, final `runtime_activation_committed`, terminal manifest
   and resume journal. Code must not read `post_cert["certification_ref"]` or merge an old
   payload after renewal.
6. Add append-only `certification_generation` records. On every resume before
   `policy_applied`, validate the latest pair's `fact_min_valid_until_ms`; if less than 30 seconds
   remain, refresh facts, produce one complete new pair, rerun lifecycle restore, persist a new
   proof bound to that pair and append generation `g+1`. Never bind a new pair to an old proof.
7. If an activation commit for generation `g` is journaled but policy is not applied, generation
   `g+1` appends a superseding activation commit; it does not rewrite history. Policy apply and
   fence removal accept only the latest matching pair/proof/commit generation and recheck the
   30-second minimum at mutation start. Refresh failure returns
   `resume_certification_generation_failed`, keeps the fence engaged and performs no policy or
   fence mutation. Once `policy_applied` is durable, later expiry does not alter that committed
   generation.
8. Compute canonical tracked-tree digest from relative path, mode and content digest.
9. Sort tracked regular files by UTF-8 POSIX relative path and hash each record as
   `mode_octal + NUL + path + NUL + sha256(content) + LF`; hash the concatenated records.
   Reject tracked symlinks, normalized-path duplicates, missing paths and untracked source
   entries in the release tree.
10. Derive the expected digest from the fetched target Git object on stage, reuse, resume and
   activation; the manifest is only a copied assertion and never the trust anchor. Rewriting
   both candidate tree and manifest coherently must still fail.
11. Recompute and compare the digest after staging, before release reuse and before activation;
   reject missing, extra, symlinked or modified source entries.
12. Before returning any journaled `candidate_staged` or `immutable_venv_ready` phase result on
    resume, rederive expected digest from the target Git object and recompute the candidate
    source tree. Tamper after staging must fail before writer fence, schema migration or pointer
    activation.
13. Run every candidate-source import with `PYTHONDONTWRITEBYTECODE=1` and remove `compileall`
    from the deploy state machine. The hashed-install four-module import gate and test suite are
    the syntax/import validation authority; no candidate-source compile cache is permitted.
    Candidate source directories are non-writable to the runtime UID. After the real
    `build_immutable_venv` install/import gate, recompute the source digest and prove it unchanged.
14. Keep `.venv`, journal, manifest and provisioned persistent config outside source digest but
   separately identity-bound.
15. Candidate target count/head are `136` and
    `2026-07-17-136_add_instrument_risk_calculation_kind.py`: prepare derives them from the
    candidate, planner records them, executor consumes the immutable plan and postdeploy
    requires exact 136. Pre-deploy remote baseline count/head are explicit read-only probe
    inputs with no 136 fallback; missing baseline values fail closed.
16. Remote state-machine config and CLI both require `expected_revision`; the CLI form is
    `--expected-revision` with **no default**. Missing or blank revision fails before candidate
    stage, writer fence, schema mutation or pointer mutation. The deploy executor must always
    pass the immutable plan's exact value.
17. Upgrade the deploy legacy fact bridge/canary to the V2 canonical capacity fact pair; it must
    reject capacity-base authority represented only as legacy `account_safe` or by the deprecated
    embedded boolean.
18. All tests are local; do not invoke SSH, systemd or activation.

**Blocker Removed Or Reclassified:** DEP-01 through DEP-07 close locally.

**Per-Symbol / Per-Fact Acceptance:** no strategy/symbol semantics change; a release candidate
is accepted only when runtime lock, certification pair, tree digest and migration identity all
match the same commit.

**Capability Unlocked:** U6 immutable local release candidate.

**Next Engineering Bottleneck:** integrated certification.

**Rehearsal/Simulation Boundary:** temporary directories and fake command runners only; zero
SSH, service mutation and deployment.

### 13.2 TDD steps

1. Add RED tests for:
   - provisional `release_activation_recorded` remains pair-free, then near-expiry pair A ->
     pair B renewal makes restore, final activation commit, terminal manifest and journal/resume
     contain B and no reference to A;
   - mixed pair fails before subprocess;
   - crash after `lifecycle_proof_persisted`, pair B expires, resume creates pair/proof/commit
     generation C before policy apply; B proof is never reused and C is the only fence-removal
     authority;
   - the same expired-resume path with refresh/certification/restore failure keeps the writer
     fence and creates no policy/fence mutation;
   - existing release tree content/mode/extra/symlink drift fails reuse;
   - coherent tree + manifest rewrite fails against the unchanged target Git object;
   - pre-activation digest is recomputed;
   - candidate tampered after `candidate_staged` or `immutable_venv_ready`, then resume, fails
     before writer fence;
   - candidate target surfaces agree on 136 while missing/incorrect explicit remote baseline
     fails rather than defaulting to 136;
   - production `build_immutable_venv` imports all four modules with bytecode writes disabled,
     leaves the Git-object tree digest unchanged before `.complete`, and an import failure writes
     no marker or later mutation;
   - source directories are runtime-UID read-only, the command runner never invokes
     `compileall`, and no candidate-source compile cache exists;
   - missing `expected_revision` in config or missing CLI `--expected-revision` fails before
     staging and all mutations;
   - deploy legacy bridge/canary preserves the V2 capacity fact pair;
   - lock contains `ijson` hashes.
2. Run:

   ```bash
   python3 -m pytest -q \
     tests/unit/test_tokyo_runtime_deploy_remote_state_machine.py \
     tests/unit/test_tokyo_runtime_governance_release_prep.py \
     tests/unit/test_tokyo_runtime_governance_git_deploy_execution.py \
     tests/unit/test_tokyo_runtime_governance_postdeploy_verify.py \
     tests/unit/test_production_writer_fence.py
   ```

3. Implement typed pair/generation, pre-policy resume recertification, fence-generation checks,
   tree/resume/bytecode controls, required revision and deploy fact-pair compatibility.
4. Regenerate `requirements-runtime.lock` from the integrated clean worktree only. Use the
   tracked integrated lock as the pin baseline and resolve inside amd64 Linux/CPython 3.10:

   ```bash
   docker run --rm --platform linux/amd64 \
     --user "$(id -u):$(id -g)" -e HOME=/tmp \
     -v "$PWD:/work" -w /work python:3.10-slim \
     sh -euc 'cp requirements-runtime.lock /tmp/baseline.lock && \
       python -m venv /tmp/resolver && \
       /tmp/resolver/bin/pip install pip-tools==7.4.1 >/dev/null && \
       /tmp/resolver/bin/pip-compile --generate-hashes --resolver=backtracking \
         --constraint=/tmp/baseline.lock \
         --output-file=requirements-runtime.lock requirements.txt'
   ```

5. Run the clean Linux/Python 3.10 hashed-install and import smoke:

   ```bash
   docker run --rm --platform linux/amd64 \
     -e PYTHONDONTWRITEBYTECODE=1 \
     -v "$PWD:/work:ro" -w /work python:3.10-slim \
     sh -euc 'python -m venv /tmp/smoke && \
       /tmp/smoke/bin/pip install --require-hashes -r requirements-runtime.lock && \
       /tmp/smoke/bin/python -c "import ijson; import src.infrastructure.streaming_http_json; import src.infrastructure.binance_usdm_streaming_signed_reader; import src.application.action_time.lifecycle_maintenance_scheduler" && \
       /tmp/smoke/bin/pip check'
   ```

   These commands may download dependencies but must not use SSH or read a source-worktree
   lockfile. If Docker, the resolver or approved dependency network is unavailable, stop T10
   as blocked; do not hand-edit hashes.
6. Rerun focused tests green and inspect `git diff -- requirements-runtime.lock` to confirm
   deterministic dependency-only change.
7. Commit with subject `fix: bind runtime and release deployment identity`.

**Done When:** lock install/import, renewal pair, resume tamper, bytecode isolation, mandatory
revision, V2 fact bridge and head-136 tests are green with no external mutation.

**Hard Stop:** copying the dirty source-worktree lock, hand-authoring hashes, trusting manifest
SHA without Git-object tree revalidation, writing bytecode into release source, defaulting a
missing revision or running any deploy command.

## 14. T11 — Run Migration, Production-Shape, Performance And Full-Suite Certification

### 14.1 Task packet

**Task ID:** `DPR-REMED-T11`

**Goal:** prove the complete merged production path rather than the sum of component tests.

**Why:** the deep review found green branch tests that never exercised the causal chain from a
raw non-flat account fact through the next recovered capacity.

**Allowed files:**

- new `tests/integration/test_dual_position_account_risk_remediation_full_chain.py`
- existing T08-owned `tests/integration/test_postgres_certification_environment.py`
- existing T08-owned `tests/integration/test_ticket_exit_policy_adoption_postgres.py`
- existing T08-owned `tests/fail_on_skip_plugin.py`
- existing T08-owned `tests/unit/test_required_gate_no_skip_plugin.py`
- existing focused tests only when a production-shape assertion is missing
- no production file unless a newly exposed defect is first documented and returned to its
  owning task

**Forbidden files:** test-only production bypass, helper seeding of Exposure/Budget, external
exchange/network calls and production deployment.

**Requirements:**

1. The full-chain test starts from raw account payload and real production entry points.
2. It creates no Exposure/Budget helper rows.
3. It proves capacity-base fact -> Invocation -> Claim -> post-Claim current -> Ticket consumed
   -> FinalGate -> official Operation Layer handoff with `operation_layer_called=false` ->
   Ticket-bound Runtime Safety State -> non-executing protected-submit preparation through a
   fake gateway -> simulated protected lifecycle -> flat/matched release -> next Claim.
4. Required migration paths: fresh -> 136, 125 -> 136, 133 -> 136 and a
   schema-only/legacy-compatible disposable `136 -> 133 -> 136`.
5. A separate post-135 fixture creates `accepted -> revoked -> accepted`; its attempted
   `135 -> 134` downgrade must fail atomically with
   `adoption_history_not_legacy_compatible`, while a legacy-compatible fixture downgrades.
6. Run concurrency, 100000-flat-row scale, fill pagination and release tree tamper tests.
7. Runtime file-I/O audit must report `performance_risk.status=clear` and no frequent report
   writes.
8. Output artifact scope and current-doc authority must remain valid.
9. PostgreSQL certification creates its own disposable `postgres:16-alpine` Docker container,
   bound to a dynamic loopback-only port with a test-only database/user. The shell block unsets
   and ignores ambient `BRC_LOCAL_TEST_POSTGRES_*`, constructs the DSN/schema itself, validates
   exact database/user identity plus `SELECT 1`, and trap-removes the container on success,
   failure or interruption. Docker absence blocks T11; there is no ambient-DSN fallback.
10. `tests/fail_on_skip_plugin.py` records every pytest skip and xfail report and forces a
    nonzero session result. `tests/unit/test_required_gate_no_skip_plugin.py` proves ordinary
    pass remains zero and skip/xfail each fail. Every required PostgreSQL command explicitly
    loads it with `-p tests.fail_on_skip_plugin`; `-ra` alone is not acceptance evidence.
11. Rerun the complete INV-01..05 direct matrix, migration immutability diff, policy-tool exact
    runtime-profile test, Operation Layer/Runtime Safety State tests and production immutable-
    venv import gate. Broad suite green cannot substitute for one of these gates.
12. Rerun the full capacity-fact consumer-conservation matrix, frozen V1/new V2 hash and
    Runtime Safety trusted-ref schema matrix,
    T08 two-connection adoption race, migration 136 exact-target preflight and T10 resume/tamper
    matrix. An omitted consumer or schema version keeps the owning finding open.

**Blocker Removed Or Reclassified:** QA-01 and all CAP/SNAP/OWN/CUR/EXT/RUN/DEP findings close
only after this task; otherwise the owning finding remains open.

**Per-Symbol / Per-Fact Acceptance:** BTC existing protected position plus ETH new candidate is
the positive chain; same-instrument, wrong bucket, unsupported kind, stale fact, ambiguous
ownership and unknown outcome are fail-closed negatives.

**Capability Unlocked:** local production-shape remediation certification.

**Next Engineering Bottleneck:** independent review and later deployment authorization.

**Rehearsal/Simulation Boundary:** local disposable PostgreSQL and fake/read-only gateway only;
zero production state and exchange writes.

### 14.2 Gate commands

Run in this exact order and stop at the first failure:

1. Run the complete required PostgreSQL gate in **one shell block** so environment and cleanup
   cannot drift between commands. It never consumes an ambient DSN:

   ```bash
   set -euo pipefail
   unset BRC_LOCAL_TEST_POSTGRES_DSN BRC_LOCAL_TEST_POSTGRES_SCHEMA
   container="brc-remediation-pg-$(python3 -c 'import secrets; print(secrets.token_hex(6))')"
   password="brc_test_only"
   cleanup() {
     original_status=$?
     trap - EXIT INT TERM
     cleanup_status=0
     docker rm -f "$container" >/dev/null 2>&1 || cleanup_status=$?
     if test "$original_status" -ne 0; then
       exit "$original_status"
     fi
     if test "$cleanup_status" -ne 0; then
       echo "ERROR: disposable_postgres_cleanup_failed:$container" >&2
       exit "$cleanup_status"
     fi
     exit 0
   }
   trap cleanup EXIT
   trap 'exit 130' INT
   trap 'exit 143' TERM

   docker run -d --rm \
     --name "$container" \
     -e POSTGRES_USER=brc_test \
     -e POSTGRES_PASSWORD="$password" \
     -e POSTGRES_DB=brc_remediation \
     -p 127.0.0.1::5432 \
     postgres:16-alpine >/dev/null

   for attempt in $(seq 1 60); do
     if docker exec "$container" pg_isready -U brc_test -d brc_remediation >/dev/null 2>&1; then
       break
     fi
     test "$attempt" -lt 60
     sleep 1
   done

   published="$(docker port "$container" 5432/tcp)"
   port="${published##*:}"
   export BRC_LOCAL_TEST_POSTGRES_DSN="postgresql+psycopg://brc_test:${password}@127.0.0.1:${port}/brc_remediation"
   export BRC_LOCAL_TEST_POSTGRES_SCHEMA="brc_remediation_$(python3 -c 'import secrets; print(secrets.token_hex(6))')"

   python3 -c 'import os,re; import sqlalchemy as sa; schema=os.environ["BRC_LOCAL_TEST_POSTGRES_SCHEMA"]; assert re.fullmatch(r"brc_remediation_[a-f0-9]{12}", schema); engine=sa.create_engine(os.environ["BRC_LOCAL_TEST_POSTGRES_DSN"]); conn=engine.connect(); assert conn.execute(sa.text("SELECT current_database()" )).scalar_one() == "brc_remediation"; assert conn.execute(sa.text("SELECT current_user" )).scalar_one() == "brc_test"; assert conn.execute(sa.text("SELECT 1" )).scalar_one() == 1; conn.execute(sa.text(f"CREATE SCHEMA \"{schema}\"")); conn.commit(); conn.close(); engine.dispose()'

   python3 -m pytest -q -ra -p tests.fail_on_skip_plugin \
     tests/integration/test_postgres_certification_environment.py \
     tests/unit/test_account_risk_policy_migration.py \
     tests/unit/test_asset_neutral_account_risk_migrations.py \
     tests/unit/test_ticket_exit_policy_adoption_migration.py \
     tests/integration/test_instrument_risk_calculation_postgres.py \
     tests/integration/test_asset_neutral_account_risk_migration_scale.py

   python3 -m pytest -q -ra -p tests.fail_on_skip_plugin \
     tests/integration/test_account_capacity_postgres.py \
     tests/integration/test_account_capacity_hot_path_scale.py \
     tests/integration/test_asset_neutral_account_risk_full_chain.py \
     tests/integration/test_ticket_exit_policy_adoption_postgres.py \
     tests/integration/test_dual_position_account_risk_remediation_full_chain.py
   ```

   Expected: zero failed, skipped or xfailed tests, including two concurrent first Claims with
   no pre-seeded Budget row, two-connection adoption serialization, the complete five-stage
   conservation matrix and every downgrade preflight. The trap removes the whole disposable
   database container; no schema or ambient server survives the block.

2. Capacity fact consumers, release authority, inherited invariants, runner and recovery:

   ```bash
   python3 -m pytest -q -ra -p tests.fail_on_skip_plugin \
     tests/unit/test_runtime_account_safe_facts.py \
     tests/unit/test_runtime_pg_fact_snapshots.py \
     tests/unit/test_action_time_invocation.py \
     tests/unit/test_pg_promotion_action_time_lane_materialization.py \
     tests/unit/test_action_time_ticket_materialization.py \
     tests/unit/test_account_capacity_gate_replacement.py \
     tests/unit/test_action_time_operation_layer_handoff_materialization.py \
     tests/unit/test_ticket_bound_runtime_safety_state_materialization.py \
     tests/unit/test_runtime_control_state_retention.py \
     tests/unit/test_strategy_fresh_signal_action_time_boundary.py \
     tests/unit/test_canary_mutation_sentinel.py \
     tests/unit/test_canary_mutation_sentinel_queries.py \
     tests/unit/test_canary_mutation_sentinel_repository.py \
     tests/unit/test_strategy_group_live_facts_readiness_artifact.py \
     tests/unit/test_strategy_live_candidate_pool.py \
     tests/unit/test_action_time_full_chain_impact.py \
     tests/unit/test_ticket_bound_protected_submit_attempt.py \
     tests/unit/test_ticket_bound_budget_settlement.py \
     tests/unit/test_set_account_risk_policy.py \
     tests/unit/test_account_exposure_current.py \
     tests/unit/test_account_budget_current.py \
     tests/unit/test_account_risk_lifecycle_reprojection.py \
     tests/unit/test_account_capacity_materialization.py \
     tests/unit/test_account_capacity_claim_persistence.py \
     tests/unit/test_account_capacity_reservation.py \
     tests/unit/test_account_capacity_finalgate_guard.py \
     tests/unit/test_ticket_exit_policy.py \
     tests/unit/test_ticket_exit_policy_service.py \
     tests/unit/test_ticket_bound_exchange_snapshot_provider.py \
     tests/unit/test_ticket_bound_exchange_snapshot_narrow_gateway.py \
     tests/unit/test_ticket_exit_execution_binding.py \
     tests/unit/test_ticket_exit_policy_adoption.py \
     tests/unit/test_ticket_exit_policy_adoption_service.py \
     tests/unit/test_ticket_bound_fill_projector.py \
     tests/unit/test_required_gate_no_skip_plugin.py
   ```

3. Clean Linux/amd64 CPython 3.10 hashed-lock installation and import gate:

   ```bash
   docker run --rm --platform linux/amd64 \
     -e PYTHONDONTWRITEBYTECODE=1 \
     -v "$PWD:/work:ro" -w /work python:3.10-slim \
     sh -euc 'python -m venv /tmp/smoke && \
       /tmp/smoke/bin/pip install --require-hashes -r requirements-runtime.lock && \
       /tmp/smoke/bin/python -c "import ijson; import src.infrastructure.streaming_http_json; import src.infrastructure.binance_usdm_streaming_signed_reader; import src.application.action_time.lifecycle_maintenance_scheduler" && \
       /tmp/smoke/bin/pip check'
   ```

4. Deploy state-machine identity and production immutable-venv gates:

   ```bash
   python3 -m pytest -q \
     tests/unit/test_tokyo_runtime_deploy_remote_state_machine.py \
     tests/unit/test_tokyo_runtime_governance_release_prep.py \
     tests/unit/test_tokyo_runtime_governance_git_deploy_execution.py \
     tests/unit/test_tokyo_runtime_governance_postdeploy_verify.py \
     tests/unit/test_production_writer_fence.py
   ```

5. Frozen-migration, authority, performance and output audits:

   ```bash
   git diff --exit-code 60bb7fedcd2b9bd300cef900c6bbb304c5a34770 -- \
     migrations/versions \
     ':(exclude)migrations/versions/2026-07-17-134_repair_account_risk_current_authority.py' \
     ':(exclude)migrations/versions/2026-07-17-135_repair_exit_policy_adoption_effective_uniqueness.py' \
     ':(exclude)migrations/versions/2026-07-17-136_add_instrument_risk_calculation_kind.py'
   python3 scripts/audit_production_runtime_file_io.py
   python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
   python3 scripts/validate_no_runtime_file_authority.py
   python3 scripts/validate_current_docs_authority.py
   git diff --check
   ```

6. Complete repository suite. This broad suite may retain explicitly known project skips and
   therefore does not load the required-gate plugin; it cannot substitute for gate 1:

   ```bash
   python3 -m pytest -q
   ```

7. Findings-first independent review checks the implementation against every registry ID and
   INV-01..05, verifies the fail-on-skip plugin was loaded in every required PostgreSQL gate,
   inspects production entry points before tests and records no unresolved P1 or key P2.

### 14.3 Failure handling

- Do not patch production code inside T11 without first reopening the owning task and adding a
  RED test there.
- The gate-1 trap owns disposal. If Docker itself cannot remove the named test container, keep
  T11 failed and record the exact container name; never fall back to or clean an ambient PG.
- A flaky or environment-dependent test is not waived; classify environment vs product cause
  and preserve exact command/output.
- Do not mark local certification complete when the clean hashed-lock venv, PostgreSQL or
  production-file-I/O gate was not actually run.

**Done When:** every command exits zero, performance risk is clear, full chain uses production
entry points, and independent review has no open required finding.

**Hard Stop:** any test requires production secrets, network access, exchange writes or local
runtime file authority.

### 14.4 Final T11 evidence

**Verified local evidence on the remediation branch:**

- one-shell disposable PostgreSQL, fail-on-skip certification: **33 passed**;
- capacity-fact consumer, runner, recovery and direct invariant matrix: **489 passed** with
  no skip or xfail accepted;
- deploy state-machine, release identity and writer-fence matrix: **77 passed**;
- frozen-migration, output scope, runtime-file-authority, current-doc and production file-I/O
  audits: passed, with `performance_risk.status=clear` and no suspicious runtime file authority;
- full repository suite in disposable PostgreSQL: **3617 passed, 1 skipped**. The skipped case
  is permitted only for the broad suite and is not evidence for any required no-skip gate.
- clean Linux/amd64 CPython 3.10 hash-lock gate: **passed** from official PyPI with
  `--require-hashes`, read-only source mount, required imports and `pip check`; exit `0`,
  `No broken requirements found`;
- `psycopg-binary==3.3.4` official metadata and independently downloaded CPython 3.10
  Linux/amd64 wheel both prove SHA256
  `fa1cbc10768a796c96d3243656016bf4e337c81c71097270bb7b0ad6210d9765`, already present in the
  tracked lock. The earlier mismatched payload was a corrupted download/cache, not a lock change.

**T11 conclusion:** all required local gates are green. No server, production database, policy,
credential or exchange state was touched. Deployment remains a separate explicit execution step.

## 15. T12 — Close Current Documentation Authority

### 15.1 Task packet

**Task ID:** `DPR-REMED-T12`

**Goal:** update current docs from `REMEDIATION_APPROVED_NOT_STARTED` to the exact evidence-backed
local state without implying deployment or activation.

**Why:** current authority must not retain a false deep-review NO-GO after all gates pass, nor
claim release readiness before certification.

**Allowed files:**

- this implementation plan;
- `docs/current/DUAL_POSITION_ACCOUNT_RISK_V0_RELEASE_BLOCKER_REMEDIATION_DESIGN.md`;
- the hard-cap and asset-neutral design/plan status headers and cross-references;
- `docs/current/MAIN_CONTROL_ROADMAP.md`;
- `docs/current/MAINLINE_ENGINEERING_PROGRAM_PLAN.md`.

**Forbidden files:** historical archive, generated output, policy values and production runtime
state.

**Requirements:**

1. Record exact certified commit SHA, migration head 136 and actual gate commands/results.
2. Preserve `LOCAL_REMEDIATION_CERTIFIED_NOT_DEPLOYED` only as the historical
   T11/T12 component result. The current whole-branch status remains
   `LOCAL_REMEDIATION_CERTIFICATION_REOPENED` until P0 Runtime Observation Truth
   and the prior Dual-Position gates pass at one exact HEAD.
3. Keep deployment, production migration, policy activation and exchange write explicitly
   unperformed.
4. If any required gate remains unrun or failed, keep status `REMEDIATION_IN_PROGRESS_NO_GO`
   and name the first blocker.
5. Make all current authority docs point to this design and plan as the remediation layer.

**Blocker Removed Or Reclassified:** documentation contradiction closes; deployment remains a
separate future authorization boundary.

**Per-Symbol / Per-Fact Acceptance:** documentation states the proven BTC/ETH production-shape
matrix and does not generalize it into unauthorized live asset scope.

**Capability Unlocked:** a reviewable local release candidate, not a deployed system.

**Next Engineering Bottleneck:** separate shadow/deploy/activation decision and plan.

**Rehearsal/Simulation Boundary:** documentation only.

### 15.2 Closure commands

```bash
python3 scripts/validate_current_docs_authority.py
rg -n '^(TBD|TODO|IMPLEMENT_LATER)(:|$)|^(status|implementation_state|integration_state): LOCAL_MERGE_CERTIFIED_NOT_DEPLOYED$' \
  docs/current/DUAL_POSITION_* docs/current/MAIN_CONTROL_ROADMAP.md \
  docs/current/MAINLINE_ENGINEERING_PROGRAM_PLAN.md
git diff --check
git status --short
```

Expected: no placeholder, no superseded false certification status, clean whitespace and only
the intended documentation changes before the final local commit.

Commit with subject `docs: certify dual position remediation readiness` only after T11.

**Done When:** current authority consistently describes exact local certification state and
the branch is ready for a separate deployment review.

**Hard Stop:** documentation says deployed, activated, live-safe or release-ready without the
corresponding separately authorized evidence.

## 16. Final Definition Of Done

### 16.1 Functional completion

- **Capacity fact:** existing protected position no longer blocks valid capacity arbitration;
  its selected fact reference survives every current consumer and retention cycle.
- **Hash compatibility:** frozen V1 Ticket/Claim/canary digests remain unchanged; Runtime Safety
  V1 trusted-ref interpretation remains audit-readable without a fabricated digest but never
  submit-authoritative; every new V2 authority field is bound by the applicable hash/equality
  checks and unknown versions fail closed.
- **Conservation:** every episode's slot, risk, cluster risk and margin are counted exactly once.
- **Atomicity:** Claim, post-Claim current, Ticket and consumed Reservation share one transaction.
- **Release:** rejected/flat terminal capacity returns exactly once from exact evidence.
- **Identity:** account, instrument, mode, bucket and order identity cannot collide silently.
- **Runner:** post-TP1 trailing progresses and restart recovery follows the real bounded Binance
  time/fromId contract beyond recent-50 fills without sending `orderId`.
- **Adoption:** accepted/revoked/accepted works under Ticket serialization; revoked protective
  reads retain truth with `mutation_allowed=false` and runner mutation remains blocked.
- **Instrument math:** explicit linear multiplier math is Decimal-correct; migration 136
  predicate-validates the exact target set, deterministically clones eligible current V1 rules
  into hashed V2 rules, preserves referenced V1 history and fails unsupported kinds.
- **Release identity:** hashed runtime lock, the latest fresh internally consistent certification
  generation, resume-safe tracked-tree digest, mandatory expected revision and migration head
  136 agree.

### 16.2 Non-functional completion

| Constraint | Required evidence |
| --- | --- |
| **Architecture** | One Ticket lifecycle, one Claim/Reservation path, one PG current authority |
| **Performance** | Bounded hot-path rows, zero flat-history materialization, no network under lock |
| **Cadence** | No unconditional watcher fetch and no no-signal recurring artifacts |
| **Extensibility** | Explicit instrument calculation kind and multiplier; no crypto-perpetual hidden constant |
| **Recovery** | Durable PG first, bounded time/fromId exchange read with exact local order filter |
| **Deployment integrity** | Clean hashed-lock venv, bytecode-isolated resume-safe tree digest, mandatory revision and consistent head 136 |
| **Certification** | Self-contained loopback Docker PG and required fail-on-skip/xfail plugin |

### 16.3 State after completion

```text
implementation_state = local_remediation_certified
integration_state = local_production_shape_certified_not_deployed
production_state = unchanged
deployment_state = not_performed
policy_activation = not_performed
exchange_write = 0
next_owner_boundary = separate shadow/deploy/activation authorization
```

No task in this plan may change the final four production-facing values.
