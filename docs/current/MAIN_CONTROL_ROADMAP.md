---
title: MAIN_CONTROL_ROADMAP
status: CURRENT
authority: docs/current/MAIN_CONTROL_ROADMAP.md
last_verified: 2026-07-01
---

# Main Control Roadmap

## Current State-Model Note

`Signal Observation grade` in older roadmap checkpoints is a historical progress label and now maps
to Signal Observation grade. It is not a lifecycle layer, not a packet family,
and not a source of can-trade or live-submit authority. New roadmap work must
flow through Strategy Asset State, Tradeability Decision, Runtime Safety State,
Execution Attempt, and Review Outcome State.

## Purpose

This is the short planning table for the main runtime window.

For source authority, follow
`docs/current/PROJECT_INFORMATION_ARCHITECTURE.md`. This roadmap describes
stage direction and checkpoints. It must not override current code, machine
config, verified runtime state, explicit Owner policy, or generated evidence
from the current monitor sequence.

The main goal is still the StrategyGroup runtime pilot, but the global project
objective is profitability through a small-capital right-tail experimentation
system:

```text
Owner enables a StrategyGroup.
The system observes, checks, executes inside official boundaries, protects,
reconciles, settles, records, and reports Owner-readable state.
```

The first-stage acceptance target is narrower and more operational:

```text
Complete the first selected StrategyGroup + allocated subaccount risk budget
bounded-aggressive real-order loop when a fresh signal exists and all official
runtime gates pass.
```

Dry-run audit and source readiness are support tracks for that target. Static
product-client work is externalized and is no longer part of the main runtime goal.

This file is not a product-client design spec or historical packet index. It is
also not a generic research backlog: research, replay, paper/simulator, and
cost-model work are included only when they remove or precisely classify a Live
Enablement blocker, help the system capture current/future opportunities through
the official runtime path, preserve net edge after execution costs, and feed
review decisions.

Strategy quality is evaluated by
`docs/current/STRATEGY_EXPERIMENT_EVALUATION_CONTRACT.md`. The roadmap must not
turn `100%` or any other high-return number into a hard intake gate, and it must
not treat `5x` or any other leverage scenario as an automatic rejection or
authorization. The current standard is experiment value: clear thesis, known
failure modes, bounded loss envelope, replay/paper evidence, and final
main-control absorbability.

Strategy tradeability is evaluated by
`docs/current/TRADEABILITY_DECISION_CONTRACT.md`. The roadmap must not let
candidate strategies sit indefinitely in reports, artifacts, or generic
`waiting_for_market`. Each active candidate should move toward one of two
answers:

```text
can trade through the official path
or
cannot trade because first blocker X remains
```

Blocker naming is governed by
`docs/current/BLOCKER_CLASSIFICATION_CONTRACT.md`. The current planning phase is
Pre-Trade Runtime V0: maintain five active StrategyGroups with bounded
candidate symbol sets, classify per-symbol readiness blockers, promote fresh
satisfied candidates without authority leakage, and narrow at most one
candidate into action-time lane input before the official path.

Pre-trade runtime is governed by `docs/current/PRE_TRADE_RUNTIME_CONTRACT.md`.
Daily management is governed by
`docs/current/MAIN_CONTROL_DAILY_LIVE_ENABLEMENT_TABLE_CONTRACT.md`. Active work
limits and seven-day stop rules are governed by
`docs/current/WIP_AND_STOP_RULE_CONTRACT.md`.

P0 now targets the multi-StrategyGroup, multi-symbol pre-trade runtime needed to
avoid missing opportunities while preserving the single-intent submit boundary.
Signal Observation grade work must now turn market observations into
machine-checkable per-symbol readiness and promotion decisions:

```text
active StrategyGroup candidate symbol set
-> per-symbol detector / watcher / facts / scope / risk readiness
-> fresh-signal promotion candidate
-> action-time lane input only after scope and facts allow it
-> candidate/auth, FinalGate, Operation Layer only for one explicit intent
```

## Current Execution Constraints

The next phase is governed by eight execution constraints:

| Constraint | Meaning |
| --- | --- |
| P0 preemption | Any real fresh satisfied candidate in the active pre-trade runtime may interrupt lower-priority work, then must narrow through promotion and action-time checks |
| Authority split | Owner controls policy and tier/risk scope; the system continues normal process execution inside selected boundaries |
| Capability closure | Every goal-mode task must close one engineering problem class, unlock a concrete capability, and expose the next engineering bottleneck |
| Capability status split | Reports must label work as `deployed`, `local`, `planned`, `blocked`, or `market-dependent` |
| Strategy Asset State evidence gate | New Signal Observation grade artifacts must move a lane forward, prove a precise blocker, or change `go_live`, `do_not_go_live`, `keep_observing`, `revise`, `park`, `kill`, `promote`, or `block_for_safety` |
| No authority leakage | Replay, proxy facts, opportunity ledger rows, and observe-only decisions never authorize FinalGate, Operation Layer, exchange write, or real orders |
| Deploy only at milestones | Bounded deploy apply is reserved for a closed local checkpoint, fresh-signal unblock, safety repair, or explicit Owner request |
| Entry-point compression | New scripts are temporary unless they feed the standard Tokyo server-side monitor, development diagnostic monitor, replay, or Strategy Asset State evidence surfaces and replace or reduce older entry points |

Production recurring monitoring is moving to the server-side ownership model in
`docs/current/SERVER_SIDE_RUNTIME_MONITOR_CONTRACT.md`: Tokyo server-side
readonly timer plus Feishu notification is the production path.

The deploy-worthy checkpoint for the current Pre-Trade Runtime V0 phase is:

```text
five active StrategyGroups
-> multiple candidate symbols per StrategyGroup
-> blocker matrix per symbol / per fact
-> fresh-signal promotion rules
-> at most one action-time lane input
-> daily table summary updated
-> stop condition named
-> server-side monitor status
-> local diagnostic snapshot only when needed for development verification
-> targeted tests pass
```

## Profitability-Oriented Operating Frame

The final business target is profit. The current engineering acceptance target
is not "prove profit now"; it is to build repeatable capability for:

```text
find opportunity
-> validate signal/facts/risk
-> capture through official runtime path
-> protect and reconcile
-> measure cost and outcome
-> promote, revise, park, or kill the StrategyGroup
```

Use this frame to prevent drift:

| Layer | Purpose | Current project meaning |
| --- | --- | --- |
| Strategy Edge | Find regime-specific right-tail opportunities | Strategy research and handoff packs propose candidate edges for final-owned admission |
| Runtime Capture | Turn current/future fresh signals into official bounded actions | Detector, watcher, RequiredFacts, candidate/auth, FinalGate, Operation Layer |
| Execution Quality | Preserve net edge after market friction | Fee, funding, slippage, filters, partial fill, retry and error taxonomy |
| Risk Capital | Use Owner-allocated loss-capable subaccount capital aggressively inside explicit boundaries | Probe, trial, promotion, parked, and kill capital states |
| Learning Loop | Convert outcomes into better decisions | Review ledger, negative evidence, promote/revise/park/kill |

The learning loop now has two main records:

| Ledger | Stage | Purpose |
| --- | --- | --- |
| Strategy Asset State pre-live evidence | Before live submit | Preserve keep, revise, promote, park, kill, go live, do not go live, or safety-block evidence from high-priority observations |
| Review Ledger | After live action | Learn from entry, exit, protection, costs, PnL, reconciliation, and final review |

Engineering work is mainline only when it improves one of those layers by
removing a blocker, proving `market_wait_validated`, or creating a scoped
live-enable proposal. Extra evidence fields, broad product-client work,
historical cleanup, read-only scope expansion, or strategy expansion are not
mainline unless they directly support this profitability-oriented loop.

## Tradeability-Oriented Operating Frame

The main-control runtime should prefer tradeability language over artifact
completion language:

```text
strategy exists
-> admitted or not admitted
-> scoped or not scoped
-> armed or not armed
-> facts ready or not ready
-> action-time gates pass or fail
-> trade or explain first blocker
```

The standard current-state question is:

```text
Can this StrategyGroup trade now?
If not, what is the first blocker, who owns it, and what action removes it?
```

| Blocker class | Mainline meaning | Default next action |
| --- | --- | --- |
| `asset_admission` | Candidate is not a final-owned trial/runtime asset | Build or reject trial asset admission proposal |
| `owner_policy_required` | Capital, profile, symbol/side, leverage scenario, attempt cap, loss unit, or tier decision is missing | Ask for scoped Owner policy only |
| `market_wait_validated` | Admission, scope, policy, detector, watcher input, facts, classification, and action-time path are closed; only current fresh signal is absent | Keep observing and preempt lower work on fresh signal |
| `computed_not_satisfied` | Detector and watcher ran, but strategy facts are false/stale/below threshold | Keep observing; preserve failing fact matrix |
| `detector_not_attached` / `watcher_tick_missing` | Live/current detector or current watcher input is absent | Attach detector or repair watcher/public facts source |
| `scope_not_attached` | Strategy/symbol/side/timeframe is not attached to selected runtime observation or live-scope proposal | Produce scoped proposal or explicit deferral |
| `replay_live_rule_mismatch` | Replay and current live detector/fact rules do not match | Normalize rules or produce a strategy revision decision |
| `action_time_boundary_not_reproduced` | Live-like event cannot reach candidate/auth or action-time rehearsal | Repair non-executing action-time path |
| `execution_gate_gap` | Runtime, protection, account, exchange, order, position, or Operation Layer path blocks submit | Repair runtime gate or recovery branch |
| `strategy_quality_gap` | Strategy is not experiment-worthy or risk cannot be bounded | Revise, park, or kill |
| `hard_safety_stop` | Action violates a hard boundary | Stop and surface safety state |

For a candidate such as `BRF2-001`, the initial main-control target is not
direct live authority. The correct target is:

```text
tiny_live_intake_candidate
-> trial_asset_admission_candidate
-> admitted_trial_asset
-> armed_observation
-> tiny_live_ready
-> future live_submit_ready only after fresh signal and official gates
```

This keeps short-side experiments from being rejected by over-conservative
evaluation while still preventing research evidence from becoming order
authority.

## Strategy Experiment Evaluation Frame

Strategy research and main-control intake should use an experiment-value frame,
not a fixed return-qualification frame.

| Concept | Current meaning | Must not mean |
| --- | --- | --- |
| `100%` or similar target | Right-tail aspiration anchor and priority signal | Mandatory pass/fail intake threshold |
| `5x` or similar leverage | Scenario for liquidation, path-risk, and loss-envelope review | Automatic live authorization or automatic disqualification |
| `tiny_live_intake_candidate` | Main control may ingest the asset for small-capital experimental review | Tiny-live ready, actionable now, or exchange-write authority |
| `path_risk_known` | Stop-hit and adverse-path risks are measured and reviewable | Path is safe |
| `risk_envelope_defined` | Attempt cap, loss cap, pause rule, or review boundary exists | Risk is eliminated |

The preferred advancement question is:

```text
Is this strategy experiment-worthy, bounded, replayable, observable, and
absorbable by main control?
```

The rejected advancement question is:

```text
Did this strategy prove a fixed 100% return under an arbitrary leverage cap?
```

## Bounded-Aggressive Risk Frame

The Owner-funded subaccount allocation is already the upstream risk-control
decision. The runtime system should not re-risk-assess that allocation into a
smaller, slower, or lower-leverage trade merely because right-tail strategies
are risky. The project is constrained, but aggressive inside those constraints.

| Boundary type | Meaning | Mainline behavior |
| --- | --- | --- |
| Owner capital boundary | The subaccount amount is loss-capable experiment capital | Use the selected allocation/profile instead of applying hidden haircuts |
| StrategyGroup boundary | Only selected StrategyGroups, symbols, sides, and profiles are eligible | Block out-of-scope actions, but do not de-risk in-scope ones |
| Execution authority boundary | FinalGate and Operation Layer remain mandatory | Prevent wrong execution path, not opportunity capture |
| Mechanical safety boundary | No stale facts, duplicate submits, missing protection, conflicting active position/open order, withdrawal, transfer, credential mutation, or unauthorized profile/sizing mutation | Fail closed only for these concrete conditions |

Do not use risk language as a generic reason to delay, reduce, or avoid an
otherwise eligible live action. Missing a valid right-tail opportunity is a
project failure mode.

## Engineering Progression Rule

Goal-mode work must progress by engineering bottleneck, not by report count:

```text
close one engineering problem
-> unlock one system capability
-> reveal the next engineering problem
```

This rule prevents `waiting_for_market`, `fresh_signal_absent`,
`live_detector_artifact_missing`, or `needs_real_trade` from becoming blanket
answers. Only real fresh signal, action-time live facts, exchange acceptance,
and real outcome calibration are truly market/live dependent. Even then, they
block only real submit or live calibration; they do not block detector
attachment, watcher integration, per-symbol / per-fact classification,
non-executing rehearsal, simulation, lifecycle modeling, or review-shape work.

Small-capital execution frictions are not reasons to stop the engineering lane:

| Friction | Default engineering treatment |
| --- | --- |
| Fill probability | Try through official small-capital path after gates pass; handle timeout/reject |
| Slippage | Use coarse spread/fee/funding buffer, then calibrate from live outcomes |
| Protection acceptance | Pre-check exchange rules and implement failure recovery/hard stop |
| Partial fill | Model lifecycle state and follow-up protection/reconciliation |
| Reject recovery | Classify reject, stop or retry inside official boundary, then review |
| PnL settlement | Estimate before action, reconcile after fills, record Review Ledger outcome |

Every Goal Packet should state `Capability unlocked` and
`Next engineering bottleneck`. If it only produces an artifact or explains why
progress is blocked, the architecture outcome should be `partial` unless the
Evidence Packet proves no engineering closure is currently possible.

### Rehearsal-Before-Live Policy

The main runtime window should exhaust non-executing closure before declaring a
live dependency:

| Engineering branch | Must be closable before live | Live dependency that remains |
| --- | --- | --- |
| Submit accepted/rejected | Yes, by paper/simulator Operation Layer and lifecycle tests | Actual exchange response calibration |
| Partial fill | Yes, by simulated fill branches | Actual partial-fill distribution |
| Protection accepted/failed | Yes, by rule precheck, failure branch, and hard-stop path | Actual protection acceptance at exchange |
| Slippage/fees/funding | Yes, by coarse buffer and cost model | Actual fill and funding calibration |
| PnL/reconciliation/settlement | Yes, by local estimate and reconciliation shape | Actual account settlement |

Live facts and live outcomes are validation layers, not the first engineering
closure path. A gate may say `live_submit blocked`; it must not say
`engineering blocked` when dry-run, simulator, replay, local lifecycle, or
review-shape work remains available.

Owner upgrade/downshift authority is strategy governance, not manual operation.
If a StrategyGroup is risky but still within scoped policy, the system should
continue the engineering path toward the appropriate tier. Escalate only when
the decision changes policy, tier, capital/profile/scope, pause/resume,
promote/downshift/park/kill, production transition, or abnormal intervention.

Goal-mode work after research intake should therefore be framed as reducing the
first tradeability blocker, not merely adding another projection or report. A task
that moves `not_tradable_asset_admission` to `not_tradable_policy`, or
`not_tradable_policy` to `not_tradable_market_wait`, has advanced the system
even if no live order exists yet.

## No-Signal Progress Policy

Healthy `market_wait_validated` is not a project blocker. It means the real
market has not supplied an eligible fresh signal after all non-market lane
blockers are closed. During no-signal periods, the main runtime window should
advance non-market-dependent proof lanes without touching real funds:

| Lane | Purpose | Boundary |
| --- | --- | --- |
| Signal Coverage Diagnostic | Compare selected mainline runtime observation with broader read-only candidates to identify scope_not_attached or computed_not_satisfied lanes | Local/read-only diagnostic only; broader would-enter signals do not authorize real submit |
| Replay Lab | Re-run historical market or signal windows through current runtime behavior to calibrate rules for future live capture | Does not create real orders or pretend historical signals are live |
| Synthetic Signal Factory | Generate fresh/stale/wrong-scope/missing-fact/conflict fixtures | Never feeds synthetic signals into real Operation Layer submit |
| Paper/Simulator Operation Layer | Exercise order lifecycle branches without real funds | Uses non-live simulation only; testnet is not a mainline value layer |
| Post-Submit Simulator | Exercise fill, partial fill, reject, protection failure, recovery, reconcile and settle branches | Non-executing simulation only |
| Cost/Slippage/Funding Model | Estimate whether strategy gross edge can survive friction | Research/review input, not submit authority |
| Allocated-Subaccount Real Loop | Validate real exchange friction, protection, reconciliation, and settlement with allocated subaccount experiment funds | Uses the official live path only after selected StrategyGroup, allocated subaccount risk budget, fresh signal, RequiredFacts, candidate/auth, FinalGate, and Operation Layer pass |

