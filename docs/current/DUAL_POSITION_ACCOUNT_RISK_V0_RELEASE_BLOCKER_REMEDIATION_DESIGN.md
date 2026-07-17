---
title: DUAL_POSITION_ACCOUNT_RISK_V0_RELEASE_BLOCKER_REMEDIATION_DESIGN
status: REMEDIATION_IN_PROGRESS_NO_GO
authority: docs/current/DUAL_POSITION_ACCOUNT_RISK_V0_RELEASE_BLOCKER_REMEDIATION_DESIGN.md
extends: docs/current/DUAL_POSITION_HARD_CAP_ACCOUNT_RISK_MODEL_V0_DESIGN.md
last_verified: 2026-07-17
owner_decision_date: 2026-07-17
implementation_state: T01_T10_IMPLEMENTED_T11_PARTIALLY_CERTIFIED
integration_state: LOCAL_REMEDIATION_IN_PROGRESS_NO_GO
repair_baseline: 60bb7fedcd2b9bd300cef900c6bbb304c5a34770
repair_branch: codex/dual-position-account-risk-remediation-v1
repair_worktree: /Users/jiangwei/Documents/final/.worktrees/dual-position-account-risk-remediation-v1
production_state: UNCHANGED
policy_activation: NOT_PERFORMED
exchange_write: 0
current_migration_head: 136_LOCAL_ONLY
planned_migration_head: 136
---

# Dual-Position Account Risk V0 Unified Remediation Design

## 1. Current Decision

### 1.1 Local implementation evidence as of 2026-07-17

**已知事实：** T01-T10 已在本独立 worktree 实施；migration **136**、V2 instrument
risk identity、容量 Claim/Ticket/Lifecycle 链、runner recovery、exit-policy adoption 与
release identity 均已有定向本地测试。无跳过 PostgreSQL 门禁 **9 passed**，发布状态机门禁
**66 passed**；运行时文件 I/O 审计为 `performance_risk.status=clear`，没有可疑运行时
文件权威来源或高频报告写入。

**当前结论：** 状态仍为 **`REMEDIATION_IN_PROGRESS_NO_GO`**。全量套件在动态 PostgreSQL
环境中已发现历史 RCI 集成夹具与当前 V2 schema 的兼容性失败，随后进入高内存 SQLite schema
构建；该轮在约十分钟、约 1.5 GB 内存时被主动终止。T11 的完整全量回归尚未绿，因此本分支
不得被描述为已部署、已激活或可部署。

**方案 B 已获 Owner 确认：在新的独立 worktree 中完成全部功能性 P1、两个被不同审查口径标为 P0/P1 的容量守恒缺陷，以及影响当前正确性、恢复、部署完整性、性能和已知扩展维度的关键 P2。**

本设计替换本文此前的“Local merge certified”结论。合并提交
`60bb7fedcd2b9bd300cef900c6bbb304c5a34770` 仅证明了两条历史能够形成一个
clean two-parent tree；深度审查已经证明绿色组件测试没有覆盖真实生产因果链，因此：

```text
60bb7fed = 唯一修复基线
60bb7fed != release-ready
fd3550e0 = 历史冲突解析参考，不得成为修复基线或新的 merge parent
```

所有文档和未来实现必须保留 `60bb7fed` 的两个父提交：

- release first parent：`6aad77ea4c67609ceed9b545d392de4ff1eaab3b`；
- budget second parent：`5b67181e2d287fb306bae953075c89e2c6be32ab`。

本轮只批准本地工程修复和认证，不批准 push、Tokyo deploy、PG production
migration、policy activation、live scope 变化或 exchange write。

## 2. Product And Authority Boundary

### 2.1 Owner policy remains unchanged

| Policy dimension | Authorized V0 value | Remediation behavior |
| --- | ---: | --- |
| **Maximum concurrent positions** | **2** | Preserve |
| **One new Action-Time Lane** | **1** | Preserve |
| **Planned stop risk per Ticket** | **2.5%** | Preserve |
| **Portfolio held-risk cap** | **6%** | Preserve |
| **Primary risk-cluster cap** | **4%** | Preserve |
| **Initial-margin cap** | **90%** | Repair conservation |
| **Maximum leverage** | **10x** | Preserve |
| **Same-instrument second Ticket** | **Prohibited** | Enforce across one-way and hedge modes |
| **Automatic downsize** | **Enabled** | Preserve exact rounded-risk semantics |
| **Unknown ownership or reconciliation** | **Fail closed for new ENTRY** | Existing protection and exit continue |
| **Rollback to one position** | **No forced close; no protection cancellation** | Stop only new ENTRY until capacity is within policy |

These values are architecture inputs, not implementation choices. Local repair must not
change them. Production activation remains a separate Owner policy event after local and
shadow certification.

### 2.2 Global authority model

```text
Owner controls policy.
System executes process.
Tradeability Decision answers can-trade.
Runtime Safety State answers live-submit safety.
Review updates strategy governance.
```

Ticket remains the sole business lifecycle owner. A Capacity Claim is an immutable
reservation fact, Account Exposure Current is a derived current fact, and Account Budget
Current is the single account/profile capacity projection. None of them creates signal,
Ticket, FinalGate, Operation Layer, protection, or exchange-write authority by itself.

## 3. Frozen Engineering Boundary

### 3.0 Evidence basis

| Evidence surface | Exact reference | Use in this design |
| --- | --- | --- |
| **Merged tree** | `60bb7fedcd2b9bd300cef900c6bbb304c5a34770` | Only repair baseline; current production-shape review target |
| **Release parent** | `6aad77ea4c67609ceed9b545d392de4ff1eaab3b` | Runner, recovery, adoption and deploy lifecycle provenance |
| **Budget parent** | `5b67181e2d287fb306bae953075c89e2c6be32ab` | Capacity, projection, identity and migration provenance |
| **Current code/schema** | Tracked code and migrations `086`, `121 -> 133` in the repair worktree | Higher authority than prior green test summaries |
| **Owner policy** | Confirmed risk table in section 2.1 | Numeric and rollback boundary; not implementation discretion |

The finding registry is derived from direct production-path code review of these surfaces.
Prior component test counts are retained only as historical evidence and do not override a
confirmed causal-path defect.

### 3.1 Allowed scope

- account-capacity fact collection and Action-Time binding;
- full-account typed snapshot and streaming parser;
- account exchange ownership and hedge bucket identity;
- Account Exposure Current and Account Budget Current;
- Capacity Claim, Ticket materialization, FinalGate revalidation and reservation release;
- lifecycle-triggered account-current refresh;
- Ticket exit-policy runner, restart recovery and adoption correctness;
- forward migrations `134 -> 136`;
- runtime dependency lock and deployment identity gates;
- focused, PostgreSQL, migration, performance and full-suite certification;
- status corrections in current authoritative documentation.

### 3.2 Forbidden scope

- changes to StrategyGroup semantics, detector parameters or trading signals;
- a second Ticket, runner, recovery, gateway, risk engine or file-backed authority;
- live profile, account, symbol, side, leverage or notional expansion;
- production policy activation, deployment or exchange write;
- JSON/Markdown/YAML/JSONL runtime fallback or recurring report writer;
- editing migrations `086` or `121 -> 133`;
- rewriting either source branch or merging `fd3550e0` into the repair branch;
- adding inverse, quanto or nonlinear instrument execution support in V0.

## 4. Deep-Review Finding Registry

Severity labels differed between branch-level and merged-tree reviews. Execution therefore
uses stable repair IDs rather than relying on P0/P1/P2 labels.

