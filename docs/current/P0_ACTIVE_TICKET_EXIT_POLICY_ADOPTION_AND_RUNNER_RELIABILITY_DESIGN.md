---
title: P0_ACTIVE_TICKET_EXIT_POLICY_ADOPTION_AND_RUNNER_RELIABILITY_DESIGN
status: DRAFT_OWNER_REVIEW
authority: docs/current/P0_ACTIVE_TICKET_EXIT_POLICY_ADOPTION_AND_RUNNER_RELIABILITY_DESIGN.md
last_verified: 2026-07-16
---

# P0 Active-Ticket Exit-Policy Adoption And Runner Reliability Design

## 1. Executive Decision

The current **AVAXUSDT SOR-001 long** is a valid pre-deployment position. Its
existence across a release switch is not a defect: the deployment contract
explicitly allows a stable active position whose lifecycle, Ticket, protection
set, exchange position, and open protection orders reconcile exactly.

The current gap is narrower:

1. migration 122 intentionally marked every pre-policy Ticket as
   `legacy_unbound` instead of synthesizing historical exit semantics;
2. the AVAX Ticket was created before migrations 122/123 reached Tokyo, so the
   new release correctly refuses to attach the future-only policy implicitly;
3. the exact SOR-LONG right-tail policy was Owner-approved **19 minutes before**
   the Ticket was created, and the Ticket's StrategyGroup, strategy version,
   Event Spec, side, entry, position, TP1, and SL lineage are available for an
   exact adoption decision;
4. lifecycle durable exchange mutation is intentionally disabled because the
   deploy preserved its pre-deploy desired policy;
5. the lifecycle oneshot runner succeeds most of the time but has exceeded its
   28-second deadline in **160 of 1,048** post-release invocations observed by
   2026-07-16 14:16 CST.

The recommended solution is:

```text
optimize and certify the existing lifecycle runner
-> add an append-only active-Ticket policy-adoption authority
-> prove the exact AVAX Ticket is eligible
-> initialize its effective exit-policy projection without rewriting the Ticket
-> enable existing durable lifecycle mutation with the existing v2 proof
-> let the existing command worker own every cancel/place action
-> certify TP1 -> cost-adjusted floor -> structural/ATR runner behavior
```

This design does not create a second runner, does not make deployment require an
empty account, does not change the StrategyGroup, capital, leverage, notional,
entry, TP1 fraction, or symbol scope, and does not use OS limits as the primary
performance solution.

## 2. Authority And Source Order

This design follows:

1. Owner decisions already persisted by migration 123;
2. current tracked code and Tokyo PG/exchange truth;
3. `TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md`;
4. `P0_LIFECYCLE_PRODUCTION_CERTIFICATION_AND_CLOSURE_DESIGN.md`;
5. `P0_RUNTIME_STABILITY_AND_SIMPLIFIED_TOKYO_DEPLOYMENT_DESIGN.md`;
6. `TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md`.

Current state comes from PG and exchange APIs. No MD, JSON, output artifact, or
chat statement becomes runtime authority.

## 3. Verified Production Facts

### 3.1 Release And Runtime

| Fact | Verified value |
| --- | --- |
| Runtime head | `2415caa565fc85d9de1a6da34163d430dbfd8fee` |
| Release | `brc-runtime-governance-2415caa5-20260716` |
| Migration | `124` |
| Backend | active, `/api/health status=ok`, `runtime_bound=true` |
| Watcher after final release | 176 successful, 0 failed, 0 post-release OOM |
| Lifecycle maintenance | 888 successful, 160 deadline failures |
| Lifecycle mutation capability | disabled, ref `deploy-policy-disabled:2415caa5...` |

### 3.2 AVAX Ticket And Protection