The no-signal lanes exist to reduce the chance that a current/future market
opportunity arrives before the runtime chain, execution shape, or review loop
is ready.

## 2026-07-01 Planning Correction: Live Enablement Blocker Closure

This checkpoint narrows the near-term plan around the current generated
runtime evidence. The generated views remain checkpoint evidence only; they do
not override code, machine config, runtime state, or Owner policy. The planning
change is that no-signal work must now remove or precisely classify
Live Enablement blockers before adding more portfolio, projection, packet, or
readiness surfaces.

Current evidence:

| Evidence | Current checkpoint | Planning meaning |
| --- | --- | --- |
| Tradeability Decision | `13` rows, `tradable_now=0` in `output/runtime-monitor/latest-strategygroup-tradeability-decision.*` | The project still needs one current first blocker per StrategyGroup rather than broad `waiting_for_market` compression |
| Replay Live Parity Audit | `131` replay signals, `14` live-detector reproductions, `117` mismatches in `output/runtime-monitor/latest-replay-live-parity-audit.*` | The main short-term bottleneck is precise blocker classification for replay/live parity, not FinalGate or Operation Layer strictness |
| Four-candidate scope review | `3` read-only watcher expansions and `0` primary live-submit scope changes in `output/runtime-monitor/latest-four-candidate-scope-review-decision.*` | Expanded symbols are not progress until they become scoped live-enable proposals or prove concrete blockers |
| Three-strategy trial portfolio | `MPG-001`, `BRF2-001`, and `SOR-001` are seated in `output/runtime-monitor/latest-three-strategy-live-trial-portfolio.*` | Seat count closure is not the same as best near-term opportunity capture |

Near-term planning must therefore treat these as separate layers:

| Layer | Meaning | Must not mean |
| --- | --- | --- |
| `live_trial_portfolio_seat` | A StrategyGroup has enough registry, tier, policy, and readiness shape to hold a trial seat | The selected set is the optimal opportunity-capture set |
| `read_only_watcher_expansion` | Binance USDM public facts may be observed for additional symbols | A milestone or live-submit scope change |
| `replay_live_parity_match` | A replay event can be reproduced by the live detector in the relevant symbol, venue, timeframe, and facts shape | Real-order authority |
| `action_time_boundary_reproduced` | A live-like signal can reach the candidate / action-time boundary without exchange write | FinalGate or Operation Layer may be bypassed |
| `market_wait_validated` | Non-market blockers are closed and only current fresh signal is absent | Generic no-trade explanation |
| `live_submit_ready` | A current fresh signal and action-time facts may proceed through FinalGate and Operation Layer | Replay or synthetic evidence is live authority |

### Near-Term Priority Order

The current planning priority is:

1. Keep the **P0 live path** ready for a real fresh selected StrategyGroup
   signal.
2. Replace broad **Replay Live Parity Audit** mismatches with precise blocker
   classes and per-symbol / per-fact evidence.
3. Convert read-only scope into evidence-backed live scope proposals only when
   detector, watcher, fact, risk-envelope, and policy boundaries are explicit.
4. Close StrategyGroup admission gaps for candidates that better match current
   opportunity evidence.
5. Keep Owner-facing state compressed to one first blocker, one owner, and one
   next action.

The first mismatch classes to reduce are:

| Blocker class | Current examples | Default next action |
| --- | --- | --- |
| `computed_not_satisfied` | CPM detector output exists for `ETHUSDT`, `SOLUSDT`, `AVAXUSDT`, and `SUIUSDT`, but current facts such as trend intact or reclaim confirmation are false | Reclassify CPM parity rows from missing detector to per-symbol / per-fact computed status |
| `replay_live_rule_mismatch` | Replay rows that still fail after detector, watcher input, scope, and computed facts are present | Compare replay rule and live detector rule field-by-field, then normalize or revise |
| `action_time_boundary_not_reproduced` | `MPG-001` and `SOR-001` on expanded read-only symbols | Make live-like detector output reach action-time boundary rehearsal without creating order authority |
| `scope_not_attached` | `MPG-001` on `OPUSDT` or any read-only-only lane | Produce a scoped live-enable proposal or explicitly defer it with policy/risk reason |

### Opportunity-Capture Queue

The trial portfolio may remain a valid trial envelope, but active execution
planning must use the WIP-limited opportunity-capture queue:

| Priority | StrategyGroup | Current planning role | Next checkpoint |
| --- | --- | --- | --- |
| `P0` | `CPM-RO-001` | Rebound / pullback reclaim lane with detector output present but broad blocker classification wrong | Reclassify CPM rows into `computed_not_satisfied` or `replay_live_rule_mismatch` per symbol / fact |
| `P0` | `MPG-001` | Main momentum / continuation lane | Reproduce replay-like expanded-symbol events through live detector and action-time boundary rehearsal |
| `P1` | `MI-001` | Relative-strength impulse / rebound candidate | Close trial admission decision instead of leaving it as an indefinite intake gap |
| `P1` | `SOR-001` | Session / opening-range lane | Keep armed observation and reduce action-time reproduction gaps on `SOLUSDT` and `AVAXUSDT` |
| `P2` | `BRF2-001` | Short-side rally-failure lane | Keep armed observation quiet while the squeeze-risk disable fact is active |

This queue does not grant live profile expansion, order-sizing changes, real
orders, FinalGate bypass, or Operation Layer bypass. It is a planning order for
engineering focus while the official runtime chain remains unchanged. Other
StrategyGroups are support-only unless one of these lanes exits mainline under
the WIP contract.

### Daily Live Enablement Status Requirement

Daily status reporting is not an independent workstream. It must use the table
shape in `docs/current/MAIN_CONTROL_DAILY_LIVE_ENABLEMENT_TABLE_CONTRACT.md` and
answer these Live Enablement blocker-closure questions before adding new
diagnostics:

1. Did the current live-submit scope have a fresh eligible signal.
2. Did expanded read-only scope have replay-like or live-like signal evidence.
3. Was the first blocker market, scope, detector, facts, admission, runtime
   safety, or strategy quality.
4. Did any replay event fail live reproduction, and which mismatch class owns
   the failure.
5. Which single next action reduces the earliest blocker.

Healthy `market_wait_validated` is valid only after admission, scope, policy,
detector, watcher input, facts, classification, and action-time boundary
readiness are not the earliest missing state.

## Server Interaction and Deploy Discipline

Production recurring monitoring is owned by the Tokyo server-side readonly
monitor timer. Tokyo deploys are intentionally less frequent now.

| Action | Default policy |
| --- | --- |
| Routine production monitor | Run `brc-runtime-monitor.timer` on Tokyo; classify quiet / notify server-side and push Feishu only when useful |
| Fresh status refresh | Use server-side current runtime facts for production monitoring |
| Bounded Tokyo deploy apply | Only after a stage-worthy fix, deployable milestone, or explicit Owner request |
| Real order path | Only after selected StrategyGroup, allocated subaccount risk budget, fresh signal, RequiredFacts, candidate/auth, action-time FinalGate, and official Operation Layer all pass |
| Static product-client work | External project; not part of this runtime branch unless the Owner explicitly reopens it |

Do not deploy for every small documentation change, planning adjustment, or
local-only replay/simulation improvement.

Server-side monitor source failures are runtime data gaps, not trading safety
authority. The server monitor records public-facts, account-safe-facts,
watcher, systemd, deploy, and readiness failures as notify-worthy monitor
states without creating live-submit authority.

## Current Audit Surface

Use `docs/current/STRATEGYGROUP_RUNTIME_PILOT_GOAL_AUDIT.md` for the current
requirement-by-requirement audit of P0 real-entry fast chain, P0 exit
hardening, P1 StrategyGroup tier governance, and the remaining
market-dependent first real-order proof.

## Current Tracks

| Track | Owner outcome | Current owner | Current status | Next checkpoint |
| --- | --- | --- | --- | --- |
| P0 Daily Live Enablement Table | Owner and main control read one WIP-limited table instead of many artifacts | Main controller | contract added; implementation pending | Produce one row per active WIP lane with first blocker, evidence, next action, and stop condition |
| P0 WIP + Stop Rules | Active mainline stays limited to CPM / MPG / MI / SOR / BRF2 until a lane exits or Owner changes scope | Main controller | contract added; implementation pending | Enforce seven-day blocker movement review and support-only status for non-WIP StrategyGroups |
| P0 Blocker Classification Contract + CPM Parity Reclassification | Broad replay/live blockers are replaced by precise blocker classes with per-symbol / per-fact evidence | Main runtime window | active planning correction; blocker contract added; CPM detector output is present but current parity wording overstates detector missing | Update parity audit code/tests so CPM fallback-ready detector output becomes `computed_not_satisfied` or `replay_live_rule_mismatch`, not detector missing |
| P0 Replay-to-Live Capture Parity | Replay-observed opportunities are either reproduced by the live detector or assigned to a concrete blocker class | Main runtime window | active local evidence; `latest-replay-live-parity-audit.*` reports `131` replay signals, `14` live-detector reproductions, and `117` mismatches | Reduce first classes: CPM computed-fact classification, MPG/SOR expanded-symbol action-time rehearsal, and MPG `OPUSDT` scope proposal/deferral |
| P0 Read-Only Scope to Live-Scope Proposal Gate | Expanded symbols become live-scope candidates only after detector, watcher, fact, parity, risk envelope, and policy boundaries are explicit | Main runtime window | read-only watcher expansion exists for MPG/CPM/SOR; primary live-submit scope changed count remains `0` | Produce symbol-level proposals only for lanes with precise blocker evidence; keep replay and read-only evidence non-authoritative until Owner-scoped live profile policy exists |
| P1 Opportunity-Capture Queue Compression | Short-term engineering focus follows the earliest removable live-enablement blocker, not only the seated trial portfolio | Main runtime window | planning queue is CPM / MPG / MI / SOR / BRF2; seated trial envelope remains MPG / BRF2 / SOR | Reclassify CPM blocker, integrate MI trial-admission fact into Tradeability Decision, repair MPG/SOR action-time reproduction gaps, and keep BRF2 quiet while squeeze-risk disable is active |
| P0 First Bounded Live Order Closure | First selected StrategyGroup + allocated subaccount risk-budget real order completes through official gates, finalize, reconciliation, settlement, and review | Main runtime window | active, deployed at `e5f8c13b`; cutover ready; live closure evidence, same-tick goal-status, same-tick source-readiness refresh, and local cutover visibility contract are deployed; waiting for fresh signal | On fresh signal, pause lower tracks and drive RequiredFacts -> candidate/auth -> FinalGate -> Operation Layer -> real submit -> protection/reconciliation/settlement/review |
| P0 Runtime Product State Repair | Owner Console can read one stable source-readiness state instead of interpreting artifacts | Main runtime window | mainline implemented | Keep `owner-console-source-readiness.json` / API stable and refresh it from Tokyo watcher evidence |
| P0 Runtime Pilot Liveness | Fresh signal can continue to candidate/auth/FinalGate/Operation Layer evidence prep without accidental watcher-side attempt burn | Main runtime window | active | Rerun fresh signal chain through standing-authorized evidence prep, action-time FinalGate, and official Operation Layer only |
| P0 Shared Runtime Pipeline Validation | Prove that execution-chain fixes are shared by all StrategyGroups and not SOR-specific patches | Main runtime window | active | After common chain closes, run cross-StrategyGroup dry-run/admission validation for MPG / TEQ / FBS / PMR / SOR |
| P0 Runtime Dry-Run Audit Chain | Main chain can expose evidence/endpoint/gate breakage without waiting for market opportunity | Main runtime window | deployed | Keep local and Tokyo `runtime-dry-run-audit-chain.json` covering the full non-executing close-loop shape |
| Signal Observation Grade Coverage Diagnostic | Mainline no-signal periods can be compared against the broader read-only StrategyGroup shelf and summarized for Owner review | Main runtime window | local diagnostic + monitor-sequence expansion/L2 readiness/tier-policy review ready | Use `latest-signal-coverage-diagnostic.json`, `latest-signal-coverage-expansion-review.json`, `latest-l2-readiness-review.json`, `latest-l2-intake-dry-run.json`, and `latest-l2-tier-policy-review.json` to decide whether the issue is market waiting, narrow scope, or strategy signal quality; the local monitor sequence now runs these artifacts after completion audit; current expansion review promotes `BTPC-001` to L2 non-executing shadow-candidate observation only, keeps `BRF-001`/`LSR-001`/`RBR-001`/`VCB-001` blocked from L2, reports each broader would-enter row with tier, suggested next tier, action, confidence, execution boundary, readiness gaps, and no-candidate reason, and does not treat broader preview signals as real-submit authority or L4 promotion authority |
| SIGNAL-OBSERVATION-STATE-001 Strategy Asset State pre-live evidence | High-priority no-action and would-enter observations become Strategy Asset State evidence before they influence StrategyGroup tier decisions | Main runtime window | direct Strategy Asset State path active | `scripts/build_strategygroup_strategy_asset_state.py` produces Strategy Asset State evidence from signal coverage and opportunity review work loop inputs. The output carries current Strategy Asset State rows for active groups and preserves no raw replay samples, FinalGate calls, Operation Layer calls, exchange-write, real-order authority, L4 expansion, profile mutation, leverage mutation, or sizing-default mutation |
| Signal Observation Grade Opportunity Review Work Loop | Observed would-enter opportunities become repeatable local recommendations by joining signal coverage, replay verification, blocking gaps, L2 tier state, and strategy-asset recommendation | Main runtime window | local review work loop + LSR/VCB local revision execution + post-revision replay review + BTPC fact-quality/proxy/proxy-replay keep-revise/live-source mapping/classifier-rule review ready | Use `latest-opportunity-review-work-loop.json` to turn broader observations into per-StrategyGroup actions and scheduled work items: continue L2 shadow quality review, repair RequiredFacts/classifier/economic gaps, build missing replay corpus, park low-quality vocabulary, or prepare future L2 intake without L4 scope change; current queue separates `local_replay_coverage_ready`, `fact_source_pending`, `strategy_asset_recommendation_pending`, `strategy_review_pending`, and `parked`; covered LSR/VCB classifier/economic replay items can roll up into `strategy_asset_recommendations` with `revise_before_l2`, concrete `revision_tasks`, `revision_completion.status=local_revision_completion_ready`, `revision_execution.status=local_revision_execution_complete`, and passed post-revision replay review when those rows are active; `latest-btpc-l2-shadow-fact-quality-review.json` classifies all five BTPC fact gaps, `latest-btpc-local-fact-proxy-review.json` attaches review-only derivatives/margin proxy coverage, and the local monitor sequence now reruns a final opportunity review work loop after `latest-btpc-proxy-replay-quality-review.json`; `latest-btpc-l2-keep-revise-fact-source-review.json` freezes BTPC into keep L2 shadow + revise fact/classifier inputs, `latest-btpc-live-derivatives-fact-source-mapping.json` maps the future live derivatives/margin source routes, and `latest-btpc-classifier-rule-review.json` records the BTPC v1 strong-uptrend and stale-signal disable rules while keeping live RequiredFacts, L4 scope, FinalGate, Operation Layer, exchange-write, and real-order authority false; RBR remains parked |
| Signal Observation Grade Replay Corpus | Historical market/signal windows can exercise StrategyGroup and runtime behavior without waiting for live market signals | Main runtime window + strategy research input | local corpus ready; `BTPC-001` L2 shadow replay plus `BRF-001` / `VCB-001` / `LSR-001` L1 observe replay added | Keep MPG-001 eight-window corpus wired into local dry-run audit; use BTPC-001 L2 shadow replay and BRF/VCB/LSR L1 observe replay for no-action / would-enter diagnostics without expanding L4 real-order scope |
| Signal Observation Grade Synthetic Signal Factory | Fresh/stale/wrong-scope/missing-fact/conflict signals can exercise blocker classes and Owner state | Main runtime window | local minimum ready | Keep MPG-001 synthetic fixtures wired into dry-run audit; expand fixture matrix after the first real live loop |
| Signal Observation Grade Post-Submit Simulator | Entry acceptance, protection failure, partial fill, rejection, SL/TP closure, and still-open lifecycle branches can be rehearsed locally | Main runtime window | local matrix ready | Keep simulator matrix non-executing and link outcomes into review evidence |
| Signal Observation Grade Cost Review Skeleton | Replay outputs carry fee, slippage, funding, min-qty/step-size, and net-edge note fields | Main runtime window + strategy research input | local skeleton ready | Improve estimates from real allocated-subaccount outcomes after first live loop |
| P1 Paper/Simulator Operation Layer | Official submit lifecycle branches can be exercised without real funds | Main runtime window | planned | Use paper/simulator for lifecycle branches; do not make testnet a mainline milestone |
| P1 Allocated-Subaccount Execution Quality | Exchange filters, fees, slippage, funding, protection, reconciliation, and settlement are validated with allocated subaccount funds | Main runtime window | planned after P0 signal | Use the official live path, not testnet, for meaningful execution-quality evidence |
| P1 Execution Cost Model | StrategyGroup review can compare gross edge against fee, funding, slippage, and filter costs | Strategy research window first, main runtime consumes summaries | planned | Define cost-survival fields in StrategyGroup review output |
| P1 Capital Promotion Policy | Probe/trial/promotion/park/kill decisions are tied to evidence and allocated subaccount experiment results | Main runtime window | planned | Add promotion/downshift criteria after first allocated-subaccount real loop and replay evidence |
| P0 Standing Reduce-Only Recovery | Protection-failure recovery is standing-authorized but still gated by FinalGate and official Operation Layer | Main runtime window | deployed | Keep the old owner-close confirmation path out of the primary runtime handoff |
| P0 Safe Tokyo Operations | Tokyo watcher stays current, alive, bounded, and auditable | Main runtime window | active | Verify watcher reports and bounded deploys after each runtime-code change |
| P0 Goal Status Summary | Main goal loop can decide waiting vs processing vs deploy/safety blocker from one read-only status artifact | Main runtime window | active | Refresh `strategygroup-runtime-goal-status.json` after watcher ticks and use it before advancing real-order actions |
| Signal Observation Grade Runtime Interaction Optimization | Owner receives useful server-side monitor notifications without reading local heartbeat/cache artifacts | Main runtime window | active, server-side monitor activation | Healthy waiting-for-market is quiet under `brc-runtime-monitor.timer`; fresh-signal / action-time / runtime-data-gap states notify through Feishu with dedupe |
| P1 Owner Runtime Readmodel Stabilization | External clients can consume one stable source-readiness/readmodel contract | Main runtime window | paused in mainline | Keep readmodel/API stable; do not maintain external client release checks in this worktree |
| P1 StrategyGroup Research Handoff | Strategy research enters main control only through reviewed handoff packs | Strategy research window | active separately | Keep research artifacts out of main runtime worktree except reviewed handoff input |
| P2 Historical Debt Reduction | Historical docs/code do not obscure current pilot behavior | Main runtime window | pending | Compress/archive only after P0 source and runtime state are stable |
| P2 LLM Assistance | LLM supports audit/readiness/notification without changing execution authority | Main runtime window | local event-adapter ready | Start with read-only audit summaries and Feishu notification text only; `runtime_advisory_event_adapter` now converts daily-check, completion-audit, watcher, trade-closed, and review-due artifacts into push-only / ledger-only advisory events without creating execution authority |
| P2 External Information Capture | External information can inform research/watch context without becoming execution authority | Strategy/research window first | pending | Treat as research input, not live-submit permission |

