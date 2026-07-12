---
title: MAIN_CONTROL_ROADMAP
status: CURRENT
authority: docs/current/MAIN_CONTROL_ROADMAP.md
last_verified: 2026-07-12
---

# Main Control Roadmap

## Purpose

This roadmap is the current planning surface for the **StrategyGroup runtime
from pre-trade readiness through ticket-bound lifecycle closure**.

It is not a historical packet index, report catalogue, or proof-chain archive.
Historical roadmap material belongs in archive-only recovery records. Current
work must follow:

```text
PG/current services decide.
Generated JSON/MD exports summarize.
Archives preserve provenance only.
```

## Current Direction

The current mainline target is:

```text
five active StrategyGroups
-> multiple candidate symbols per StrategyGroup
-> PG-backed watcher coverage and fact snapshots
-> PG-backed readiness / promotion / action-time lane rows
-> PG Action-Time Ticket identity
-> ticket-bound Runtime Safety State / FinalGate / Operation Layer handoff
-> protected submit only inside official boundaries
-> protection / reconciliation / settlement / review
```

The system must not depend on repo MD/JSON, `output/**`, or report-dir JSON as
runtime or trading decision sources.

The program-level execution map for the next engineering phase is
`docs/current/MAINLINE_ENGINEERING_PROGRAM_PLAN.md`. That document is the
current ordering surface for large workstreams and links each program to its
design documents and acceptance proof.

## Current Program Order

| Order | Program | State | Primary design surface |
| --- | --- | --- | --- |
| 1 | **P1-TFC Trade Feedback Core Consolidation** | **active P1 medium-scale mainline** | `docs/current/P1_TRADE_FEEDBACK_CORE_CONSOLIDATION_DESIGN.md`, `docs/current/P1_TRADE_FEEDBACK_CORE_CONSOLIDATION_IMPLEMENTATION_PLAN.md` |
| P0 interrupt | **R1B Natural Live Lifecycle Calibration** | Starts only on a different-identity natural fresh signal or an active safety incident | `docs/current/P0_LIFECYCLE_PRODUCTION_CERTIFICATION_AND_CLOSURE_DESIGN.md` |
| 2 | **Strategy Opportunity / Replay-Live Calibration** | P1 after P1-TFC | Production Event Spec parity plus research-side opportunity frequency |
| 3 | **Owner Supervision Product Integration** | P1/P2 after feedback vocabulary stabilizes | `docs/current/OWNER_EXPLANATION_READ_MODEL_CONTRACT.md` |
| 4 | **Capital Allocation V1** | P2 after reliable real per-ticket outcomes | `docs/current/TRADING_QUALITY_CAPITAL_RISK_ALLOCATION_DESIGN.md` |
| 5 | **Multi-Asset Execution Kernel** | P2 after crypto live lifecycle calibration | asset-neutral Instrument/Venue/Calendar/Policy contracts |

P0-RT, P0-PC, Operation Layer capability, lifecycle safety core, first tick,
runner, recovery, Live Outcome, continuous reconciliation, and P0-LC are
deployed component baselines. They are not concurrent WIP programs. Real venue
calibration remains **R1B**, while engineering proceeds through P1-TFC without
waiting for market opportunity.

## Current Verified Progress