| Fact | Verified value |
| --- | --- |
| Ticket | `ticket:481588f12989f47ef626a63992fd2cbe9fef4b7d02c38649bbd0799cb28f540a` |
| Ticket created | `2026-07-15 00:19:12.742 CST` |
| StrategyGroup | `SOR-001` |
| Strategy version | `sgv:SOR-001:v2` |
| Event Spec | `event_spec:SOR-001:SOR-LONG:v2`, version `v2` |
| Side | long |
| Lifecycle | `position_protected` |
| Filled quantity | 65 AVAX |
| Average entry | 6.658784615384615385 USDT |
| Existing TP1 | reduce-only LIMIT, 32 AVAX at 6.875, exchange id `39583407650` |
| Existing SL | reduce-only STOP_MARKET, 65 AVAX at 6.449, exchange id `4000001769200556` |
| Venue price tick | 0.001 USDT |
| Policy actual-entry 1R TP1 | raw 6.868569230769230770, long-side ceiling 6.869 |
| Existing TP1 difference | 0.006 USDT, **6 price ticks above** policy 1R |
| Protection set | complete and reconciled with exchange |
| Ticket exit policy | `legacy_unbound` |
| Exit-policy current projection | absent |

### 3.3 Approved Policy

| Fact | Verified value |
| --- | --- |
| Policy | `exit-policy:SOR-001:SOR-LONG:right-tail-v1` |
| Version | `2026-07-15-v1` |
| Approved at | `2026-07-15 00:00:00 CST` |
| Approved by | `owner-delegated:2026-07-15:recommended-values` |
| Policy hash | `324b2be50b3e1f020837e0f4687e76339a52dd757b272d4336b20de196bef02b` |
| TP1 | 1 actual-entry R, 50%, limit GTC, no market fallback |
| Post-TP1 floor | cost-adjusted break-even for the runner leg |
| Runner | confirmed 15m higher-low minus 0.5 ATR, monotonic improvement only |
| Time stop | 96 closed 15m bars |

The approved timestamp precedes the Ticket timestamp, and the policy identity
matches the Ticket's StrategyGroup, strategy version, Event Spec, version, and
side. That makes the Ticket a candidate for explicit adoption. It does not make
implicit backfill safe or authorized.

## 4. Is A Pre-Deployment AVAX Position Normal?

### 4.1 Normal Behavior

The following is normal and intended:

```text
old release creates a Ticket and protected position
-> deploy quiesces writer units
-> read-only gate proves exact position/protection consistency
-> immutable release pointer switches
-> new release resumes reconciliation of the same Ticket
```

An empty account is not a deployment prerequisite. The position belongs to its
original Ticket and remains protected by exchange-native reduce-only orders
during deployment.

### 4.2 Expected Fail-Closed Behavior

It is also expected that migration 122 did not attach a new policy to that old
Ticket. The migration records:

```json
{
  "binding_kind": "legacy_unbound",
  "historical_semantics_not_synthesized": true
}
```

That prevents a new release from silently changing how an existing real-money
position exits. The resulting `ticket_exit_policy_state_missing` is therefore
not evidence that the position itself is abnormal. It is evidence that an
explicit cross-version adoption operation has not yet been defined.

### 4.3 Current Classification

| Question | Answer |
| --- | --- |
| Is the pre-deploy position valid? | Yes |
| Is deployment with this position valid? | Yes, because protection reconciles |
| Is `legacy_unbound` expected? | Yes, under migration 122's future-only rule |
| Is existing TP1/SL protection valid? | Yes at the current exchange snapshot |
| Is automatic post-TP1 protection active? | No |
| Is this a strategy defect? | No |
| Is a missing product operation exposed? | Yes: explicit active-Ticket policy adoption |

## 5. Problem Statement

The system needs one safe operation for a narrow but recurring product case:

```text
a real Ticket was created before an approved policy implementation reached the
server, the position remains active and exactly protected, and the Owner wants
the already-approved exit semantics to govern the remainder without rewriting
historical Ticket truth.
```

At the same time, the production lifecycle runner must finish reliably inside
its cadence without repeatedly loading unnecessary venue metadata or relying on
larger timeouts as the main fix.

## 6. Goals And Non-Goals

### 6.1 Goals

1. Preserve the original `legacy_unbound` Ticket row unchanged.
2. Record one append-only, Owner-authorized policy-adoption event.
3. Prove exact strategy, event, side, position, protection, policy, and exchange
   lineage before adoption.
4. Initialize one effective exit execution snapshot from confirmed fill and
   protection facts.
5. Handle TP1-unfilled, partial, complete, and flat states deterministically.
6. Reuse the existing durable exchange-command worker for every mutation.
7. Eliminate routine lifecycle deadline failures through program/data-path
   optimization.
