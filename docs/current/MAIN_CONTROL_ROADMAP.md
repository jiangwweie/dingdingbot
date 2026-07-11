---
title: MAIN_CONTROL_ROADMAP
status: CURRENT
authority: docs/current/MAIN_CONTROL_ROADMAP.md
last_verified: 2026-07-11
---

# Main Control Roadmap

## Purpose

This roadmap is the current planning surface for the **StrategyGroup
pre-trade runtime**.

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

| Order | Program | Priority | Primary design surface |
| --- | --- | --- | --- |
| 1 | **P0-RT Real Signal -> Ticket Closure** | P0 | `docs/current/MAINLINE_ENGINEERING_PROGRAM_PLAN.md` |
| 2 | **P0-PC Production-Shaped Chain Certification** | P0 | `docs/current/MAINLINE_ENGINEERING_PROGRAM_PLAN.md` and `docs/current/PRE_TRADE_RUNTIME_CONTRACT.md` |
| 3 | **Operation Layer / Exchange Capability Boundary** | P0 | `docs/current/TICKET_BOUND_LIFECYCLE_SAFETY_CORE_IMPLEMENTATION_PLAN.md` |
| 4 | **Ticket-Bound Lifecycle Safety Core** | P0 | `docs/current/TICKET_BOUND_LIFECYCLE_SAFETY_CORE_IMPLEMENTATION_PLAN.md` |
| 5 | **Full Chain Simulation Harness** | P0 | `docs/current/PRE_TRADE_RUNTIME_CONTRACT.md` and `docs/current/TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md` |
| 6 | **Official Runner SL Mutation + Protection Reconciler** | P0 | `docs/current/TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md` |
| 7 | **Post-Submit First Tick + Recovery Command Matrix** | P0 | `docs/current/POST_SUBMIT_RECONCILIATION_AND_RECOVERY_COMMAND_DESIGN.md` |
| 8 | **P0 Capital Safety Closure** | P0 | `docs/current/P0_CAPITAL_SAFETY_CLOSURE_DESIGN.md` |
| 9 | **Live Outcome Ledger** | P0/P1 | `docs/current/LIVE_OUTCOME_LEDGER_CONTRACT.md` |
| 10 | **Continuous Reconciliation Tick** | P0/P1 | `docs/current/P0_CAPITAL_SAFETY_CLOSURE_DESIGN.md` |
| 11 | **Risk Reservation v0** | P1 | `docs/current/TRADING_QUALITY_CAPITAL_RISK_ALLOCATION_DESIGN.md` |
| 12 | **Owner Explanation Read Model** | P1 | `docs/current/OWNER_EXPLANATION_READ_MODEL_CONTRACT.md` |
| 13 | **Performance And Retention Control** | P1 | `docs/current/PRODUCTION_RUNTIME_FILE_IO_ELIMINATION_DESIGN.md` |
| 14 | **Frontend Read Model Integration** | P2 | frontend read-model contracts |
| 15 | **Advanced Capital Risk Allocation** | P2 | `docs/current/TRADING_QUALITY_CAPITAL_RISK_ALLOCATION_DESIGN.md` |

## Current Verified Progress

| Area | Current fact |
| --- | --- |
| **Focused delivery branch** | `codex/p0-real-signal-ticket-closure`; exact Tokyo release head is recorded by `.brc-release-manifest.json` |
| **Tokyo release line** | `/home/ubuntu/brc-deploy/app/current` follows the focused real-signal-to-Ticket release line |
| **Deployment method** | Server-side `git fetch + git archive export`; no local upload package is required for normal deploy |
| **PG migration** | Tokyo is at migration `112` (`2026-07-10-112_version_live_signal_identity.py`) |
| **Current branch verification** | Full local suite passes with `2720 passed, 1 skipped`; production file-I/O audit remains a mandatory deploy gate |
| **Backend / watcher / monitor** | Backend and both timers are active; watcher and monitor oneshot services complete with `Result=success` outside signal-time blocked runs |
| **Real gateway submit-boundary test** | Deployed `110e680c` includes local impact coverage proving constructed PG fresh signal can reach `real_gateway_action -> gateway.place_order(...)` boundary with controlled test-gateway stop |
| **Post-submit first tick** | Deployed release includes `brc_ticket_bound_reconciliation_ticks`, `brc_ticket_bound_scope_freezes`, first post-submit tick selection, TP1 degraded recovery, retry limit, scope freeze writes, and stop-risk reservation rechecks |
| **P0 capital-safety closure** | `381aed34` deploys current-risk scope freeze blocking, stale/no-risk freeze resolution, scheduled/recovery reconciliation ticks, Live Outcome Ledger projection, and protective stop-risk direction validation |
| **Current runtime coverage** | Five StrategyGroups, 22 candidate scopes, and six current v2 Event Specs have current watcher coverage and execution-eligibility declarations |
| **Typed Ticket boundary** | Side-aware price, normalized quantity, positive stop risk, one reservation, atomic fact-to-Ticket transaction, and six-Event-Spec production-shaped certification are implemented on the focused branch |
| **Latest production acceptance finding** | CPM/SUI and MPG/SUI exposed two same-candle terminal identities; no new lane or Ticket was created, but per-candidate aggregation incorrectly wrote successful process outcomes instead of the parent terminal blocker |
| **Temporal truth correction** | Duplicate signal identity preserves the first event row, and a failed parent promotion forces every affected lane outcome to remain blocked; this closes the false `processing` projection without reopening terminal identities |

