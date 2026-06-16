---
title: MAIN_CONTROL_ROADMAP
status: CURRENT
authority: docs/current/MAIN_CONTROL_ROADMAP.md
last_verified: 2026-06-16
---

# Main Control Roadmap

## Purpose

This is the short planning table for the main runtime window.

The main goal is still the StrategyGroup runtime pilot:

```text
Owner enables a StrategyGroup.
The system observes, checks, executes inside official boundaries, protects,
reconciles, settles, records, and reports Owner-readable state.
```

The first-stage acceptance target is narrower and more operational:

```text
Complete the first selected StrategyGroup + tiny risk bounded real-order loop
when a fresh signal exists and all official runtime gates pass.
```

Dry-run audit, source readiness, and UI work are support tracks for that target.
They are not substitutes for the first bounded live-order closure.

This file is not a research backlog, frontend design spec, or historical packet
index.

## Current Tracks

| Track | Owner outcome | Current owner | Current status | Next checkpoint |
| --- | --- | --- | --- | --- |
| P0 First Bounded Live Order Closure | First selected StrategyGroup + tiny risk real order completes through official gates, finalize, reconciliation, settlement, and review | Main runtime window | active, waiting for fresh signal | On fresh signal, pause lower tracks and drive RequiredFacts -> candidate/auth -> FinalGate -> Operation Layer -> real submit -> close loop |
| P0 Runtime Product State Repair | Owner Console can read one stable source-readiness state instead of interpreting packets | Main runtime window | mainline implemented | Keep `owner-console-source-readiness.json` / API stable and refresh it from Tokyo watcher packets |
| P0 Runtime Pilot Liveness | Fresh signal can continue to candidate/auth/FinalGate/Operation Layer evidence prep without accidental watcher-side attempt burn | Main runtime window | active | Rerun fresh signal chain through standing-authorized evidence prep, action-time FinalGate, and official Operation Layer only |
| P0 Shared Runtime Pipeline Validation | Prove that execution-chain fixes are shared by all StrategyGroups and not SOR-specific patches | Main runtime window | active | After common chain closes, run cross-StrategyGroup dry-run/admission validation for MPG / TEQ / FBS / PMR / SOR |
| P0 Runtime Dry-Run Audit Chain | Main chain can expose evidence/endpoint/gate breakage without waiting for market opportunity | Main runtime window | deployed | Keep local and Tokyo `runtime-dry-run-audit-chain.json` covering the full non-executing close-loop shape |
| P0 Safe Tokyo Operations | Tokyo watcher stays current, alive, bounded, and auditable | Main runtime window | active | Verify watcher reports and bounded deploys after each runtime-code change |
| P0 Goal Status Summary | Main goal loop can decide waiting vs processing vs deploy/safety blocker from one read-only packet | Main runtime window | active | Refresh `strategygroup-runtime-goal-status.json` after watcher ticks and use it before advancing real-order actions |
| P1 Owner Console Mainline Stabilization | Owner sees simple state, not raw gate vocabulary | Main runtime window | active | Stabilize real-backend UI semantics, source-health display, and responsive visual QA from mainline |
| P1 StrategyGroup Research Handoff | Strategy research enters main control only through reviewed handoff packs | Strategy research window | active separately | Keep research artifacts out of main runtime worktree except reviewed handoff input |
| P2 Historical Debt Reduction | Historical docs/code do not obscure current pilot behavior | Main runtime window | pending | Compress/archive only after P0 source and runtime state are stable |
| P2 LLM Assistance | LLM supports audit/readiness/notification without changing execution authority | Main runtime window | pending | Start with read-only audit summaries and Feishu notification text only |
| P2 External Information Capture | External information can inform research/watch context without becoming execution authority | Strategy/research window first | pending | Treat as research input, not live-submit permission |

## P0 Subgoal: Owner Console Source Readiness Productization

### Current State

Owner Console exploration is no longer treated as an isolated authority source.
The main runtime branch now owns the source-readiness contract and exposes the
machine-readable packet/API that the console consumes.

### Scope

Build one stable Owner Console source-readiness surface from main runtime facts:

```text
StrategyGroup catalog
runtime pilot status
watcher status
live facts readiness
account funds
orders
positions
protection
reconciliation detail state
operation audit detail state
runtime dry-run audit state
StrategyGroup runtime goal status
```

### Required Artifacts

| Artifact | Path |
| --- | --- |
| Human confirmation | `docs/current/OWNER_CONSOLE_SOURCE_READINESS_CONFIRMATION.md` |
| Machine-readable packet | `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/owner-console-source-readiness.json` |
| API surface | `GET /api/trading-console/owner-console-source-readiness` |
| Watcher refresh hook | `scripts/refresh_strategygroup_runtime_product_state_packets.py` |

### Acceptance

| Requirement | Expected result |
| --- | --- |
| StrategyGroup catalog ready | Owner Console can show MPG / TEQ / FBS / PMR / SOR even if runtime overlay degrades |
| Runtime source reachable | Source status is `ready` or `degraded`, not an empty strategy list |
| Orders source readable and empty | Source status is `ready_empty`, Owner language is `暂无订单` |
| Positions source readable and empty | Source status is `ready_empty`, Owner language is `暂无持仓` |
| Account facts readable | Source status is `ready`, Owner language is `资金正常` |
| Watcher waiting for signal | Owner state is `waiting_for_opportunity`, Owner language is `等待机会` |
| Runtime dry-run audit passed | Source status is `ready`, Owner language is `审计演练正常` |
| Runtime goal status reports liveness or safety degradation | Owner state is `needs_intervention` or `temporarily_unavailable`, not `waiting_for_opportunity` |
| Reconciliation/audit detail missing | Detail degrades without hiding StrategyGroups |
| Safety | No order, exchange write, FinalGate bypass, Operation Layer bypass, secret mutation, profile expansion, sizing change, withdrawal, or transfer |

### 2026-06-16 Checkpoint

| Item | Result |
| --- | --- |
| Source-readiness API | Returns `market_opportunity=等待机会`, `funds=资金正常`, `orders=暂无订单`, `positions=暂无持仓`, `protection=保护正常`, `runtime_dry_run_audit=审计演练正常` in the real-backend smoke fixture |
| Owner Console UI | Homepage treats readable funds/orders/positions/protection as business-ready even when candidate-prep details are still progressive; StrategyGroup rows show `等待机会` during no-signal observation |
| System page | Shows `审计演练` as a secondary system-health item, not a homepage gate |
| Visual governance | Strategy rows show one primary health chip plus one Owner-readable summary sentence instead of a four-chip evidence wall |
| Verification | Python source-readiness/dry-run tests, frontend build, real-backend smoke, normal smoke, state smoke, and visual QA passed |
| Runtime goal overlay | Source-readiness API now reads `strategygroup-runtime-goal-status.json`; `runtime_liveness_degraded` overrides the Owner state to `需要介入` so the console does not mislabel liveness repair as market waiting |

### 2026-06-17 Selected Scope Refresh Checkpoint

| Item | Result |
| --- | --- |
| Selected StrategyGroup scope | Watcher service now carries default `BRC_SELECTED_STRATEGY_GROUP_ID=MPG-001`, `BRC_STRATEGYGROUP_MAX_SYMBOLS=3`, and `BRC_STRATEGYGROUP_STALE_AFTER_SECONDS=180`; `/home/ubuntu/brc-deploy/env/runtime-signal-watcher.env` may override them |
| Product-state refresh | `80-product-state-refresh.conf` now performs signed GET-only live-facts precollection and writes `product-state-refresh-packet.json` before refreshing Owner Console source-readiness |
| Stale drop-in hygiene | Tokyo deploy planner removes legacy `50-product-state-refresh.conf` so old refresh semantics do not race or overwrite current selected-scope packets |
| Safety | This remains readmodel/live-facts GET-only work; it does not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

## P0 Subgoal: Runtime Liveness Repair

### Current State

The watcher has reached the post-signal boundary where the fresh StrategyGroup
signal, candidate, grant, authorization, and FinalGate preview can exist, but
the official Operation Layer submit path still depends on prepared evidence
IDs. The previous blocker language was still tied to old per-chat Owner
confirmation for attempt consumption and local registration.

### Correct Current Path

