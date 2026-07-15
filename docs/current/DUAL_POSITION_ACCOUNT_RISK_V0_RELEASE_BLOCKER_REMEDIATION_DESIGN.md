---
title: DUAL_POSITION_ACCOUNT_RISK_V0_RELEASE_BLOCKER_REMEDIATION_DESIGN
status: OWNER_APPROVED_IMPLEMENTED_LOCAL_PG_CERTIFICATION_PENDING
authority: docs/current/DUAL_POSITION_ACCOUNT_RISK_V0_RELEASE_BLOCKER_REMEDIATION_DESIGN.md
extends: docs/current/DUAL_POSITION_HARD_CAP_ACCOUNT_RISK_MODEL_V0_DESIGN.md
last_verified: 2026-07-14
implementation_state: LOCAL_IMPLEMENTED_NO_DEPLOY_PG_CERTIFICATION_PENDING
---

# Dual-Position Account Risk V0 Release-Blocker Remediation Design

> **Current identity extension:** 本文关于 Account Capacity Claim 的风险守恒修复继续有效；
> Candidate Scope exact instrument、InstrumentRiskIdentity / RuleSnapshot 分层、
> exposure episode、snapshot 语义重验和 cluster membership 的新增约束，以
> `docs/current/DUAL_POSITION_ACCOUNT_RISK_V0_ASSET_NEUTRAL_IDENTITY_EXTENSION_DESIGN.md`
> 为当前权威。现有本地实现通过旧 remediation tests 不等于满足资产中立 release gate。

Status: Draft for Owner confirmation

Date: 2026-07-14

Scope: Local design only; no implementation, migration apply, deployment, policy activation, or exchange write is authorized by this document.

## 1. Decision Summary

The current Dual-Position Hard-Cap Account Risk V0 implementation must not be
released in its present form. The release review found three P0 defects and
three P1 defects. They share one architectural cause:

> risk ceiling, actual stop risk, policy authorization identity, account
> snapshot identity, and PG capacity reservation are not conserved by one
> atomic contract from sizing through Ticket materialization and FinalGate.

This design does not create another risk engine, Ticket type, evidence packet,
or file-backed authority. It extends the existing sizing decision, PG budget
reservation, account projections, Ticket materialization, and FinalGate into
one typed **Account Capacity Claim** contract.

The selected direction is:

1. preserve the existing Ticket as the execution lifecycle owner;
2. preserve PG current projections as runtime truth;
3. use the existing budget reservation row as the persisted Account Capacity
   Claim rather than adding a parallel table;
4. make policy event identity, actual stop risk, reserved margin, instrument
   identity, and claimed projection version mandatory claim facts;
5. make capacity materialization one lock-first PG transaction;
6. revalidate the same claim at FinalGate;
7. keep rollback fail-closed for new entries without closing existing positions
   or weakening protection and reconciliation.

## 2. Authority And Scope

This remediation is subordinate to:

1. `AGENTS.md`;
2. `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md`;
3. `docs/current/AI_AGENT_CONSTRAINTS.md`;
4. `docs/current/BLOCKER_CLASSIFICATION_CONTRACT.md`;
5. `docs/current/DUAL_POSITION_HARD_CAP_ACCOUNT_RISK_MODEL_V0_DESIGN.md`.

The Owner-authorized policy remains unchanged:

| Policy dimension | Authorized value | Remediation effect |
| --- | ---: | --- |
| Planned stop-risk fraction | 2.5% of current wallet balance | No change |
| Maximum concurrent positions | 2 | No change |
| Portfolio held-risk cap | 6% of current wallet balance | No change |
| Risk-cluster held-risk cap | 4% of current wallet balance | No change |
| Initial-margin cap | 90% of current wallet balance | Conservation repaired |
| Maximum leverage | 10x | No change |
| Same-instrument second Ticket | Prohibited | Identity enforcement repaired |
| Automatic downsize | Allowed | Risk semantics repaired |