## Current Next Execution Order

This is the current remaining order for the focused real-signal-to-Ticket
release line.

| Order | Work | Priority | Done when |
| --- | --- | --- | --- |
| 1 | **Temporal truth postdeploy acceptance** | P0 | Same-candle duplicate input remains immutable, parent blockers remain visible per lane, services are healthy, and no exchange write occurs |
| 2 | **Production lifecycle wiring and continuous reconciliation** | P0 | Continue non-market-dependent engineering through protection, deterministic recovery, settlement, and review |
| 3 | **Next distinct natural signal acceptance** | P0 | A new eligible `signal_event_id` creates Ticket and Runtime Safety State or exposes one genuine current blocker; it preempts lower work when it appears |
| 4 | **Live Outcome Ledger validation** | P0/P1 | Every future real ticket has one structured outcome row or one exact hard-blocked outcome row |
| 5 | **Owner Explanation and frontend integration** | P1/P2 | Owner sees waiting, processing, blocked, protected, recovered, and closed states without decoding internal chain objects |
| 6 | **Capital allocation V1 then advanced allocation** | P1/P2 | Allocation starts from reliable per-ticket stop risk and outcomes, then adds sleeves, clusters, cooldown, and drawdown |

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
| **Deploy acceptance** | Postdeploy validation runs one non-exchange-write production-shaped certification and verifies PG lineage; service health alone is insufficient |
| **Temporal identity** | Repeating the same closed-candle event cannot mutate first fact lineage, authority fields, observed time, expiry, or terminal state |
| **Outcome conservation** | Parent business/retryable/hard failure cannot be downgraded by child candidate rows; each affected lane preserves the parent blocker |

## Long-Horizon Development Route

The product target is a **small-capital, bounded-aggressive, multi-asset
right-tail experiment operating system**, not a general institutional quant
platform.

| Stage | Capability | Entry condition | Exit condition |
| --- | --- | --- | --- |
| **R0 Real Signal -> Ticket** | Close pricing, sizing, risk reservation, Ticket, Runtime Safety State, and pre-submit handoff for all current Event Specs | Current stage | Six Event Specs pass production-shaped certification and the next eligible natural signal no longer stops at Ticket materialization |
| **R1 Live Lifecycle Calibration** | Observe real fill, slippage, partial fill, protection acceptance, TP1, runner, final exit, reconciliation, settlement, and Live Outcome Ledger | R0 closed | Every real ticket reaches structured closure or one exact hard blocker |
| **R2 Capital Allocation V1** | Allocate loss-capable capital across StrategyGroup sleeves, symbols, sides, clusters, open risk, and pending reservations | Reliable per-ticket stop risk and live outcomes exist | Simultaneous candidates receive deterministic PG-backed allocation without changing per-ticket safety semantics |
| **R3 Multi-Asset Execution Kernel** | Add asset-neutral Instrument, Venue, TradingCalendar, MarketDataSource, ExecutionPolicy, ProtectionPolicy, and SettlementPolicy boundaries | Crypto lifecycle is stable | A new supported contract class reuses the core chain through adapters instead of copying it |
| **R4 Strategy Portfolio And Regime Routing** | Allocate observation and risk by regime, correlation, strategy role, and future option value | Multi-strategy live outcomes exist | `current_active`, `future_option`, `support_filter`, `conditional_trigger`, and `parked` roles affect budget without widening runtime authority silently |
| **R5 Autonomous Experiment Governance** | Produce versioned promote/downshift/park/kill and policy-change recommendations from outcomes | Versioned outcomes and regime evidence are mature | Recommendations are machine-generated but only PG Owner policy events can change authority |
| **R6 Owner Supervision Product** | Owner sees running, waiting, processing, protected, recovering, intervention-needed, and completed states | Backend explanation and lifecycle states are stable | Owner controls policy and capital while the system performs normal operation automatically |

The route is sequential by capability, not by calendar. R1-R6 must not become
active WIP before R0 exits its stop condition, but R0 abstractions must remain
asset-neutral enough that R3 does not require a second execution chain.

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
-> all six current Event Specs pass production-shaped producer-to-consumer certification
-> fresh signal creates PG promotion / lane / ticket rows
-> Action-Time Ticket can continue through lifecycle-safe protected submit
-> TP1 / runner / final-exit lifecycle states are reconciled against exchange truth
-> real submitted tickets produce Live Outcome Ledger rows
-> Risk Reservation v0 records stop-risk before FinalGate-ready state
-> Owner Explanation can explain why no trade, why blocked, or what happened after submit
-> old MD/JSON proof-chain readers are deleted or archive-only
-> validators prevent regression
```
