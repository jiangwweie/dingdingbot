---
title: MAIN_CONTROL_ROADMAP
status: CURRENT
authority: docs/current/MAIN_CONTROL_ROADMAP.md
last_verified: 2026-07-11
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
| 1 | **P0-LC Production Lifecycle Wiring And Continuous Reconciliation** | **active P0 mainline** | `docs/current/P0_LIFECYCLE_PRODUCTION_CERTIFICATION_AND_CLOSURE_DESIGN.md`, `docs/current/P0_LIFECYCLE_PRODUCTION_CERTIFICATION_IMPLEMENTATION_PLAN.md` |
| 2 | **Owner Explanation Read Model** | P1 after lifecycle truth stabilizes | `docs/current/OWNER_EXPLANATION_READ_MODEL_CONTRACT.md` |
| 3 | **Capital Allocation V1** | P1 after reliable per-ticket stop risk and outcomes | `docs/current/TRADING_QUALITY_CAPITAL_RISK_ALLOCATION_DESIGN.md` |
| 4 | **Multi-Asset Execution Kernel** | P2 after crypto lifecycle certification | asset-neutral Instrument/Venue/Calendar/Policy contracts |
| 5 | **Advanced Portfolio And Regime Allocation** | P2 after multi-strategy live outcomes | `docs/current/TRADING_QUALITY_CAPITAL_RISK_ALLOCATION_DESIGN.md` |

P0-RT, P0-PC, Operation Layer capability, lifecycle safety core, first tick,
runner, recovery, Live Outcome, and continuous reconciliation remain component
baselines. Their unfinished production integration is absorbed into **P0-LC**;
they are not separate concurrent WIP programs.

## Current Verified Progress

| Area | Current fact |
| --- | --- |
| **Focused delivery branch** | `codex/p0-lifecycle-production-certification`; Tokyo remains on the prior real-signal-to-Ticket release until P0-LC acceptance |
| **Tokyo release line** | `/home/ubuntu/brc-deploy/app/current` currently points to release `5f40c62d`, migration `112` |
| **Deployment method** | Server-side `git fetch + git archive export`; no local upload package is required for normal deploy |
| **PG migration** | Tokyo is at migration `112` (`2026-07-10-112_version_live_signal_identity.py`) |
| **Current branch verification** | P0-LC local targeted lifecycle/pre-trade/ops suites and producer-shaped 22-scope closure coverage pass; full-suite verification and Tokyo cutover remain pre-completion gates |
| **Backend / watcher / monitor** | Backend and both timers are active; watcher and monitor oneshot services complete with `Result=success` outside signal-time blocked runs |
| **Real gateway submit-boundary test** | Deployed `110e680c` includes local impact coverage proving constructed PG fresh signal can reach `real_gateway_action -> gateway.place_order(...)` boundary with controlled test-gateway stop |
| **Post-submit first tick** | Deployed release includes `brc_ticket_bound_reconciliation_ticks`, `brc_ticket_bound_scope_freezes`, first post-submit tick selection, TP1 degraded recovery, retry limit, scope freeze writes, and stop-risk reservation rechecks |
| **P0 capital-safety closure** | `381aed34` deploys current-risk scope freeze blocking, stale/no-risk freeze resolution, scheduled/recovery reconciliation ticks, Live Outcome Ledger projection, and protective stop-risk direction validation |
| **Current runtime coverage** | Five StrategyGroups, 22 candidate scopes, and six current v2 Event Specs have current watcher coverage and execution-eligibility declarations |
| **Typed Ticket boundary** | Side-aware price, normalized quantity, positive stop risk, one reservation, atomic fact-to-Ticket transaction, and six-Event-Spec production-shaped certification are implemented on the focused branch |
| **Latest current-truth finding** | 20/22 scopes show `market_wait_validated`; CPM/SUI and MPG/SUI are still overridden by event-scoped historical Action-Time outcomes whose source identities have expired |
| **Temporal truth correction** | Deployed `5f40c62d` preserves signal identity and parent blocker truth; P0-LC Batch 0 adds the missing current-relevance rule so historical process results cannot become permanent blockers |
| **Lifecycle production audit** | Tokyo timer has only exercised `no_maintainable_lifecycle`; the focused branch now closes typed identity, conditional views, fill projection, short command transactions, continuous reconciliation, settlement, finalization, and Outcome locally, pending two-phase production cutover |