This remediation does not change StrategyGroup admission, symbol scope, side
scope, strategy parameters, leverage authorization, capital allocation, live
profile, or exchange-write authority.

## 3. Confirmed Defects

| ID | Confirmed defect | Direct consequence | Required design response |
| --- | --- | --- | --- |
| P0-1 | Account-capacity sizing emits an unsupported reservation basis and stores allocated risk as actual risk | Capacity-adjusted sizing cannot reliably materialize a Ticket | Unify risk vocabulary and one typed claim |
| P0-2 | Multiple protection stops are collapsed into one stop price | Held risk can be understated, including zero | Quantity-specific conservative protection segments |
| P0-3 | Activate and rollback reuse the same policy version | An old claim may survive Owner rollback | Bind claims to immutable policy event identity |
| P1-1 | Budget projection is written before the capacity row is locked | Concurrent transactions can compute and overwrite from stale state | Lock-first atomic materialization |
| P1-2 | Closed historical Tickets still claim current exchange positions | Repeated trading of one instrument can cause false identity conflict | Nonterminal ownership scope |
| P1-3 | Active reservation margin is not represented in pending margin | Initial-margin headroom is overstated before exchange reflection | Margin accounting state conservation |

## 4. Alternatives Considered

| Alternative | Description | Advantages | Disadvantages | Decision |
| --- | --- | --- | --- | --- |
| A. Local patch set | Add the new basis to an allowlist, change several queries, and add regression tests | Small diff and fast implementation | Preserves split semantics; rollback and transaction gaps can recur | Rejected |
| B. Unified Account Capacity Claim | Extend existing sizing, reservation, projection, and FinalGate contracts around one claim | Removes root cause without a second engine; auditable and testable | Requires coordinated domain, PG, and action-time changes | Selected |
| C. Full lifecycle/risk rewrite | Replace the current budget, Ticket, and protection path with a new risk lifecycle service | Clean theoretical model | Excessive scope, duplicates stable lifecycle capability, delays trading feedback | Rejected |

Alternative B is the minimum system-level correction. It repairs the boundary
that failed while preserving the current execution and lifecycle architecture.

## 5. Unified Risk Vocabulary

The implementation must stop using one field to mean both a ceiling and an
actual amount.

| Fact | Exact meaning | Formula or source | Persisted authority |
| --- | --- | --- | --- |
| `requested_risk_budget` | Maximum risk requested by sizing before account-wide arbitration | Current wallet balance times 2.5%, further bounded by strategy sizing | Sizing decision |
| `allowed_risk_budget` | Maximum risk still available after Ticket, portfolio, cluster, slot, and margin caps | Minimum of all applicable remaining limits | Account Capacity Claim |
| `actual_risk_at_stop` | Risk represented by the final exchange-valid rounded quantity | `abs(entry_reference_price - protective_stop_price) * intended_qty` | Claim `risk_at_stop` and Ticket budget |
| `reserved_margin` | Initial margin required by final quantity and selected leverage | `effective_notional / selected_leverage` | Account Capacity Claim |
| `risk_reservation_basis` | Formula used to derive actual stop risk | Shared domain enum/value for entry-reference stop distance | Sizing decision and claim |

Required invariants:

```text
actual_risk_at_stop > 0
actual_risk_at_stop <= allowed_risk_budget
allowed_risk_budget <= requested_risk_budget
reserved_margin = effective_notional / selected_leverage
intended_qty conforms to minQty, stepSize, and minNotional
```

`risk_reservation_basis` describes the calculation formula; it must not encode
which policy or capacity subsystem supplied the ceiling. Capacity provenance is
represented by policy event identity and budget projection identity.

For compatibility with the existing `ExecutionSizingDecision`:

```text
planned_stop_risk_budget := allowed_risk_budget
planned_stop_risk        := actual_risk_at_stop
risk_at_stop             := actual_risk_at_stop
```

The current centralized stop-distance basis remains valid. The remediation must
not introduce a special account-capacity basis whose only purpose is to bypass
downstream validation.

## 6. Account Capacity Claim