```text
fresh signal
-> standing-authorized scoped evidence preparation
-> action-time FinalGate
-> official Operation Layer action only
-> post-submit finalize / reconciliation / budget settlement
```

### Acceptance

| Requirement | Expected result |
| --- | --- |
| Default arm preview | Still stops before attempt consumption |
| Standing evidence prep | Records bounded attempt/local-registration/exchange-arm evidence only when explicitly enabled |
| Local registration blocked | Stops before exchange-submit evidence calls and emits a reviewable blocker instead of noisy `RuntimeExecutionOrderLifecycleAdapterResult not found` 404s |
| Disabled smoke | Can prove the action endpoint without exchange write |
| FinalGate | Must rerun at action time before real Operation Layer action |
| Operation Layer | Must use official endpoint and required evidence IDs |
| Safety | No secret mutation, profile expansion, sizing change, withdrawal, transfer, stale-fact execution, duplicate submit, or conflicting position/order execution |

### 2026-06-16 Checkpoint

| Item | Result |
| --- | --- |
| Runtime renewal RCA | New profile-confirmation runtime drafts now reset `attempts_used=0` and `budget_reserved=0` instead of inheriting exhausted proposal counters |
| Fresh signal chain | Tokyo reached `ready_for_action_time_final_gate` for the fresh SOR signal after bounded runtime renewal |
| Operation Layer RCA | Exchange-submit evidence prep was incorrectly continuing after local registration remained blocked; the downstream 404 was a symptom, not the root blocker |
| Flow repair | Arm flow now stops before exchange-submit action/enablement/adapter calls when local registration result is not `registered_created_local_orders` |
| Safety | Blocked local registration remains reviewable project progress, but it is not treated as a real-order green light |
| Attempt mutation boundary | Followup / dry-run / arm preview no longer authorizes attempt or budget mutation; mutation belongs only to the official Operation Layer submit boundary after action-time gates pass |
| Pre-attempt evidence blockers | Shadow-mode, stale trusted-submit facts, missing deployment-readiness evidence, or non-live authorization warnings now block before attempt reservation or mutation |
| Standing evidence prep | Standing prep can be requested as a non-executing proof surface, but its blockers cannot be hidden behind disabled-smoke completion |
| Dispatcher evidence relay | After same-run action-time FinalGate passes, resume dispatcher can run standing-authorized Operation Layer evidence prep, persist the evidence report, recalculate readiness, and only then call the official Operation Layer submit endpoint |
| Reservation warning guard | Attempt reservation warnings that prove shadow-mode, stale facts, missing deployment evidence, or non-live authorization now stop before attempt mutation and budget consumption |
| Live enablement relay | After same-run FinalGate pass, dispatcher can request bounded live-runtime enablement only when hard safety blockers are absent, then rerun Operation Layer evidence prep |
| Operation evidence deferral | Live enablement may defer only downstream Operation Layer evidence IDs that cannot exist until the runtime leaves shadow; safety facts, Owner authorization, deployment, staged-chain, protection, budget, duplicate-submit, active-position, open-order, and scope blockers remain hard blockers |
| Live runtime handoff | A runtime that has left shadow mode and is execution-enabled is no longer eligible for B0 shadow-candidate scheduler planning; it must be handled by Operation Layer evidence/readiness or closed-loop recovery |
| Observation blocker hygiene | Plain `waiting_for_signal` and non-mutating historical attempt/candidate blockers do not create Owner attention; they remain runtime-level audit warnings unless prepare/order/exchange/budget/attempt side effects occurred |

## P0 Subgoal: Runtime Dry-Run Audit Chain

### Purpose

The real market path should not be the only way to discover evidence relay,
FinalGate, Operation Layer, or source-readiness breakage. A dry-run audit chain
must exercise the same semantics without creating real orders or exchange
writes.

### Target Chain

```text
mock fresh signal
-> RequiredFacts readiness
-> candidate / authorization evidence
-> action-time FinalGate dry-run / preflight
-> Operation Layer evidence prep
-> disabled submit smoke
-> fake or non-executing post-submit finalize / reconciliation / budget settlement / review shape check
-> unified audit packet
```

### Required Artifact