## P0 Subgoal: Owner Console Source Readiness Productization

### Current State

Owner Console exploration is no longer treated as an isolated authority source.
The main runtime branch now owns the source-readiness contract and exposes the
machine-readable artifact/API that the console consumes.

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
real-order readiness detail state
```

### Required Artifacts

| Artifact | Path |
| --- | --- |
| Human confirmation | `docs/current/OWNER_CONSOLE_SOURCE_READINESS_CONFIRMATION.md` |
| Machine-readable artifact | `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/owner-console-source-readiness.json` |
| API surface | `GET /api/trading-console/owner-console-source-readiness` |
| Watcher refresh hook | `scripts/refresh_strategygroup_runtime_product_state_artifacts.py` |

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
| Real-order readiness matrix available | `real_order_readiness` summarizes pass/waiting/blocked counts and submit-blocking keys without requiring raw artifact reading |
| Reconciliation/audit detail missing | Detail degrades without hiding StrategyGroups |
| Safety | No order, exchange write, FinalGate bypass, Operation Layer bypass, secret mutation, profile expansion, sizing change, withdrawal, or transfer |

### 2026-06-16 Checkpoint

| Item | Result |
| --- | --- |
| Source-readiness API | Returns `market_opportunity=等待机会`, `funds=资金正常`, `orders=暂无订单`, `positions=暂无持仓`, `protection=保护正常`, `runtime_dry_run_audit=审计演练正常` in the real-backend smoke fixture |
| Owner Runtime readmodel | Readable funds/orders/positions/protection are business-ready even when candidate-prep details are still progressive; StrategyGroup rows show `等待机会` during no-signal observation |
| System health detail | Shows `审计演练` as a secondary system-health item, not a primary action gate |
| Owner language governance | Strategy rows expose one primary health state plus one Owner-readable summary sentence instead of an evidence wall |
| Verification | Python source-readiness/dry-run tests, real-backend smoke, normal smoke, and state smoke passed |
| Runtime goal overlay | Source-readiness API now reads `strategygroup-runtime-goal-status.json`; `runtime_liveness_degraded` overrides the Owner state to `需要介入` so the console does not mislabel liveness repair as market waiting |
| Real-order readiness detail | Source-readiness API now forwards `real_order_readiness` from goal-status so the console can distinguish waiting-for-market from submit-blocking safety conditions through one API |
| Owner real-order readmodel | Mainline readmodel now carries `real_order_readiness`, pass/waiting/blocked counts, and one Owner-readable action state without exposing internal gate names as the primary Owner state |

### 2026-06-17 Selected Scope Refresh Checkpoint

| Item | Result |
| --- | --- |
| Selected StrategyGroup scope | Watcher service now carries default `BRC_SELECTED_STRATEGY_GROUP_ID=MPG-001`, `BRC_STRATEGYGROUP_MAX_SYMBOLS=3`, and `BRC_STRATEGYGROUP_STALE_AFTER_SECONDS=180`; `/home/ubuntu/brc-deploy/env/runtime-signal-watcher.env` may override them |
| Product-state refresh | `80-product-state-refresh.conf` now performs signed GET-only live-facts precollection and writes the compatibility artifact file `product-state-refresh-packet.json` before refreshing Owner Console source-readiness |
| Stale drop-in hygiene | Tokyo deploy planner removes legacy `50-product-state-refresh.conf` so old refresh semantics do not race or overwrite current selected-scope artifacts |
| Resume dispatcher guard | `40-resume-dispatcher.conf` passes the selected StrategyGroup scope to `runtime_signal_watcher_resume_dispatcher.py`; actionable fresh-authorization, FinalGate, or Operation Layer dispatch is blocked unless the artifact proves the action belongs to the selected StrategyGroup |
| Safety | This remains readmodel/live-facts GET-only work; it does not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### 2026-06-17 Runtime Objective Chain Visibility Checkpoint

| Item | Result |
| --- | --- |
| Objective chain segments | `runtime_execution_chain_closure_status.py` projects six target-aligned segments: fresh/mock signal, RequiredFacts, candidate/auth evidence, action-time FinalGate, official Operation Layer evidence handoff, and disabled/dry-run proof |
| Daily monitor | `run_strategygroup_runtime_daily_check.py` now carries goal-chain ready/missing counts separately from lower-level implementation checks |
| Goal progress | `run_strategygroup_runtime_goal_progress_audit.py` now degrades Signal Observation grade engineering rehearsal when any objective chain segment is missing |
| Old deployed artifacts | Missing `ready_goal_chain_segments` is reported as `unknown`, not as `0 ready / 0 missing` |
| Safety | This is non-executing visibility work only; it does not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### 2026-06-17 Runtime Objective Chain Deploy Checkpoint

The target-chain visibility change was pushed and deployed to Tokyo through the
standing-authorization git deploy path. The deployment repaired the old Tokyo
monitor gap where `required_facts_readiness_checked` was missing from the
runtime dry-run audit summary.

| Item | Result |
| --- | --- |
| Deployed runtime head | `0e2af29a040159857a29b705c563fff27e651a7b` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-0e2af29a-objective-chain-progress` |
| Runtime deploy apply | `status=applied`, `interaction.level=L3_bounded_deploy_apply`, `remote_interaction_count=7`, `blockers=[]` |
| Postdeploy snapshot | `status=ready`, `runtime_dry_run_audit_passed=true`, `runtime_execution_chain_closure_status_ready=true`, `watcher_timer_active=true`, `source_readiness_ready=true` |
| Objective chain | `ready_goal_chain_segments=6`, `missing_or_failed_goal_chain_segments=[]` |
| Daily progress | `status=waiting_for_market`, `notification=DONT_NOTIFY`, `目标链路段: 6 ready / 0 missing` |
| Goal progress | `P0=waiting_for_market`, `Signal Observation grade=ready`, `blockers=[]`, `product_gaps=[]` |
| Safety | Deploy/postdeploy checks did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### 2026-06-17 Runtime Monitor Atomic Artifact Checkpoint

The runtime monitor scripts now write their machine-readable artifacts through
same-directory temporary files followed by atomic replacement. This prevents a
parallel reader from seeing an empty or partially-written snapshot during
postdeploy or fresh-signal resume checks.

| Item | Result |
| --- | --- |
| Snapshot output | `probe_tokyo_runtime_snapshot.py --output-json` writes the L1 snapshot atomically |
| Daily check output | `run_strategygroup_runtime_daily_check.py` writes JSON and Owner progress artifacts atomically |
| Goal progress output | `run_strategygroup_runtime_goal_progress_audit.py` writes JSON and Owner progress artifacts atomically |
| Postdeploy verification | Current Tokyo snapshot remains `status=ready`, `ready_goal_chain_segments=6`, `missing_or_failed_goal_chain_segments=[]` |
| Safety | The monitor hardening is file-output-only; it does not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### 2026-06-17 Runtime Monitor Atomic Deploy Checkpoint

The monitor artifact hardening was pushed and deployed to Tokyo. This ensures
future postdeploy and fresh-signal resume checks can write their local snapshot,
daily-check, and goal-progress artifacts without exposing empty or partially
written JSON to parallel readers.