| Repair ID | Confirmed defect | Functional consequence | Mandatory outcome |
| --- | --- | --- | --- |
| **CAP-01** | `account_capacity_base_safe=true` is stored inside an unsatisfied/unbound legacy `account_safe` fact | Existing protected position prevents Invocation before capacity arbitration | Independent bindable capacity-base fact |
| **CAP-02** | Exposure/Budget are projected before Claim; Claim/Ticket are written afterward | FinalGate sees zero slot for its own Ticket | Post-claim projection in one transaction |
| **CAP-03** | Reservation-only Exposure stores pending margin as zero while Budget removes the same Reservation | Portfolio initial margin is understated | Episode-level risk/slot/margin exactly once |
| **CAP-04** | Budget Current permits multiple policy-version rows while locks query only account/profile | Policy version change can raise multiple-row failure or split current authority | One current row per account/profile |
| **CAP-05** | Retention, canary, readiness and readmodel consumers recognize only the legacy account-safe reference | A valid capacity-base fact can be deleted, ignored or downgraded after Ticket creation | Canonical fact pair conserved through every consumer and retention query |
| **CAP-06** | Adding capacity/Claim fields to model-wide or fixed-field hashes would reinterpret historical digests | Upgrade can invalidate immutable Tickets/Claims or leave new authority fields unhashed | Frozen V1 verifiers plus explicit V2 schemas; migrations never rehash history |
| **SNAP-01** | Zero position with `entryPrice=0` is validated before zero-quantity filtering | Whole account snapshot becomes unavailable | Zero rows accepted and filtered before positive entry validation |
| **SNAP-02** | Algo order parser discards `clientAlgoId` | Owned protection can be classified as external unknown | Preserve canonical client identity |
| **SNAP-03** | Open-order facts discard executed quantity | Partial-fill entry and protection risk use original quantity | Preserve orig/executed/remaining quantity |
| **OWN-01** | Order identity matching omits instrument/account identity | Cross-instrument ID collision can misclassify ownership | Composite identity key |
| **OWN-02** | Position classification and Exposure IDs collapse hedge LONG/SHORT to `BOTH` | One bucket can overwrite or mis-own the other | Mode and bucket are first-class identity |
| **OWN-03** | Historical migration backfill chooses one overlapping mapping with `LIMIT 1` | Incorrect canonical instrument can become enforced current truth | Forward migration revalidates exactly one mapping |
| **CUR-01** | Account Current refresh is gated by Ticket-local lifecycle enums | Wallet, qty, margin or other instrument changes can remain stale | Every fresh complete snapshot refreshes current |
| **CUR-02** | Reservation release happens after lifecycle reprojection | Released risk/slot/margin remain in current until a later trigger | Release and post-release projection are one closure |
| **CUR-03** | Exposure projector scans all historical flat instruments | Runtime cost grows with account history | Query and update only current non-flat/blocked scope |
| **EXT-01** | Core capacity math assumes `contract_multiplier=1` | Non-unit linear contracts are mispriced | Explicit linear calculation kind and multiplier math |
| **EXT-02** | “Backfill provably linear” had no exact target set or predicate | Migration could label unsupported current instruments as linear or partially mutate before abort | Preflighted target set and exact Binance USD-M predicate |
| **RUN-01** | TP1-complete evaluator returns break-even floor before structural/reference trailing | Runner never advances beyond the first floor | Floor becomes lower/upper bound, not terminal decision |
| **RUN-02** | Restart recovery reads only the most recent 50 symbol fills | Older or highly split Entry cannot restore runner state | Exact order fill recovery with bounded pagination |
| **RUN-03** | Adoption index permits only one accepted event for Ticket history | accepted -> revoked -> accepted cannot recover | Effective, non-revoked uniqueness under Ticket lock |
| **RUN-04** | Proposed Binance recovery sent unsupported `orderId` to `/userTrades` and omitted bounded order-lifetime discovery | Recovery contract cannot be implemented against the real venue API | Time/fromId algorithm with local exact-order filtering |
| **RUN-05** | Revoked adoption semantics did not distinguish protective reads from new runner mutation | Revocation can either erase recovery truth or accidentally retain mutation authority | Capability-specific binding with `mutation_allowed=false` |
| **DEP-01** | Near-expiry recertification renews payload but restores with old certification ref | Deploy remains contained after pointer/schema switch | Ref and payload replaced atomically |
| **DEP-02** | `requirements.txt` imports `ijson`, runtime hashed lock does not contain it | Immutable runtime venv can fail at import | Regenerated Linux/Python 3.10 lock and import smoke |
| **DEP-03** | Existing release reuse trusts mutable manifest SHA | Altered tree can masquerade as intended commit | Canonical tracked-tree digest on stage, resume and activation |
| **DEP-04** | Deploy/postdeploy defaults still describe migration `124/125` | Default release path disagrees with integrated schema | All release gates target planned head `136` |
| **DEP-05** | Pre-certification activation record was incorrectly required to contain a later renewed pair | Certification phase order would become cyclic or mix A/B identity | Pair-free provisional record; one renewed pair for post-certification surfaces |
| **DEP-06** | Import/compile may mutate candidate source and resumed phases can trust stale journal output | A staged tree can drift after its digest check | Bytecode isolation, read-only source and Git-object revalidation on resume |
| **DEP-07** | Remote state machine still defaults missing `expected_revision` | Direct CLI/config path can target the wrong schema revision | Mandatory revision with no default before staging |
| **QA-01** | `pytest -ra` does not fail on skip/xfail and an ambient DSN can point at a non-disposable database | Required integration proof can appear green without running or can mutate the wrong PG | Fail-on-skip plugin and self-contained loopback Docker PG gate |

Existing remediation invariants remain mandatory and are recertified rather than
reimplemented as parallel services: actual rounded stop risk, immutable policy-event epoch,
quantity-specific conservative protection segments, nonterminal ownership and lock-first
PostgreSQL arbitration.

### 4.1 Inherited-invariant recertification matrix

| Invariant ID | Inherited invariant | Owning tasks | Mandatory direct evidence |
| --- | --- | --- | --- |
| **INV-01** | Actual rounded quantity is used to recompute stop risk | T05, T09, T11 | `tests/unit/test_account_capacity_materialization.py`, `tests/unit/test_account_capacity_reservation.py`, `tests/unit/test_account_capacity_finalgate_guard.py` |
| **INV-02** | One immutable policy event is the authorization epoch for Claim, Budget and Ticket | T04, T05, T11 | `tests/unit/test_account_budget_current.py`, `tests/unit/test_account_capacity_claim_persistence.py`, `tests/integration/test_account_capacity_postgres.py` |
| **INV-03** | Protection risk is conserved by quantity-specific segments | T02, T04, T11 | `tests/unit/test_account_exposure_current.py`, `tests/unit/test_account_risk_lifecycle_reprojection.py`, `tests/integration/test_dual_position_account_risk_remediation_full_chain.py` |
| **INV-04** | Nonterminal Ticket ownership cannot be reassigned or collapsed across account/instrument/bucket | T02, T11 | `tests/unit/test_account_exposure_current.py`, `tests/unit/test_ticket_exit_execution_binding.py`, full-chain identity negatives |
| **INV-05** | Account/profile arbitration locks PostgreSQL authority before capacity calculation | T04, T05, T11 | `tests/integration/test_account_capacity_postgres.py`, including two concurrent first Claims with no pre-existing Budget Current row |

An inherited invariant is not recertified by a broad suite alone. Its owning task must run the
named direct tests, and T11 must rerun the matrix against the integrated head.

## 5. Selected Architecture

### 5.1 Options considered

| Alternative | Description | Benefit | Cost | Decision |
| --- | --- | --- | --- | --- |
| **A. Patch failing call sites** | Add conditions around current facts, projection and tests | Small diff | Preserves contradictory sources and fixture-only success | Rejected |
| **B. Unified current-authority remediation** | Repair fact, Claim, episode, current projection, lifecycle and deployment contracts on `60bb7fed` | Closes the whole functional class without a second engine | Coordinated migrations and cross-boundary tests | **Selected** |
| **C. Repair source branches then remerge** | Fix release and budget independently | Smaller per-branch diffs | Repeats semantic merge, risks losing seven release repairs and changes source histories | Rejected |

### 5.2 Core authority split

```text
FullAccountRiskSnapshot = one fresh exchange observation
Account Capacity Claim = immutable planned capacity facts for one attempt
Budget Reservation status = mutable capacity lifecycle for that Claim
Account Exposure Current = current per-episode exchange/reservation projection
Account Budget Current = one account/profile aggregate current projection
Ticket = sole trade lifecycle owner
FinalGate = revalidation of the same persisted Claim and current facts
```