8. Preserve the 30-second exchange-truth cadence and 15-minute SOR runner-fact
   cadence without reducing symbols, facts, TP1, runner, or protection scope.
9. Allow future protected-position deployments without requiring empty account.
10. Produce no recurring JSON/MD files and no duplicate PG business events for
    unchanged exchange truth.

### 6.2 Non-Goals

- No new entry or new Ticket.
- No symbol, side, StrategyGroup, leverage, notional, or capital expansion.
- No TP1 market fallback.
- No TP2 fixed limit order for the right-tail runner policy.
- No direct exchange call from the adoption service or policy service.
- No modification of historical Ticket identity or policy snapshot.
- No generic migration that binds every `legacy_unbound` Ticket.
- No daemon rewrite in the first release unit.
- No primary reliance on swap, cgroup memory ceilings, CPU quota removal, or
  arbitrary timeout inflation.

## 7. Options Considered

### 7.1 Active-Ticket Policy Options

| Option | Safety | Auditability | Product result | Decision |
| --- | --- | --- | --- | --- |
| Leave every old Ticket `legacy_unbound` | High | High | Existing SL/TP1 only; no moving protection | Valid fallback, not recommended outcome |
| Update the Ticket in place | Low | Low | Enables policy quickly but rewrites historical authority | Rejected |
| Append policy-adoption event and derive effective current state | High | High | Enables exact policy without rewriting the Ticket | **Recommended** |

### 7.2 Runner Performance Options

| Option | Engineering effect | Risk | Decision |
| --- | --- | --- | --- |
| Increase timeouts / CPU quota only | Masks slow path | Deadline and memory regressions remain | Rejected as primary fix |
| Optimize current oneshot path | Small architecture change, keeps crash isolation | Requires narrow venue adapter and due-work selector | **Recommended** |
| Replace timer with long-lived daemon | Reuses gateway and market cache | Persistent RSS, larger operational change | Reserve only if optimized oneshot fails acceptance |

## 8. Recommended Architecture

### 8.1 One Effective Policy Resolver

Add one core resolver:

```python
resolve_effective_ticket_exit_policy_binding(
    conn,
    *,
    ticket_id: str,
    now_ms: int,
) -> EffectiveTicketExitPolicyBinding
```

Resolution order is exact:

1. if the Ticket carries a versioned policy, use the immutable Ticket binding;
2. if the Ticket is `legacy_unbound`, look for one accepted adoption event;
3. if neither exists, return `ticket_exit_policy_state_missing`;
4. conflicting events, hashes, versions, or identities hard-stop.

No caller may independently infer an effective policy.

### 8.2 Append-Only Adoption Authority

Add `brc_ticket_exit_policy_adoption_events` through migration 125.

| Column | Type / rule |
| --- | --- |
| `adoption_event_id` | deterministic String PK |
| `ticket_id` | exact existing Ticket |
| `from_exit_policy_hash` | must equal the Ticket's legacy hash |
| `to_exit_policy_id` | approved current policy id |
| `to_exit_policy_version` | approved current policy version |
| `to_exit_policy_hash` | approved policy hash |
| `owner_authorization_ref` | non-null explicit Owner policy reference |
| `eligibility_snapshot` | bounded typed JSONB, maximum 64 KiB |
| `eligibility_hash` | canonical SHA-256 |
| `decision` | `accepted`, `rejected`, or `revoked` |
| `runtime_head` | exact release SHA applying the event |
| `created_at_ms` | append timestamp |

Constraints:

- at most one accepted, non-revoked adoption per Ticket;
- accepted identity must match one current approved policy exactly;
- no UPDATE or DELETE through application services;
- revocation appends a new event and disables future mutation; it does not
  rewrite the original adoption;
- no adoption event creates an exchange command by itself.

This table is a core authority event, not a compatibility bridge. It represents
an explicit product operation: changing the future management policy of an
already-open position while preserving its original Ticket truth.

### 8.3 Typed Eligibility Snapshot

The adoption snapshot must prove:

| Dimension | Required invariant |
| --- | --- |
| Ticket | exact id, `legacy_unbound`, submitted, nonterminal |
| Approval order | `policy.approved_at_ms <= ticket.created_at_ms` unless a newer explicit Owner adoption ref names the Ticket |
| Strategy identity | StrategyGroup, strategy version, Event Spec, version, and side exactly match |
| Lifecycle | exactly one active lifecycle for the Ticket |
| Position | exchange and PG filled quantity/entry agree within venue precision |
| Protection | one complete reconciled set with exact SL/TP1 refs |
| SL | active reduce-only close-side stop with exact quantity and trigger |
| TP1 | active or filled reduce-only close-side limit order; no market fallback |
| Commands | no prepared, dispatching, or outcome-unknown command for the Ticket |
| Scope freeze | no unrelated active freeze or contradictory lifecycle |
| Venue scope | exact exchange/account/instrument/position mode resolved from PG |
| Runtime | exact release head and migration 125 active |

Any mismatch returns one exact blocker and writes nothing.

### 8.4 Existing TP1 Price Reconciliation

The approved policy uses `actual_entry_r`, while the existing TP1 was created
before the policy projection existed. Adoption must calculate:

```text
actual_r_per_unit = abs(entry_avg_fill_price - initial_stop_price)
policy_tp1_price = entry_avg_fill_price +/- actual_r_per_unit
```

It then compares the venue-rounded policy TP1 with the live TP1 order.

| State | Required action |
| --- | --- |
| Exact match | adopt without order mutation |
| Difference within one price tick | freeze the exchange price as the execution snapshot and record the rounding reason |
| Difference greater than one tick, TP1 unfilled | adoption remains `blocked_tp1_reprice_required`; prepare no command until durable mutation is enabled, then use one ticket-bound cancel/replace command |
| TP1 partially filled | never reprice the filled quantity; resize remaining protection first and adopt the remaining runner truth |
| TP1 complete | skip TP1 replacement and immediately require the cost-adjusted runner floor |
| Position flat | do not adopt; finalize the lifecycle |

The current AVAX prices already prove that the existing 6.875 order is not an
exact actual-entry 1R match: the approved long-side ceiling rule produces
6.869 at the venue's 0.001 tick, so the existing order is 6 ticks higher.
Therefore Unit C must enter `blocked_tp1_reprice_required` while TP1 remains
unfilled and use the existing durable cancel/replace path after mutation
enablement. If TP1 changes before Unit C, the fresh partial/complete/flat branch
supersedes this calculation.

### 8.5 Projection Initialization

After an accepted adoption event, initialize `brc_ticket_exit_policy_current`
with:

- adopted policy identity and hash;
- adoption event id as binding source;
- exact exit protection set id;
- confirmed entry average and filled quantity;
- confirmed initial stop;
- actual R per unit;
- resolved TP1 price and target quantity;
- cumulative TP1 fill truth;
- remaining position quantity;
- active SL/runner order id, generation, stop, and quantity;
- next evaluation watermark and blocker.

Add `binding_source` and `adoption_event_id` columns to the current projection.
Allowed `binding_source` values are `ticket` and `adoption_event`.

Initialization uses compare-and-set. Repeating the same exact adoption is
idempotent; a different hash or execution snapshot is a hard contradiction.

### 8.6 TP1 And Runner State Machine

```text
legacy_unbound
-> adoption_eligible
-> adoption_accepted
-> execution_bound
-> tp1_unfilled
-> tp1_partial (optional)
-> tp1_complete
-> runner_floor_pending
-> runner_floor_command_prepared
-> runner_floor_confirmed
-> runner_trailing
-> runner_closed
```

Rules:

1. existing exchange-native SL and TP1 remain authoritative until a replacement
   command is confirmed;
2. TP1 partial fill resizes the stop quantity before any trail improvement;
3. TP1 completion first applies the cost-adjusted floor, independent of 15m
   market-fact availability;
4. structural/ATR trailing begins only after the floor is confirmed;
5. every stop move is monotonic and improves by at least two ticks;
6. cancel old stop and submit replacement use the existing durable command
   state machine and unknown-outcome reconciliation;
7. no mutation may open, increase, reverse, or transfer exposure;
8. every exit order remains reduce-only and bound to `positionSide=LONG`.

### 8.7 Durable Mutation Authority

Reuse `ticket_lifecycle_durable_mutation`; do not add another capability.