| Item | Result |
| --- | --- |
| Deployed runtime head | `14f76105efedafdc0be7e2b49d9d8618ad51a0b1` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-14f76105-monitor-atomic-artifacts` |
| Runtime deploy apply | `status=applied`, `interaction.level=L3_bounded_deploy_apply`, `remote_interaction_count=7`, `blockers=[]` |
| Postdeploy snapshot | `status=ready`, `runtime_dry_run_audit_passed=true`, `runtime_execution_chain_closure_status_ready=true`, `watcher_timer_active=true`, `source_readiness_ready=true` |
| Objective chain | `ready_goal_chain_segments=6`, `missing_or_failed_goal_chain_segments=[]` |
| Daily progress | `status=waiting_for_market`, `notification=DONT_NOTIFY`, `目标链路段: 6 ready / 0 missing` |
| Goal progress | `P0=waiting_for_market`, `Signal Observation grade=ready`, `blockers=[]`, `product_gaps=[]` |
| Safety | Deploy/postdeploy checks did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### 2026-06-17 Deploy Channel Diagnostic Checkpoint

Tokyo deploy readiness now distinguishes deployment channel failures from
runtime gate failures. When the local-to-Tokyo path cannot reach SSH/TCP, the
git owner deploy policy artifact remains blocked and surfaces explicit channel blockers
instead of collapsing into a generic readonly-probe failure.

| Item | Result |
| --- | --- |
| Connectivity probe | `scripts/probe_tokyo_runtime_governance_readonly.py` can build a non-mutating `tokyo_runtime_governance_connectivity_probe` |
| TCP blocker | Unreachable SSH/TCP produces `tokyo_tcp_22_unreachable` |
| Deploy policy artifact | `scripts/build_tokyo_runtime_governance_git_owner_deploy_policy_artifact.py` catches readonly probe errors and emits a blocked JSON artifact |
| Safety | The diagnostic does not modify remote files, run migrations, restart services, read secrets, create orders, call OrderLifecycle, call exchange APIs, withdraw, or transfer |

Historical observed state for the diagnostic `a9e3e0f2` deploy artifact was:

```text
deploy_diagnostic_status=blocked
tokyo_connectivity_blockers=tokyo_tcp_22_unreachable
```

That was a deploy-channel diagnostic blocker only. It did not imply that the
StrategyGroup runtime chain, Owner Console source readiness, or dry-run audit
chain failed. Later bounded git deploys reached `postdeploy_accepted`; use the
latest deploy-channel artifact or the newest checkpoint below for current state.

### 2026-06-17 Owner Console Deploy Channel Source Checkpoint

Owner Console source readiness now carries deploy-channel health as a
non-critical `sourceHealth` item. This keeps deployment connectivity distinct
from market opportunity, runtime liveness, live facts, and real-order safety.

| Item | Result |
| --- | --- |
| Backend source | `owner-console-source-readiness` reads `BRC_TOKYO_DEPLOY_CHANNEL_STATUS_PATH` or `tokyo-deploy-channel-status.json` under the watcher report directory |
| Default state | Missing deploy-channel artifact maps to `ready_empty` / `部署通道未检查` |
| Degraded state | Blocked deploy artifact with `tokyo_tcp_22_unreachable` maps to `degraded` / `部署通道暂不可用` |
| Owner readmodel boundary | The status appears only as system/source-health detail, not as a primary Owner action gate |
| Safety | Deploy-channel degradation does not hide StrategyGroups, create orders, call exchange write APIs, bypass FinalGate, or bypass Operation Layer |

## Signal Observation Grade Subgoal: Runtime Interaction Optimization

### Purpose

Routine Tokyo checks should not appear as many unrelated server interactions.
The main runtime window should use one compact interaction report whenever
possible:

```text
L1 read-only snapshot
-> Owner-readable current state
-> product gaps or blockers
-> next safe action
```

### 2026-07-02 Server-Side Runtime Monitor Activation

| Item | Result |
| --- | --- |
| Production monitor owner | `brc-runtime-monitor.timer` runs `scripts/run_tokyo_runtime_server_monitor.py` on Tokyo |
| Baseline policy | `docs/current/RUNTIME_MONITOR_BASELINE.json` records the server-side monitor entrypoint/service/timer |
| Routine interaction level | Production monitoring uses `L1_tokyo_server_readonly_monitor` |
| Fresh signal behavior | Fresh-signal and action-time boundary states notify through Feishu with dedupe |
| Non-quiet summary | Any non-quiet output must state interaction level, remote interaction count, server mutation, and real-order proximity |
| Safety | Server monitor remains readonly; it does not call FinalGate, call Operation Layer, exchange write, or create orders |

### 2026-06-17 Checkpoint

| Item | Result |
| --- | --- |
| Interaction taxonomy | `scripts/runtime_interaction_levels.py` defines L0-L5 as a machine-readable policy for local read, read-only remote checks, dry-run rehearsal, bounded server mutation, action-time pre-execution checks, and official allocated-subaccount real-order actions |
| Unified snapshot | `scripts/probe_tokyo_runtime_snapshot.py` collects runtime release, watcher timer/service, backend service, source-readiness, goal-status, latest-summary, dry-run audit, and execution-chain closure facts through one read-only SSH interaction |
| Interaction labels | Snapshot reports `L1_readonly_snapshot`; deploy executor reports `L1_deploy_plan_only` or `L3_bounded_deploy_apply` |
| Deploy summary | `scripts/execute_tokyo_runtime_governance_git_deploy.py` now emits runtime `owner_summary`, changed/not-changed fields, and safety flags |
| Batched deploy apply | `scripts/plan_tokyo_runtime_governance_git_deploy.py` batches contiguous Tokyo operations so the git deploy path uses 4 direct SSH commands instead of many small server command fragments |
| Deploy interaction count | `scripts/execute_tokyo_runtime_governance_git_deploy.py` writes `interaction.remote_interaction_count`; current git deploy apply budget is 7 counted remote interactions including readonly/postdeploy verifier probes |
| Static release scope | Static product-client publishing has been removed from the main runtime worktree; external product clients consume the stable readmodel/API |
| Deploy session summary | `scripts/run_tokyo_runtime_deploy_session.py` combines runtime deploy and one postdeploy daily check into a single Owner-readable report with highest interaction level, total remote interactions, mutation status, and real-order proximity |
| Tokyo verification | L1 snapshot reports the runtime head, watcher/backend active state, source-readiness, dry-run audit, execution-chain closure status, and safety invariants; it no longer reads nginx or external client release files |
| Daily check | `scripts/run_strategygroup_runtime_daily_check.py` consumes one L1 snapshot and returns `waiting_for_market`, `degraded`, or `blocked` with Owner-readable current action and safety invariants |
| Monitor baseline | `docs/current/RUNTIME_MONITOR_BASELINE.json` is the machine-readable SSOT for server-side runtime monitor ownership, systemd timer identity, and local diagnostic boundaries |
| Interaction budget | Daily check defaults to `--max-remote-interactions 1`; if the source snapshot exceeds the budget, the report becomes a `NOTIFY` engineering blocker instead of silently becoming chatty |
| Notification result | Daily check now emits `notification.notification_result` as `DONT_NOTIFY` only for healthy `waiting_for_market`; fresh/processing/degraded/blocked states emit `NOTIFY` so automation does not re-interpret raw checks |
| Server-side monitor output | `scripts/run_tokyo_runtime_server_monitor.py` classifies quiet / notify on Tokyo from server-side runtime facts, records dedupe state, and sends Feishu only when useful |
| Owner progress output | `scripts/run_strategygroup_runtime_daily_check.py --owner-progress` remains available for manual development diagnostics and postdeploy verification; it is not the production Owner notification path |
| Dry-run coverage visibility | Owner progress output includes the runtime dry-run audit scenario count, so a healthy rehearsal loop reads as `审计演练正常` plus `演练场景: 14` instead of a vague green label |
| Execution-chain closure visibility | L1 snapshot and daily-check read `runtime-execution-chain-closure-status.json`, so healthy non-market closure appears as `非市场链路已收口` without rereading raw audit artifacts |
| Closure segment projection | `runtime-execution-chain-closure-status.json` now projects key dry-run segments such as fresh-signal fast auto-chain, scoped Operation Layer handoff, submit-blocker matrix, shared runtime pipe, and post-submit guards into `projected_checks`, `ready_segments`, and `missing_or_failed_segments` |
| Goal-chain segment projection | Closure status now also maps lower-level checks into six objective-aligned segments: `fresh_or_mock_signal`, `required_facts_readiness`, `candidate_authorization_evidence`, `action_time_finalgate`, `official_operation_layer_evidence_relay_projection`, and `disabled_dry_run_proof` |
| Closure segment Owner progress | L1 snapshot and daily-check can carry closure segment counts into Owner progress; older deployed artifacts without segment fields render `链路段: unknown` instead of falsely reporting `0 ready / 0 missing` |
| Server monitor SSOT | `docs/current/RUNTIME_MONITOR_BASELINE.json` records `server_side_runtime_monitor_check`, `brc-runtime-monitor.service`, and `brc-runtime-monitor.timer` as the production monitor path |
| Goal progress audit | `scripts/run_strategygroup_runtime_goal_progress_audit.py --owner-progress` remains a development diagnostic and now checks for the server-side monitor baseline |
| Goal progress evidence table | Goal progress output now includes a compact Evidence table, including dry-run scenario count, closure segment readiness count, missing closure segment count, interaction source, notification state, and forbidden-effect count |
| Deploy-session check mode | `scripts/run_tokyo_runtime_deploy_session.py --run-daily-check --daily-check-mode fresh --json` remains the postdeploy verification path |
| Engineering rehearsal check | L1 snapshot now requires the dry-run audit artifact to include required checks such as `fresh_signal_fast_auto_chain_checked`, `dangerous_effects_absent`, `disabled_smoke_not_real_execution_proof`, Operation Layer evidence relay, shared runtime pipeline, and StrategyGroup adapter-boundary coverage |
| Owner visibility classification | The daily check emits `owner_summary.visibility.category` as `等待市场机会`, `系统处理中`, `工程状态暂不可用`, `安全边界阻断`, or `需要介入` without exposing raw gate names as the primary Owner state |
| Owner language guard | Owner readmodels map internal `fresh signal` and evidence-instruction wording to Owner language such as `等待市场机会`, `真实订单路径保持关闭`, and `无需操作`; smoke checks prevent those internal terms from returning to the primary Owner state |
| Monitor Owner language guard | Healthy waiting notifications say `当前没有可用市场机会`; internal signal terms remain audit/detail concepts instead of the default Owner heartbeat text |
| Signal detection source | Fresh opportunity detection and Owner notification are Tokyo server-side watcher / runtime-monitor / Feishu responsibilities |
| Safety | These tools do not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets, live-profile mutation, or order-sizing mutation |

### Deploy Interaction Rule

After bounded Tokyo deploys, the main runtime window should
prefer one deploy-session report instead of narrating each server command. The
normal shape is:

```text
runtime deploy report
+ one L1 daily check
-> tokyo_runtime_deploy_session
```

The report must state:

| Field | Meaning |
| --- | --- |
| `interaction.level` | Highest interaction level in the session, for example `L3_bounded_deploy_apply` |
| `interaction.remote_interaction_count` | Total counted remote interactions from the session steps |
| `interaction.mutates_remote_files` | Whether the session changed remote runtime files |
| `interaction.approaches_real_order` | Must remain `false` for deploy sessions |
| `owner_summary.non_authority_checkpoint` | One Owner-readable status checkpoint, usually `继续等待市场机会` when healthy |

This is a communication and tooling optimization only. It does not authorize
FinalGate bypass, Operation Layer bypass, exchange write, live-profile changes,
order-sizing changes, withdrawals, transfers, or stale-fact execution.

### Deploy Tooling Optimization Rule

The default deploy workflow should minimize Tokyo interaction without hiding
safety state:

| Step | Preferred shape | Interaction budget |
| --- | --- | --- |
| Production monitor | `brc-runtime-monitor.timer` -> `scripts/run_tokyo_runtime_server_monitor.py` | Server-side readonly, quiet when healthy, Feishu notify with dedupe when useful |
| Explicit signal/regression investigation | `--json` or one direct L1 snapshot | `L1`, 1 remote interaction |
| Fresh runtime status | One `probe_tokyo_runtime_snapshot.py` collection | `L1`, 1 remote interaction |
| Runtime deploy apply | Batched git deploy phases with explicit remote count | `L3`, 4 direct SSH commands, 7 counted remote interactions |
| Postdeploy acceptance | One daily-check snapshot plus one deploy-session summary | `L1` snapshot, summary local |

When a tool can reuse a server-side monitor artifact or a single snapshot, it
must not run extra Tokyo probes only to restate the same state. When a deploy is
necessary, the report should summarize the whole session instead of narrating
each command.

### 2026-06-17 Batched Deploy Interaction Checkpoint

The runtime deploy tool optimization was pushed and deployed to Tokyo. The
server now carries the batched git deploy planner/executor plus the Owner
Runtime interaction projection.

| Item | Result |
| --- | --- |
| Local head | `83bd0d6aa07c4784fd28e4182c214db4c344efe0` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-83bd0d6a-batched-deploy-interactions` |
| Runtime deploy apply | `status=applied`, `interaction.level=L3_bounded_deploy_apply`, `remote_interaction_count=7`, `blockers=[]` |
| Postdeploy daily check | `status=waiting_for_market`, `runtime_ready=true`, `watcher_ready=true`, `source_readiness_ready=true`, `runtime_dry_run_audit_passed=true` |
| Deploy session summary | `status=waiting_for_market`, `all_steps_safe_for_deploy_session_summary=true` |
| Monitor baseline | `docs/current/RUNTIME_MONITOR_BASELINE.json` now expects runtime head only |
| Safety | Deploy and postdeploy checks did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### 2026-06-17 Owner Runtime Visibility Checkpoint

The low-interaction monitor defaults and Owner runtime visibility changes were
pushed and deployed to Tokyo.

| Item | Result |
| --- | --- |
| Deployed runtime head | `7df799e1ee3dbabd69060f92758a6b84ba2a0ae6` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-7df799e1-owner-runtime-visibility` |
| Runtime deploy apply | `status=applied`, `interaction.level=L3_bounded_deploy_apply`, `remote_interaction_count=7`, `blockers=[]` |
| Postdeploy daily check | `status=waiting_for_market`, `notification=DONT_NOTIFY`, `blockers=[]`, `product_gaps=[]` |
| Deploy session summary | `status=waiting_for_market`, `all_steps_safe_for_deploy_session_summary=true` |
| Owner Runtime visibility | Runtime status no longer shows deploy-channel status as a primary operating state; deploy-channel detail remains system/source-health evidence |
| Visibility coverage | Runtime state smoke covers waiting for market, processing, engineering blocker, safety blocker, and needs-intervention states |
| Monitor baseline | `docs/current/RUNTIME_MONITOR_BASELINE.json` expects runtime head `7df799e1ee3dbabd69060f92758a6b84ba2a0ae6` |
| Safety | Deploy and postdeploy checks did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

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

### Common Pipeline vs StrategyGroup Adaptation

The runtime chain must be validated as one shared execution pipeline. A fresh
signal from MPG, TEQ, FBS, PMR, or SOR should reuse the same common path:

```text
fresh signal
-> RequiredFacts readiness
-> candidate / authorization evidence
-> action-time FinalGate
-> official Operation Layer
-> finalize / reconciliation / settlement / review
```

| Area | Classification | Repeated per StrategyGroup |
| --- | --- | --- |
| Fresh signal -> candidate/auth automatic chain | Common runtime pipeline | No |
| RequiredFacts readiness reading | Common facts/readiness layer | No |
| Attempt renewal / admission | Common runtime admission | No |
| FinalGate call order | Common execution-safety layer | No |
| Operation Layer evidence relay | Common execution layer | No |
| Active position / open order checks | Common account-safety layer | No |
| Protection / budget / duplicate-submit checks | Common protection, budget, idempotency layer | No |
| Post-submit finalize / reconciliation / settlement | Common closed-loop layer | No |
| Owner Console status projection | Common product readmodel | No |
| Supported symbols/sides, signal rule, strategy RequiredFacts, risk defaults, hard stops, conflict policy | StrategyGroup handoff adaptation | Yes |

The expected ratio is roughly:

```text
80% common execution-chain repair
20% StrategyGroup handoff adaptation
```

If a blocker appears in candidate/auth, FinalGate, Operation Layer, account
safety, protection, budget, idempotency, or closed-loop settlement, treat it as
a common pipeline defect first. StrategyGroup-specific work should only define
inputs and boundaries: supported symbols, supported sides, signal-ready rule,
RequiredFacts, risk defaults, hard stops, and conflict policy.

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

### 2026-06-17 Non-Executing Prepare Evidence Checkpoint

The resume dispatcher now treats `ready_for_non_executing_prepare` as an
actionable common-pipeline checkpoint when `--execute-preflight` is enabled:

```text
fresh selected StrategyGroup signal
-> official non-executing next-attempt prepare
-> prepared authorization / candidate evidence
-> action-time FinalGate preflight
-> Operation Layer evidence readiness
```

| Requirement | Result |
| --- | --- |
| Common-chain execution | The dispatcher calls the existing `runtime_next_attempt_prepare_api_flow.py` prepare wrapper instead of adding StrategyGroup-specific candidate/auth code |
| Safety invariants | Prepare may create bounded pre-submit evidence, but it must not arm local registration, arm exchange submit, call OrderLifecycle, create orders, call exchange write APIs, mutate attempt counters, mutate runtime budget, or create withdrawal/transfer actions |
| Missing input handling | Missing runtime instance or signal/order-candidate input blocks as `missing_fact` before FinalGate |
| Forbidden effect handling | Any forbidden prepare effect blocks as `hard_safety_stop` before FinalGate |
| Cross-StrategyGroup proof | Unit coverage proves the same prepare -> FinalGate proof works for MPG, TEQ, and SOR with only StrategyGroup/runtime IDs changed |
| Remaining scope | Operation Layer evidence readiness, live boundary enablement, submit, finalize, reconciliation, settlement, and review remain shared runtime stages rather than StrategyGroup adapters |

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
-> unified audit artifact
```

### Required Artifact

| Artifact | Path |
| --- | --- |
| Local audit artifact | `output/strategygroup-runtime-pilot/dry-run-audit-chain/runtime-dry-run-audit-chain.json` |
| Local closure status artifact | `output/strategygroup-runtime-pilot/chain-closure-status/runtime-execution-chain-closure-status.json` |
| Tokyo audit artifact | `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/runtime-dry-run-audit-chain.json` |

### Current Implementation

The local script is:

```text
scripts/runtime_dry_run_audit_chain.py
scripts/runtime_execution_chain_closure_status.py
```

It currently runs fourteen fixture-backed scenarios and treats expected blocked
states as successful audit coverage when they stop before dangerous actions.
Tokyo refreshes the dry-run audit script as a watcher-adjacent non-executing
audit step. The closure-status script compresses the local dry-run result into
one go/no-go status for main-control progress reviews.

### Scenario Matrix

| Scenario | Expected result |
| --- | --- |
| No signal | `waiting_for_signal`; no candidate, authorization, FinalGate, or Operation Layer |
| Mock fresh signal pass | Evidence IDs connect; dangerous action flags remain false |
| Mock Operation Layer submit/finalize pass | Dispatcher reaches settled and next-attempt-ready with mock responses only |
| RequiredFacts missing | Clear `missing_fact` blocker before Operation Layer |
| Active position or open-order conflict | Clear conflict blocker before FinalGate or Operation Layer action |
| Operation Layer blocker review matrix | Active position, open order, protection, budget, duplicate-submit, and scope mismatches become reviewable blocked evidence |
| Selected StrategyGroup dispatch guard | Selected MPG-001 mock fresh signal can reach FinalGate dispatch; out-of-scope StrategyGroup signal is blocked before FinalGate or Operation Layer |

### 2026-06-17 Chain Closure Status Checkpoint

`scripts/runtime_execution_chain_closure_status.py` now converts the full
dry-run audit artifact into compact status evidence. This keeps routine progress
reviews from rereading many raw evidence artifacts while still refusing to treat
mock or disabled-smoke proof as a real-order proof.

| Item | Result |
| --- | --- |
| Non-market status | `non_market_execution_chain_ready` only when the dry-run audit passes, all required checks are true, and no dangerous effect is present |
| Real-order status | Remains `waiting_for_live_action_time_proof` after local dry-run success |
| Missing live proofs | Sourced from the first-live-closure contract: live watcher signal, RequiredFacts, candidate/runtime grant/fresh authorization, action-time FinalGate, Operation Layer submit authorization, exchange acceptance, exchange-native hard stop, post-submit finalize, reconciliation, budget settlement, and review evidence IDs |
| Next safe actions | Keep watcher running, rerun dry-run audit after runtime changes, and on fresh signal run same-run FinalGate then official Operation Layer |
| Safety | The closure-status script does not call Tokyo, FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets, live profile, or sizing mutation |

### 2026-06-17 Order-Capable Experiment Profile Checkpoint

The runtime pilot now treats Tokyo as an experimental allocated-subaccount
server: inside the selected StrategyGroup and Owner-allocated subaccount/profile
boundary, trading permission is not itself a risk blocker. The system must
still fail closed on stale facts, missing protection, duplicate-submit risk,
conflicting active positions or open orders, FinalGate failure, or Operation
Layer failure.

| Item | Result |
| --- | --- |
| SSOT | `docs/current/RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md` |
| Server overlay | `/home/ubuntu/brc-deploy/env/runtime-order-capable.env` |
| Tracked template | `.env.tokyo.experimental-live-order-capable.example` |
| Required env | `TRADING_ENV=live`, `EXCHANGE_TESTNET=false`, `BRC_EXECUTION_PERMISSION_MAX=order_allowed`, `RUNTIME_EXCHANGE_SUBMIT_GATEWAY_BINDING_ENABLED=true` |
| Runtime control/test surfaces | Must remain `RUNTIME_CONTROL_API_ENABLED=false` and `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=false` |
| Watcher systemd | Loads the optional order-capable overlay after `live-readonly.env` |
| Operation Layer mode | Resume dispatcher explicitly uses `--operation-layer-submit-mode real_gateway_action` |
| Credential preflight | Now checks `order_allowed` and gateway-binding env readiness without printing secrets |

### 2026-06-17 Order-Capable Experiment Deploy Checkpoint

The order-capable experiment profile was pushed and deployed to Tokyo through
the git-based standing-authorization deploy path. Tokyo now has a server-only,
non-secret overlay at `/home/ubuntu/brc-deploy/env/runtime-order-capable.env`.