| Area | Current fact |
| --- | --- |
| **Live Candidate Baseline** | Tokyo runs `0368de6a109a366658e0cf45f1012ad5c7779153`; it is deployed and no-active accepted, but no natural real Ticket has completed exchange lifecycle calibration |
| **Active delivery branch** | `codex/p1-trade-feedback-core-consolidation` starts from the exact deployed `0368de6a` baseline |
| **Tokyo release line** | `/home/ubuntu/brc-deploy/app/current` points to `brc-runtime-governance-0368de6a-20260711T175627Z` |
| **Deployment method** | Server-side `git fetch + git archive export`; no local upload package is required for normal deploy |
| **PG migration** | Tokyo is at migration `114` (`2026-07-11-114_extend_exchange_commands_for_lifecycle.py`) |
| **P0-LC deployment acceptance** | Postdeploy verification passes; backend HTTP checks, schema count, lifecycle units, and no-active lifecycle service are accepted without exchange write |
| **Backend / watcher / monitor / lifecycle** | Backend, watcher timer, monitor timer, and lifecycle timer are active; latest lifecycle service result is success with zero active lifecycle scopes |
| **Real gateway submit-boundary test** | Deployed `110e680c` includes local impact coverage proving constructed PG fresh signal can reach `real_gateway_action -> gateway.place_order(...)` boundary with controlled test-gateway stop |
| **Post-submit first tick** | Deployed release includes `brc_ticket_bound_reconciliation_ticks`, `brc_ticket_bound_scope_freezes`, first post-submit tick selection, TP1 degraded recovery, retry limit, scope freeze writes, and stop-risk reservation rechecks |
| **P0 capital-safety closure** | `381aed34` deploys current-risk scope freeze blocking, stale/no-risk freeze resolution, scheduled/recovery reconciliation ticks, Live Outcome Ledger projection, and protective stop-risk direction validation |
| **Current runtime coverage** | Five StrategyGroups, 22 candidate scopes, and six current v2 Event Specs have current watcher coverage and execution-eligibility declarations |
| **Typed Ticket boundary** | Side-aware price, normalized quantity, positive stop risk, one reservation, atomic fact-to-Ticket transaction, and six-Event-Spec production-shaped certification are deployed |
| **Current tradeability** | The latest five-group PG acceptance classified current lanes as `market_wait_validated`; no current signal, promotion, lane, Ticket, or active lifecycle exists |
| **Lifecycle production capability** | Typed exchange truth, fill projection, durable short-transaction commands, continuous reconciliation, settlement, finalization, terminal Outcome, account-mode bootstrap, and migration-shaped ops health are deployed |
| **Current simplification finding** | The 31 migration-114 lifecycle statuses mix phase, protection, reconciliation, control, and recovery semantics; production callers duplicate event and next-action interpretation |

## Current Next Execution Order

This is the current execution order for **P1-TFC**. A new different
`signal_event_id` is a P0 interrupt event: after any unprotected position or
unknown exchange outcome is handled, engineering pauses at the next committed
transaction boundary, runs natural-signal acceptance, persists the result, and
then resumes this order.

| Order | Work | Priority | Done when |
| --- | --- | --- | --- |
| 1 | **Typed lifecycle decision model** | P1 | Every migration-114 status maps to one phase/protection/reconciliation/control/recovery/Owner decision; unknown state and terminal regression fail closed |
| 2 | **Production caller consolidation** | P1 | Protection, recovery, Runner, Fill, and Finalizer consume the existing lifecycle core instead of local event/action maps |
| 3 | **Replay/Rehearsal/Live decision parity** | P1 | Direct replay-shaped projection and production-shaped 22-scope/nine-failure rehearsal return the same typed decision without live authority |
| 4 | **Owner feedback in standard Ops path** | P1 | Tokyo Ops translates current lifecycle attention into processing, automatic recovery, temporary unavailability, intervention, or completion without mutation |
| 5 | **Regression and planning closure** | P1 | Full tests and runtime file-I/O/docs/output validators pass; current documents name one active medium-scale program |
| 6 | **Strategy Opportunity / Replay-Live Calibration** | P1 next | Current Event Specs explain expected opportunity frequency and replay/live rule parity without modifying live authority |

## Why This Was Not Detected Before Production Signals

The failure was detectable before market arrival. It escaped because tests proved
consumer behavior with privileged fixture dictionaries instead of proving the
production producer-to-consumer contract.

| Layer | Test or design assumption | Production fact | Escaped defect |
| --- | --- | --- | --- |
| Action-time fact fixture | Ticket tests inject `last_price`, `mark_price`, or `entry_price` directly | Production action-time fact materialization did not preserve a canonical entry reference for the observed CPM/BRF2 lanes | Ticket consumer passed tests against a field the production producer did not guarantee |
| Risk allocation | Zero requested risk was treated as no allocation value | `requested_risk_at_stop=0` allowed promotion/lane progression | Missing price and quantity were discovered only at Ticket materialization |
| Full-chain harness | Constructed downstream-complete dictionaries represented action-time state | Raw exchange/public facts were not replayed through the exact production projector chain for all six Event Specs | The harness proved lifecycle behavior after the missing handoff, not the handoff itself |
| Readiness/monitor | Latest no-signal state could return to market wait | A prior fresh signal had already exposed a repeatable Ticket engineering blocker | The unresolved blocker disappeared from the current Owner view |
| Repeated watcher cadence | Idempotency was treated as duplicate-row prevention | The same event identity could still overwrite first-observation fact and timing lineage | Event identity was stable while event content was mutable |
| Multi-candidate outcome aggregation | `arbitration_lost` meant a healthy loser after a winner was selected | Parent promotion can fail before any winner exists | Child success semantics overwrote the parent terminal blocker |

