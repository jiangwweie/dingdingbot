---
title: MAIN_CONTROL_ROADMAP
status: CURRENT
authority: docs/current/MAIN_CONTROL_ROADMAP.md
last_verified: 2026-07-18
dual_position_status_verified: 2026-07-17
runtime_observation_truth_status_verified: 2026-07-18
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
-> PG-backed fresh signal / ActionTimeInvocation / promotion / action-time lane rows
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
| 1 | **P0 Action-Time Failure Conservation And Natural-Event Acceptance** | **deployed and accepted; natural-event production calibration remains interrupt-driven** | `docs/current/P0_ACTION_TIME_FAILURE_CONSERVATION_AND_NATURAL_EVENT_ACCEPTANCE_DESIGN.md` |
| 2 | **P0 Signal Identity Conservation And Owner Notification Truth** | **deployed and production-accepted; anonymous readiness is conserved as a PG lane failure and only the server monitor notifies the Owner** | `docs/current/P0_SIGNAL_IDENTITY_CONSERVATION_AND_OWNER_NOTIFICATION_TRUTH_DESIGN.md` |
| P0 interrupt | **R1B Natural Live Lifecycle Calibration** | Starts only on a different-identity natural fresh signal or an active safety incident | `docs/current/P0_LIFECYCLE_PRODUCTION_CERTIFICATION_AND_CLOSURE_DESIGN.md` |
| 3 | **P0 Runtime Causal Integrity And Adversarial Certification** | **completed and deployed; 12 PostgreSQL/process scenarios passed and four demonstrated defects were repaired** | `docs/current/P0_RUNTIME_CAUSAL_INTEGRITY_AND_ADVERSARIAL_CERTIFICATION_DESIGN.md` |
| 4 | **Owner Supervision Product Integration** | **P0 notification/forensics closure deployed and accepted** | `docs/current/P0_OWNER_NOTIFICATION_LANGUAGE_AND_RUNTIME_FORENSICS_DESIGN.md`, `docs/current/OWNER_EXPLANATION_READ_MODEL_CONTRACT.md` |
| 5 | **P0 Runtime Observation Truth And Forensics Remediation** | **deployed component baseline; HTTP 400/compact transport defect is closed, but production closure is superseded** | `docs/current/P0_RUNTIME_OBSERVATION_TRUTH_AND_FORENSICS_REMEDIATION_DESIGN.md`, `docs/current/P0_RUNTIME_OBSERVATION_TRUTH_AND_FORENSICS_REMEDIATION_IMPLEMENTATION_PLAN.md` |
| 6 | **P0 Production Runtime Full-Chain Readiness Remediation** | **design complete; awaiting Owner confirmation before implementation** | `docs/current/P0_PRODUCTION_RUNTIME_FULL_CHAIN_READINESS_REMEDIATION_DESIGN.md`, `docs/current/P0_PRODUCTION_RUNTIME_FULL_CHAIN_READINESS_REMEDIATION_IMPLEMENTATION_PLAN.md` |
| P0 correction | **P0 Account Truth Convergence And Failed-Submit Capacity Conservation** | **2026-07-20 local implementation and PostgreSQL certification complete; awaiting Tokyo deployment approval for T09-T10** | `docs/current/P0_ACCOUNT_TRUTH_CONVERGENCE_AND_FAILED_SUBMIT_CAPACITY_CONSERVATION_DESIGN.md`, `docs/current/P0_ACCOUNT_TRUTH_CONVERGENCE_AND_FAILED_SUBMIT_CAPACITY_CONSERVATION_IMPLEMENTATION_PLAN.md` |
| 7 | **Dual-Position Hard-Cap Account Risk Model V0** | **migrations 134-136 and component evidence are deployed; full-chain recertification is folded into P0 readiness remediation** | `docs/current/DUAL_POSITION_ACCOUNT_RISK_V0_RELEASE_BLOCKER_REMEDIATION_DESIGN.md`, `docs/current/DUAL_POSITION_ACCOUNT_RISK_V0_RELEASE_BLOCKER_REMEDIATION_IMPLEMENTATION_PLAN.md` |
| 8 | **Capital Allocation V1** | P2 after V0 dual-position, observation truth closure, and additional real per-ticket outcomes | `docs/current/TRADING_QUALITY_CAPITAL_RISK_ALLOCATION_DESIGN.md` |
| 9 | **Multi-Asset Execution Kernel** | P2 after crypto live lifecycle calibration | asset-neutral Instrument/Venue/Calendar/Policy contracts |