| Item | Result |
| --- | --- |
| Commit | `bceea34db0317325c368a67514967f824d9694b6` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-bceea34d-order-capable-experiment` |
| Runtime deploy apply | `status=applied`, `interaction.level=L3_bounded_deploy_apply`, `remote_interaction_count=7`, `blockers=[]` |
| Watcher systemd | `brc-runtime-signal-watcher.timer` active/enabled; service loads `runtime-order-capable.env` after `live-readonly.env` |
| Masked env check | `TRADING_ENV=live`, `EXCHANGE_TESTNET=false`, `BRC_EXECUTION_PERMISSION_MAX=order_allowed`, `RUNTIME_EXCHANGE_SUBMIT_GATEWAY_BINDING_ENABLED=true` |
| Credential preflight | Passed with futures permission present, withdrawals disabled, scoped position count `0`, scoped open order count `0` |
| Daily check | `status=waiting_for_market`, `notification=DONT_NOTIFY`, `blockers=[]`, `product_gaps=[]` |
| Safety | Deploy and checks did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### 2026-06-17 Goal Status Local Dry-Run Checkpoint

The goal-status artifact now accepts the local dry-run audit artifact from either
the Tokyo-style report root or the local audit subdirectory:

```text
runtime-dry-run-audit-chain.json
dry-run-audit-chain/runtime-dry-run-audit-chain.json
```

This keeps local P0 audit runs usable without waiting for a market signal or
manually copying artifact files.

| Item | Result |
| --- | --- |
| Local dry-run fallback | `strategygroup-runtime-goal-status` reads nested `dry-run-audit-chain/runtime-dry-run-audit-chain.json` |
| Fast auto-chain audit | Goal status treats `fresh_signal_fast_auto_chain_checked=true` as a required dry-run check |
| Submit-blocker review | Active position/open-order conflicts remain submit blockers, but `active_position:missing` and `open_orders:missing` are classified through missing facts instead of fake conflict resolution |
| Budget/protection missing facts | `budget:missing` and `protection:missing` surface as missing-fact submit blockers |
| Safety | This remains read-only artifact aggregation; it does not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets, live profile, or sizing mutation |

### 2026-06-17 Local Product-State Refresh Checkpoint

`scripts/refresh_strategygroup_runtime_product_state_artifacts.py` can now be
used as a local main-control refresh wrapper. When explicitly requested, it
refreshes the non-executing dry-run audit chain and then rebuilds
`strategygroup-runtime-goal-status.json` from the same report directory.

If local operator auth is missing, API readmodel refresh is recorded as a
reviewable blocker, but local dry-run audit and goal-status artifacts are still
written. This prevents no-signal development turns from stopping only because
the local console server/auth environment is not running.

| Item | Result |
| --- | --- |
| Optional dry-run refresh | `--refresh-dry-run-audit-chain` writes `runtime-dry-run-audit-chain.json` |
| Optional closure-status refresh | `--refresh-chain-closure-status` writes `runtime-execution-chain-closure-status.json` from the current dry-run audit artifact |
| Optional goal-status refresh | `--refresh-goal-status` writes `strategygroup-runtime-goal-status.json` |
| Tokyo watcher hook | `80-product-state-refresh.conf` now writes `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/runtime-execution-chain-closure-status.json` after the dry-run audit post-step |
| Local auth missing | Records `operator_cookie_unavailable` and skips API readmodel refresh instead of aborting the local audit refresh |
| Long local goal mode | `--allow-degraded-local-refresh-success` may return exit code `0` only when operator auth is missing, dry-run audit passed, goal-status refreshed, source-readiness unavailable evidence was written, and no forbidden safety effect is present |
| Current local command result | `dry_run_audit_refresh.status=passed`, `scenario_count=14`, `goal_status_refresh.runtime_dry_run_audit_passed=true`, `goal_status_refresh.status=missing_fact` |
| Safety | The wrapper remains readmodel/local-artifact only; the degraded-success flag is not installed in Tokyo systemd and does not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets, live profile, or sizing mutation |

### 2026-06-17 Source-Readiness Unavailable Evidence Checkpoint

When local operator auth is missing, product-state refresh now writes a
degraded `owner-console-source-readiness.json` unavailable evidence artifact instead of
leaving the source-readiness file absent. The evidence keeps the Owner Console
contract shape but marks account, orders, positions, protection, runtime source,
and watcher as unavailable.

| Item | Result |
| --- | --- |
| Evidence trigger | `operator_cookie_unavailable` while refreshing readmodel APIs |
| Unavailable evidence | `owner-console-source-readiness.json.status=source_unavailable` |
| Preserved health | `runtime_dry_run_audit=审计演练正常` when the local dry-run audit passed |
| Goal-status effect | `strategygroup-runtime-goal-status` no longer reports packet-shaped missing source blockers; it reports `missing_artifact:source_readiness`, `source_readiness_not_ready`, and `live_facts_not_ready` until real readmodels/facts are available |
| No fake readiness | Funds, orders, positions, protection, runtime source, and watcher remain unavailable in the evidence artifact |
| Safety | Unavailable evidence generation is local/read-only and does not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets, live profile, or sizing mutation |

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
| Strategy-specific inputs | Each StrategyGroup only changes handoff contract inputs: signal observation shape, RequiredFacts, symbol, side, risk defaults, hard stops, and conflict rules |
| Dry-run coverage | The dry-run audit chain includes at least one pass-like fixture and one blocked fixture that are not SOR-only |
| No execution fork | No StrategyGroup adds a custom FinalGate, Operation Layer, order lifecycle, exchange gateway, or settlement implementation |
| Owner readmodel | StrategyGroup differences appear as product state, not separate artifact-reading workflows |

### 2026-06-17 Checkpoint

| Item | Result |
| --- | --- |
| Dry-run audit artifact | `runtime-dry-run-audit-chain.json` now includes `shared_runtime_pipeline_validation` and `selected_strategygroup_dispatch_guard_checked` |
| StrategyGroups covered | MPG / TEQ / FBS / PMR / SOR |
| Common-chain proof | All five StrategyGroups share the same runtime stages: admission, candidate/auth, RequiredFacts, FinalGate, Operation Layer evidence relay, account/protection/budget/idempotency checks, submit, finalize/reconcile/settle/review, and Owner readmodel |
| Strategy-specific proof | Each handoff only supplies symbols, sides, signal rule, RequiredFacts, risk defaults, hard stops, and sample artifacts |
| Execution authority proof | Each handoff keeps `candidate_creation_authorized=false`, `final_gate_input=false`, `operation_layer_input=false`, and `real_submit_authorized=false` |
| Goal status guard | `strategygroup-runtime-goal-status` now requires `shared_runtime_pipeline_checked=true`, `common_execution_chain_reuse_checked=true`, `strategygroup_adapter_boundary_checked=true`, and `selected_strategygroup_dispatch_guard_checked=true` before treating dry-run audit as healthy |

### 2026-06-17 80/20 Verification Checkpoint

The current architecture judgment is verified as a runtime audit invariant:

| Share | Scope | Verification result |
| --- | --- | --- |
| 80% | Common runtime pipe | `runtime-dry-run-audit-chain.json` proves MPG / TEQ / FBS / PMR / SOR share the same admission, candidate/auth, RequiredFacts, FinalGate, Operation Layer evidence relay, submit, finalize, reconciliation, settlement, review, and Owner readmodel stages |
| 20% | StrategyGroup adapter | Each handoff only supplies symbols, sides, signal rule, RequiredFacts, allocated risk/profile defaults, hard stops, and sample artifacts |

Current local validation:

```text
python3 scripts/runtime_dry_run_audit_chain.py \
  --output-dir output/strategygroup-runtime-pilot/dry-run-audit-chain \
  --output-json output/strategygroup-runtime-pilot/dry-run-audit-chain/runtime-dry-run-audit-chain.json

pytest tests/unit/test_runtime_dry_run_audit_chain.py \
  tests/unit/test_strategygroup_runtime_goal_status.py -q
```

Result:

```text
runtime-dry-run-audit-chain.status=passed
scenario_count=14
shared_runtime_pipeline_checked=true
common_execution_chain_reuse_checked=true
strategygroup_adapter_boundary_checked=true
selected_strategygroup_dispatch_guard_checked=true
29 passed
```

This means active position, open order, missing protection, missing budget,
duplicate-submit risk, and symbol/side/notional/leverage mismatch remain
real-submit blockers, but they do not require StrategyGroup-specific execution
forks and do not stop watcher observation or common-chain project progress.

### 2026-06-17 Goal-Status Projection Checkpoint

`strategygroup-runtime-goal-status.json` now projects the required dry-run audit
checks into its top-level `checks` object. Automation and Owner Console
readmodels can distinguish a live-source gap from a shared-chain gap without
digging into the raw dry-run artifact.

| Item | Result |
| --- | --- |
| Fast chain projection | `checks.fresh_signal_fast_auto_chain_checked=true` when the local audit proves fresh signal -> authorization -> FinalGate dispatch -> Operation Layer evidence prep |
| Shared pipeline projection | `checks.common_execution_chain_reuse_checked=true` and `checks.strategygroup_adapter_boundary_checked=true` when MPG / TEQ / FBS / PMR / SOR reuse the common runtime pipe |
| Selected-scope projection | `checks.selected_strategygroup_dispatch_guard_checked=true` and `checks.all_selected_strategygroups_reach_finalgate_dispatch_checked=true` when selected StrategyGroup dispatch can reach the action-time FinalGate plan and out-of-scope signals are blocked |
| Current local effect | Local `goal-status` can report `runtime_dry_run_audit_passed=true` while still blocking real submit on `missing_artifact:*`, `source_readiness_not_ready`, or `live_facts_not_ready` |
| Safety | This is read-only projection only; it does not call Tokyo, FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets, live profile, or sizing mutation |

### 2026-06-17 Tokyo Deploy Checkpoint

The latest main-control branch head was deployed to Tokyo through the
git-based standing-authorization deploy path.

| Item | Result |
| --- | --- |
| Local / remote branch head | `ee0c248e` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-ee0c248e-goal-status-projection` |
| Deploy apply | `status=applied`, `commands_executed=18`, `blockers=[]` |
| Postdeploy verifier | `postdeploy_acceptance_passed`; release identity is read from `.brc-release-manifest.json` because the release is a git export, not a git working tree |
| Watcher timer | `brc-runtime-signal-watcher.timer` is enabled and active |
| Current Tokyo goal status | `strategygroup-runtime-goal-status.status=waiting_for_signal` |
| Source readiness | `owner-console-source-readiness.status=ready` |
| Live facts | `strategy-group-live-facts-readiness.status=strategy_group_live_facts_ready_for_armed_observation` |
| Dry-run audit | `runtime-dry-run-audit-chain.status=passed`, `scenario_count=14` |
| Real order boundary | `ready_for_real_order_action=false` because there is no fresh signal |
| Next checkpoint | `continue_watcher_observation` until a fresh selected StrategyGroup signal appears |
| Safety | Deploy and postdeploy checks did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### 2026-06-17 Local Refresh Evidence Relay Deploy Checkpoint

The local product-state refresh evidence relay fix was pushed and deployed to
Tokyo through the git-based standing-authorization deploy path.

| Item | Result |
| --- | --- |
| Deployed code head | `f8f5482a` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-f8f5482a-local-refresh-evidence-relay` |
| Deploy apply | `status=applied`, `commands_executed=18`, `blockers=[]` |
| Postdeploy verifier | `postdeploy_acceptance_passed`; current head is `f8f5482aedcf3777fe10ce84a4d2420781d88d7c` |
| Watcher timer | `brc-runtime-signal-watcher.timer` is enabled and active |
| Current Tokyo goal status | `strategygroup-runtime-goal-status.status=waiting_for_signal`, `runtime_dry_run_audit_passed=true` |
| Source readiness | `owner-console-source-readiness.status=ready`; Owner summary reports `等待机会`, `资金正常`, `暂无订单`, `暂无持仓`, and `保护正常` |
| Dry-run audit | `runtime-dry-run-audit-chain.status=passed`, `scenario_count=14`, fast-auto-chain/shared-pipeline/adapter-boundary checks are true |
| Live facts | `strategy-group-live-facts-readiness.status=strategy_group_live_facts_ready_for_armed_observation` |
| Real order boundary | `ready_for_real_order_action=false` because there is no fresh signal |
| Safety | Deploy and postdeploy checks did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### 2026-06-17 Deploy Channel Status Publish Checkpoint

The git-based deploy plan now writes the watcher-facing deploy-channel status
artifact after postdeploy verification succeeds. This prevents Owner Console from
showing `部署通道未检查` immediately after a successful bounded deploy.

| Item | Result |
| --- | --- |
| Deployed code head | `cd61c69d` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-cd61c69d-deploy-channel-status` |
| Deploy apply | `status=applied`, `commands_executed=19`, `blockers=[]` |
| Postdeploy verifier | `postdeploy_acceptance_passed`; current head is `cd61c69d3421abe23d43c6ab4953403ac72e6258` |
| Deploy-channel artifact | `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/tokyo-deploy-channel-status.json` exists with `status=postdeploy_accepted`, `blockers=[]` |
| Owner Console source readiness | `deploy_channel=部署通道正常`, source status `ready`, `connectivity_ready=true` |
| Goal status | `strategygroup-runtime-goal-status.status=waiting_for_signal`, `deploy_channel_blockers=[]`, `fresh_signal_present=false` |
| Dry-run audit | `runtime-dry-run-audit-chain.status=passed` |
| Real order boundary | `ready_for_real_order_action=false` because there is no fresh signal |
| Safety | Deploy-channel status publication is a report-artifact write only; deploy/postdeploy checks did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### 2026-06-17 Readonly Probe Structured Failure Checkpoint

The Tokyo readonly probe now emits a structured JSON artifact even when SSH
read-only collection fails. This keeps automation and Owner Console source
readiness from treating deployment-channel failures as opaque runtime failures.

| Item | Result |
| --- | --- |
| Public-key failure | `probe_tokyo_runtime_governance_readonly.py --json` returns `status=blocked` with `tokyo_ssh_publickey_denied` |
| Error preservation | Release-identity fallback preserves underlying SSH stderr so the blocker can be classified |
| Automation contract | JSON output remains parseable on failure; stderr text is no longer the only evidence |
| Historical observed local result | `status=blocked`, `checks.blockers=["tokyo_ssh_publickey_denied"]`; later deploy-channel checks reached `postdeploy_accepted` |
| Safety | Readonly probe failure handling does not modify remote files, read env/secrets, run migrations, restart services, create orders, call OrderLifecycle, call exchange APIs, withdraw, or transfer |

### 2026-06-17 Source Readiness Deploy-Channel Fallback Checkpoint

Owner Console source readiness now uses the readonly probe artifact as a
deploy-channel fallback when `tokyo-deploy-channel-status.json` is absent. This
keeps the product surface specific even before the next successful deploy writes
the postdeploy channel artifact.

| Item | Result |
| --- | --- |
| Readmodel fallback | `owner-console-source-readiness` reads `BRC_TOKYO_READONLY_PROBE_STATUS_PATH` or `tokyo-readonly-probe-current.json` under the watcher report directory when the deploy-channel artifact is missing |
| Product status | `tokyo_ssh_publickey_denied` maps to `deploy_channel=部署通道暂不可用` |
| Local fallback artifact | `refresh_strategygroup_runtime_product_state_artifacts.py` mirrors the same deploy-channel language in source-readiness fallback output |
| Owner readmodel boundary | The deploy-channel item remains a source-health/system detail and does not become a primary execution gate |
| Safety | This is read-only state projection; it does not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets, live profile, or sizing mutation |

### 2026-06-17 Source Readiness Fallback Deploy Checkpoint

The latest Owner Console source-readiness fallback repair was deployed to Tokyo
through the standing-authorization git deploy path. Tokyo is current again, and
the watcher/product-state loop is healthy while waiting for a fresh selected
StrategyGroup signal.