No consumer may infer one authority from another. In particular, an Exposure row does not
create a Claim, a Claim does not create a Ticket, and a current projection does not grant
exchange-write authority.

### 5.3 Branch semantic conflict resolution

| Boundary | Release-parent assumption | Budget-parent assumption | Unified resolution |
| --- | --- | --- | --- |
| **Account entry fact** | `account_safe` requires flat candidate-symbol scope | Active risk policy must admit a complete non-flat account to capacity arbitration | Preserve legacy fact; add full-account `account_capacity_base.v1` |
| **Lifecycle owner** | Ticket owns order/protection/recovery/settlement | Claim/Reservation owns planned account capacity | Claim never owns trade lifecycle; Ticket never invents capacity |
| **Atomic creation** | Ticket IDs are produced inside the Action-Time sequence | Claim hash requires Ticket/episode identity | Pre-generate immutable Ticket/episode IDs before Claim; commit Claim/current/Ticket once |
| **Terminal release** | Real Exposure/open-order truth prevents release | Reservation-only Exposure intentionally holds a planned slot | Exclude only the exact planned row from real-exposure detection; retain every real/unknown row |
| **Current refresh** | Lifecycle enum change drives work | Wallet, qty, margin and cross-instrument truth can change independently | Every fresh complete snapshot refreshes current; fingerprint gates audit events only |
| **Instrument/order identity** | Symbol and order IDs are sufficient in older paths | Exact instrument, mode, bucket and episode are required | Composite account/instrument/type/value identity plus explicit hedge bucket |
| **Migration chain** | Release ends at `125` | Budget migrations were authored on another numbering base | Merged `126 -> 133` remains immutable; only `134 -> 136` moves forward |
| **Runtime package** | Existing hashed lock has no `ijson` | Integrated parser imports `ijson` | Resolve one Linux/CPython 3.10 hashed lock from the integrated tree |
| **Runner behavior** | Release lifecycle owns trailing and recovery | Budget model must not redefine exit policy | Repair the release path in place; capacity code has zero runner authority |

These are resolved architecture conflicts, not outstanding Owner policy choices. A future
implementation that restores either parent assumption in isolation fails this design.

## 6. Account-Capacity Fact Surface

### 6.1 Preserve legacy flat semantics

The existing `account_safe` fact retains its exact flat-account meaning. It must not be
silently redefined when an account-risk policy becomes active because older profiles and
diagnostics still depend on it.

### 6.2 Add one independent fact

When an active account-risk policy exists, the production collector uses
`BinanceUsdmAccountRiskSnapshotProvider` and the streaming signed reader to fetch all five
full-account endpoints, including regular and Algo orders, outside PG. That one snapshot
produces a separate typed PG fact:

```text
fact_key = account_capacity_base
fact_values.schema_version = account_capacity_base.v1
satisfied = snapshot_ready
            AND can_trade is true
            AND position_mode in {one_way, hedge}
            AND account/profile identity is exact
            AND positions + regular orders + algo orders are complete
```

`account_capacity_base` may be satisfied while the account is not flat. It does not decide
remaining capacity and does not authorize ENTRY; it only permits the Account Capacity
materializer to run.

The current `account_capacity_base_safe` boolean embedded in legacy `account_safe` payloads is
deprecated decision data. It may remain in historical rows, but no Invocation, Ticket,
FinalGate, Runtime Safety State or Operation Layer consumer may use it after migration 134.

Migration 134 adds `account_capacity_base_fact_snapshot_id` to ActionTimeInvocation, Action-Time
Lane and Ticket. It makes the legacy Ticket `account_safe_fact_snapshot_id` nullable through a
forward schema change. After fact binding:

```text
no active account-risk policy -> account_safe_fact_snapshot_id set
                              -> account_capacity_base_fact_snapshot_id null

active account-risk policy    -> account_safe_fact_snapshot_id null
                              -> account_capacity_base_fact_snapshot_id set
```

An open Invocation may have neither capacity reference before fact collection, but it may never
hold both. Exactly one reference must be present before Invocation evidence can enter capacity
arbitration, and on every bound Lane and materialized Ticket. Each consumer validates the
referenced row's exact `fact_surface`, `satisfied`, freshness,
account/profile/exchange identity and snapshot ID; it never “relaxes” blockers from the other
surface.

Action-Time binding rule:

```text
no active account-risk policy -> require legacy account_safe
active account-risk policy    -> require account_capacity_base
```

Both facts retain the same bounded freshness window and the same source snapshot identity.
An unsatisfied fact is persisted for audit but is never bound into an Invocation.

Every downstream surface derives one canonical selected reference instead of branching on two
nullable columns independently:

```text
account_capacity_fact_surface in {account_safe, account_capacity_base}
account_capacity_fact_snapshot_id = the non-null physical reference selected by that surface
```

The physical Invocation, Lane and Ticket rows retain
`account_safe_fact_snapshot_id` plus `account_capacity_base_fact_snapshot_id` because they must
preserve historical legacy identity. The canonical pair above is the only form passed to new
FinalGate, Runtime Safety, canary, candidate-pool and simulation consumers. An unknown surface,
a missing selected row, both physical references, or a canonical/physical mismatch fails closed.

Reference conservation applies to every current consumer, not only Ticket materialization:

| Consumer class | Required change | Retention / compatibility rule |
| --- | --- | --- |
| **Invocation, Lane, Ticket** | Persist the two physical nullable references and expose the canonical selected pair | Invocation may temporarily have neither; evidence-ready Invocation, bound Lane and Ticket require exactly one |
| **FinalGate, Operation Layer, Runtime Safety Truth** | Validate canonical surface, ID, identity, freshness and satisfaction; V2 Runtime Safety rows physically copy the canonical pair as trusted-reference columns | New Runtime Safety Truth rows use V2; V1 remains audit-readable but is never submit-authoritative, even when its stored status was historically `live_submit_ready` and has not yet expired |
| **Fresh-signal boundary, readiness and candidate pool** | Carry the canonical pair without converting `account_capacity_base` back to `account_safe` | Missing/unknown V2 reference blocks promotion; it cannot be relaxed by a legacy boolean |
| **Canary mutation sentinel and repository** | Add V2 column sets/digest input for both physical references plus canonical surface | V1 digest verification remains frozen for historical sentinels; V2 is required for newly captured rows |
| **Full-chain simulation harness** | Exercise both surfaces through the same production materializers | Typed in-memory/PG fixtures only; no file evidence fallback |
| **Runtime-control retention** | Preserve every fact directly referenced by Invocation, Lane, Ticket or a non-expired V2 Runtime Safety trusted-current row | Migration 134 indexes every physical fact-reference column; retention uses set-based `NOT EXISTS` joins and never deletes a still-referenced capacity fact |
| **Deploy legacy bridge/canary** | Treat the pair as a versioned deploy contract and reject a one-column downgrade | T10 owns deploy-state-machine compatibility; no target-derived legacy default |

Migration 134 and T04 must run a whole-repository consumer inventory before implementation.
The frozen minimum inventory is:

```text
scripts/run_runtime_control_state_retention.py
scripts/build_strategy_fresh_signal_action_time_boundary.py
src/application/readmodels/canary_mutation_sentinel.py
src/infrastructure/canary_mutation_sentinel_repository.py
src/application/readmodels/runtime_safety_truth.py
src/application/readmodels/strategy_group_live_facts_readiness.py
src/application/readmodels/strategy_live_candidate_pool.py
src/application/action_time/full_chain_simulation_harness.py
scripts/tokyo_runtime_deploy_remote_state_machine.py
```

The inventory is an acceptance floor, not a whitelist: any additional producer, reader,
retention query, digest, serializer or trusted-reference comparison found by `rg` must be
classified and migrated in T04 or explicitly assigned to T10 before CAP-01 can close.