P0-RT, P0-PC, Operation Layer capability, lifecycle safety core, first tick,
runner, recovery, Live Outcome, continuous reconciliation, and P0-LC are
deployed component baselines. P1-TFC is also a deployed component baseline, not
concurrent WIP. Real venue calibration remains **R1B**, while engineering uses
the deployed P1-OFC baseline to distinguish market absence, near misses,
coverage gaps, and replay/live mismatches without waiting idly for market
opportunity. The first 2026-07-18 production forensics invalidated the prior
claim that all 22 lanes had healthy observation coverage: 19 lanes returned HTTP
400. The deployed transport fix then exposed a deeper current blocker: 19 lanes
now return typed `NEXT-ATTEMPT-POSITION-ORDER-CONFLICT` before detector
computation because five terminal ticket-bound protection orders remain OPEN in
the core `orders` projection. No current lane may be called validated market
wait until P0 Production Runtime Full-Chain Readiness closes.

## Current Verified Progress

| Area | Current fact |
| --- | --- |
| **Live Candidate Baseline** | Tokyo runs release `19719b93d840742a76fd8f79548c720193a08989`; real exchange trades have occurred and six ticket-bound production lifecycles are terminally closed |
| **Active delivery branch** | `codex/dual-position-account-risk-remediation-v1` remains the repair branch. The deployed component head closed HTTP/compact transport failure, while new full-chain readiness design awaits Owner confirmation before implementation. |
| **Tokyo release line** | `/home/ubuntu/brc-deploy/app/current` and its release manifest are the exact deployed-head authority |
| **Deployment method** | Server-side `git fetch + git archive export`; no local upload package is required for normal deploy |
| **PG migration** | Tokyo is at migration **136** (`2026-07-17-136_add_instrument_risk_calculation_kind.py`) |
| **P0-LC deployment acceptance** | Postdeploy verification passes; backend HTTP checks, schema count, lifecycle units, and no-active lifecycle service are accepted without exchange write |
| **Backend / watcher / monitor / lifecycle** | Backend and all three timers are active; infrastructure is healthy, but watcher business observation remains blocked before detector computation on 19 selected instances |
| **Real gateway submit-boundary test** | Deployed `110e680c` includes local impact coverage proving constructed PG fresh signal can reach `real_gateway_action -> gateway.place_order(...)` boundary with controlled test-gateway stop |
| **Post-submit first tick** | Deployed release includes `brc_ticket_bound_reconciliation_ticks`, `brc_ticket_bound_scope_freezes`, first post-submit tick selection, TP1 degraded recovery, retry limit, scope freeze writes, and stop-risk reservation rechecks |
| **P0 capital-safety closure** | `381aed34` deploys current-risk scope freeze blocking, stale/no-risk freeze resolution, scheduled/recovery reconciliation ticks, Live Outcome Ledger projection, and protective stop-risk direction validation |
| **Current runtime coverage** | Five StrategyGroups and 22 candidate lanes have current healthy technical coverage; this no longer proves detector computation because 19 selected instances return typed lifecycle blockers before signal evaluation |
| **Typed Ticket boundary** | Side-aware price, normalized quantity, positive stop risk, one reservation, atomic fact-to-Ticket transaction, and six-Event-Spec production-shaped certification are deployed |
| **Current tradeability** | Market wait is not validated. The first systemic blocker is observation/action-time coupling backed by five stale core OPEN protection rows while ticket-bound lifecycle, reconciliation and post-submit closure are terminal |
| **Opportunity calibration** | All 22 scopes produced historical signals with zero invalid observations; Replay was stdout-only and created no PG/file/runtime/exchange authority |
| **Lifecycle production capability** | Typed exchange truth, fill projection, durable short-transaction commands, continuous reconciliation, settlement, finalization, terminal Outcome, account-mode bootstrap, and migration-shaped ops health are deployed |
| **Trade feedback core** | P1-TFC uses one typed lifecycle decision across production callers, rehearsal, and Owner feedback; it is deployed rather than active WIP |
| **Dynamic execution risk** | Deployed sizing uses fresh wallet/available balance, **3%** planned Stop risk, 90% margin utilization, lowest sufficient leverage, and a 10x Owner ceiling; the Owner-approved V0 target is **2.5%** per Ticket and is not active before implementation/shadow acceptance |
| **Historical Action-Time acceptance** | Five 2026-07-12 CPM Tickets and the separate ETH sizing-control signal reach protected-submit preparation plus durable ENTRY/SL/TP1 commands inside their original validity windows in isolated fixed-clock tests; all stop before exchange write |
| **Signal identity and notification truth** | Deployed `8b6cd166` conserves anonymous readiness as a lane-scoped PG process failure, removes direct watcher Feishu, and makes the Tokyo server monitor the sole typed Owner notification path; production acceptance captured `CPM-RO-001 + SOLUSDT + short` and sent one Chinese no-order card with repeated delivery suppressed by PG dedupe |
| **Runtime causal integrity certification** | All 12 bounded PostgreSQL/process scenarios pass; contradictory repeat fill truth hard-stops, newer success clears older current blockers, and terminal pre-dispatch attempts cannot leave reclaimable or misleading command truth |