## Current Next Execution Order

This is the current remaining order for **P0-LC**. A new different
`signal_event_id` is a P0 interrupt event: after any unprotected position or
unknown exchange outcome is handled, engineering pauses at the next committed
transaction boundary, runs natural-signal acceptance, persists the result, and
then resumes this order.

| Order | Work | Priority | Done when |
| --- | --- | --- | --- |
| 1 | **Current process-outcome relevance** | P0 | Expired identities remain inspectable but Candidate Pool, Daily Table, Goal Status, Tradeability, and Monitor agree on current market wait; Signal B cannot inherit Signal A blocker |
| 2 | **Typed exchange truth and netting-aware ownership** | P0 | PG instrument mapping drives venue symbol; conditional orders, side-scoped positions, and shared net-position conflicts are classified correctly |
| 3 | **Exchange fill projection and monotonic lifecycle** | P0 | ENTRY/TP1/SL/RUNNER_SL fills update PG without fixture-only transitions or repeated-tick regression |
| 4 | **One durable command authority and short transactions** | P0 | Existing exchange-command rows own place/cancel effects; timeout/termination is reconciled before retry; network I/O is outside long PG transactions |
| 5 | **Settlement, review, closure, and terminal Live Outcome** | P0 | Independent settlement evidence and validated review close the lifecycle before one terminal Outcome is created |
| 6 | **Pre-live rehearsal certification and Tokyo acceptance** | P0 | Six Event Specs / 22 test scopes pass isolated producer-to-lifecycle certification; postdeploy proves units, PG schema, zero-effect no-active tick, and ops health without synthetic production rows |
| 7 | **Owner Explanation and frontend integration** | P1/P2 | Owner sees waiting, processing, blocked, protected, recovered, and closed states without decoding internal chain objects |
| 8 | **Capital allocation V1 then advanced allocation** | P1/P2 | Allocation starts from reliable per-ticket stop risk and outcomes, then adds sleeves, clusters, cooldown, and drawdown |

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
| **R2 Capital Allocation V1** | Allocate loss-capable capital across StrategyGroup sleeves, symbols, sides, clusters, open risk, and pending reservations | Reliable per-ticket stop risk and live outcomes exist | Simultaneous candidates receive deterministic PG-backed allocation without changing per-ticket safety semantics |
| **R3 Multi-Asset Execution Kernel** | Add asset-neutral Instrument, Venue, TradingCalendar, MarketDataSource, ExecutionPolicy, ProtectionPolicy, and SettlementPolicy boundaries | Crypto lifecycle is stable | A new supported contract class reuses the core chain through adapters instead of copying it |
| **R4 Strategy Portfolio And Regime Routing** | Allocate observation and risk by regime, correlation, strategy role, and future option value | Multi-strategy live outcomes exist | `current_active`, `future_option`, `support_filter`, `conditional_trigger`, and `parked` roles affect budget without widening runtime authority silently |
| **R5 Autonomous Experiment Governance** | Produce versioned promote/downshift/park/kill and policy-change recommendations from outcomes | Versioned outcomes and regime evidence are mature | Recommendations are machine-generated but only PG Owner policy events can change authority |
| **R6 Owner Supervision Product** | Owner sees running, waiting, processing, protected, recovering, intervention-needed, and completed states | Backend explanation and lifecycle states are stable | Owner controls policy and capital while the system performs normal operation automatically |

The route is sequential by capability, not by calendar. **R1A continues without
market opportunity; only R1B requires a real event.** Later stages must not
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

**P0-LC is the only active medium-scale integration program.** P0-F, P0-G,
P0-H, and P0-J below are retained component responsibilities, not parallel
programs.

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
-> the next real submitted ticket automatically enters the same wired lifecycle for live calibration
-> Risk Reservation v0 records stop-risk before FinalGate-ready state
-> Owner Explanation can explain why no trade, why blocked, or what happened after submit
-> old MD/JSON proof-chain readers are deleted or archive-only
-> validators prevent regression
```