| Artifact | Path |
| --- | --- |
| Local audit packet | `output/strategygroup-runtime-pilot/dry-run-audit-chain/runtime-dry-run-audit-chain.json` |
| Tokyo audit packet | `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/runtime-dry-run-audit-chain.json` |

### Current Implementation

The local script is:

```text
scripts/runtime_dry_run_audit_chain.py
```

It currently runs five fixture-backed scenarios and treats expected blocked
states as successful audit coverage when they stop before dangerous actions.
Tokyo refreshes this script as a watcher-adjacent non-executing audit step.

### Scenario Matrix

| Scenario | Expected result |
| --- | --- |
| No signal | `waiting_for_signal`; no candidate, authorization, FinalGate, or Operation Layer |
| Mock fresh signal pass | Evidence IDs connect; dangerous action flags remain false |
| Mock Operation Layer submit/finalize pass | Dispatcher reaches settled and next-attempt-ready with mock responses only |
| RequiredFacts missing | Clear `missing_fact` blocker before Operation Layer |
| Active position or open-order conflict | Clear conflict blocker before FinalGate or Operation Layer action |

### Evidence Relay Checks

The mock fresh signal pass scenario must prove these handoff checks before a
real signal appears:

| Check | Expected result |
| --- | --- |
| Required Operation Layer evidence IDs | All required IDs are present; no `missing_evidence_id` remains |
| Authorization chain | Operation Layer command, evidence report, and closed-loop shapes use the same fresh authorization |
| Action-time FinalGate | Same-run FinalGate preflight is called and passes before Operation Layer readiness |
| Official Operation Layer endpoint | The selected endpoint is the official first-real-submit action path |
| Legacy local-registration probe | Legacy `RuntimeExecutionOrderLifecycleAdapterResult` probe blocker is tolerated only when adapter result evidence exists |

### Full Close-Loop Shape

The dry-run pass scenario must prove these non-executing shapes exist before the
project waits for a real signal:

| Shape | Expected result |
| --- | --- |
| Post-submit finalize | Runtime can return to a fresh-signal next-attempt gate |
| Reconciliation | No active position, no open order, no mismatch blockers |
| Budget settlement | Reservation is released or accounted |
| Review record | Runtime outcome is recorded without requiring Owner action |

## P0 Subgoal: Shared Runtime Pipeline Validation

### Purpose

The pilot must prove that current blockers are mostly shared runtime-chain
issues, not per-strategy execution implementations. StrategyGroups provide
signal, facts, symbols, side, risk boundary, and hard stops. They must not each
own a separate candidate/auth/FinalGate/Operation Layer/finalize path.

### Validation Model

| Area | Ownership | Repeated per StrategyGroup |
| --- | --- | --- |
| Fresh signal to candidate/auth | Runtime main chain | No |
| RequiredFacts readiness read | Runtime facts layer | No |
| Attempt renewal and admission | Runtime admission | No |
| FinalGate call order | Execution safety | No |
| Operation Layer evidence relay | Execution layer | No |
| Active position / open order / protection / budget / duplicate-submit checks | Account, protection, budget, idempotency layers | No |
| Post-submit finalize / reconciliation / settlement | Closed-loop layer | No |
| Owner Console source state | Product readmodel | No |
| Supported symbols and sides | StrategyGroup handoff | Yes |
| Signal-ready rule | StrategyGroup handoff | Yes |
| Strategy RequiredFacts definition | StrategyGroup handoff | Yes |
| Risk defaults and hard stops | StrategyGroup handoff | Yes |
| Conflict policy | StrategyGroup handoff plus portfolio policy | Yes |

### Acceptance

| Requirement | Expected result |
| --- | --- |
| Shared chain | MPG / TEQ / FBS / PMR / SOR enter the same runtime admission, candidate/auth, FinalGate, Operation Layer, finalize, reconcile, and settle code path |
| Strategy-specific inputs | Each StrategyGroup only changes handoff contract inputs: signal packet, RequiredFacts, symbol, side, risk defaults, hard stops, and conflict rules |
| Dry-run coverage | The dry-run audit chain includes at least one pass-like fixture and one blocked fixture that are not SOR-only |
| No execution fork | No StrategyGroup adds a custom FinalGate, Operation Layer, order lifecycle, exchange gateway, or settlement implementation |
| Owner Console | The UI/readmodel shows StrategyGroup differences as product state, not separate packet-reading workflows |