`runtime_safety_submit_authorized` dispatches on `trusted_fact_refs_schema_version` before
interpreting status or freshness. V1 may be rendered for audit and recovery diagnosis, but it
always returns `false` for submit authority. Only V2 with an exactly matching canonical fact
pair, V2 Ticket hash schema, current identity and fresh satisfied facts may return `true`.
Migration 134 does not rewrite historical V1 status to simulate this rule; the versioned reader
enforces it, and the first new authoritative materialization must be V2.

The active-policy collector reads exact account/profile/exchange identity and policy presence
in a short PG transaction, closes it, performs the full signed GET collection, then writes the
fact in another short transaction. The no-policy legacy collector remains unchanged.

### 6.3 Runtime-profile technical identity

The exact `runtime_profile_id` comes from the current runtime scope binding selected for the
account. Policy tooling must require explicit `account_id` and `runtime_profile_id`, validate
that exact binding, and must not default to either `runtime-order-capable` or
`owner-runtime-console-v1`. A mismatch is a technical identity blocker and creates no policy
event or second Budget Current authority. This remediation tests the tool contract but does
not activate a policy.

## 7. Canonical Identity And Snapshot Contract

### 7.1 Position identity

```text
Exposure netting domain = account_id
                        + exchange_instrument_id
                        + position_mode
                        + position_bucket

V0 capacity slot       = account_id + exchange_instrument_id
```

One-way mode uses bucket `BOTH`. Hedge mode uses `LONG` or `SHORT`. V0 still prohibits a
second system Ticket for the same instrument; an unexpected nonzero opposite bucket is
`external_unowned` or `identity_conflict` and blocks new ENTRY.

### 7.2 Order identity

Every exchange order identity lookup uses:

```text
(account_id, exchange_instrument_id, id_kind, id_value)
```

Supported `id_kind` values are `order_id`, `algo_id`, `client_order_id` and
`client_algo_id`. Matching also validates side, position bucket and lifecycle role.

### 7.3 Quantity contract

The normalized open-order model stores:

```text
orig_qty
executed_qty
remaining_qty = max(orig_qty - executed_qty, 0)
```

Working-entry risk and outstanding protection coverage use `remaining_qty`. Filled position
risk uses current position quantity. Original quantity remains audit evidence only.

### 7.4 Zero-position rows

For `positionAmt == 0`, `entryPrice == 0` is valid exchange output. The streaming reader
must parse symbol, quantity and bucket first, discard the zero row, and require positive
entry price only for nonzero positions.

## 8. Current Projection And Capacity Accounting

### 8.1 One Budget Current row

`brc_account_budget_current` has exactly one current row for:

```text
(account_id, runtime_profile_id)
```

The row stores current `risk_policy_version` and `account_risk_policy_event_id` as values.
Historical policy/budget meaning belongs in append-only events. `projection_version` is
monotonic inside the account/profile scope.

Policy tightening applies immediately to whether a new ENTRY is allowed. It does not
rewrite or terminate existing Ticket lifecycle facts.

### 8.2 Episode-level exactly-once accounting

The deduplication identity is `reservation_id + exposure_episode_id`, not Ticket ID alone.

| Episode stage | Held / cluster risk | Slot | Local pending margin | Portfolio margin used | Entry authority |
| --- | ---: | ---: | ---: | ---: | --- |
| **Claim active/consumed, no exchange exposure** | `claim.risk_at_stop` | `1` | `reserved_margin` | `exchange_total_initial_margin + reserved_margin` | Capacity held |
| **Working or partial fill, partially reflected** | `max(claim risk, filled directional risk + remaining working risk)` | `1` | Margin for only the still-unreflected planned quantity | `exchange_total_initial_margin + unreflected_remaining_margin` | Capacity held |
| **Working/filled, exact exchange-reflected** | Quantity-specific held risk | `1` | `0` | `exchange_total_initial_margin` | Capacity held |
| **Unknown or mismatch** | `max(last-known hold, claim risk)` | `1` plus global new-entry block | `max(last-known local hold, reserved_margin)` | Conservative upper bound | Blocked |
| **Flat, matched, released** | `0` | `0` | `0` | Current exchange margin only | Capacity released |

For a known episode, exact owned position quantity plus exact owned remaining Entry-order
quantity forms `exchange_reflected_entry_qty`, capped at planned quantity. Decimal-only local
pending margin is:

```text
unreflected_qty = max(planned_qty - exchange_reflected_entry_qty, 0)
unreflected_remaining_margin = reserved_margin * unreflected_qty / planned_qty
```

This prevents both disappearance and double counting when only part of an Entry is reflected.
If exact quantity/lineage is unavailable, the episode is `unknown`; it does not guess a ratio.

Margin reflection states are:

- `reserved_unreflected`: add local `reserved_margin`;
- `partially_reflected`: add only exact `unreflected_remaining_margin`;
- `exchange_reflected`: do not add local margin again;
- `unknown`: fail closed for new ENTRY;
- `released`: add zero.

Transition to `exchange_reflected` requires exact command/order/position lineage. Elapsed
time or mere existence of an Exposure row is insufficient.

### 8.3 Risk calculation kind

V0 supports only:

```text
risk_calculation_kind = linear_quote_settled
notional = abs(qty) * price * contract_multiplier
stop_risk = abs(entry - stop) * abs(qty) * contract_multiplier
reserved_margin = notional / leverage
```

Unknown, inverse, quanto or nonlinear kinds fail closed before Claim creation. Supporting
them later requires a new adapter and Owner live-scope decision; this remediation only
prevents unit-multiplier assumptions in the core model.

Migration 136 does not infer this kind from a default. It builds an explicit target set from:

```text
1. every brc_instrument_rule_snapshots row with status = 'current';
2. every rule snapshot referenced by a brc_budget_reservations row whose status is
   'active' or 'consumed';
3. for every brc_account_exposure_current row whose exposure_state is not 'flat' or 'closed',
   the exactly one current rule snapshot for its exchange_instrument_id.
```

Before any UPDATE, every target must join exactly one `brc_exchange_instruments` row and pass
all of the following predicates:

```text
instrument.exchange_id = 'binance_usdm'
instrument.status = 'active'
instrument.asset_class = 'crypto'
instrument.instrument_type in ('perpetual', 'future')
trim(instrument.settlement_asset) <> ''
trim(instrument.margin_asset) <> ''
instrument.settlement_asset = instrument.margin_asset
rule.contract_multiplier > 0
```

These predicates prove only the already-supported Binance USD-M linear adapter; they do not
authorize another venue or asset class. Zero/multiple instrument joins, zero/multiple current
rule rows for a nonterminal Exposure, unsupported metadata and a non-positive multiplier abort
the migration before semantic-row mutation with, respectively,
`risk_calculation_backfill_instrument_mapping_missing_or_ambiguous`,
`risk_calculation_backfill_current_rule_missing_or_ambiguous`,
`risk_calculation_backfill_not_provably_linear` or
`risk_calculation_backfill_multiplier_invalid`.

Rule Snapshot V1 is immutable semantic history. Migration 136 adds nullable
`risk_calculation_kind` and `supersedes_instrument_rule_snapshot_id` with no server defaults; its
check permits null or `linear_quote_settled`. It **never** adds the kind to a V1 row, changes
`rule_schema_version='v1'`, or recomputes a V1 `semantic_hash`.

For every current, provably supported V1 row, migration 136 precomputes a deterministic V2
clone with:

```text
rule_schema_version = 'v2'
risk_calculation_kind = 'linear_quote_settled'
supersedes_instrument_rule_snapshot_id = exact V1 snapshot ID
instrument_rule_snapshot_id = 'instrument-rule:v2:'
                              + sha256(V1 snapshot ID + '|' + V2 semantic_hash)
```

The preflight also verifies all generated IDs/hashes are unique and non-conflicting before any
semantic-row mutation. Migration 133's immediate partial unique index permits only one
`status='current'` row per `exchange_instrument_id`, so migration 136 performs this exact switch
inside its one database transaction while the deployment writer fence is held:

```text
1. lock all target current V1 rows in stable key order;
2. update those exact V1 rows from current -> superseded;
3. bulk-insert the fully precomputed V2 clones as current;
4. assert each target instrument has exactly one current V2 and zero current V1.
```