| Item | Result |
| --- | --- |
| Deployed code head | `00847a6f` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-00847a6f-source-readiness-fallback` |
| Deploy apply | `status=applied`, `commands_executed=19`, `blockers=[]` |
| Postdeploy verifier | `postdeploy_acceptance_passed`; current head is `00847a6fe8611c2609726d88ce9c7b3fd276fcab` |
| Watcher timer/service | Timer is enabled and active; latest service tick exited `0/SUCCESS` |
| Current watcher state | `watcher-tick.status=watching_no_signal`; `latest-summary.status=waiting_for_signal` |
| Current goal status | `strategygroup-runtime-goal-status.status=waiting_for_signal`, `fresh_signal_present=false`, `runtime_dry_run_audit_passed=true` |
| Source readiness | `owner-console-source-readiness.status=ready` |
| Live facts | `strategy-group-live-facts-readiness.status=strategy_group_live_facts_ready_for_armed_observation` |
| Dry-run audit | `runtime-dry-run-audit-chain.status=passed` |
| Deploy channel | `tokyo-deploy-channel-status.status=postdeploy_accepted`, `blockers=[]` |
| Real order boundary | `ready_for_real_order_action=false` because there is no fresh signal |
| Safety | Deploy, probe, postdeploy, watcher refresh, and status reads did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### 2026-06-17 External Product-Client Boundary Checkpoint

The Owner Console product client was removed from the main runtime goal.
The main worktree keeps the source-readiness/readmodel contract for future
external clients, but external client build/release checks no longer affect
runtime monitoring or first real-order closure.

| Item | Result |
| --- | --- |
| External client release | Removed from mainline runtime monitoring |
| Product-client governance docs/assets | Removed from `docs/current` |
| Runtime snapshot | No longer checks nginx or `/var/www/brc-owner-console` release files |
| Daily check | Healthy waiting-for-market can stay quiet without external client release proof |
| Goal progress audit | No longer contains an external client release track |
| Runtime/API contract | Source-readiness and readmodel/API surfaces remain available for a future external client |
| Readonly probe | `status=ready_for_controlled_deploy_preflight`, `blockers=[]`, health is `ok`, `live_ready=false` |
| Watcher state | `watcher-tick.status=watching_no_signal`; `latest-summary.status=waiting_for_signal` |
| Goal status | `strategygroup-runtime-goal-status.status=waiting_for_signal`, `fresh_signal_present=false`, `source_readiness_ready=true`, `live_facts_ready=true` |
| Owner summary | `部署通道正常`, `等待机会`, `资金正常`, `暂无订单`, `暂无持仓`, `保护正常`, `审计演练正常` |
| Real order boundary | `ready_for_real_order_action=false` because there is no fresh signal |
| Safety | Smoke, deploy, probe, postdeploy, watcher refresh, and status reads did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### 2026-06-17 Submit-Blocker Review State Deploy Checkpoint

The submit-blocker review state was pushed and deployed to Tokyo so the
watcher-facing goal-status artifact can distinguish normal waiting from
reviewable submit blockers.

| Item | Result |
| --- | --- |
| Deployed code head | `315af1b7` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-315af1b7-submit-blocker-review` |
| Deploy apply | `status=applied`, `commands_executed=19`, `blockers=[]` |
| Postdeploy verifier | `postdeploy_acceptance_passed`; current head is `315af1b784ae8526f505e6b8e0d577a9728bde7e` |
| Watcher state | `watcher-tick.status=watching_no_signal`; `latest-summary.status=waiting_for_signal`; `resume-dispatch-artifact.status=waiting_for_market` |
| Goal status | `strategygroup-runtime-goal-status.status=waiting_for_signal`, `next_safe_checkpoint=continue_watcher_observation`, `ready_for_real_order_action=false` |
| Submit-blocker review | `submit_blocker_review.required=false`, `blocker_keys=[]`; natural no-signal waiting is not a review task |
| Real order boundary | `submit_blocker_keys=["fresh_signal","candidate_authorization","action_time_finalgate","official_operation_layer"]`, but `submit_blocker_review_required=false` because these are waiting states, not blocked rows |
| Safety | Deploy, postdeploy verify, watcher refresh, and status reads did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### 2026-06-17 Owner Console Submit-Blocker Review Projection Checkpoint

The Owner Console source-readiness readmodel now consumes the
submit-blocker review state instead of forcing the Owner to interpret raw
matrix keys.

| Item | Result |
| --- | --- |
| Deployed code head | `6b615aac` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-6b615aac-console-submit-blocker-review` |
| Deploy apply | `status=applied`, `commands_executed=19`, `blockers=[]` |
| Postdeploy verifier | `postdeploy_acceptance_passed`; current head is `6b615aaca2b6f593d7feaa98ee3f7884ad22b56f` |
| Source-readiness projection | `real_order_readiness.submit_blocker_review.required=false`, `blocker_keys=[]`, `ready_for_real_order_action=false` |
| Current Owner state | `owner_summary.real_order_readiness=等待机会`; no-signal waiting remains a normal waiting state, not a review task |
| Owner copy | Real submit blockers show `系统审查已记录` and `真实订单保持关闭`; normal waiting does not show that warning |
| Validation | `pytest` readmodel checks passed |
| Safety | Readmodel validation and deploy did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### P0 Common Runtime Pipe Reuse Verification

After the first bounded live chain closes, the main controller must verify that
the fixed path is a shared runtime pipe, not an MPG-only or SOR-only special
case. The working hypothesis is:

```text
80% common execution-chain work
20% StrategyGroup adapter work
```

The common pipe owns these stages once:

| Common stage | Owner | StrategyGroup-specific rewrite allowed |
| --- | --- | --- |
| fresh signal to candidate / authorization | runtime mainline | No |
| RequiredFacts readiness read | runtime / facts layer | No |
| attempt renewal / admission | runtime admission | No |
| action-time FinalGate order | execution safety | No |
| Operation Layer evidence handoff | execution layer | No |
| active position / open order checks | account safety | No |
| protection missing check | protection layer | No |
| budget missing check | budget layer | No |
| duplicate submit risk | idempotency / order lifecycle | No |
| post-submit finalize / reconciliation / settlement | closed-loop layer | No |
| Owner Console state projection | product readmodel | No |

Each StrategyGroup may only swap its adapter inputs:

| Adapter input | Example | Purpose |
| --- | --- | --- |
| supported symbols | `MSTR/USDT:USDT`, `XAG/USDT:USDT` | limit observable markets |
| supported sides | `long`, `short` | limit direction |
| signal ready rule | momentum, funding stress, session breakout | decide whether a fresh signal exists |
| RequiredFacts definition | mark, funding, session, OI, position | declare required evidence |
| allocated profile defaults | notional/leverage from Owner-selected subaccount profile | keep execution inside the selected profile without adding hidden de-risking |
| hard stops | stale signal, conflict, low liquidity | stop unsafe strategy-specific conditions |
| conflict policy | TEQ / MPG same beta concentration | prevent stacked exposure |

The P0 close-loop is accepted only when one real or fully dry-run audited path
proves the common stages above are parameterized by StrategyGroup handoff data.
The verification must then run at least one non-executing adapter replay for a
second StrategyGroup so that a future MPG / TEQ / FBS / SOR / PMR activation does
not require rebuilding candidate, FinalGate, Operation Layer, or finalize logic.

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
as real execution proof. The global audit artifact must still show no actual
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
artifacts before deciding whether to keep observing or advance toward the first
bounded real order. A read-only summary artifact now classifies the current
runtime state from already-written evidence.

### Required Artifact

| Artifact | Path |
| --- | --- |
| Local/generated artifact | `output/strategygroup-runtime-pilot/goal-status/strategygroup-runtime-goal-status.json` |
| Tokyo watcher artifact | `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/strategygroup-runtime-goal-status.json` |
| Builder | `scripts/build_strategygroup_runtime_goal_status.py` |
| Watcher drop-in | `deploy/systemd/brc-runtime-signal-watcher.service.d/70-goal-status.conf` |

### Classification

| Status | Meaning | Next safe checkpoint |
| --- | --- | --- |
| `waiting_for_signal` | Runtime is healthy and no fresh StrategyGroup signal exists | `continue_watcher_observation` |
| `fresh_signal_processing` | Fresh signal exists but candidate/authorization evidence is not complete | `prepare_candidate_grant_authorization_evidence` |
| `action_time_finalgate_ready` | Candidate/authorization reached action-time gate boundary | `run_official_action_time_finalgate` |
| `operation_layer_ready` | Required evidence is ready for the official Operation Layer path | `call_official_operation_layer_submit_after_action_time_recheck` |
| `deployment_issue` | Tokyo release, deploy channel, or target runtime head is not ready | Repair deploy channel while continuing watcher observation |
| `hard_safety_stop` | Forbidden effect evidence is present | Stop and investigate |

### Safety

The builder only reads local JSON artifacts. It does not call Tokyo APIs,
FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawals,
transfers, secrets, live profile, or order sizing. It must never mark a real
order action ready unless selected StrategyGroup, allocated subaccount risk
budget, fresh signal,
RequiredFacts, candidate/grant/authorization evidence, action-time FinalGate,
and official Operation Layer evidence are all represented by current artifacts.

The `runtime_dry_run_audit_passed` check is intentionally stricter than
`runtime-dry-run-audit-chain.json.status=passed`. The goal status artifact must
also see these dry-run sub-checks as true before treating the runtime chain as
healthy:

| Dry-run sub-check | Purpose |
| --- | --- |
| `required_scenarios_present` | Confirms the no-signal, mock signal, missing fact, conflict, blocker-review, and closed-loop scenarios are all represented. |
| `all_scenarios_passed` | Confirms every dry-run scenario passed. |
| `dangerous_effects_absent` | Confirms no forbidden effect flag escaped the dry-run artifact. |
| `disabled_smoke_not_real_execution_proof` | Prevents disabled smoke from being mistaken for real execution evidence. |
| `operation_layer_evidence_relay_checked` | Confirms evidence IDs connect through the Operation Layer handoff shape. |
| `fresh_signal_fast_auto_chain_checked` | Confirms mock fresh signal reaches candidate/authorization readiness, FinalGate dispatch, and Operation Layer evidence readiness without calling real submit. |
| `legacy_local_registration_probe_tolerance_checked` | Confirms old local-registration probe semantics are tolerated only when the new evidence path is present. |
| `mock_operation_layer_closed_loop_checked` | Confirms fake submit/finalize/reconcile/budget/review shape remains covered without exchange write. |
| `operation_layer_blocker_review_policy_checked` | Confirms active position, open order, protection, budget, duplicate-submit, and scope mismatches become reviewable blocked evidence rather than project-stopping chat confirmations, while real submit remains forbidden. |
| `common_execution_chain_reuse_checked` | Confirms MPG / TEQ / FBS / PMR / SOR reuse the shared execution chain and remain input-only StrategyGroup adapters. |
| `strategygroup_adapter_boundary_checked` | Confirms each StrategyGroup handoff only supplies symbols, sides, signal rule, RequiredFacts, allocated risk/profile defaults, and hard stops, while candidate/auth, FinalGate, Operation Layer, finalize, reconciliation, settlement, and Owner readmodel remain in the shared runtime pipe. |
| `selected_strategygroup_dispatch_guard_checked` | Confirms selected MPG-001 mock fresh signal can reach FinalGate dispatch while an out-of-scope StrategyGroup signal is blocked before FinalGate or Operation Layer. |

Operation Layer blockers such as active position, open order, missing protection,
missing budget, duplicate-submit risk, and symbol/side/notional/leverage scope
mismatch must not stop project progress or watcher observation. They must
produce auditable review evidence and Owner-readable unavailable/intervention
state, but `real_submit_allowed` must remain false until the blocker is
resolved through the official path.

### 2026-06-17 Readiness Matrix Checkpoint

`strategygroup-runtime-goal-status.json` now includes
`real_order_readiness_matrix`. This read-only matrix lets the active goal loop
and Owner Console detail surfaces distinguish normal market waiting from
submit-blocking safety conditions.

The artifact also projects the common readiness decision at stable top-level
fields so automation and external clients do not need to know internal artifact
nesting:

| Field | Meaning |
| --- | --- |
| `ready_for_real_order_action` | Direct boolean mirror of the common real-order boundary decision. It remains `false` while waiting for market, missing facts, blocked by safety matrix items, or before official Operation Layer readiness. |
| `checks.ready_for_real_order_action` | Machine-check mirror for smoke tests, heartbeat monitors, and readmodel consumers. |
| `non_authority_checkpoint` | Owner/runtime continuation checkpoint, such as `continue_watcher_observation` while no fresh signal exists; not submit authority. |

`owner-console-source-readiness` and the product-state refresh script now
prefer these top-level fields first, then fall back to `checks` and the older
`real_order_boundary` shape only for compatibility with historical artifacts.

| Matrix item | Purpose |
| --- | --- |
| `selected_strategygroup_scope` | Proves the signal/runtime belongs to the selected StrategyGroup before any real-submit boundary. |
| `fresh_signal` | Separates normal market waiting from runtime failure. |
| `required_facts` | Shows whether RequiredFacts / signed live facts are ready. |
| `candidate_authorization` | Shows whether candidate / authorization evidence has reached the action-time boundary. |
| `action_time_finalgate` | Shows whether action-time FinalGate has passed in the same chain. |
| `official_operation_layer` | Shows whether the official Operation Layer path is ready. |
| `active_position_open_order` | Turns active position or open-order conflicts into explicit blocked evidence. |
| `protection` | Shows missing protection as a submit blocker, not a project blocker. |
| `budget` | Shows missing budget as a submit blocker, not a project blocker. |
| `duplicate_submit` | Keeps duplicate-submit risk as a hard submit blocker. |
| `symbol_side_notional_leverage_scope` | Keeps symbol, side, notional, leverage, and exposure scope mismatches out of real submit. |
| `hard_safety` | Summarizes forbidden effects such as exchange write, order creation, bypass flags, withdrawal, or transfer. |

Each item carries `status`, `blocker_class`, `blocks_real_submit`, `detail`,
and `evidence`. Non-pass states can still allow watcher observation and project
progress, but any item with `blocks_real_submit=true` keeps
`ready_for_real_order_action=false`.

### 2026-06-17 False-Positive Hardening Checkpoint

The readiness matrix now uses explicit blocker-family matching for active
position, open order, and symbol/side/notional/leverage scope rows. Stale fact
names such as `open_order_facts_stale` block `required_facts` only; they must
not be misclassified as active position or open-order conflicts. Benign source
errors such as `symbol_read_error` also must not become scope blockers, while
true `scope_mismatch` and out-of-scope StrategyGroup signals still block real
submit.

### 2026-06-17 Submit-Boundary Closure Checkpoint

`Operation Layer evidence ready` is not sufficient by itself to open the real
order boundary. If any `real_order_readiness_matrix` item has
`blocks_real_submit=true`, `ready_for_real_order_action` must remain false and
the status artifact must record `matrix_submit_blocker:<key>`.

This keeps the project moving while preserving the live-funds boundary:

| Condition | Project behavior | Real submit behavior |
| --- | --- | --- |
| No fresh signal | Continue watcher observation | Closed |
| Fresh signal with candidate/auth/FinalGate progress | Continue automatic evidence chain | Closed until Operation Layer and matrix pass |
| Operation Layer evidence ready but matrix blocker exists | Record submit-blocker review evidence | Closed |
| Operation Layer evidence ready and matrix has no submit blockers | Call official Operation Layer only | Open inside selected Owner-allocated subaccount/profile boundary |

Submit blockers such as active position, open order, missing protection,
missing budget, duplicate-submit risk, and symbol/side/notional/leverage
mismatch therefore become reviewable evidence and Owner-readable status, not
per-strategy execution forks or opaque project-wide chat confirmations.

Regression coverage now exercises the full submit-blocker family while the
status artifact is otherwise `official_operation_layer_evidence_ready`: active position,
open order, missing protection, missing budget, duplicate submit, and
symbol/side/notional/leverage mismatch all keep
`ready_for_real_order_action=false` and emit `matrix_submit_blocker:<key>`.

`strategygroup-runtime-goal-status.json` also emits an explicit
`submit_blocker_review` object under `evidence` and mirrored fields under
`real_order_boundary`. When these blockers appear, the status artifact states:

| Field | Meaning |
| --- | --- |
| `submit_blocker_review.required=true` | Submit-blocker review evidence should be recorded. |
| `submit_blocker_review.project_progress_allowed=true` | The project can continue with review/repair work instead of waiting for chat confirmation. |
| `submit_blocker_review.continue_observation_allowed=true` | Watcher observation can continue while real submit stays closed. |
| `submit_blocker_review.real_submit_allowed=false` | No real exchange action is allowed until the blocker is resolved through the official path. |

The review object is limited to matrix rows with `status=blocked`. Natural
waiting states such as no fresh signal, candidate/auth not reached yet,
FinalGate not reached yet, or Operation Layer not reached yet keep real submit
closed but do not create a submit-blocker review requirement.

This makes active position, open order, missing protection, missing budget,
duplicate-submit risk, and symbol/side/notional/leverage mismatch reviewable
runtime evidence, not per-StrategyGroup execution forks.

## P0 Subgoal: Common Runtime Pipe Before Strategy-Specific Adapters

### Current Judgment

The current first-real-submit blocker mix is treated as:

| Share | Scope | Meaning |
| --- | --- | --- |
| 80% | Common runtime pipe | Fresh signal, RequiredFacts readiness, candidate/auth, FinalGate, Operation Layer evidence, live boundary enablement, submit, finalize, reconcile, settle, and Owner readmodel are shared infrastructure. |
| 20% | StrategyGroup adapter | Each StrategyGroup supplies signal semantics, RequiredFacts definitions, supported symbol/side, allocated risk/profile defaults, hard stops, and conflict policy. |

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

### 2026-06-17 Scoped Dry-Run Proof Tightening

The dry-run audit chain keeps `scenario_count=14` but now strengthens the
`scoped_pipeline_operation_layer_submit_projection` scenario:

```text
scoped pipeline evidence
-> dispatcher accepts Operation Layer evidence
-> handoff artifact is built from the same evidence IDs
-> official first-real-submit endpoint is called in disabled-smoke mode
-> dispatcher can also call the same endpoint in disabled-smoke mode
-> owner_confirmed_for_first_real_submit_action=false
-> no order, no OrderLifecycle call, no exchange write
```

This closes a rehearsal gap between generic mock disabled-smoke proof and the
real pipeline-shaped scoped local-registration evidence. The dispatcher mode is
selected explicitly with `--operation-layer-submit-mode disabled_smoke` and keeps
the existing real gateway action mode as the default. It is still not real
execution proof and does not authorize bypassing action-time FinalGate or the
official Operation Layer.

### 2026-06-17 Watcher Artifact Atomic Deploy Checkpoint

Tokyo is now deployed at
`0414db6fd1a3575d27019663fb39bfd91d5175db` through the bounded git deploy path.
This deploy is a runtime/watcher artifact durability repair, not a static client
publish and not a trading action.

| Item | Result |
| --- | --- |
| Release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-0414db6f-watcher-packet-atomic-writes` |
| Deploy apply | `status=applied`, `interaction.level=L3_bounded_deploy_apply`, `remote_interaction_count=7`, `blockers=[]` |
| Atomic artifact writes | `runtime-dry-run-audit-chain.json`, `runtime-execution-chain-closure-status.json`, `strategygroup-runtime-goal-status.json`, and compatibility artifact file `product-state-refresh-packet.json` now use temp-file replacement |
| Postdeploy snapshot | `status=ready`, `runtime_dry_run_audit_passed=true`, `runtime_execution_chain_closure_status_ready=true`, `watcher_timer_active=true`, `source_readiness_ready=true` |
| Objective chain | `ready_goal_chain_segments=6`, `missing_or_failed_goal_chain_segments=[]` |
| Runtime progress | `P0=waiting_for_market`, `Signal Observation grade=ready`, `product_gaps=[]`, `blockers=[]` |
| Safety proof | Deploy and postdeploy checks did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secret mutation, live profile mutation, or order-sizing mutation |