## Current Next Execution Order

Action-Time Boundary Reproduction And Projection Truth is deployed and
accepted. A new different
`signal_event_id` is a P0 interrupt event: after any unprotected position or
unknown exchange outcome is handled, engineering pauses at the next committed
transaction boundary, runs natural-signal acceptance, persists the result, and
then resumes this order.

| Order | Work | Priority | Done when |
| --- | --- | --- | --- |
| 1 | **Outer Action-Time failure conservation** | P0 complete | Required-step failure persists exact lane, Ticket/source watermark, first blocker, and timing; false market wait is impossible |
| 2 | **Six-event historical pre-exchange acceptance** | P0 complete | Five Ticket cases and one sizing-control signal reach durable prepared commands without exchange write inside original validity windows |
| 3 | **Deploy certification ordering** | P0 complete | Watcher starts only after exact-head capability and current projection truth publish; mixed-generation tick race is removed |
| 4 | **Signal identity and notification truth** | P0 complete | Only named execution-eligible PG signals can produce opportunity language; materialization failures persist by lane and the server monitor owns typed deduplicated Owner notification |
| 5 | **Natural-signal interrupt acceptance** | P0 interrupt | A different-identity natural event preempts normal work and persists its live Ticket-chain outcome through the deployed refresh outcome path |
| 6 | **Runtime causal integrity certification** | P0 complete | Twelve bounded real-PostgreSQL/process scenarios pass; six demonstrated implementation defects are repaired without authority expansion; migration 120 conserves historical pre-dispatch failure truth and notification correlation preserves production identity |
| 7 | **Owner Supervision Product Integration** | P1 deployed baseline | Typed static notifications and read-only runtime forensics consume conserved PG truth without exposing internal gate vocabulary; natural-event language calibration remains event-driven |
| 8 | **Runtime Observation Truth And Forensics Remediation** | **P0 deployed component baseline** | Typed compact blockers and HTTP semantics are accepted; its observation/business-gate and core-order closure assumptions are superseded |
| 9 | **Production Runtime Full-Chain Readiness Remediation FRR-T00-T10** | **P0 proposed; awaiting Owner confirmation** | Separate observation from action-time safety, converge core/ticket lifecycle order truth, persist detector decisions, repair Goal Status/Monitor, and certify natural-signal-capable production |
| 10 | **Dual-Position Hard-Cap Account Risk Model V0** | **P1 deployed component baseline** | Migrations 134-136 remain active; exact-head regression is included in FRR-T08 |

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
| **R1D Opportunity Feedback Calibration** | Measure version-pinned opportunity supply, near misses, replay/live parity, and complete nullable real-ticket economics | R1C deployed | Six Event Specs have one typed calibration path and real Outcomes can include funding and exit slippage without authority expansion |
| **R1E Dual-Position Account Risk V0** | Allow at most two different-instrument positions under 2.5% per Ticket, 6% portfolio, 4% cluster, 90% margin and one-new-Lane boundaries | Single-Ticket lifecycle and real exchange truth are accepted | A protected first position no longer hides a valid second opportunity; ownership, capacity and release remain PG-backed and rollback-safe |
| **R2 Capital Allocation V1** | Allocate loss-capable capital across StrategyGroup sleeves, symbols, sides, clusters, open risk, and pending reservations | R1E dual-position V0 and additional real outcomes exist | Simultaneous candidates receive deterministic PG-backed allocation without changing per-ticket safety semantics |
| **R3 Multi-Asset Execution Kernel** | Add asset-neutral Instrument, Venue, TradingCalendar, MarketDataSource, ExecutionPolicy, ProtectionPolicy, and SettlementPolicy boundaries | Crypto lifecycle is stable | A new supported contract class reuses the core chain through adapters instead of copying it |
| **R4 Strategy Portfolio And Regime Routing** | Allocate observation and risk by regime, correlation, strategy role, and future option value | Multi-strategy live outcomes exist | `current_active`, `future_option`, `support_filter`, `conditional_trigger`, and `parked` roles affect budget without widening runtime authority silently |
| **R5 Autonomous Experiment Governance** | Produce versioned promote/downshift/park/kill and policy-change recommendations from outcomes | Versioned outcomes and regime evidence are mature | Recommendations are machine-generated but only PG Owner policy events can change authority |
| **R6 Owner Supervision Product** | Owner sees running, waiting, processing, protected, recovering, intervention-needed, and completed states | Backend explanation and lifecycle states are stable | Owner controls policy and capital while the system performs normal operation automatically |