The Account Capacity Claim is a typed domain/application contract persisted in
the existing budget reservation row. It is not a new lifecycle owner and not a
new source of truth.

The claim must contain:

```text
reservation_id
ticket_id
account_id
runtime_profile_id
exchange_instrument_id
risk_cluster_id
account_risk_policy_version
account_risk_policy_event_id
account_source_fact_snapshot_id
claimed_budget_projection_version
entry_reference_price
protective_stop_price
intended_qty
allowed_risk_budget
risk_at_stop
selected_leverage
reserved_margin
margin_accounting_state
status
reserved_at_ms
expires_at_ms
```

Claim invariants are checked at creation and rechecked at FinalGate. A mismatch
must block the new entry and must never be normalized silently.

## 7. Policy Identity And Owner Rollback

### 7.1 Separate semantic version from authorization event

`risk_policy_version` identifies the policy schema/family. It is not sufficient
to identify an Owner authorization decision.

The existing policy event `event_id` and current projection `source_event_id`
become the immutable authorization identity:

```text
account_risk_policy_event_id := brc_account_risk_policy_current.source_event_id
```

Every distinct Owner policy command, including shadow, activate, modify,
rollback, pause, and resume, creates a new append-only event with a new event
identity. Retrying the same command with the same operation/idempotency ID is
idempotent; a new Owner command must never overwrite the old event.

### 7.2 Claim invalidation

The reservation stores `account_risk_policy_event_id`. FinalGate requires exact
equality with current `source_event_id`.

```text
claim.policy_event_id != current_policy.source_event_id
-> account_risk_policy_event_changed
-> block new exchange write
```

An Owner rollback therefore invalidates all earlier in-flight claims without
closing existing positions. Protection, reconciliation, exit, and settlement
continue normally.

## 8. Lock-First Atomic Capacity Transaction

Exchange I/O must not occur while a PG row lock is held. The required sequence
is:

```text
1. Fetch the bounded-timeout full-account exchange snapshot outside PG lock.
2. Begin the action-time PG transaction.
3. SELECT the existing account budget current row FOR UPDATE.
4. Fail closed if the row is missing; bootstrap is not allowed inside action-time.
5. Validate policy event, registry instrument, snapshot freshness, and scope.
6. Reproject exposure and budget under the lock using current PG reservations.
7. Compute allowed risk, final rounded quantity, actual risk, and margin.
8. Insert/update the active Account Capacity Claim.
9. Materialize the Ticket using the same claim inside the same transaction.
10. Commit once; any validation or Ticket failure rolls back budget and claim.
```

No budget projection update, reservation status transition, or Ticket insert may
occur before step 3 or outside this transaction.

The current single action-time lane remains an operational constraint, but
correctness must not depend on it. PostgreSQL serialization is the account-wide
capacity authority.

## 9. Quantity-Specific Protection Risk

### 9.1 Eligible protective orders

An exchange order can contribute protection coverage only when all of the
following match the position:

```text
account_id
exchange_id
exchange_instrument_id
position_side
opposite order side
reduce_only or close_position protection semantics
live exchange status
nonterminal owning Ticket
recognized protection purpose
```

The Binance normalized order model must retain the required side,
`positionSide`, `reduceOnly`, `closePosition`, trigger price, original quantity,
executed quantity, and remaining quantity facts.

### 9.2 Conservative segment allocation

Protection is projected as quantity-specific segments:

```text
ProtectionCoverageSegment(
    order_id,
    ticket_id,
    covered_qty,
    stop_price,
    protection_purpose,
)
```

To avoid double-counting overlapping initial/runner stops:

1. discard ineligible orders;
2. rank stops by worst directional loss first: lower stop first for a long,
   higher stop first for a short;
3. allocate each order's remaining quantity only up to the unallocated position
   quantity;
4. cap total covered quantity at current absolute position quantity;
5. treat any uncovered quantity or ambiguous ownership as unknown exposure and
   block new entries.

Directional held risk is:

```text
long segment risk  = max(entry_price - stop_price, 0) * covered_qty
short segment risk = max(stop_price - entry_price, 0) * covered_qty
position held risk = sum(segment risk)
```

Locked-in profit remains floored at zero for risk-capacity purposes. It does not
create negative held risk or additional budget.

## 10. Current Ownership Scope

Historical execution facts remain audit evidence but must not own the current
position.

Current position ownership may be claimed only by:

1. a nonterminal Ticket in the same account and exchange scope;
2. an active or unresolved command/order whose lifecycle can still explain the
   current position;
3. canonical `exchange_instrument_id` identity from PG registry/mapping.

Closed, cancelled, settled, or reconciled-absent Tickets cannot claim current
ownership. Symbol-string fallback must not fabricate canonical instrument
identity. Missing or ambiguous registry identity remains fail-closed.

The nonterminal Ticket status set must be defined once in the lifecycle domain
and reused by ownership, exposure, reconciliation, and tests.

## 11. Margin Conservation

The account budget formula becomes:

```text
effective_initial_margin
  = exchange_total_initial_margin
  + sum(active unreflected claim reserved_margin)

available_margin_capacity
  = wallet_balance * 0.90 - effective_initial_margin
```

Each active claim has one margin accounting state:

| State | Meaning | Budget treatment |
| --- | --- | --- |
| `reserved_unreflected` | Capacity is reserved but not yet represented by an identified exchange order/position margin fact | Add `reserved_margin` |
| `exchange_reflected` | The claim is matched to current exchange margin facts | Do not add reservation margin again |
| `unknown` | Reflection cannot be established safely | Fail closed for new entry |
| `released` | Claim is terminally released or settled | Add zero |

The transition to `exchange_reflected` requires command/order/position identity
evidence. Time passage alone must not release or reflect margin.

## 12. FinalGate Revalidation

FinalGate does not calculate a second independent budget. It revalidates the
persisted claim against current authority and facts.

Required checks:

```text
claim status is active
claim policy event equals current policy source event
claim policy semantic version equals current policy version
claim instrument and cluster mapping remain current
claim source account snapshot remains fresh
claim projection version is still admissible
claim intended quantity matches Ticket quantity
claim risk_at_stop equals abs(entry - stop) * quantity
claim risk_at_stop is within allowed_risk_budget
claim reserved_margin matches notional / leverage
no conflicting current position or open-order ownership exists
```

A failure blocks only the new entry. It must not stop protection, exit,
reconciliation, or settlement for an existing position.

## 13. PG Schema Evolution

Because revisions 121-124 are already committed and exercised by local/CI
databases, remediation uses a new additive migration rather than rewriting
applied revision history.

Required additions to the existing reservation authority include:

```text
account_risk_policy_event_id
allowed_risk_budget
margin_accounting_state
```

New claims require these fields to be non-null at the application boundary.
Upgrade compatibility may use nullable database columns initially, but release
activation must fail if any active legacy claim lacks the new facts. The system
must not invent a policy event ID or mark margin reflected during backfill.

No JSON, Markdown, YAML, JSONL, or file-backed compatibility authority is
permitted.

## 14. Failure And Blocker Semantics

| Condition | Blocker | Classification | Owner action |
| --- | --- | --- | --- |
| Claim risk formula mismatch | `account_capacity_risk_conservation_invalid` | `hard_safety` | None during normal engineering repair |
| Policy event changed | `account_risk_policy_event_changed` | `owner_policy` at policy boundary; fail-closed at live submit | None if change was intentional |
| Account snapshot stale | Existing stale account-fact blocker | `fact_stale` | None unless fact source remains unavailable |
| Protection coverage incomplete | Existing unprotected/unknown exposure blocker | `hard_safety` | Intervention only for an actual open position |
| Current ownership ambiguous | Existing ownership conflict blocker | `fact_mapping` or `hard_safety` by exchange state | Intervention only when live exposure is unresolved |
| Capacity row missing | `account_budget_current_missing` | `runtime_readiness` | None; bootstrap/repair engineering path |
| Margin reflection unknown | `account_margin_reflection_unknown` | `reconciliation` | Intervention only after automated reconciliation is exhausted |