Enablement requires the existing `LifecycleMutationEnablementProof v2` bound to:

- exact runtime head;
- exact release activation;
- all 22 current lane identities;
- post-canary Action-Time certification ref;
- current projection digest;
- schema 124 or later;
- valid account mode and no unsafe lifecycle/command state.

The adoption event is an additional Ticket-local prerequisite, not a substitute
for lifecycle capability proof.

The command worker remains the only exchange-write authority. Adoption,
projection, policy evaluation, deployment, and verification never call the
exchange write API directly.

For the pre-policy TP1 mismatch only, extend the existing command-source enum
with `exit_policy_tp1_reprice`. This is not a new writer. It is accepted by the
same command table, claimant lease, deterministic client-order identity,
unknown-outcome reconciliation, netting-domain serialization, gateway, and
capability gate used by the other lifecycle command sources.

The reprice sequence is:

```text
prepare cancel-old-TP1 command
-> dispatch and reconcile until confirmed cancelled
-> reread position, TP1 fills, and current protection
-> if still eligible, prepare new reduce-only LIMIT GTC TP1 at 6.869
-> dispatch and reconcile until confirmed submitted
-> bind the new exchange order id and generation
```

The new TP1 must never be submitted before cancellation is confirmed. During
the bounded replacement interval the existing SL remains live for the full
position. A cancellation unknown outcome stops before replacement submission.

## 9. Runner Performance Repair

### 9.1 Current Root Causes

The observed timeout path has three program-level causes:

1. every 30-second oneshot imports the application gateway binding and
   initializes CCXT market state for approximately 4,508 symbols;
2. the process performs gateway binding before fully narrowing due work;
3. the outer `/usr/bin/timeout 28s` equals the application global deadline, so
   the OS wrapper can kill the process before it emits a structured deadline
   result.

`CPUQuota=40%` and no swap may amplify failure, but neither is the primary
solution.

### 9.2 Due-Work Selector

Before gateway initialization, select exactly one of:

```text
no_work
exchange_truth_due
command_reconciliation_due
command_dispatch_due
policy_market_fact_due
finalization_due
```

Use indexed `EXISTS ... LIMIT 1` queries. A `legacy_unbound` Ticket with no
adoption event does not initialize the policy evaluator. It may still receive
exchange-truth reconciliation for its current SL/TP1.

### 9.3 Narrow Lifecycle Venue Adapter

Extend the existing exchange gateway adapter with one typed lifecycle snapshot
operation that accepts a resolved `TicketBoundExchangeScope` and performs only:

- position query for the exact venue instrument and position side;
- regular open-order query for the exact symbol;
- conditional-order query for the exact symbol and known parent ids;
- bounded recent-fill query only when the known order watermarks require it.

The Binance adapter may use raw signed futures endpoints internally so it does
not load all venue markets on every tick. It must still validate quantity,
price tick, order type, reduce-only side, and instrument identity against the
PG `InstrumentRuleSnapshot`. Missing or stale instrument rules fail closed;
they do not fall back to a report file or unchecked symbol string.

This is an adapter optimization under the existing exchange gateway boundary,
not a Binance-specific domain model.

### 9.4 Split Cadence Without Feature Loss

| Work | Cadence | Trigger |
| --- | --- | --- |
| Position/open-order truth | 30 seconds while lifecycle active |
| Unknown command reconciliation | immediately due, max one per invocation |
| TP1 fill projection | when exchange snapshot watermark changes |
| Cost-adjusted floor | immediately after TP1 complete |
| Structural/ATR runner | one evaluation per new closed 15m watermark |
| Finalization/settlement | when position/order state changes |
| No-active lifecycle | PG selector only; no gateway initialization |

No symbol, fact, protection, TP1, or runner behavior is removed.

### 9.5 Timeout Hierarchy

After the data-path repair:

| Boundary | Value |
| --- | ---: |
| Exchange request | 8 seconds maximum |
| Application global deadline | 28 seconds |
| Outer process timeout | 36 seconds |
| systemd `TimeoutStartSec` | 45 seconds |
| systemd stop grace | 10 seconds |

The larger outer timeout is a failure-reporting margin, not the performance
fix. The application must normally finish well before 28 seconds.