An UPDATE, INSERT or postcondition failure rolls back the whole transaction, including every V1
status change; other transactions see either the complete pre-136 V1 authority or the complete
post-136 V2 authority, never an intermediate committed gap. A V1 row
referenced by an active/consumed Claim keeps its exact stored `rule_schema_version`, economic
fields and opaque historical `semantic_hash`; the Claim V1 hash continues to validate its
embedded rule fields. Migration 136 does not invent a new V1 rule-hash algorithm. That row is
never used to create a new Claim after 136. A referenced superseded V1 row is predicate-validated
but not cloned unless it is also current.

V2 `semantic_hash` is SHA-256 over canonical Decimal strings and this exact economic payload:

```text
schema = brc.instrument_rule_snapshot.v2
exchange_instrument_id
price_tick
quantity_step
min_qty
min_notional
contract_multiplier
risk_calculation_kind
exchange_max_leverage_for_claim_notional
```

Snapshot ID, source fact, validity timestamps, status and creation time are provenance/control
fields and are excluded. `InstrumentRuleSnapshotRefV2` carries this semantic hash, kind and
multiplier into Claim V2. New-Claim/current loaders require exactly one current V2 row, recompute
its semantic hash and fail on null, mismatch, V1 current or unknown schema. Historical Claim V1
paths use only the frozen Claim V1 verifier and exact referenced V1 row; its opaque stored V1 rule
hash is compared for identity where already referenced, never recomputed.

Superseded, unreferenced historical V1 rows remain audit-only and unchanged. A legacy-compatible
136 downgrade requires no Claim V2 and only deterministic migration-created V2 clones. After a
complete preflight it deletes those current clones, restores each exact superseded V1 predecessor
to current in the same transaction, and asserts one current V1/zero current V2 per instrument.
Any runtime-created V2,
missing predecessor, changed V1 hash/status lineage or V2 Claim aborts before mutation with
`instrument_risk_history_not_legacy_compatible`.

## 9. Atomic Claim-To-Ticket Transaction

Exchange I/O is completed outside the PG transaction. The only valid mutation order is:

```text
1. Fetch FullAccountRiskSnapshot with one total timeout outside PG.
2. Begin the existing Action-Time PG transaction.
3. Lock the unique Account Risk Policy Current row FOR UPDATE as the bootstrap/serialization anchor.
4. Validate its active policy event plus snapshot freshness, account/profile identity and rules.
5. Refresh pre-claim Exposure Current from snapshot + effective claims.
6. Insert-or-update the unique Account Budget Current row, then hold that row FOR UPDATE.
7. Compute remaining slot/risk/cluster/margin and final rounded quantity.
8. Pre-generate Ticket/episode IDs and insert all immutable Claim fields with Reservation status=active.
9. Project the new Claim as reservation-only Exposure with risk/slot/margin.
10. Write post-claim Budget Current and increment projection_version.
11. Materialize Ticket from the same immutable Claim identity.
12. Verify Ticket/episode/hash equality and transition only Reservation status active -> consumed.
13. Commit once.
```

Any failure from step 3 through 12 rolls back Claim, projections, Ticket and status change.
No network or subprocess work is allowed under the account lock.

### 9.1 Claim and Reservation semantics

- Claim payload fields are immutable after insertion.
- `ticket_id`, `exposure_episode_id` and `capacity_claim_hash` are pre-generated Claim fields;
  the consumed transition verifies them and does not update them.
- Reservation `active` means capacity exists before Ticket creation.
- Reservation `consumed` means the same Claim is bound to a Ticket.
- FinalGate for a materialized Ticket requires `consumed`, not `active`.
- FinalGate requires exact `ticket_id`, `exposure_episode_id`, `capacity_claim_hash`, policy
  event, source snapshot and post-claim projection lineage.

FinalGate revalidates current authority; it does not calculate a second independent budget.

### 9.2 Immutable hash and readmodel version boundary

Adding the capacity fact pair or `risk_calculation_kind` must not reinterpret an already stored
hash. Migration changes are additive and schema-dispatched:

| Authority | Historical verifier | New verifier | Required payload change |
| --- | --- | --- | --- |
| **Action-Time Ticket** | `action_time_ticket_hash.v1` uses the frozen pre-134 field set | `action_time_ticket_hash.v2` | V1 fields plus canonical capacity fact surface/ID, `exposure_episode_id` and `capacity_claim_hash` |
| **Account Capacity Claim** | verifier contract `account_capacity_claim.v1` uses the frozen pre-136 model dump; stored `capacity_claim_schema_version='v1'` | verifier contract `account_capacity_claim.v2`; stored value `'v2'` | `InstrumentRuleSnapshotRefV2` adds `risk_calculation_kind`; hash includes kind and multiplier |
| **Canary mutation sentinel** | `brc.canary_mutation_sentinel.v1` keeps its frozen column lists and digest algorithm | `brc.canary_mutation_sentinel.v2` | Both physical capacity refs, canonical surface and the Ticket hash schema version |
| **Runtime Safety Truth / trusted refs** | stored `runtime_safety_trusted_refs.v1` preserves the frozen legacy trusted-ref keys/interpretation | stored `runtime_safety_trusted_refs.v2` | Canonical capacity pair and Ticket hash schema version are equality-checked end to end; this readmodel has no historical digest to rehash |

Migration 134 adds `ticket_hash_schema_version`, backfills existing Tickets as
`action_time_ticket_hash.v1` and **does not recompute or update `ticket_hash`**. Before labeling,
it keyset-scans existing Tickets in bounded batches and verifies each stored hash with the frozen
V1 field tuple; a blank or mismatch aborts before the version UPDATE with
`ticket_hash_v1_preflight_failed`. Every Ticket created after 134 uses V2. Mutation of any new
V2-bound field must invalidate the V2 hash; an unknown schema version fails closed.

Migration 136 introduces stored Claim schema value `v2` for new Claims. Existing Claim `v1`
rows and hashes continue to
validate against the exact frozen V1 model/field set; they are not deserialized into V2 and
rehashed. Ticket V2 binds `capacity_claim_hash`, so the calculation kind and multiplier of a
new Claim V2 are transitively protected through FinalGate and Runtime Safety.

Migration 134 adds `trusted_fact_refs_schema_version` to Runtime Safety snapshots, labels
existing rows `runtime_safety_trusted_refs.v1`, and writes the physical canonical pair only for
new V2 rows. It does not fabricate a Runtime Safety Truth hash. Downgrade 134 aborts with
`capacity_fact_history_not_legacy_compatible` if any Ticket V2 or
V2-only selected capacity reference exists. Downgrade 136 aborts with
`instrument_risk_history_not_legacy_compatible` if any Claim `v2` or calculation-kind authority
cannot be represented by the V1 schema. A fixture is legacy-compatible only when it has no Claim
`v2`, every V2 row is an unchanged deterministic migration clone, and every clone has its exact
V1 predecessor. The downgrade deletes only those clones and restores the predecessor's mutable
`current` status; it never drops an explicit kind from, or recomputes, a historical V1 row. Only
such an explicitly seeded fixture may complete the local downgrade proof. No migration may
rewrite a historical Ticket, Claim or canary digest, or fabricate a Runtime Safety digest, to
make downgrade succeed.

## 10. Current Refresh And Release Semantics

### 10.1 Separate current refresh from audit emission

Every fresh, complete account snapshot refreshes quantitative current fields and extends
their validity, even when Ticket lifecycle enums do not change. The semantic fingerprint
controls only append-only event emission.

The account fingerprint includes wallet/available/initial margin, position mode, instrument
and bucket, quantity, entry price, open order identity, remaining quantity, trigger price,
reflection state and source snapshot identity.

### 10.2 Bounded current scope

The projector reads only:

- current non-flat, working, unknown or blocked Exposure rows;
- effective active/consumed Reservations bounded by policy `max_positions + 1`;
- instruments present in the new snapshot.

Historical flat episodes remain in append-only events and are not loaded into each runtime
tick. Snapshot-absent current rows are set-based transitioned to flat only when the complete
snapshot proves absence.

### 10.3 Pre-submit release