The route is sequential by capability, not by calendar. **R1A, R1C, and the
engineering portion of R1D are deployed; only R1B and R1D Live parity/economics
calibration require a real event.** Later stages must not
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
| Action-time identity | PG ActionTimeInvocation, action-time lane, and Action-Time Ticket rows | resume pack or dispatch JSON identity |
| Safety | Runtime Safety State over PG/current facts | dry-run audit or closure evidence file |
| Owner explanation | backend read model over current projections | frontend or MD/JSON self-interpretation |

## Current P0 Workstreams

**P0 Action-Time Failure Conservation And Natural-Event Acceptance is
deployed.** New execution-core expansion is deliberately stopped until natural
trading feedback or a concrete safety incident arrives. P1-OFC, P0-F, P0-G,
P0-H, P0-J, and P0-LC are deployed component responsibilities, not parallel
programs.

**P0 Action-Time Invocation Consistency And Failure Truth is deployed and
read-only accepted.** Migration `119` binds one typed fresh signal, fresh
account/action facts, promotion, lane, Ticket, watcher coverage, and parent
process outcome to the same identity. No order or exchange command was created
during deployment acceptance.

**P0 Runtime Causal Integrity And Adversarial Certification is complete and
deployed.** It tests the deployed invariants on disposable PostgreSQL 16
databases and independent local processes. The 12 scenarios found two defects;
the first exact-head deployment acceptance exposed and closed a third
selector/worker ownership mismatch plus a fourth missing configuration
preflight. The program adds no second execution path, production failpoint,
schema state, or trading authority. **R1B** remains the only proof for real
venue behavior.