### 9.6 Performance Telemetry

Each invocation emits one bounded structured journal record containing:

- selected work kind;
- stage durations in milliseconds;
- exchange request count;
- PG transaction count and total transaction duration;
- peak RSS from `resource.getrusage`;
- deadline remaining;
- exchange read/write booleans;
- final typed status and first blocker.

The current `/usr/bin/time` `%M` format is not reliable under the unit file and
must be removed. No JSON/MD file is written. Unchanged ticks do not append a new
business event; current component health may be upserted into the existing PG
current process-health projection if Owner UI consumption is required.

## 10. Release Units

### 10.1 Release Unit A — Runner Data-Path Repair

Scope:

- due-work selector;
- narrow lifecycle venue snapshot adapter;
- stage timing and RSS telemetry;
- timeout hierarchy correction;
- unchanged-snapshot dedupe;
- production-shape performance tests.

Runtime mutation remains disabled. No policy adoption occurs.

Acceptance:

- 240 consecutive natural 30-second invocations;
- zero systemd failure and zero application deadline failure;
- p95 total duration no greater than 12 seconds;
- maximum total duration below 24 seconds;
- peak lifecycle process RSS no greater than 256 MiB;
- zero OOM;
- zero exchange writes;
- unchanged exchange truth creates zero duplicate business events;
- production file-I/O audit `performance_risk.status=clear`.

### 10.2 Release Unit B — Generic Active-Ticket Adoption Core

Scope:

- migration 125 adoption event and projection fields;
- typed eligibility model and canonical digest;
- effective policy resolver;
- idempotent projection initialization;
- TP1 unfilled/partial/complete/flat branches;
- read-only AVAX eligibility preview;
- no capability enablement and no exchange write.

Acceptance:

- positive AVAX-shaped rehearsal produces one exact eligible preview;
- every identity/protection/command/position mismatch writes nothing;
- Ticket remains byte-for-byte unchanged;
- repeated preview and apply are deterministic;
- no accepted adoption can exist without one exact Owner authorization ref;
- full targeted tests and PG migration downgrade tests pass.

### 10.3 Release Unit C — Exact AVAX Adoption And Mutation Activation

Scope:

- rerun fresh exchange/PG eligibility at action time;
- append one accepted adoption event for the exact AVAX Ticket;
- initialize the effective policy projection;
- resolve any TP1 price mismatch through the existing durable command path;
- produce and persist a fresh lifecycle enablement proof for the exact release;
- enable `ticket_lifecycle_durable_mutation`;
- observe TP1 and runner lifecycle without creating a new entry.

Acceptance:

- existing SL remains live throughout;
- no duplicate TP1 or stop command can be dispatched;
- command unknown outcome fail-closes and reconciles before retry;
- TP1 complete produces a cost-adjusted runner floor command;
- runner stop quantity equals remaining exchange position;
- runner stop only moves in the favorable direction;
- PG, exchange, lifecycle, outcome, monitor, and notification agree;
- no capital/profile/scope/entry authority changes.

### 10.4 Expected File Boundary

| Responsibility | Expected file action |
| --- | --- |
| Adoption schema | create `migrations/versions/2026-07-16-125_add_active_ticket_exit_policy_adoption.py` |
| Adoption domain types | create `src/domain/ticket_exit_policy_adoption.py` |
| Adoption eligibility/apply | create `src/application/action_time/ticket_exit_policy_adoption_service.py` |
| Effective binding | modify `src/application/action_time/ticket_exit_policy_binding.py` |
| Execution snapshot | modify `src/application/action_time/ticket_exit_execution_binding.py` |
| Policy maintenance | modify `src/application/action_time/ticket_exit_policy_service.py` |
| Due-work selection | modify `src/application/action_time/lifecycle_maintenance_scheduler.py` |
| Runner process deadline/telemetry | modify `scripts/run_ticket_bound_lifecycle_maintenance_once.py` |
| Narrow snapshot | modify `src/application/action_time/exchange_snapshot_provider.py` and `src/infrastructure/exchange_gateway.py` |
| Durable TP1 reprice | modify `src/domain/ticket_bound_exchange_command.py` and the existing exchange-command worker/reconciliation modules |
| Service boundary | modify `deploy/systemd/brc-ticket-lifecycle-maintenance.service` |
| Postdeploy acceptance | modify `scripts/verify_tokyo_runtime_governance_postdeploy.py` and Tokyo deploy verification |
| Tests | add focused domain, PG, command, scheduler, performance, deploy, and postdeploy suites under `tests/` |