```text
Ticket terminal
AND no exchange dispatch/write/unknown outcome
AND no real position or open order
-> consumed Reservation released
-> reservation-only Exposure removed or projected flat
-> Budget Current refreshed in the same transaction
```

The reservation-only slot derived from the Claim is not evidence of exchange exposure and
must not create a circular refusal to release itself.

### 10.4 Post-submit release

```text
Ticket lifecycle terminal
AND exact exchange position flat
AND reconciliation matched
AND residual protection handled
-> Reservation released
-> Exposure projected flat
-> Budget Current refreshed once
```

A settlement evidence ID without flat + matched exchange truth cannot release capacity.

## 11. Runner And Restart Recovery

### 11.1 Trailing evaluation order

After TP1 completion, the break-even floor is a directional bound:

- long runner stop cannot move below the floor;
- short runner stop cannot move above the floor.

It is not a terminal return and it is not an immediate hard-state rewrite. It is the minimum
target for any **emitted** post-TP1 mutation. A floor-only move uses the floor rule's own
`minimum_improvement_ticks`; if the current stop is one tick outside a two-tick threshold, the
runner remains a no-op until the threshold is reached. If a floor move reaches its threshold,
emit exactly one floor generation. Otherwise evaluate only the candidate authorized by the
immutable policy's mutually exclusive `runner_rule`:

- `structural_atr` reads only `structural_stop_candidate`;
- `reference_trail` reads only `reference_stop_candidate`;
- `no_runner` reads neither.

Clamp any emitted structural/reference candidate by the floor, apply that runner rule's own
`minimum_improvement_ticks`, and emit at most one strict directional improvement per newer
closed watermark. An unconfigured candidate is ignored. Open candles, repeated watermarks and
sub-threshold/non-improving candidates remain idempotent no-ops.

### 11.2 Exact Entry fill recovery

Recovery first consumes durable PG fill/order lineage. If quantity, average price or fee
evidence is incomplete, it calls a read-only gateway method scoped to exact symbol and Entry
exchange order ID.

The narrow gateway interface is:

```text
fetch_order_trades_exact(
    exchange_market_id,
    exchange_order_id,
    entry_order_created_at_ms,
    entry_order_terminal_at_ms=None,
    first_durable_trade_id=None,
    page_limit=1000,
    max_pages=20,
    timeout_seconds=8,
) -> ExactOrderTradeReadResult
```

The result distinguishes `complete`, `history_incomplete`, `timeout` and `identity_mismatch`;
it never exposes a write capability.