| Priority | Workstream | Goal | Done when |
| --- | --- | --- | --- |
| **P0-A** | **File-authority elimination** | remove production/current reads from repo MD/JSON, `output/**`, and report-dir proof files | validators reject reintroduced runtime file authority |
| **P0-B** | **PG current projection closure** | make Goal Status, Candidate Pool, Daily Table, Runtime Safety State, Action-Time Ticket, and Owner Explanation read from PG/current services | one owner projector per current projection |
| **P0-C** | **Action-time ticket path** | fresh signal opens one exact PG ActionTimeInvocation and then one explicit Action-Time Ticket before FinalGate / Operation Layer | Ticket identity contains StrategyGroup, symbol, side, profile, policy versions, invocation-bound facts, and risk scope |
| **P0-D** | **Server monitor ownership** | server-side readonly monitor classifies quiet / notify from PG/current state | no production dependency on local heartbeat or local cache |
| **P0-E** | **Performance and retention** | no-signal ticks stay quiet and bounded in disk / CPU / PG rows | report growth and restart storms are structurally prevented |
| **P0-F** | **Ticket-bound lifecycle hardening** | post-submit lifecycle state machine, runner mutation, protection reconciliation, and failure recovery remain one safety core | every submitted ticket reaches protected/closed state or one exact lifecycle hard blocker |
| **P0-G** | **Post-submit first tick and recovery command determinism** | immediate exchange-truth first tick and one recovery command or hard stop for every unsafe lifecycle blocker | every real protected submit result reaches matched/protected, pending visibility, deterministic recovery command, or exact hard stop |
| **P0-H** | **Live outcome ledger** | real tickets become structured result and learning rows | every real ticket has one outcome row or one exact hard-blocked outcome |
| **P0-I** | **Scope freeze pre-submit gate** | active lifecycle/reconciliation freeze blocks the same StrategyGroup + symbol + side before another submit path can form | promotion, lane, ticket, Runtime Safety State, FinalGate preflight, and protected submit all reject frozen scopes |
| **P0-J** | **Continuous reconciliation tick** | keep exchange-truth reconciliation alive after the first tick | lifecycle reaches closure, exact recovery command, or hard stop without recurring report files |
| **P0-K** | **Real Signal -> Ticket closure** | make production action-time pricing, sizing, stop-risk reservation, and Ticket creation one coherent typed chain | every eligible real-submit lane either creates one Ticket inside freshness bounds or stops at one producer-owned blocker before lane readiness |
| **P0-L** | **Production-shaped certification** | prevent complete downstream dictionaries from hiding missing production handoffs | all six Event Specs pass raw-source-to-Ticket certification and projection consistency checks without exchange write |
| **P0-M** | **Runtime causal integrity certification** | prove transaction, process-death, retry, concurrency, lifecycle, and projection invariants at production-shaped boundaries | 12 bounded PostgreSQL/process scenarios pass; findings are fixed or explicitly retained as live-only |
| **P1-N** | **Real-trade fact truth and venue lineage** | conserve exact conditional parent/actual order identity, fill role, fees, funding availability, PnL, and terminal Ticket state | every closed real Ticket has one internally consistent lifecycle and Outcome projection; unchanged reconciliation creates no duplicate business event |

**P1-N Release certification and Tokyo production acceptance are complete.**
All three real Tickets are terminal and internally consistent; exact
conditional parent/actual-child lineage is preserved for SL fills, and an
unchanged maintenance pass returns no maintainable lifecycle with zero exchange
write. The implementation does not
change strategy semantics, sizing, leverage, risk policy, runtime profile,
FinalGate, Operation Layer, or exchange-write authority.

## Active Runtime Loop

```text
StrategyGroup candidate scope
-> watcher coverage
-> public/account/action-time facts
-> fresh live signal
-> ActionTimeInvocation
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