No public Owner API is required for Units A/B. Unit C consumes a bounded
Owner-authorization reference through the deployment/adoption command and
persists it in PG. No current runtime behavior is added through a file-backed
repository, artifact validator, or report directory.

## 11. Failure Matrix

| Failure | Required result |
| --- | --- |
| Policy approved after Ticket without explicit Ticket authorization | adoption blocked |
| Strategy/Event/side mismatch | adoption blocked |
| Position quantity or side mismatch | hard safety stop |
| Protection order missing | hard safety stop; no adoption |
| TP1 is market order | hard safety stop |
| Existing command prepared/dispatching/unknown | adoption blocked until reconciliation |
| TP1 fills during adoption | refresh snapshot and enter partial/complete branch; never reuse stale preview |
| Position closes during adoption | no adoption; finalize lifecycle |
| Duplicate adoption request | same hash returns idempotent success |
| Conflicting adoption request | hard contradiction |
| TP1 cancel outcome unknown | do not place replacement until reconciled |
| Old SL cancel outcome unknown | do not place runner replacement until reconciled |
| Runner replacement rejected | preserve/recover known protection and freeze new entries |
| Exchange snapshot timeout | keep existing exchange orders, record retryable blocker |
| Process deadline | structured failure before outer timeout; no partial PG transaction |
| Release head changes | lifecycle mutation capability fail-closes |

## 12. Tests

### 12.1 Domain Tests

- canonical adoption eligibility hash;
- approval-before-Ticket ordering;
- exact identity matrix;
- actual-entry-R TP1 rounding;
- partial/full TP1 quantity math using `Decimal`;
- cost-adjusted break-even floor;
- monotonic structural/ATR trail;
- long/short direction negative cases;
- no market fallback.

### 12.2 PG Tests

- migration 125 upgrade/downgrade;
- append-only constraints;
- one accepted adoption per Ticket;
- compare-and-set projection initialization;
- conflicting hash rejection;
- no Ticket UPDATE;
- transaction rollback on every negative case;
- indexed selector plans on production-shaped row counts.

### 12.3 Exchange-Command Tests

- TP1 cancel/reprice exact sequence;
- `exit_policy_tp1_reprice` uses the existing worker and capability gate;
- TP1 partial fill race;
- floor stop cancel/replace;
- duplicate client order id;
- reject, timeout, outcome unknown, reconciliation, and retry exhaustion;
- quantity never exceeds current remaining position;
- reduce-only and exact position side enforced.

### 12.4 Runtime And Performance Tests

- 1,000 unchanged active-position ticks;
- no-active selector path;
- due/no-due policy watermark path;
- narrow adapter request-count assertion;
- p50/p95/max duration and peak RSS;
- process death at every committed transaction boundary;
- 240 natural Tokyo ticks with mutation disabled before Unit C;
- 240 natural Tokyo ticks after activation or until TP1 state changes.

### 12.5 Deployment Tests

- active protected position allows release switch;
- unsafe active lifecycle blocks release switch;
- disabled mutation remains disabled in Units A/B;
- Unit C enablement requires exact v2 proof;
- rollback disables mutation before pointer rollback;
- postdeploy verifier checks exact SHA, migration, units, timeout hierarchy,
  adoption table shape, capability proof, and current Ticket state.

## 13. Deployment Sequence

### 13.1 Unit A

```text
local TDD and performance benchmark
-> deploy with lifecycle mutation disabled
-> verify exact release and migration
-> run 240 natural ticks
-> accept only at zero timeout / zero OOM / bounded RSS
```

### 13.2 Unit B

```text
deploy migration 125 and adoption code with mutation disabled
-> run read-only AVAX eligibility preview
-> compare preview digest with fresh PG/exchange truth
-> do not append adoption event until Unit C authorization
```

### 13.3 Unit C