### 2026-06-17 Checkpoint

| Item | Result |
| --- | --- |
| Dry-run audit artifact | `runtime-dry-run-audit-chain.json` now includes `shared_runtime_pipeline_validation` |
| StrategyGroups covered | MPG / TEQ / FBS / PMR / SOR |
| Common-chain proof | All five StrategyGroups share the same runtime stages: admission, candidate/auth, RequiredFacts, FinalGate, Operation Layer evidence relay, account/protection/budget/idempotency checks, submit, finalize/reconcile/settle/review, and Owner readmodel |
| Strategy-specific proof | Each handoff only supplies symbols, sides, signal rule, RequiredFacts, risk defaults, hard stops, and sample packets |
| Execution authority proof | Each handoff keeps `candidate_creation_authorized=false`, `final_gate_input=false`, `operation_layer_input=false`, and `real_submit_authorized=false` |
| Goal status guard | `strategygroup-runtime-goal-status` now requires `shared_runtime_pipeline_checked=true` before treating dry-run audit as healthy |

### Mock Dispatcher Close-Loop

The dry-run audit chain also includes a local mock dispatcher close-loop. It
uses mocked API responses to exercise the same dispatcher handoff shape:

```text
Operation Layer submit
-> post-submit finalize
-> budget settlement id
-> review id
-> next-attempt gate ready
```

This scenario may contain simulated exchange-effect fields inside its own
artifact. Those fields are explicitly marked as mock-only and are not accepted
as real execution proof. The global audit packet must still show no actual
exchange write, no actual order creation, no actual order-lifecycle call, and
no withdrawal or transfer.

### Safety

The dry-run chain must not call exchange write, create real orders, mutate
secrets, mutate live profile, expand order sizing, create withdrawals or
transfers, treat disabled smoke as real execution proof, or mark missing
evidence as ready.

## P0 Subgoal: Runtime Goal Status Summary

### Purpose

The active goal loop should not require manually reading several watcher
packets before deciding whether to keep observing or advance toward the first
bounded real order. A read-only summary packet now classifies the current
runtime state from already-written evidence.

### Required Artifact

| Artifact | Path |
| --- | --- |
| Local/generated packet | `output/strategygroup-runtime-pilot/goal-status/strategygroup-runtime-goal-status.json` |
| Tokyo watcher packet | `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/strategygroup-runtime-goal-status.json` |
| Builder | `scripts/build_strategygroup_runtime_goal_status.py` |
| Watcher drop-in | `deploy/systemd/brc-runtime-signal-watcher.service.d/70-goal-status.conf` |

### Classification

| Status | Meaning | Next safe checkpoint |
| --- | --- | --- |
| `waiting_for_signal` | Runtime is healthy and no fresh StrategyGroup signal exists | `continue_watcher_observation` |
| `fresh_signal_processing` | Fresh signal exists but candidate/authorization evidence is not complete | `prepare_candidate_grant_authorization_evidence` |
| `action_time_finalgate_ready` | Candidate/authorization reached action-time gate boundary | `run_official_action_time_finalgate` |
| `operation_layer_ready` | Required evidence is ready for the official Operation Layer path | `call_official_operation_layer_submit_after_action_time_recheck` |
| `deployment_issue` | Tokyo release does not match expected runtime head | Align deployment before runtime action |
| `hard_safety_stop` | Forbidden effect evidence is present | Stop and investigate |

### Safety

The builder only reads local JSON packets. It does not call Tokyo APIs,
FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawals,
transfers, secrets, live profile, or order sizing. It must never mark a real
order action ready unless selected StrategyGroup, tiny risk, fresh signal,
RequiredFacts, candidate/grant/authorization evidence, action-time FinalGate,
and official Operation Layer evidence are all represented by current packets.

The `runtime_dry_run_audit_passed` check is intentionally stricter than
`runtime-dry-run-audit-chain.json.status=passed`. The goal status packet must
also see these dry-run sub-checks as true before treating the runtime chain as
healthy:

| Dry-run sub-check | Purpose |
| --- | --- |
| `required_scenarios_present` | Confirms the no-signal, mock signal, missing fact, conflict, blocker-review, and closed-loop scenarios are all represented. |
| `all_scenarios_passed` | Confirms every dry-run scenario passed. |
| `dangerous_effects_absent` | Confirms no forbidden effect flag escaped the dry-run packet. |
| `disabled_smoke_not_real_execution_proof` | Prevents disabled smoke from being mistaken for real execution evidence. |
| `operation_layer_evidence_relay_checked` | Confirms evidence IDs connect through the Operation Layer handoff shape. |
| `fresh_signal_fast_auto_chain_checked` | Confirms mock fresh signal reaches candidate/authorization readiness, FinalGate dispatch, and Operation Layer evidence readiness without calling real submit. |
| `legacy_local_registration_probe_tolerance_checked` | Confirms old local-registration probe semantics are tolerated only when the new evidence path is present. |
| `mock_operation_layer_closed_loop_checked` | Confirms fake submit/finalize/reconcile/budget/review shape remains covered without exchange write. |
| `operation_layer_blocker_review_policy_checked` | Confirms active position, open order, protection, budget, duplicate-submit, and scope mismatches become reviewable blocked packets rather than project-stopping chat confirmations, while real submit remains forbidden. |

Operation Layer blockers such as active position, open order, missing protection,
missing budget, duplicate-submit risk, and symbol/side/notional/leverage scope
mismatch must not stop project progress or watcher observation. They must
produce an auditable review packet and Owner-readable unavailable/intervention
state, but `real_submit_allowed` must remain false until the blocker is
resolved through the official path.

## P0 Subgoal: Common Runtime Pipe Before Strategy-Specific Adapters

### Current Judgment

The current first-real-submit blocker mix is treated as:

| Share | Scope | Meaning |
| --- | --- | --- |
| 80% | Common runtime pipe | Fresh signal, RequiredFacts readiness, candidate/auth, FinalGate, Operation Layer evidence, live boundary enablement, submit, finalize, reconcile, settle, and Owner readmodel are shared infrastructure. |
| 20% | StrategyGroup adapter | Each StrategyGroup supplies signal semantics, RequiredFacts definitions, supported symbol/side, tiny risk defaults, hard stops, and conflict policy. |

### 2026-06-16 Runtime Boundary Repair

The resume dispatcher now includes a bounded runtime live-enablement relay after
same-run action-time FinalGate pass:

```text
FinalGate PASS
-> prepare Operation Layer evidence
-> if blocked only by runtime shadow boundary
-> official live-enablement preview / mutation
-> re-prepare Operation Layer evidence
-> official Operation Layer submit only when evidence is ready
```

This is a common-chain repair. It must apply to MPG / TEQ / FBS / SOR / PMR
through the same dispatcher path and must not be copied into StrategyGroup
specific code.

### Guardrails

| Guardrail | Required behavior |
| --- | --- |
| Hard safety blockers | Active position, open order, duplicate submit, scope mismatch, withdrawal, transfer, and bypass tokens block live enablement relay. |
| Live enablement mutation | May mutate runtime execution state only through the official API; it must not create orders, call OrderLifecycle, call exchange, mutate budget, or create withdrawal/transfer actions. |
| Operation Layer readiness | Missing evidence is never fabricated; after live enablement the dispatcher must re-run evidence prep and re-check readiness. |
| Strategy adapters | StrategyGroup code remains limited to signal/facts/risk/hard-stop inputs. It must not implement custom FinalGate, Operation Layer, gateway, or settlement paths. |

## Boundaries

- Keep UI experiments outside mainline until reviewed, but the Owner Console
  source-readiness contract is now mainline-owned in `/Users/jiangwei/Documents/final`.
- Keep strategy research in `/Users/jiangwei/Documents/final-strategy-research`.
- Keep main runtime work in `/Users/jiangwei/Documents/final`.
- Do not expose internal gate names as Owner homepage labels.
- Do not treat weak strategy evidence as a live-safety blocker.
- Do not treat missing audit detail as a reason to hide StrategyGroups.