These blockers must remain developer/audit diagnostics. Healthy Owner-facing
surfaces continue to report `running`, `waiting_for_opportunity`, `processing`,
or `temporarily_unavailable` without exposing internal claim terminology.

## 15. Test And Certification Design

### 15.1 Contract tests

The following tests are mandatory:

1. non-divisible quantity step produces `planned_stop_risk` and `risk_at_stop`
   equal to the rounded quantity's actual stop risk;
2. the account-capacity sizing decision materializes a real Ticket without a
   reservation-basis blocker;
3. FinalGate rejects a one-cent or one-step risk mismatch;
4. policy activate followed by rollback creates a different event identity and
   invalidates the old claim;
5. two closed historical Tickets do not conflict with a current nonterminal
   Ticket for the same instrument;
6. canonical instrument mapping failure blocks rather than fabricates identity.

### 15.2 Protection tests

Required scenarios include:

| Position | Protection orders | Expected held risk |
| --- | --- | ---: |
| Long 1 at 100 | 0.5 stop at 90; 0.5 stop at 105 | 5 |
| Long 1 at 100 | 1 stop at 90; overlapping 1 stop at 105 | 10 conservatively |
| Short 1 at 100 | 0.4 stop at 110; 0.6 stop at 95 | 4 |
| Long 1 at 100 | 0.5 valid stop; 0.5 uncovered | Unknown exposure; new entry blocked |
| Hedge-mode long | Short-side or wrong-positionSide stop | Not eligible coverage |

All calculations use `Decimal`.

### 15.3 PostgreSQL concurrency test

The integration test must execute the complete materialization path in two real
PostgreSQL transactions, not call only the reservation helper.

It must prove:

1. the second transaction blocks on the account budget row;
2. after the first commit, the second transaction recomputes from current
   projection/reservation state;
3. portfolio, cluster, slot, and margin capacity cannot be oversubscribed;
4. a Ticket materialization failure rolls back its claim and budget update;
5. exactly one current projection version wins without stale overwrite.

### 15.4 Full non-executing chain certification

Before release approval, one test must cover:

```text
dynamic account snapshot fixture
-> account exposure projection
-> account budget projection
-> capacity downsize
-> Account Capacity Claim
-> Action-Time Ticket
-> FinalGate revalidation
-> lifecycle release
-> next Ticket capacity recovery
```

This is a rehearsal/integration proof only. It grants no exchange-write
authority and does not substitute for later natural-event production acceptance.

### 15.5 Test feedback stratification

| Layer | Purpose | When run |
| --- | --- | --- |
| Fast unit/contract | Risk arithmetic, policy event, ownership, protection segments | Every implementation commit |
| PG integration | Locking, rollback, projection and reservation conservation | Every remediation task checkpoint |
| Full repository suite | Global regression and release certification | Once after all remediation tasks pass |

The existing passing component tests remain useful, but they cannot be the
release proof until the complete claim-to-Ticket chain is exercised.

## 16. Performance, Cadence, And File-I/O Boundary

This remediation adds no periodic report or watcher workload.

1. full-account exchange snapshot remains action-time/candidate triggered and
   timeout-bounded;
2. no exchange network request runs while holding the PG capacity lock;
3. no-signal ticks create zero JSON/Markdown files and zero policy/claim rows;
4. account budget and exposure projections remain current-row updates, not
   append-only report streams;
5. PG row growth is limited to one policy event per Owner policy command and one
   reservation/claim per Ticket attempt;
6. no CPU-heavy builder is added to production cadence;
7. audit/history retention remains PG-governed or manual archive-only;
8. `scripts/audit_production_runtime_file_io.py` must report
   `performance_risk.status=clear` or its current equivalent before release.

## 17. Affected Boundaries And Expected Files