```text
quiesce lifecycle writer
-> fresh PG/exchange snapshot
-> assert exact AVAX eligibility digest
-> append adoption event and initialize projection in one PG transaction
-> produce exact-head lifecycle capability proof
-> enable durable mutation
-> resume lifecycle worker
-> verify first pass and command state
-> observe exchange/PG reconciliation
```

Unit C may run with the AVAX position open. It must stop if the position or
orders change between preview and compare-and-set apply.

## 14. Rollback And Containment

Rollback order:

1. stop lifecycle maintenance timer;
2. disable `ticket_lifecycle_durable_mutation` and clear its proof payload;
3. reconcile any prepared/dispatching/unknown command read-only;
4. prove one valid exchange-native stop remains for the current position;
5. restore the previous release pointer if required;
6. resume read-only lifecycle reconciliation;
7. append an adoption revocation event only if policy execution must remain
   disabled after the old release is restored.

The original Ticket and accepted adoption event are never deleted. A release
that does not understand adoption sees the original `legacy_unbound` Ticket and
fails closed. Exchange-native orders already confirmed before rollback remain
the protection boundary.

## 15. Cadence, Storage, And Retention Impact

| Dimension | Target impact |
| --- | --- |
| Exchange reads | bounded to exact active Ticket/instrument; no all-symbol market load per tick |
| Exchange writes | zero until one existing durable command is eligible and capability proof is valid |
| PG reads | indexed due selector plus exact Ticket/protection rows |
| PG writes | adoption is one-time append; projection is current-state update; unchanged ticks add no business event |
| JSON/MD files | zero production reads and zero recurring writes |
| Journal | one bounded structured record per invocation, retained by system journal policy |
| Archive | manual Owner-scoped export only; no runtime dependency |
| CPU/RSS | measured by Unit A; function coverage unchanged |

## 16. Chain Position And State Transition

```text
chain_position: post_submit_protected_position
strategy_group_id: SOR-001
symbol: AVAXUSDT
stage_before: position_protected / legacy_exit_policy_unbound
first_blocker_before: ticket_exit_policy_state_missing
engineering_blocker: lifecycle_global_deadline_exceeded
stage_after_unit_a: position_protected / runner_reliable / mutation_disabled
stage_after_unit_b: adoption_eligible / mutation_disabled
stage_after_unit_c: execution_bound / tp1_monitoring_or_runner_protected
blocker_removed: ticket_exit_policy_state_missing
capability_unlocked: bounded ticket-local exit-policy mutation
next_bottleneck: natural TP1 fill and venue-calibrated runner acceptance
stop_condition: any position/protection/identity contradiction or unknown exchange outcome
owner_action_required: yes, Unit C production adoption and mutation activation only
authority_boundary: no new Ticket, entry, capital, leverage, scope, transfer, withdrawal, or credential authority
```

## 17. Owner Decision Boundary

Ordinary architecture, schema, test, timeout, adapter, deployment, and rollback
choices are Codex engineering responsibilities.

One Owner decision remains before Unit C:

> Authorize the exact existing AVAX Ticket to adopt
> `exit-policy:SOR-001:SOR-LONG:right-tail-v1@2026-07-15-v1` and authorize the
> existing durable lifecycle command worker to perform only reduce-only TP1/SL/
> runner cancel-replace actions required by that frozen policy after exact-head
> certification passes.

This authorization does not permit a new entry, larger position, leverage or
notional change, another symbol/side, withdrawal, transfer, or credential
change.

Units A and B can be implemented and deployed with mutation disabled. Unit C
must not execute until this design and the exact production adoption boundary
are confirmed.

## 18. Design Acceptance Criteria

The design is accepted when all of the following are agreed:

1. pre-deployment protected positions are valid deploy inputs;
2. historical Ticket rows remain immutable;
3. policy adoption is explicit and append-only;
4. the approved SOR-LONG policy is the only adoption target for this Ticket;
5. existing durable command authority remains the only exchange writer;
6. program/data-path optimization precedes timeout or OS-resource relaxation;
7. TP1 stays reduce-only limit with no market fallback;
8. TP1 completion raises the runner to the cost-adjusted floor before trailing;
9. the runner evaluates structural/ATR improvement only on closed 15m facts;
10. deployment remains valid with a stable protected active position;
11. Unit C is the only step requiring explicit Owner production authorization.