The systemic root cause is therefore:

```text
untyped dictionary compatibility
+ privileged downstream fixtures
+ no producer-consumer field ownership check
+ no production-shaped six-event certification
+ no repeated-cadence state-machine certification
+ no parent-child blocker conservation rule
-> tests green while the real PG chain is incomplete
```

## Production-Shaped Certification Gate

No runtime capability may be called complete merely because a consumer unit test
passes with a hand-authored dictionary. Every field required by Ticket,
FinalGate, Operation Layer, protection, or reconciliation must satisfy this
gate.

| Gate | Required proof |
| --- | --- |
| **Typed ownership** | Every required field has one named typed producer, one PG persistence owner, one freshness rule, and one consuming contract |
| **No privileged fixture injection** | Acceptance starts before the producer boundary; tests may not insert `last_price`, `entry_price`, quantity, stop risk, or similar downstream-ready values unless that producer is the unit under test |
| **Raw-source chain proof** | Venue/public/account source -> PG fact snapshot -> strategy evaluation -> signal -> promotion -> lane -> Ticket is exercised using the production code path |
| **Six-event matrix** | CPM-LONG, MPG-LONG, MI-LONG, SOR-LONG, SOR-SHORT, and BRF2-SHORT each pass positive, missing, stale, malformed, and conflicting-fact cases |
| **Earliest blocker** | Missing execution price, quantity, stop, TP1, account fact, protection, policy, or instrument precision must block before a real-submit lane is declared ready |
| **Projection consistency** | Candidate Pool, Readiness, Tradeability, Goal Status, Server Monitor, and lane-scoped process outcomes agree on the same first blocker and input watermark; one failed lane cannot hide another |
| **Production cadence** | The action-time path finishes within source validity windows; only lightweight PG readiness runs inside the Ticket transaction; Owner projections run afterward; business blockers keep watcher health green; no-signal ticks create zero JSON/MD files |
| **Deploy acceptance** | Isolated commit-bound rehearsal proves active behavior; Tokyo postdeploy verifies release, schema, units, no-active zero effects, PG lineage, and ops health without inserting synthetic production signal/Ticket rows |
| **Temporal identity** | Repeating the same closed-candle event cannot mutate first fact lineage, authority fields, observed time, expiry, or terminal state |
| **Outcome conservation** | Parent business/retryable/hard failure cannot be downgraded by child candidate rows; each affected lane preserves the parent blocker |

## Long-Horizon Development Route

The product target is a **small-capital, bounded-aggressive, multi-asset
right-tail experiment operating system**, not a general institutional quant
platform.