The static Owner Console product client has already been removed from this main
runtime worktree. Static client experiments and future product-client implementation
remain external and do not affect watcher, dry-run audit, FinalGate readiness,
Operation Layer evidence preparation, or runtime monitoring.

### 2026-06-17 Local Dry-Run Deploy-Channel Context Checkpoint

`strategygroup-runtime-goal-status` now separates local dry-run goal audit from
deployment-head verification. A degraded `deploy_channel` source-health item is
still recorded as evidence, but it only becomes a `deployment_issue` blocker
when the caller provides an explicit deployment context such as
`--release-manifest` or `--expected-head`.

| Context | Deploy-channel degraded behavior |
| --- | --- |
| Local dry-run / goal rehearsal without deployment baseline | Evidence only; do not turn a healthy dry-run chain into `deployment_issue` |
| Tokyo watcher or explicit release/head verification | Blocking `deployment_issue`; real submit remains closed |
| Real-order boundary | Deploy channel evidence alone never opens submit; fresh signal, live facts, candidate/auth, FinalGate, Operation Layer, budget, protection, idempotency, scope, and safety all still need to pass |

This keeps the non-market rehearsal chain useful when the local machine lacks
Tokyo SSH public-key access, while preserving fail-closed deploy verification on
the server path.

### 2026-06-17 Snapshot Goal-Status Nested Checks Checkpoint

The low-interaction Tokyo snapshot now reads `strategygroup-runtime-goal-status`
checks from the nested `checks` object as well as top-level compatibility
fields. This keeps the Owner progress layer from losing important goal-loop
facts when the artifact is produced by the current builder.

| Field | Snapshot behavior |
| --- | --- |
| `checks.fresh_signal_present` | Projected into the compact `goal_status` summary as explicit `true` / `false` |
| `checks.deployment_aligned=false` | Blocks the snapshot as `runtime_goal_status_deployment_not_aligned` |
| `checks.watcher_liveness_healthy=false` | Blocks the snapshot as `watcher_liveness_not_healthy` |

This is a monitoring/readability repair only. It does not call FinalGate,
Operation Layer, exchange write, OrderLifecycle, or any real-order path.

### 2026-06-17 Closure Segment Evidence Map Checkpoint

`runtime-execution-chain-closure-status.json` now includes
`dry_run_chain.goal_chain_segment_evidence`. Each objective segment maps back
to both the required dry-run checks and the specific scenario names that proved
the segment.

| Objective segment | Evidence examples |
| --- | --- |
| `fresh_or_mock_signal` | `fresh_signal_fast_auto_chain_checked`, `mock_fresh_signal_dry_run_pass` |
| `required_facts_readiness` | `required_facts_readiness_checked`, `required_facts_missing` |
| `candidate_authorization_evidence` | `execution_attempt_rehearsal_prepare_checked`, `execution_attempt_rehearsal_prepare` |
| `action_time_finalgate` | `all_selected_strategygroups_reach_finalgate_dispatch_checked`, `execution_attempt_rehearsal_prepare` |
| `official_operation_layer_evidence_relay_projection` | `operation_layer_evidence_relay_checked`, `scoped_pipeline_operation_layer_submit_projection` |
| `disabled_dry_run_proof` | `disabled_smoke_not_real_execution_proof`, `mock_operation_layer_submit_finalize_pass` |

This makes the non-market closure proof auditable from one artifact without
re-reading all raw dry-run artifacts. It remains non-executing and does not
promote disabled smoke into real execution proof.

### 2026-06-17 Closure Evidence Map Deploy Checkpoint

Tokyo is now deployed at
`6a49b8ba9904a10d21f52e946e84bd33d494af84` through the bounded git deploy
path. This deploy publishes the non-market closure evidence map and the latest
monitoring/readability repairs. It does not publish or depend on a static client.

| Item | Result |
| --- | --- |
| Release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-6a49b8ba-closure-evidence-map` |
| Deploy apply | `status=applied`, `interaction.level=L3_bounded_deploy_apply`, `remote_interaction_count=7`, `blockers=[]` |
| Postdeploy snapshot | `status=ready`, `watcher_timer_active=true`, `runtime_dry_run_audit_passed=true`, `runtime_execution_chain_closure_status_ready=true`, `source_readiness_ready=true` |
| Goal status | `waiting_for_signal`, `fresh_signal_present=false`, `ready_for_real_order_action=false` |
| Objective chain | `ready_goal_chain_segments=6`, `missing_or_failed_goal_chain_segments=[]` |
| Safety proof | Deploy and postdeploy checks did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secret mutation, live profile mutation, or order-sizing mutation |

The local low-interaction snapshot reader now also projects
`goal_chain_segment_evidence` from the closure artifact, so one snapshot can show
which dry-run scenarios proved each objective segment.

### 2026-06-17 Pilot Confidence Floor Checkpoint

The StrategyGroup handoff `confidence_min` floor is aligned with the current
pilot reference evaluators. The previous `0.70` floor could block otherwise
valid pilot ready signals before candidate preparation because current pilot
ready-signal evaluators emit `0.58` to `0.62`.

| Item | Result |
| --- | --- |
| Updated handoffs | `MPG-001`, `TEQ-001`, `FBS-001`, `PMR-001`, `SOR-001` |
| Pilot floor | `confidence_min=0.58` |
| Meaning | Candidate-preparation floor only; not execution authority |
| Execution boundary | FinalGate and Operation Layer still required |
| Safety proof | Local tests and dry-run audit only; no Tokyo call, server mutation, exchange write, OrderLifecycle call, or real order |

This checkpoint removes an internal self-contradiction in the fresh-signal fast
chain without expanding symbol, side, notional, leverage, live profile,
credentials, or order-sizing defaults.

### 2026-06-17 Runtime Exit Hardening Checkpoint

The first live-order pilot treats an active position as protected only when the
system can see an exchange-native reduce-only stop. A local SL record is a
useful intent/projection fact, but it is not sufficient to prove live
runaway-loss protection on the exchange.

| Item | Result |
| --- | --- |
| Exchange-native hard stop | `runtime_live_position_monitor` now requires an exchange reduce-only stop for active-position hard-stop protection |
| Local-only SL | A local SL record without exchange stop evidence produces `active_position_missing_hard_stop` plus `local_sl_record_present_but_exchange_native_stop_missing` |
| Holding rule | `can_continue_holding` requires active position, fresh exchange facts, clean severe reconciliation, and exchange-native hard stop |
| TP1 rule | TP1 remains a right-tail exit-plan review shape: default 50% at 1R; when quantity is below market minimum/step, the system keeps hard-stop-only or routes to full reduce-only close review instead of faking a TP order |
| Runner first-stage rule | Runner management is `structure_invalidation_first`; ATR trailing and time stop are review-only helpers; first stage does not auto-amend stops or create runner exit orders |
| Protection failure rule | Entry fill with protection creation failure remains a recovery state: consume/account attempt, hold/reconcile budget, block new entries, require reconciliation, recovery review, and reduce-only recovery mode |
| Standing reduce-only recovery | Protection-failure recovery uses standing authorization plus action-time FinalGate and official Operation Layer; it must not reintroduce per-order Owner chat confirmation |
| Post-submit exit outcome matrix | The dry-run audit now names six non-executing post-submit outcomes: entry filled + protection ok, entry filled + protection failed, partial fill, exchange submit failed before acceptance, active position remains open, and position closed by SL / TP / reduce-only recovery |
| Required-check promotion | `post_submit_exit_outcome_matrix_checked` is now a top-level required dry-run check consumed by goal status, Tokyo snapshot, and chain-closure status |
| Safety proof | Local tests only; no Tokyo call, server mutation, FinalGate call, Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secret mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-17 StrategyGroup Runtime Tier Policy Checkpoint

StrategyGroup expansion is now separated from first-live-order eligibility.
New strategy groups can enter the catalog or observation layers without
competing with the first selected `MPG-001` allocated-subaccount real-order
loop.

| Item | Result |
| --- | --- |
| Tier model | `L0 catalog_only`, `L1 observe_only`, `L2 shadow_candidate`, `L3 armed_observation`, `L4 tiny_real_order_eligible` as a legacy compatibility label for allocated-subaccount real-order eligibility |
| Current L4 lane | Only `MPG-001` is `L4` for the first bounded live-order pilot |
| Current non-L4 lanes | `TEQ-001=L2`, `BTPC-001=L2`, `FBS-001=L3`, `SOR-001=L3 conditional`, `PMR-001=L1` |
| New group default | `BRF`, `VCB`, `LSR`, and `RBR` default to `L1 observe_only` unless reviewed and promoted |
| Safety proof | Tier policy is not execution authority, FinalGate input, Operation Layer input, live-profile change, or sizing default |

### 2026-06-17 Runtime Monitor Exit Matrix Schema Checkpoint

The low-noise runtime monitor now treats the post-submit exit outcome matrix as
part of the objective-chain progress surface. Fresh local closure artifacts
already prove seven objective segments; the daily-check cache schema is bumped
so old six-segment cache artifacts cannot remain quietly accepted after this
P0 exit-hardening change.

| Item | Result |
| --- | --- |
| Daily-check schema | `DAILY_CHECK_REPORT_SCHEMA_VERSION=5` |
| Objective chain | `ready_goal_chain_segments=7`, `missing_or_failed_goal_chain_segments=[]` when the exit outcome matrix is present |
| Added segment | `post_submit_exit_outcome_matrix` |
| Cache behavior | Older six-segment cache is treated as `runtime_progress_cache_schema_stale` and refreshed through the normal low-noise path |
| Owner progress | Engineering rehearsal evidence now reports `goal_chain_ready_segments=7` after refresh |
| Safety proof | This is monitor/reporting-only; it does not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secret mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-18 StrategyGroup Tier Policy Dry-Run Checkpoint

StrategyGroup tier governance is now part of the non-executing dry-run audit
chain instead of remaining only a planning document. This makes strategy
expansion auditable without letting new StrategyGroups compete with the first
selected `MPG-001` allocated-subaccount real-order loop.

| Item | Result |
| --- | --- |
| Required dry-run checks | `runtime_tier_policy_checked`, `only_mpg_tiny_real_order_eligible_checked`, and `new_strategygroups_default_observe_only_checked`; legacy `tiny` names mean allocated-subaccount bounded-aggressive eligibility |
| Current L4 lane | Only `MPG-001` may be `tiny_real_order_eligible` for the first allocated-subaccount live-order pilot |
| New group default | `BRF`, `VCB`, `LSR`, and `RBR` must remain `L1 observe_only` unless promoted through reviewed intake; `BTPC-001` has passed reviewed intake and is now `L2 shadow_candidate` only |
| Shared pipeline | Tier policy is validated as an input boundary; it does not define candidate, FinalGate, Operation Layer, submit, finalize, reconciliation, budget settlement, live profile, or sizing defaults |
| Daily-check schema | `DAILY_CHECK_REPORT_SCHEMA_VERSION=6` so cache artifacts that predate the tier-policy required checks are refreshed |
| Safety proof | This is dry-run/reporting-only; it does not call Tokyo, FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secret mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-18 StrategyGroup Tier Policy Deploy Checkpoint

The tier-policy dry-run required checks were pushed and deployed to Tokyo
through the bounded git deploy path. The postdeploy daily check accepted the
new runtime head and reported healthy waiting-for-market state.

| Item | Result |
| --- | --- |
| Deployed runtime head | `dc58c7506aca99e011101f2f2e2641798bffcd6a` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-dc58c750-tier-policy-dry-run` |
| Runtime deploy apply | `status=applied`, `interaction.level=L3_bounded_deploy_apply`, `remote_interaction_count=7`, `blockers=[]` |
| Postdeploy daily check | `status=waiting_for_market`, `blockers=[]`, `product_gaps=[]`, `warnings=[]` |
| Required dry-run checks | `runtime_dry_run_missing_required_checks=[]` |
| Goal progress | `P0=waiting_for_market`, `Signal Observation grade=ready`, `owner_intervention_required=false` |
| Safety proof | Deploy and postdeploy checks did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secret mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Exchange-Native Hard Stop Shape Checkpoint

The active-position exit surface now accepts the common CCXT/Binance stop-order
shape where `reduceOnly` is nested under `info.reduceOnly`. This fixes a false
`active_unprotected` classification when a real exchange-native reduce-only
stop exists but the reduce-only marker is not projected to the top level.

| Item | Result |
| --- | --- |
| Root cause | `runtime_live_position_monitor` previously checked only top-level `reduceOnly` when proving an exchange-native hard stop |
| Fix | Hard-stop proof now accepts top-level `reduceOnly` or nested `info.reduceOnly` when a stop/trigger price is present |
| Boundary retained | A local SL record without exchange-native stop evidence still blocks with `active_position_missing_hard_stop` |
| Restored surfaces | live-position monitor, active-position exit plan, and post-close follow-up can proceed when the exchange-native stop is actually visible |
| Safety proof | Local tests only; no Tokyo call, server mutation, FinalGate call, Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secret mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-18 Nested Hard Stop Deploy Checkpoint

The exchange-native hard-stop shape fix was pushed and deployed to Tokyo through
the bounded git deploy path. Postdeploy acceptance reported a healthy
waiting-for-market state.