`exchange_market_id` is the exact venue request symbol stored by instrument identity; it is not
the display symbol. Binance USD-M `/fapi/v1/userTrades` does **not** accept `orderId`. The Entry
order ID is therefore a mandatory local equality filter and is never sent as an endpoint
parameter. The official endpoint accepts `symbol`, `startTime`, `endTime`, `fromId` and `limit`;
`fromId` cannot be combined with a time range, a requested time range is at most seven days,
and omitting both time and ID restricts the result to recent history
([Binance official USD-M Account Trade List implementation](https://github.com/binance/binance-futures-connector-python/blob/main/binance/um_futures/account.py#L3280-L3322)).

The request algorithm is deterministic:

1. If durable PG lineage includes `first_durable_trade_id`, request
   `symbol + fromId + limit`, paginate in ascending trade-ID order and locally retain only the
   exact Entry `exchange_order_id`.
2. Otherwise derive bounded `startTime/endTime` windows from the durable Entry order creation
   and terminal timestamps; an open order uses the bounded recovery observation time as its
   temporary upper bound. Each window is no longer than seven days. Iterate chronological
   windows even when a window returns fewer than `limit` rows; every HTTP request consumes one
   of the global `max_pages` slots. The first page of each new window uses
   `symbol + startTime + endTime + limit`.
3. If a time-window page is full, continue with
   `symbol + fromId(last_seen_trade_id + 1) + limit` because Binance forbids combining
   `fromId` with time parameters. Apply the durable time bound locally and stop when that bound
   plus expected quantity are satisfied; rows from other orders remain ignored but advance the
   cursor.
4. Dedupe by exact exchange trade ID. Same-timestamp fills never drive pagination; trade ID is
   the only continuation cursor.

Cross-window transition is an explicit state machine. Time windows are closed millisecond
intervals `[window_start_ms, window_end_ms]`; the next window starts at
`window_end_ms + 1`, so boundary rows are neither omitted nor owned by two windows:

```text
TIME_WINDOW
  -> page not full and upper order bound not reached: NEXT_TIME_WINDOW
  -> page full: FROM_ID_WITH_WINDOW_END_GUARD(last_trade_id + 1)

FROM_ID_WITH_WINDOW_END_GUARD
  -> row.time <= window_end: consume/filter and advance trade-ID cursor
  -> first row.time > window_end: discard it for this window, NEXT_TIME_WINDOW
  -> page not full without crossing end: NEXT_TIME_WINDOW
  -> page full within end: next FROM_ID page

either state
  -> expected quantity + complete fee truth: COMPLETE
  -> order upper bound or global page/deadline bound exhausted without complete truth:
     entry_fill_history_incomplete
```

Every returned page must be strictly monotonic by exchange trade ID after dedupe. A repeated ID
is ignored; a decreasing/new non-monotonic ID is `entry_fill_history_incomplete`. The global page
counter and deadline span all states and windows and are never reset at a seven-day boundary.

Binance USD-M fallback is bounded by all of:

```text
page_limit = 1000
max_pages = 20
total_timeout_seconds = 8
dedupe_key = exchange_trade_id
continuation = bounded time window or durable fromId, then ascending fromId
identity_filter = exact local exchange_order_id equality
```

Completion requires total quantity equal to durable lifecycle quantity, average price within
one rule tick, and complete fee asset/amount. Exhausted bounds return
`entry_fill_history_incomplete`; they must not be reported as quantity contradiction or
silently accepted. An Entry outside retrievable history, empty/incomplete bounded history,
wrong raw market symbol, non-monotonic cursor or exhausted seven-day windows has the same
fail-closed outcome. The path performs zero exchange writes.

### 11.3 Adoption effective uniqueness

Adoption events remain append-only. The application locks the Ticket row before adding an
accepted or revoked event and derives effective acceptance as:

```text
accepted event for ticket
AND no later revoke supersedes that accepted event
```

At most one effective accepted event may exist. Historical accepted events do not prevent a
new acceptance after their explicit revoke. Concurrent double acceptance, duplicate revoke
of another event and revoke of an already revoked event fail closed.

Migration 135 separates adoption mutation authority from the projection's existing execution
`state`. It adds `adoption_state`, `mutation_allowed` and monotonic
`adoption_projection_version`; only the adoption service may write them. Fill, TP1 reprice,
market-fact, protection and reconciliation projectors continue to own execution/TP1 fields and
must never overwrite adoption fields.

The adoption authority has this atomic state machine under the same Ticket lock:

```text
no adoption current
-> accept A: adoption_state=accepted, mutation_allowed=true,
             adoption_event_id=A, adoption_projection_version=n+1
-> revoke A: CAS ticket_id + adoption_event_id=A + adoption_state=accepted
             + expected adoption_projection_version;
             set adoption_state=revoked, mutation_allowed=false, version=n+1
-> accept B: CAS ticket_id + adoption_event_id=A + adoption_state=revoked
             + expected adoption_projection_version;
             set adoption_state=accepted, mutation_allowed=true,
             adoption_event_id=B, version=n+1
```

The general execution `state` and `first_blocker` may continue changing during revocation and
are not CAS predicates for adoption. A database check keeps `mutation_allowed=false` exactly for
`adoption_state=revoked`; `ticket_bound` and `accepted` are true. Migration backfill maps legacy
`binding_source=ticket` to `ticket_bound`, and an exact matched accepted adoption event to
`accepted`; ambiguous/missing binding aborts migration 135 before mutation.

While `adoption_revoked`, two capabilities are intentionally separated:

- read-only legacy/protection/reconciliation/fill-recovery binding may read the last accepted
  snapshot with `mutation_allowed=false` so protective truth and TP1 coverage do not disappear;
- the runner mutation resolver fails closed and emits no new stop generation until a later
  accepted policy becomes effective.

The fill projector may continue to reconcile TP1/protection truth but cannot create runner
mutations. Accept B CAS-replaces the revoked current row, restores `mutation_allowed=true` and
binds only B for future mutations. B's current projection is rebuilt from the same durable Entry
fill, TP1 filled quantity, active protection and last emitted stop generation; adoption never
resets progress or makes an already emitted exchange command eligible again. Reaccept never
deletes the old projection/event; it replaces
the one current row by CAS and keeps all events. A downgrade that would need to recreate
migration 125's lifetime unique index aborts before DDL if multiple accepted history exists.

## 12. Forward Migration Plan

Applied history `086` and `121 -> 133` is immutable.

| Revision | Filename | Purpose |
| --- | --- | --- |
| **134** | `2026-07-17-134_repair_account_risk_current_authority.py` | Add independent capacity-fact references and exactly-one binding checks; add Ticket hash schema version without rehashing V1; version canary/Runtime Safety consumers; revalidate active/current instrument mapping; backfill Budget policy-event from exact current policy; replace Budget unique scope with account/profile |
| **135** | `2026-07-17-135_repair_exit_policy_adoption_effective_uniqueness.py` | Drop lifetime accepted-event unique index; add adoption-only state/mutation/version columns; require Ticket-row serialization and preserve append-only events |
| **136** | `2026-07-17-136_add_instrument_risk_calculation_kind.py` | Add Rule/Claim V2 and exact target-set V1-to-V2 cloning for `linear_quote_settled`; reject every non-provable current/referenced rule snapshot without rewriting V1 hashes |

Required migration proofs:

- seeded fresh bootstrap through `136`;
- release-like `125 -> 136`;
- integrated local `133 -> 136`;
- schema-only/legacy-compatible round trip `136 -> 133 -> 136` in disposable PostgreSQL;
- frozen V1 Ticket/Claim/canary hashes remain byte-identical, and Runtime Safety V1 trusted-ref
  interpretation remains unchanged, through upgrade;
- V2-only Ticket or capacity reference aborts `134 -> 133` with
  `capacity_fact_history_not_legacy_compatible` before DDL;
- V2 Claim/calculation history aborts `136 -> 135` with
  `instrument_risk_history_not_legacy_compatible` before DDL;
- after a post-135 `accepted -> revoked -> accepted` history exists, downgrade `135 -> 134`
  must abort with `adoption_history_not_legacy_compatible` without deleting or rewriting rows;
- active/current/live-eligible/nonterminal identity rows require exactly one timestamp-valid
  mapping; zero or multiple matches abort before mutation;
- terminal rows already classified `legacy_audit_only_identity_unresolved` may preserve zero or
  multiple historical matches, remain audit-only, and are excluded from current/hot/runtime
  authority; an exactly-one match may correct their stored identity without deleting evidence;
- two Budget Current policy versions in one account/profile abort rather than choose one;
- a Budget Current row with no exact account/profile current-policy `source_event_id` aborts;
- no edit to any migration through `133`.

Database downgrade is a local compatibility proof, not the production rollback path.

## 13. Runtime Packaging And Deployment Identity

### 13.1 Hashed dependency lock

`requirements-runtime.lock` is regenerated in a clean Linux Python 3.10 resolver from the
integrated `requirements.txt`, preserving `ccxt==4.5.56` and adding
`ijson>=3.5.1,<4.0.0` with hashes. Validation creates a clean venv using
`pip install --require-hashes` and imports:

```text
ijson
src.infrastructure.streaming_http_json
src.infrastructure.binance_usdm_streaming_signed_reader
src.application.action_time.lifecycle_maintenance_scheduler
```

The pre-existing uncommitted lockfile in the release source worktree is never read, copied,
staged or modified.

The production `build_immutable_venv` gate runs the same four imports after hashed install and
before writing its complete marker. A local Docker smoke is supporting evidence; it cannot
replace the production state-machine import gate.

### 13.2 Certification pair conservation

Lifecycle mutation restore receives one typed pair:

```text
(certification_ref, certification_payload)
```

If near-expiry facts are renewed, both members are replaced from the same renewed result
before any child process or capability mutation. The pre-certification
`release_activation_recorded` phase is explicitly a **provisional code/schema/pointer activation
record** and is pair-free by design because it is an input to certification. After renewal, one
typed `cert_pair` object is the only source for lifecycle restore, final
`runtime_activation_committed`, terminal manifest and resume journal. Mixed old/new pairs, use
of `post_cert` after renewal, or any old ref surviving in those post-certification surfaces
fails before subprocess execution or final activation commit.

Certification freshness is revalidated on **every resume while `policy_applied` is absent**,
including when `lifecycle_proof_persisted` or an older activation commit is already journaled.
The journal supports append-only certification generations:

```text
generation g = cert_pair_g
             + lifecycle_proof_g bound to the exact pair
             + activation_commit_g bound to the exact pair/proof/generation
```

If the latest pair has less than 30 seconds remaining, the state machine refreshes facts,
certifies a complete new pair, reruns lifecycle restore, persists a new proof and appends
generation `g+1`. It never replaces only the ref/payload or reuses proof `g`. If an older
activation commit exists but `policy_applied` does not, commit `g+1` explicitly supersedes it;
old journal entries remain audit evidence.

`policy_applied` and writer-fence removal require the latest generation's pair, lifecycle proof
and activation commit to match and still have at least 30 seconds remaining at mutation start.
If refresh/certification/restore fails, the state machine returns
`resume_certification_generation_failed`, retains the writer fence and performs no policy/fence
mutation. After `policy_applied` is durably journaled, later fact expiry does not reinterpret the
already committed activation; terminal/resume reporting uses the exact generation that applied.

### 13.3 Exact release tree

Release preparation computes a canonical source-tree digest from tracked relative path,
file mode and content digest at the target commit. The **authoritative expected digest is
rederived from the fetched target Git object on every stage/reuse/resume/activation check**;
the release manifest stores a copy but is never the trust anchor. The remote candidate
recomputes its actual tree:

```text
entries = tracked regular files sorted by UTF-8 POSIX relative path
entry   = mode_octal + NUL + relative_path + NUL + sha256(file_bytes) + LF
tree_digest = sha256(concatenate(entry for entry in entries))
```

Absolute paths, mtimes, uid/gid and directory traversal order are excluded. A tracked symlink,
untracked source entry inside the release tree, missing tracked path or duplicate normalized
path fails closed.

Changing the release tree and its manifest coherently still fails because neither can change
the digest rederived from the content-addressed target Git object.

1. immediately after fresh staging;
2. before reusing an existing release directory;
3. immediately before activation.

`.venv`, deploy journal, manifest itself and explicitly provisioned persistent runtime config
are outside the source-tree digest and are separately identity-bound. Missing, extra,
symlinked, owner-invalid or content-modified source entries reject reuse.

All candidate-source imports run with `PYTHONDONTWRITEBYTECODE=1`. The deploy state machine
removes `compileall`; the hashed-install four-module import gate and the later test suite are the
syntax/import validation authority, so no compile cache is created for release source. The
release source directories are non-writable by the runtime UID.
After the real `build_immutable_venv` install and import smoke, the actual source-tree digest is
recomputed and must remain equal to the Git-object-derived digest.

Resume is not allowed to trust a journaled `candidate_staged` or `immutable_venv_ready` result.
Before returning any reused phase result, the state machine rederives the expected digest from
the target Git object and recomputes the candidate's actual tree; tamper after staging must fail
before writer fence, migration or pointer activation.

### 13.4 Migration target versus remote baseline

| Surface | Target candidate authority | Pre-deploy remote baseline |
| --- | --- | --- |
| **Release preparation** | Minimum/count `136`; latest `2026-07-17-136_add_instrument_risk_calculation_kind.py` | Not applicable |
| **Deploy planner** | Derive target count from candidate and require latest `136...py` | Required explicit count/head from the read-only remote probe; no target-derived default |
| **Deploy executor** | Consume the immutable plan's target 136 identity | Consume the same explicit observed remote baseline; reject missing values |
| **Postdeploy verifier** | Exact current count/head 136 | Historical prestate is audit only |
| **Remote state machine** | Migrate candidate to exact 136 and journal it | Fence/rollback decisions use the probed prestate, never a fabricated 136 baseline |

Tests assert target constants agree without overwriting the observed remote baseline. An
explicit inspection parameter cannot make a candidate with another target head release-ready.

## 14. Performance And Cadence Contract

| Dimension | Required result |
| --- | --- |
| **No-signal file writes** | `0` JSON/MD/YAML/JSONL files |
| **No-signal PG growth** | `0` Claim, Ticket, ExposureEpisode or audit rows |
| **Account snapshot trigger** | Action-Time or lifecycle refresh only; no unconditional extra watcher fetch |
| **Network under PG lock** | `0` calls |
| **Capacity current reads** | At most `max_concurrent_positions + 1` effective rows plus current snapshot instruments |
| **Historical flat scan** | `0` rows materialized per runtime refresh |
| **Audit event growth** | Only on semantic fingerprint change |
| **Fill recovery** | At most 20 pages, 1000 fills/page, 8 seconds total |
| **Tree digest** | Deploy/resume/activation only; never watcher cadence |
| **Subprocess timeout** | Every deploy child and verification command remains bounded |
| **Archive output** | Manual, Owner-scoped and retention-bounded only |

Release certification requires `scripts/audit_production_runtime_file_io.py` to report
`performance_risk.status=clear` and zero frequent report writes.

## 15. Verification Matrix

### 15.1 Functional production-shape chain

One real PostgreSQL integration test must run the production entry points without helper
seeding of Exposure or Budget:

```text
raw account payload
-> account_capacity_base PG fact
-> Invocation binding
-> capacity arbitration
-> immutable Claim
-> post-claim Exposure/Budget Current
-> Ticket with consumed Reservation
-> FinalGate pass
-> official Operation Layer handoff materialized with operation_layer_called=false
-> Ticket-bound Runtime Safety State materialized from the same fact/Claim/Ticket lineage
-> non-executing protected-submit preparation with fake gateway
-> simulated protected lifecycle
-> flat + matched release
-> next Claim regains capacity exactly once
```

### 15.2 Required negative matrix

- existing first protected position and valid different-instrument second candidate;
- same-instrument second candidate in one-way and hedge mode;
- hedge LONG and SHORT rows for one instrument;
- external opposite bucket;
- zero position with zero entry price;
- partial-filled normal and Algo orders;
- cross-instrument order/client/algo ID collision;
- Claim/Ticket failure rollback;
- FinalGate reject followed by pre-submit capacity release;
- policy event and semantic-version changes;
- `contract_multiplier != 1` linear instrument;
- unsupported calculation kind;
- frozen Ticket/Claim/canary V1 hashes plus Runtime Safety V1 trusted-ref interpretation through
  upgrade, and V2 field tamper;
- migration 136 exact-target positives plus wrong-venue/type/asset/join/multiplier negatives;
- wallet/margin/qty change without lifecycle enum change;
- 100000 historical flat episodes with bounded current refresh;
- TP1 sub-threshold floor no-op then clamped structural/reference runner improvement;
- Entry fill after more than 50 newer fills, seven-day windows, mixed orders and same-timestamp
  trade-ID pagination without an `orderId` request parameter;
- accepted -> revoked -> accepted adoption, revoked protective-read/mutation split and real PG
  concurrent double acceptance;
- renewed deploy certification ref/payload pair;
- missing `ijson`, post-stage/resume tree tamper, bytecode source mutation, missing expected
  revision and migration-head mismatch;
- required PostgreSQL test intentionally skips/xfails and must make the gate nonzero.

### 15.3 Gate order

```text
fast domain and parser tests
-> focused application/service tests
-> real PostgreSQL migration/concurrency/full-chain tests
-> clean runtime-lock venv smoke
-> deploy-state-machine tests
-> performance/file-I/O/output audits
-> complete repository pytest
-> independent findings-first review
```

The PostgreSQL gate creates one disposable loopback-only Docker PostgreSQL container with a
test-only database/user, ignores ambient DSNs, performs identity plus `SELECT 1` checks and
accepts **zero skipped or xfailed tests** through a required fail-on-skip pytest plugin. Container
cleanup is trap-owned by the same shell block. Passing component tests or pytest exit code zero
with missing Docker/PostgreSQL configuration cannot override a failed production-shape gate;
there is no ambient-DSN fallback.

## 16. Delivery Units

| Unit | Closed problem class | Independent exit gate |
| --- | --- | --- |
| **U1 Snapshot and ownership truth** | SNAP/OWN defects | Raw payload, hedge bucket, remaining qty and composite identity tests |
| **U2 Capacity fact and current authority** | CAP/CUR/PERF defects | Consumer-conserved fact pair, frozen/V2 hashes, existing-position Invocation and bounded current projection tests |
| **U3 Atomic Claim and lifecycle release** | Claim/slot/margin/release defects | Production entry point through next capacity recovery |
| **U4 Runner and adoption recovery** | RUN defects | Real endpoint-contract pagination, revoked capability split and PG adoption concurrency tests |
| **U5 Instrument calculation** | EXT defects | Versioned Claim hash, exact migration predicate, multiplier and unsupported-kind tests |
| **U6 Release identity** | DEP defects | Clean lock venv, renewed pair, resume-safe exact tree, mandatory revision and head-136 tests |
| **U7 Final certification** | QA/cross-unit regressions | Self-contained no-skip PG gate, full suite, audits and independent review green |

Units are ordered by the implementation plan. Each is reviewable and commit-worthy. No unit
authorizes deployment or policy activation.

## 17. Live Enablement, Rollback And Stop Conditions

### 17.1 State transition

Before remediation:

```text
local two-parent merge exists
-> account-capacity production chain not conserved
-> runner/deploy recovery gaps remain
-> NO-GO for deploy or activation
```

After all local gates pass:

```text
production-shape local capability certified
-> shadow/deployment review candidate
-> production policy still inactive
```

### 17.2 Rollback

- Before any future deployment, rollback is deletion of only the repair worktree/branch.
- After a future code deploy but before policy activation, disable the account-risk capability;
  do not restore file authority or downgrade schema in production.
- After policy activation, append a new rollback policy event setting max positions to one;
  invalidate unsubmitted Claims; preserve existing protection, exit, reconciliation and
  settlement.
- No rollback path force-closes a position or cancels valid protection.

### 17.3 Hard stop

Stop implementation immediately when:

- a required change falls outside the files and boundaries in the implementation plan;
- a migration through `133` would need editing;
- a historical Ticket, Claim or canary hash would need recomputing, or a Runtime Safety digest
  would need fabricating instead of preserving versioned trusted-ref interpretation;
- any capacity-fact consumer or retention path cannot preserve the canonical selected pair;
- Claim, Ticket and post-claim projection cannot share one transaction;
- current truth would require PG + file dual authority;
- any exchange/network call occurs under the account lock;
- a test requires an exchange write;
- Entry-fill recovery would require an unsupported `orderId` endpoint parameter or unbounded
  history scan;
- migration 136 cannot prove the exact target row is supported linear Binance USD-M before
  UPDATE;
- deploy resume cannot rederive the expected tree from the target Git object, or a missing
  expected revision would be defaulted;
- a core invariant is bypassed to make a green test;
- PostgreSQL no-skip, runtime-lock, migration, performance or full-suite gates fail;
- work would change Owner policy, live scope or production state.

## 18. Owner Decision Status

No additional Owner decision is required to write or execute the local remediation plan.
`source_event_id` as authorization epoch, conservative protection allocation and rollback
without forced close are Codex architecture consequences of the already confirmed policy and
project authority model; they are not new chat-confirmation blockers.

The next Owner authorization is requested only after local certification and independent
review, for a separately specified shadow/deploy/activation scope. Until then:

```text
production_state = unchanged
policy_activation = not_performed
exchange_write = 0
```