| Stage | Capability | Entry condition | Exit condition |
| --- | --- | --- | --- |
| **R0 Real Signal -> Ticket** | Close pricing, sizing, risk reservation, Ticket, Runtime Safety State, and pre-submit handoff for all current Event Specs | Deployed baseline | Six Event Specs pass producer-to-Ticket certification and distinct signal identities do not inherit historical blockers |
| **R1A Lifecycle Engineering Certification** | Wire exchange truth, fills, durable commands, protection/recovery, finalization, settlement, review, and terminal Outcome without waiting for market | R0 engineering baseline | 22 isolated rehearsal scopes reach simulated closure or one deterministic blocker; Tokyo no-active and ops acceptance pass |
| **R1B Live Lifecycle Calibration** | Measure real visibility latency, partial fills, fees, funding, slippage, protection/runner acceptance, and exchange-specific behavior | R1A closed and a natural opportunity occurs | Every real ticket reaches structured closure or one exact hard blocker; measured venue behavior feeds policy review |
| **R1C Trade Feedback Core Consolidation** | Unify post-Ticket phase, protection, reconciliation, control, recovery, and Owner feedback while R1B waits | R1A deployed | Production callers and Replay/Rehearsal use one reducer; no schema or trading-authority expansion; full regression passes |
| **R2 Capital Allocation V1** | Allocate loss-capable capital across StrategyGroup sleeves, symbols, sides, clusters, open risk, and pending reservations | Reliable per-ticket stop risk and live outcomes exist | Simultaneous candidates receive deterministic PG-backed allocation without changing per-ticket safety semantics |
| **R3 Multi-Asset Execution Kernel** | Add asset-neutral Instrument, Venue, TradingCalendar, MarketDataSource, ExecutionPolicy, ProtectionPolicy, and SettlementPolicy boundaries | Crypto lifecycle is stable | A new supported contract class reuses the core chain through adapters instead of copying it |
| **R4 Strategy Portfolio And Regime Routing** | Allocate observation and risk by regime, correlation, strategy role, and future option value | Multi-strategy live outcomes exist | `current_active`, `future_option`, `support_filter`, `conditional_trigger`, and `parked` roles affect budget without widening runtime authority silently |
| **R5 Autonomous Experiment Governance** | Produce versioned promote/downshift/park/kill and policy-change recommendations from outcomes | Versioned outcomes and regime evidence are mature | Recommendations are machine-generated but only PG Owner policy events can change authority |
| **R6 Owner Supervision Product** | Owner sees running, waiting, processing, protected, recovering, intervention-needed, and completed states | Backend explanation and lifecycle states are stable | Owner controls policy and capital while the system performs normal operation automatically |

The route is sequential by capability, not by calendar. **R1A is deployed,
R1C continues without market opportunity, and only R1B requires a real event.** Later stages must not
become active WIP before their entry conditions, while current abstractions must
remain asset-neutral enough that multi-asset support does not require a second
execution chain.

## Authority Boundary

| Layer | Current authority | Not authority |
| --- | --- | --- |
| Strategy semantics | PG strategy registry/current versions | historical handoff JSON as runtime source |
| Owner policy | PG owner policy events/current projection | repo policy JSON as runtime source |
| Candidate universe | PG candidate scopes and runtime scope bindings | Candidate Pool JSON export |
| Facts | PG runtime fact snapshots | `latest-*facts.json` exports |
| Readiness/promotion | PG readiness rows and promotion candidates | Daily Table / Candidate Pool JSON exports |
| Action-time identity | PG action-time lane and Action-Time Ticket rows | resume pack or dispatch JSON identity |
| Safety | Runtime Safety State over PG/current facts | dry-run audit or closure evidence file |
| Owner explanation | backend read model over current projections | frontend or MD/JSON self-interpretation |

## Current P0 Workstreams

**P1-TFC is the only active medium-scale integration program.** P0-F, P0-G,
P0-H, P0-J, and P0-LC below are deployed component responsibilities, not
parallel programs.

| Priority | Workstream | Goal | Done when |
| --- | --- | --- | --- |
| **P0-A** | **File-authority elimination** | remove production/current reads from repo MD/JSON, `output/**`, and report-dir proof files | validators reject reintroduced runtime file authority |
| **P0-B** | **PG current projection closure** | make Goal Status, Candidate Pool, Daily Table, Runtime Safety State, Action-Time Ticket, and Owner Explanation read from PG/current services | one owner projector per current projection |
| **P0-C** | **Action-time ticket path** | fresh satisfied signal becomes one explicit PG Action-Time Ticket before FinalGate / Operation Layer | ticket identity contains StrategyGroup, symbol, side, profile, policy versions, facts, risk scope |
| **P0-D** | **Server monitor ownership** | server-side readonly monitor classifies quiet / notify from PG/current state | no production dependency on local heartbeat or local cache |
| **P0-E** | **Performance and retention** | no-signal ticks stay quiet and bounded in disk / CPU / PG rows | report growth and restart storms are structurally prevented |
| **P0-F** | **Ticket-bound lifecycle hardening** | post-submit lifecycle state machine, runner mutation, protection reconciliation, and failure recovery remain one safety core | every submitted ticket reaches protected/closed state or one exact lifecycle hard blocker |
| **P0-G** | **Post-submit first tick and recovery command determinism** | immediate exchange-truth first tick and one recovery command or hard stop for every unsafe lifecycle blocker | every real protected submit result reaches matched/protected, pending visibility, deterministic recovery command, or exact hard stop |
| **P0-H** | **Live outcome ledger** | real tickets become structured result and learning rows | every real ticket has one outcome row or one exact hard-blocked outcome |
| **P0-I** | **Scope freeze pre-submit gate** | active lifecycle/reconciliation freeze blocks the same StrategyGroup + symbol + side before another submit path can form | promotion, lane, ticket, Runtime Safety State, FinalGate preflight, and protected submit all reject frozen scopes |
| **P0-J** | **Continuous reconciliation tick** | keep exchange-truth reconciliation alive after the first tick | lifecycle reaches closure, exact recovery command, or hard stop without recurring report files |
| **P0-K** | **Real Signal -> Ticket closure** | make production action-time pricing, sizing, stop-risk reservation, and Ticket creation one coherent typed chain | every eligible real-submit lane either creates one Ticket inside freshness bounds or stops at one producer-owned blocker before lane readiness |
| **P0-L** | **Production-shaped certification** | prevent complete downstream dictionaries from hiding missing production handoffs | all six Event Specs pass raw-source-to-Ticket certification and projection consistency checks without exchange write |