| Item | Result |
| --- | --- |
| Deployed runtime head | `001bf2667a766279fba928215780ad94fa0d6370` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-001bf266-nested-hard-stop` |
| Runtime deploy apply | `status=applied`, `interaction.level=L3_bounded_deploy_apply`, `remote_interaction_count=7`, `blockers=[]` |
| Deploy session | `status=waiting_for_market`, total remote interactions `8` including one L1 postdeploy daily check |
| Postdeploy daily check | `status=waiting_for_market`, `blockers=[]`, `product_gaps=[]`, `warnings=[]` |
| Monitor baseline | `expected_runtime_head=001bf2667a766279fba928215780ad94fa0d6370` |
| Safety proof | Deploy and postdeploy checks did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secret mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Post-Submit Closure Truth Local Checkpoint

The first bounded live-order closure chain now requires post-submit closure
truth, not only post-submit evidence IDs. This keeps the official runtime path
from treating a present `submit_outcome_review_id` or
`post_submit_budget_settlement_id` as proof that finalize, reconciliation,
budget settlement, and review actually completed.

| Item | Result |
| --- | --- |
| Domain contract | `RuntimePostSubmitFinalizePacket` now emits `post_submit_reconciliation_evidence_id`, `post_submit_finalize_complete`, `post_submit_reconciliation_matched`, `post_submit_budget_settled`, and `submit_outcome_review_recorded` |
| Dispatcher guard | `runtime_signal_watcher_resume_dispatcher.py` blocks `finalized_ready_for_next_attempt` when any close-loop truth field is absent or false |
| Dry-run audit | `post_submit_closed_loop_evidence_guard` now covers missing reconciliation evidence plus false finalize/reconciliation/budget/review truth cases |
| Official proof | `runtime_official_post_submit_finalize_proof.py` carries the same close-loop truth fields into its proof artifact and top-level report |
| Local validation | `python3 -m py_compile ...`; targeted tests `54 passed`; expanded post-submit/closure/readmodel tests `314 passed, 1 skipped`; dry-run audit `status=passed` |
| Current owner progress | `status=not_complete_runtime_processing`, `non_market_gaps=0`, `Signal Observation grade=ready`, `owner_intervention_required=false`, `remote_interaction_count=0` for goal-progress; one L1 read-only daily-check refresh reported `remote_interaction_count=1` |
| Deployment | Not deployed in this checkpoint; deploy only after a stage-worthy batch or explicit Owner request |
| Safety proof | Local tests and one read-only cache refresh only; no server file mutation, FinalGate call, Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secret mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Live Closure Evidence Source Filter Checkpoint

Postdeploy acceptance for `90ab93c1` exposed a product-state false alarm:
`runtime-live-closure-evidence.json` was rebuilt as an official live closure
artifact from passive runtime reports such as handoff/intake, goal-status, and
waiting-for-market resume artifacts. Those reports can carry sample or stale
signal/candidate IDs, but they are not official closure sources.

| Item | Result |
| --- | --- |
| Root cause | `refresh_runtime_live_closure_evidence_artifacts.py` included every non-dry-run JSON in the watcher report directory and then marked the aggregate as `official_live_closure_evidence`; the old packet-named command has been removed |
| Symptom | Fresh postdeploy daily check returned `degraded` with `live_closure_evidence:*_mismatch` and `*_missing` product gaps despite no exchange write and no real submit |
| Fix | Passive report scopes such as `handoff`, `intake`, `goal_status`, `product_state_refresh`, `source_readiness`, `deployment_readiness`, `bootstrap`, and observation reports are skipped before live closure artifact assembly |
| Read-error behavior | Malformed historical JSON artifacts in the long-running watcher report directory are recorded in `read_errors` but do not fail the default refresh; `--strict-read-errors` keeps the blocker behavior available for strict offline audits |
| Preserved path | Real closure sources still include live signal, RequiredFacts/live facts, candidate authorization, action-time FinalGate, Operation Layer, exchange submit, hard stop/protection, reconciliation, settlement, and review markers |
| Validation | `py_compile` passed; `119 passed` across `test_refresh_runtime_live_closure_evidence_artifacts.py`, `test_strategygroup_runtime_product_state_refresh.py`, `test_tokyo_runtime_snapshot.py`, `test_strategygroup_runtime_daily_check.py`, `test_strategygroup_runtime_goal_progress_audit.py`, `test_runtime_first_bounded_live_order_completion_audit.py`, and `test_tokyo_runtime_deploy_session.py` |
| Deployment | Stage-worthy because Tokyo currently regenerates a false official closure artifact; deploy in the next bounded git apply only |
| Safety proof | Local script/tests only in this checkpoint; no FinalGate call, Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secret mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Closure Truth And Source Filter Deploy Checkpoint

The first bounded live-order closure fixes were deployed through the bounded git
deploy path. The final postdeploy acceptance is `processing`, not complete:
there is still no first bounded real-order closure proof, but non-market
product gaps and blockers are cleared.

| Item | Result |
| --- | --- |
| Post-submit closure truth deploy | `90ab93c1d3f9623ebc6a579d8ed5365cf4051df5` deployed as `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-90ab93c1-closure-truth` |
| Source filter deploy | `a57f3c5e54f1de56a266c229d0051319901a7ef3` deployed as `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-a57f3c5e-live-closure-source-filter` |
| Read-error tolerance deploy | `1eccf446c393ac58095a4174ec0730d8f53bf99b` deployed as `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-1eccf446-closure-read-error-tolerance` |
| Final postdeploy acceptance | `output/tokyo-runtime-deploy-session-1eccf446.json`: `status=processing`, `blockers=[]`, `product_gaps=[]`, `warnings=[]`, total remote interactions `8` |
| Monitor baseline | `docs/current/RUNTIME_MONITOR_BASELINE.json` now expects runtime head `1eccf446c393ac58095a4174ec0730d8f53bf99b` |
| Current P0 state | `processing`; first bounded real-order closure is not complete because real action-time FinalGate, official Operation Layer submit, exchange acceptance, and post-submit reconciliation remain market-dependent |
| Safety proof | Deploy and postdeploy checks did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secret mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Stale Wakeup Waiting Resume Local Checkpoint

The low-noise monitor exposed a status-classification edge case: a stale
`wakeup-evidence.json` could still push the Owner progress layer into
`fresh_signal_processing` even when the authoritative `latest-summary`,
`post-signal-resume-pack`, `resume-dispatch-artifact`, and pilot status had
already returned to waiting-for-market semantics.

| Item | Result |
| --- | --- |
| Root cause | `_current_status` still considered `wakeup-evidence.json` fresh-chain statuses even after `_has_fresh_signal` had correctly returned `false` |
| Fix | `build_strategygroup_runtime_goal_status.py` now returns `waiting_for_signal` when fresh signal is absent and authoritative latest/post-resume evidence is waiting; `wakeup` participates in chain progression only when `fresh_signal_present=true` |
| Regression test | Added `test_goal_status_ignores_stale_wakeup_when_resume_waits_for_market` |
| Validation | `test_strategygroup_runtime_goal_status.py`: `32 passed`; monitor/readmodel suite: `122 passed`; expanded runtime monitor/deploy-session suite: `151 passed`; py_compile passed |
| Deployment | Not deployed in this checkpoint; deploy only after batching or if the Tokyo monitor keeps emitting false processing from stale wakeup evidence |
| Safety proof | Local code/tests/cache reads only; no server file mutation, FinalGate call, Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secret mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Stale Wakeup Waiting Resume Deploy Checkpoint

The stale-wakeup status fix was deployed because the live monitor kept reading
the old server-side goal-status artifact as `processing`. After deploy and one
fresh L1 postdeploy check, the server-side Owner progress layer returned to
healthy waiting-for-market semantics.

| Item | Result |
| --- | --- |
| Deployed runtime head | `6239199be96111585e9d1b2bf51816b2d71746b0` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-6239199b-stale-wakeup-waiting-resume` |
| Runtime deploy apply | `output/tokyo-git-deploy-apply-6239199b.json`: `status=applied`, interaction `L3_bounded_deploy_apply`, remote interactions `7` |
| Deploy session | `output/tokyo-runtime-deploy-session-6239199b.json`: `status=waiting_for_market`, remote interactions `8`, blockers/product gaps/warnings all empty |
| Daily check cache | `output/runtime-monitor/latest-daily-check.json`: `status=waiting_for_market`, notification `DONT_NOTIFY`, waiting keys `fresh_signal`, `candidate_authorization`, `action_time_finalgate`, `official_operation_layer` |
| Goal progress | `output/runtime-monitor/latest-goal-progress.json`: `status=waiting_for_market`, `Signal Observation grade=ready`, blockers/product gaps empty |
| Completion audit | `output/runtime-monitor/latest-p0-live-order-closure-completion-audit.json`: `not_complete_waiting_for_market`, non-market gaps empty, market-dependent remaining `5` |
| Monitor baseline | `docs/current/RUNTIME_MONITOR_BASELINE.json` now expects runtime head `6239199be96111585e9d1b2bf51816b2d71746b0` |
| Safety proof | Deploy and postdeploy checks did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secret mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Local Monitor Sequence Checkpoint

### 2026-06-18 Standing First-Real-Submit Authorization Checkpoint

The first-real-submit execute flow no longer treats the legacy
`OWNER_APPROVED_RUNTIME_FIRST_REAL_SUBMIT` env value as mandatory when the
runtime is using the selected bounded standing authorization path. This keeps
the first bounded live-order cutover aligned with the current operating model:
inside selected StrategyGroup, allocated subaccount boundary, fresh signal,
RequiredFacts, candidate/auth evidence, action-time FinalGate, and official
Operation Layer, the system should not ask for another per-order chat
confirmation.

| Item | Result |
| --- | --- |
| Removed non-market blocker | `--standing-authorized-first-real-submit` satisfies the first-real-submit execution guard without the legacy env string |
| Preserved hard gates | `--execute-real-submit`, prearmed evidence ids, action-time FinalGate, official Operation Layer, protection, idempotency, deployment readiness, and post-submit accounting remain required |
| Followup next step | Disabled-smoke completion now points to waiting for a fresh signal and then running the standing-authorized official Operation Layer chain |
| Local validation | `py_compile` passed; first-real-submit API flow, action authorization evidence, and active-observation followup tests: `57 passed` |
| Deployment | Not deployed; batch with the next stage-worthy runtime cutover fix or fresh-signal unblock |
| Safety proof | Local code/tests only. No server file mutation, FinalGate call, Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secret mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Operation Layer Standing Authorization Relay Checkpoint

The automatic resume dispatcher now makes the first bounded live-order cutover
authorization model explicit all the way to the official Operation Layer submit
payload. The official endpoint still receives
`owner_confirmed_for_first_real_submit_action=true` for real submit, but the
dispatcher now records that this is satisfied by standing authorization inside
the selected StrategyGroup and allocated subaccount boundary, not by a new
per-order chat confirmation.

| Item | Result |
| --- | --- |
| Automatic path | `runtime_signal_watcher_resume_dispatcher.py` carries `standing_authorized_first_real_submit=true`, `owner_chat_confirmation_required_for_real_submit=false`, and `legacy_owner_confirmation_env_required=false` in Operation Layer command and submit payloads |
| Regression guard | Official Operation Layer submit is blocked before POST if the payload regresses to missing standing authorization, chat confirmation required, or legacy env required |
| Disabled smoke boundary | Disabled smoke keeps `standing_authorization_consumed_for_real_submit=false`, so it remains rehearsal proof only |
| Local validation | `py_compile` passed; dispatcher tests: `40 passed` |
| Local monitor sequence | `status=waiting_for_market`, blockers empty, non-market gaps empty, remote interactions `0` |
| Deployment | Not deployed; batch with the next stage-worthy runtime cutover fix or fresh-signal unblock |
| Safety proof | Local code/tests/cache reads only. No server file mutation, FinalGate call, Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secret mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-18 Standing Authorization Dry-Run Audit Checkpoint

The first-live submit standing authorization relay is now a required local
dry-run audit check. This means the quiet monitor can detect a regression where
the automatic Operation Layer path starts requiring per-order chat confirmation
or the legacy `OWNER_APPROVED_RUNTIME_FIRST_REAL_SUBMIT` env gate again.

| Item | Result |
| --- | --- |
| New required check | `operation_layer_standing_authorization_relay_checked=true` |
| Relay details | `operation_layer_relay_checks` proves standing authorization is bound, chat confirmation is not required, and the legacy env gate is not required |
| Monitor integration | Daily check and goal-progress entry fast-chain readiness include the new required check |
| Local validation | `py_compile` passed; dry-run, goal-progress, and daily-check tests: `67 passed` |
| Local artifact refresh | `output/runtime-monitor/latest-runtime-dry-run-audit-chain.json` now reports `operation_layer_standing_authorization_relay_checked=true` |
| Local monitor sequence | `status=waiting_for_market`, blockers empty, non-market gaps empty, remote interactions `0` |
| Deployment | Not deployed; this is local audit/monitor hardening |
| Safety proof | Local code/tests/cache reads only. No server file mutation, FinalGate call, Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secret mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-19 Observation Decision Loop Gap Closure Checkpoint

The Signal Observation grade local loop now stops treating broader observe-only
would-enter rows as unreviewed once the opportunity review work loop has converted
them into repeatable decision output. This keeps the roadmap focused on useful
next work instead of re-reporting an already reviewed observation-scope item.

| Item | Result |
| --- | --- |
| Closed loop | `opportunity_review_work_loop=review_work_loop_ready` clears `observation_scope_expansion_review_needed` when no conditional L2 dry-run or tier-policy update is pending |
| Preserved escalation | Actual conditional L2 intake/tier updates, failed dry-runs, and forbidden effects still remain non-market gaps |
| Current local run | `output/runtime-monitor/latest-local-monitor-sequence.json`: blockers empty, non-market gaps empty, remote interactions `0`, server mutation `false`, approaches real order `false` |
| Remaining state | `needs_refresh` comes from monitor cache freshness, not from opportunity review or live-order readiness |
| Deployment | Not deployed; this is local monitor sequence logic only |
| Safety proof | No server file mutation, FinalGate call, Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secret mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-19 Priority-Aware Observation Expansion Checkpoint

The opportunity discovery path now distinguishes high-priority Signal
Observation grade / P1 would-enter observations from low-priority parked
observations before they become roadmap pressure. This keeps the main loop
focused on opportunity quality and replay closure, not on reviving parked
vocabulary.

| Item | Result |
| --- | --- |
| Priority join | Signal coverage expansion rows include policy priority, L2 readiness, and recommended action from `main-control-signal-coverage-expansion-policy.json` |
| Current RBR handling | RBR would-enter is recorded as `low_priority_observe_only_would_enter_parked`, not as a Signal Observation expansion push |
| High-priority preservation | Signal Observation grade / P1 rows still trigger `review_needed_broader_observe_only_would_enter` |
| Current local run | `output/runtime-monitor/latest-local-monitor-sequence.json`: expansion review low-priority parked, blockers empty, non-market gaps empty, remote interactions `0`, server mutation `false`, approaches real order `false` |
| Deployment | Not deployed; local diagnostic classification only |
| Safety proof | No server file mutation, FinalGate call, Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secret mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-19 Priority-Aware Signal Coverage Diagnostic Checkpoint

The first coverage diagnostic now shares the same priority classification as
the expansion review, so a low-priority parked would-enter observation no
longer looks like a high-priority coverage gap at the top of the local monitor
sequence.

| Item | Result |
| --- | --- |
| Diagnostic status | RBR/P2 parked would-enter now reports `mainline_no_signal_low_priority_broader_would_enter` |
| Count split | Diagnostic output separates actionable and low-priority broader would-enter counts |
| Current local run | `output/runtime-monitor/latest-local-monitor-sequence.json`: signal coverage low-priority parked, expansion review parked, blockers empty, non-market gaps empty, remote interactions `0` |
| P0 posture | First bounded live-order path remains ready/waiting; low-priority observation work does not interrupt selected StrategyGroup readiness |
| Deployment | Not deployed; local diagnostic classification only |
| Safety proof | No server file mutation, FinalGate call, Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secret mutation, live profile mutation, order-sizing mutation, or real order |

### 2026-06-19 High-Priority No-Action Diagnostic Checkpoint

No-signal periods now produce useful high-priority no-action review input. The
diagnostic does not only report whether would-enter exists; it also shows which
Signal Observation grade / P1 StrategyGroups are visible, not triggering, and
why.

| Item | Result |
| --- | --- |
| High-priority no-action | Diagnostic emits `broader_observation.high_priority_no_action_signals` with policy priority, L2 readiness, recommended action, and reason codes |
| Current rows | `BRF-001`, `BTPC-001`, `LSR-001`, and `VCB-001` are present as high-priority no-action observations |
| Use | These rows become local review/replay input for opportunity discovery without waiting for a live signal |
| Boundary | No-action rows remain non-executing and cannot authorize candidate/auth, FinalGate, Operation Layer, exchange write, or real order |
| Deployment | Not deployed; local diagnostic enrichment only |
| Safety proof | No server file mutation, FinalGate call, Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secret mutation, live profile mutation, order-sizing mutation, or real order |

## Boundaries

- Keep static product-client experiments outside mainline; the Owner Console source-readiness
  contract remains mainline-owned in `/Users/jiangwei/Documents/final`.
- Keep strategy research in `/Users/jiangwei/Documents/final-strategy-research`.
- Keep main runtime work in `/Users/jiangwei/Documents/final`.
- Do not expose internal gate names as primary Owner labels.
- Do not treat weak strategy evidence as a live-safety blocker.
- Do not treat missing audit detail as a reason to hide StrategyGroups.