| Boundary | Expected files | Responsibility |
| --- | --- | --- |
| Pure domain | `src/domain/account_risk.py`, `src/domain/execution_sizing.py` | Claim arithmetic and invariants |
| Policy authority | `src/application/action_time/account_risk_policy.py`, `scripts/ops/set_account_risk_policy.py` | Append-only event identity and current pointer |
| Account facts | `src/infrastructure/binance_usdm_account_risk_snapshot.py` | Complete order-side and protection facts |
| Ownership/exposure | `src/application/action_time/account_exchange_ownership.py`, `src/application/action_time/account_exposure_current.py` | Current claims and protection segments |
| Budget/capacity | `src/application/action_time/account_budget_current.py`, `src/application/action_time/account_capacity_reservation.py`, `src/application/action_time/account_capacity_materialization.py` | Lock-first claim materialization |
| Action-time gate | `src/application/action_time/action_time_ticket.py`, `src/application/action_time/finalgate_preflight.py` | Same-transaction Ticket and claim revalidation |
| PG schema | New additive migration after revision 124 | Claim policy-event, risk-limit, and margin state |
| Verification | Focused unit, PG integration, and full-chain tests | Release certification |

The remediation must not modify live profiles, StrategyGroup registry semantics,
the official exchange gateway, or order lifecycle behavior unless a failing test
proves such a change is unavoidable and a separate design amendment is approved.

## 18. Delivery Stages And Review Gates

| Stage | Deliverable | Independent acceptance gate |
| --- | --- | --- |
| R1 | Unified risk vocabulary and claim contract | Rounded sizing creates a valid Ticket budget |
| R2 | Policy event identity and rollback invalidation | Old claim fails after rollback; same command retry is idempotent |
| R3 | Protection segmentation and current ownership | Held risk and historical isolation tests pass |
| R4 | Lock-first transaction and margin conservation | Real-PG concurrent materialization cannot oversubscribe |
| R5 | Full non-executing chain certification | Snapshot through lifecycle capacity recovery passes |
| R6 | Release review | Targeted, PG, full suite, diff, and file-I/O audits pass |

Each stage is separately reviewable and commit-worthy. No stage authorizes
deployment. A failure at any stage stops progression and must not be hidden by
passing component tests from another stage.

## 19. Rollback Strategy

Runtime rollback is an Owner policy event, not a schema downgrade and not a
position-close command.

On rollback:

1. append a new rollback policy event;
2. update current policy to the rollback event identity;
3. invalidate all earlier unsubmitted claims at FinalGate;
4. stop new entries governed by the account-capacity model;
5. continue protection, exit, reconciliation, settlement, and review for
   existing exchange exposure;
6. preserve all audit rows;
7. do not delete or rewrite exchange facts.

Database downgrade is not part of normal rollback. Additive columns may remain
dormant while the policy is inactive.

## 20. Live Enablement And WIP Impact

Before remediation:

```text
local component implementation present
-> release certification failed
-> Ticket materialization and risk conservation not proven
-> deployment prohibited
```

After remediation and local certification:

```text
dynamic account facts
-> atomic dual-position capacity claim
-> valid Action-Time Ticket
-> FinalGate revalidation
-> lifecycle capacity conservation
-> locally release-eligible
```

Natural production acceptance remains a later deployment-stage event. Absence
of a fresh market signal does not block this non-executing engineering closure.

This remediation occupies one active medium-size engineering lane. Strategy
expansion, UI work, and unrelated lifecycle refactors remain outside its WIP
scope.

## 21. Owner Confirmation Gate

Implementation must not start until the Owner accepts these three durable
decisions:

1. the existing policy event `source_event_id`, persisted on every claim, is the
   authorization epoch; `risk_policy_version` remains a semantic policy version;
2. overlapping protection orders use worst-loss-first conservative quantity
   allocation, and uncovered/ambiguous quantity blocks new entries;
3. rollback invalidates new-entry claims but never auto-closes existing positions
   or disables their protection, exit, reconciliation, or settlement paths.

No additional risk percentage, leverage, capital, StrategyGroup, symbol, side,
or live-permission decision is requested by this design.