## Active Runtime Loop

```text
StrategyGroup candidate scope
-> watcher coverage
-> public/account/action-time facts
-> per-symbol readiness row
-> promotion candidate
-> single action-time lane
-> Action-Time Ticket
-> Runtime Safety State
-> FinalGate
-> Operation Layer
-> protected submit
-> post-submit lifecycle
-> review outcome
```

## Blocker Language

Current planning must use blocker classes from
`docs/current/BLOCKER_CLASSIFICATION_CONTRACT.md`.

Valid current conclusions include:

| State | Meaning |
| --- | --- |
| `market_wait_validated` | system is ready for that lane and only current market event is absent |
| `computed_not_satisfied` | detector/watcher/facts ran, but strategy facts are false |
| `scope_not_attached` | strategy/symbol/side is not bound to runtime scope |
| `action_time_boundary_not_reproduced` | fresh/live-like event cannot reach action-time chain |
| `execution_gate_gap` | official safety/execution gate blocks submit |
| `hard_safety_stop` | exchange write would violate a hard boundary |

Generic `waiting_for_market`, stale proof-chain files, or dry-run audit pass
must not stand in for current tradeability.

## Deleted Current Paths

These names are no longer current runtime surfaces:

```text
runtime_dry_run_audit_chain.py
runtime_execution_chain_closure_status.py
runtime_live_cutover_readiness.py
runtime_live_closure_evidence*.json
runtime_first_bounded_live_order_completion_audit.py
run_strategygroup_runtime_local_monitor_sequence.py
run_strategygroup_runtime_goal_progress_audit.py
```

If historical evidence is valuable, preserve it only as archive/provenance. Do
not reintroduce these names as production blockers, readiness checks, Owner
surfaces, or file inputs.

## Non-Negotiable Constraints

1. **No production runtime decision from repo MD/JSON**.
2. **No production runtime decision from `output/**` latest files**.
3. **No production runtime decision from dry-run / closure evidence files**.
4. **No fallback chain that silently revives old file authority**.
5. **No frontend interpretation of blockers, facts, lanes, tickets, or submit authority**.
6. **No FinalGate, Operation Layer, exchange write, live profile, or sizing expansion through cleanup work**.

## Near-Term Acceptance

The next stable checkpoint is:

```text
server watcher and monitor run from PG/current state
-> no-signal tick has bounded writes
-> all six current Event Specs pass isolated producer-to-lifecycle certification
-> fresh signal creates PG promotion / lane / ticket rows
-> Action-Time Ticket can continue through lifecycle-safe protected submit
-> TP1 / runner / final-exit lifecycle states are reconciled against exchange truth
-> simulated terminal lifecycles produce one final Live Outcome row without privileged fixture transitions
-> one typed lifecycle reducer owns phase / protection / reconciliation / control / recovery interpretation
-> Tokyo Ops consumes the same reducer for Owner lifecycle feedback
-> the next real submitted ticket automatically enters the same wired lifecycle for live calibration
-> Risk Reservation v0 records stop-risk before FinalGate-ready state
-> Owner Explanation can explain why no trade, why blocked, or what happened after submit
-> old MD/JSON proof-chain readers are deleted or archive-only
-> validators prevent regression
```
