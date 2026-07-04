---
title: STRATEGYGROUP_REGISTRY_CONTRACT
status: CURRENT_PILOT_CONTRACT
authority: docs/current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md
last_verified: 2026-06-23
---

# StrategyGroup Registry Contract

## Purpose

The StrategyGroup Registry is the Owner-readable strategy asset layer for the
StrategyGroup runtime-governance pilot.

It answers:

```text
What does this StrategyGroup eat?
How does it trade?
Which tier is it allowed to reach?
Which Tradeability Decision and Runtime Safety State summarize current runtime authority?
What risks or evidence gaps remain?
What would promote, downshift, park, or kill it?
```

It is not a runtime database, a Strategy Picker implementation, FinalGate
input, Operation Layer input, exchange-write authority, live-profile authority,
or order-sizing authority.

## Relationship To Existing Artifacts

| Artifact | Role |
| --- | --- |
| Research Strategy Cabinet | Research-side shelf of strategy semantics and evidence |
| StrategyGroup handoff pack | Reviewed main-control intake artifact for one StrategyGroup |
| StrategyGroup Registry | Owner-readable asset registry contract for strategy governance |
| Runtime tier policy | Defines what each tier may do |
| Strategy Asset State evidence | Records current keep, revise, promote, park, kill, go-live, do-not-go-live, or safety-block evidence |
| Tradeability Decision | Records whether the strategy can trade now and the first blocker when it cannot |
| Review Ledger | Records real action outcomes and post-trial learning |

The registry should summarize handoff and research evidence. It must not copy
large replay corpora or raw packet details into the main-control layer.

## Governance Authority

The registry supports this authority split:

```text
Owner controls policy.
System executes process.
Tradeability Decision answers can-trade; Runtime Safety State answers live-submit safety.
Review updates strategy governance.
```

The Owner may use the registry to decide whether a StrategyGroup should be
enabled, paused, promoted, downshifted, parked, killed, or accepted for a scoped
risk tier. The registry must not require the Owner to manually assemble
RequiredFacts, validate fresh signals, inspect candidate/auth evidence, judge
FinalGate, or operate the Operation Layer.

Registry and Owner policy may make a StrategyGroup `trial_eligible`. Only the
Tradeability Decision may answer whether it can trade now. Only Runtime Safety
State may answer whether live-submit safety is currently satisfied.

The registry may support those read models, but it must not compute live
actionability or live order authority by itself. Registry rows explain asset
admission, policy scope, risk envelope, and hard blocks. Tradeability Decision
and Runtime Safety State decide whether the current market moment can actually
enter the official path.

## Required Registry Fields

Each StrategyGroup registry row should define these fields:

| Field | Meaning |
| --- | --- |
| `strategy_group_id` | Stable StrategyGroup identifier |
| `owner_label` | Short Owner-readable name |
| `edge_thesis` | Market opportunity the StrategyGroup is designed to capture |
| `trade_logic` | Plain-language entry, direction, and exit/protection idea |
| `regime_fit` | Market regime, session, product class, or crowding context where it belongs |
| `supported_sides` | Allowed side set, such as long, short, overlay, or context-only |
| `default_tier` | Default runtime-governance tier |
| `trial_eligible` | Whether the StrategyGroup may be considered for small-capital trial eligibility |
| `tradeability_stage` | Lifecycle stage, such as `tiny_live_intake_candidate`, `trial_asset_admission_candidate`, `admitted_trial_asset`, `armed_observation`, `tiny_live_ready`, or `live_submit_ready` |
| `first_tradeability_blocker` | Current first non-runtime reason it cannot trade, when known |
| `tradeability_decision_ref` | Reference to the generated Tradeability Decision when a current can-trade answer is needed |
| `runtime_safety_state_ref` | Reference to the generated Runtime Safety State when live-submit safety is needed |
| `risk_gaps` | Strategy risks the Owner may accept or reject |
| `hard_blocks` | Mechanical or authority issues the Owner cannot override |
| `required_facts_summary` | Human-readable RequiredFacts summary by market, strategy, derivatives, risk, account, exchange |
| `promotion_gate` | Evidence needed to move to a higher tier |
| `downshift_rule` | Conditions that move a StrategyGroup to a lower tier or disable candidate preparation |
| `park_rule` | Conditions that keep it inactive without deleting the idea |
| `kill_condition` | Conditions that remove it from active strategy allocation |
| `evidence_refs` | Links to handoff packs, replay summaries, Strategy Asset State evidence rows, or Review Ledger rows |
| `authority_boundary` | Explicit statement that the row does not authorize real orders |

## Trial Eligibility And Runtime Authority

The registry must separate strategy eligibility from action-time execution:

| Boundary | Meaning | Source |
| --- | --- | --- |
| `trial_eligible` | This StrategyGroup is allowed to enter the small-capital trial candidate pool under scoped Owner policy | Registry plus Owner policy |
| Tradeability Decision | Current can-trade answer and first blocker | Generated Tradeability Decision |
| Runtime Safety State | Current live-submit safety answer for the official path | Generated Runtime Safety State |

No fresh signal means the Tradeability Decision reports market wait. It does
not necessarily mean `trial_eligible=false`.

## Tradeability Stages

The registry should make the path from research to trading explicit:

| Stage | Registry meaning | Real order |
| --- | --- | --- |
| `tiny_live_intake_candidate` | Research-side asset is worth main-control review | No |
| `trial_asset_admission_candidate` | Main control is preparing final-owned admission | No |
| `admitted_trial_asset` | Asset exists in final-owned governance scope | No |
| `armed_observation` | Runtime may observe the asset under scoped rules | No |
| `tiny_live_ready` | Non-executing readiness is closed | No, unless action-time chain later passes |
| `live_submit_ready` | Current runtime state says official submit path may proceed | Yes, only through official gates |

The registry should not display a candidate as merely `waiting_for_market`
unless it is already admitted, scoped, armed, and non-live readiness is closed.
Before that, the first blocker is usually asset admission, Owner policy, facts,
strategy quality, or a hard safety boundary.

## Risk Classes

The registry must separate strategy risk from execution safety:

| Risk class | Examples | Owner can accept? |
| --- | --- | --- |
| `strategy_quality_risk` | Thin sample, weak replay, classifier uncertainty, false breakout risk, right-tail instability | Yes, if scoped |
| `fact_coverage_risk` | Missing OI history, top-trader ratio, funding windows, session transfer evidence | Yes for L1/L2/L3; not for action-time facts that are required for execution |
| `economic_risk` | Fee, funding, slippage, spread, min-notional, fill-slot uncertainty | Yes when scoped; cannot bypass exchange-rule facts |
| `execution_safety_risk` | Stale facts, missing protection, duplicate submit, conflicting position/open order, wrong scope | No |
| `authority_risk` | FinalGate bypass, Operation Layer bypass, live-profile mutation, sizing-default expansion, withdrawal, transfer, credential mutation | No |

Owner risk acceptance can advance trial or observation eligibility. It cannot
override execution safety or authority hard stops.

Strategy quality risk should become a tier, revise, park, or kill decision. It
should not silently become a request for the Owner to manually operate the
execution chain.

## Experiment Evaluation Semantics

Registry review follows
`docs/current/STRATEGY_EXPERIMENT_EVALUATION_CONTRACT.md`.

Do not use fixed return thresholds or arbitrary leverage caps as the registry's
primary pass/fail language. A high-return number such as `100%` is a right-tail
aspiration anchor and priority signal. A leverage number such as `5x` is a
scenario for liquidation, path-risk, loss-envelope, and profile-boundary review.

The registry should prefer these labels:

| Label | Meaning |
| --- | --- |
| `experiment_worthy` | Thesis and risk envelope justify further bounded work |
| `paper_observation_candidate` | Worth live read-only observation without submit authority |
| `tiny_live_intake_candidate` | Worth main-control intake as a small-capital experimental asset |
| `trial_asset_admission_candidate` | Worth formal final-owned admission preparation |
| `admitted_trial_asset` | Accepted as a final-owned trial asset without action-time authority |
| `armed_observation` | Runtime may observe under scoped rules without real-order authority |
| `role_only_intake_candidate` | Useful as detector, portfolio role, or classifier input |
| `classifier_enhancement` | Improves another StrategyGroup but is not an independent trial lane |
| `StrategyGroup_revision_evidence` | Changes keep, revise, promote, park, or kill logic |
| `watchlist` | Interesting but not worth active observation yet |
| `reject` | Negative evidence says not to spend near-term work |

The registry should avoid labels that imply a strategy is dead merely because it
missed a fixed target or used a higher leverage scenario in research.

## Tier Meanings

| Tier | Owner meaning | Real order |
| --- | --- | --- |
| `L0` | Catalog only | No |
| `L1` | Observe-only strategy asset | No |
| `L2` | Shadow candidate, non-executing candidate evidence may be prepared | No |
| `L3` | Armed observation, close to runtime rehearsal but still no real order | No |
| `L4` | Small-capital real-order eligible when action-time execution gates pass | Yes, bounded |

`L4` is not direct order authority. It only means the StrategyGroup is allowed
to attempt the official real-order path when Tradeability Decision and Runtime
Safety State both allow the action-time path.

## Current Active Runtime Event Registry

The current active pre-trade runtime uses these Owner-confirmed StrategyGroup
semantics. This section is the durable registry contract for the PG initial
seed and must not be replaced by old handoff JSON, old code constants, or
generated output artifacts.

| StrategyGroup | Candidate symbols | Supported side | Event spec | Event time authority | Protection reference |
| --- | --- | --- | --- | --- | --- |
| `CPM-RO-001` | `ETHUSDT`, `SOLUSDT`, `AVAXUSDT`, `SUIUSDT` | long only | `CPM-LONG` | closed 1h reclaim trigger candle close | `pullback_low_reference` |
| `MPG-001` | `OPUSDT`, `SOLUSDT`, `AVAXUSDT`, `SUIUSDT` | long only | `MPG-LONG` | closed 1h momentum-persistence trigger candle close | `momentum_floor_reference` |
| `MI-001` | `AVAXUSDT`, `ETHUSDT`, `SOLUSDT` | long only / long-first | `MI-LONG` | closed 1h candle anchoring 12h impulse | impulse invalidation / fast reversal threshold |
| `SOR-001` | `ETHUSDT`, `SOLUSDT`, `AVAXUSDT`, `BTCUSDT` | long and short through explicit side events | `SOR-LONG`, `SOR-SHORT` | closed 15m session breakout/breakdown candle close | opening-range invalidation |
| `BRF2-001` | `BTCUSDT`, `AVAXUSDT`, `ETHUSDT` | short only | `BRF2-SHORT` | closed 1h rally-failure trigger candle close | `rally_high_reference` |

Unsupported opposite sides are not dormant permissions. They are rejected
runtime scope. A future unsupported side requires a new StrategyGroup or a
versioned strategy variant with its own event spec, RequiredFacts, scope,
policy, protection, and negative tests.

### Event Meanings

| Event spec | Plain-language event |
| --- | --- |
| `CPM-LONG` | 4h uptrend remains intact, 1h pullback is normal, and 1h reclaim confirms continuation |
| `MPG-LONG` | 4h context is upward, 1h momentum persists, and a closed 1h candle confirms continuation or breakout |
| `MI-LONG` | A strong 12h close-to-close impulse appears in an allowed high-beta asset and passes exhaustion/reversal checks |
| `SOR-LONG` | Session opening range is formed, price breaks above the range high, follow-through confirms, and invalidation holds |
| `SOR-SHORT` | Session opening range is formed, price breaks below the range low, bearish follow-through confirms, and reclaim does not occur |
| `BRF2-SHORT` | A weak or non-strong-uptrend market rallies, rally failure/rejection confirms, and squeeze risk remains acceptable |

### Current Event RequiredFacts Boundary

The current PG seed must not include transitional `v0` exceptions inside
RequiredFacts. If a RequiredFact is not part of a strategy event, that absence
must be represented by a new versioned event spec or RequiredFacts version, not
by free-text exceptions.

Current special case:

| Event spec | RequiredFact decision |
| --- | --- |
| `MI-LONG` | `relative_strength_confirmed=true` is required for the current event spec |

### Version Boundary

StrategyGroup versions, event specs, RequiredFacts, policy, execution policy,
and protection policy are versioned.

Signals, promotion candidates, Action-Time Tickets, orders, protection,
reconciliation, and reviews must bind the versions that were current when they
were created. New versions affect future events. They must not rewrite the
meaning of historical signals, tickets, orders, or reviews.

## Current Pilot Registry Sketch

This table is a human-readable sketch. Generated or machine-readable registry
rows should remain structured and testable before they become execution inputs.

| StrategyGroup | Edge thesis | Current governance posture |
| --- | --- | --- |
| `MPG-001` | Momentum persistence / trend continuation | First L4 live-trial lane; waiting for fresh signal and official gates |
| `TEQ-001` | Equity-like perpetual momentum | L2 shadow candidate; low-history and product/session risks constrain promotion |
| `FBS-001` | Funding / basis / crowding stress | L3 armed observation candidate; derivatives facts heavy before L4 review |
| `SOR-001` | Session opening-range structure | L3 conditional armed observation; session and branch conditions matter |
| `PMR-001` | Precious-metal regime overlay | L1 observe/overlay until target-specific role and facts mature |
| `BTPC-001` | Bear trend pullback continuation with derivatives/crowding review | L2 shadow candidate; revise fact/classifier inputs before higher review |
| `VCB-001` | Volatility compression breakout | L1 observe; false-breakout and pre-entry classifier risk remain |
| `LSR-001` | Liquidity sweep / short-revival lane | L1 observe; side-specific rewrite quality and cost review remain |
| `BRF-001` | Bear rally failure short lane | L1 observe; rally context and squeeze-risk facts remain |
| `RBR-001` | Range-boundary reversion vocabulary | Parked or low-priority until materially new edge evidence appears |

## Admission Board Contract

An Owner-facing admission board may summarize registry state, but it must not
become a raw evidence browser.

It should answer:

- which StrategyGroups are visible;
- which are enabled, paused, parked, or killed;
- which are `trial_eligible`;
- which have a current Tradeability Decision and Runtime Safety State allowing
  the official path;
- what risk gap blocks or limits promotion;
- what Owner decision is needed, if any.

It should not expose `FinalGate`, `Operation Layer`, `RequiredFacts`,
`candidate`, `authorization`, `route`, `proof`, `refId`, or blocker codes as
primary labels. Those belong in audit or developer details.

## Promotion And Downshift Rules

Promotion should require a decision-changing evidence path:

```text
registry row
-> observation / no-action / would-enter evidence
-> replay or live outcome review
-> Strategy Asset State evidence row
-> tier review
-> Owner policy when risk acceptance or L4 eligibility changes
```

Promotion must be scoped. New artifacts should use:

- `promotion_scope=intake_only`;
- `promotion_scope=trial_admission`;
- `promotion_scope=armed_observation`;
- `promotion_scope=tiny_live_ready_review`;
- `promotion_scope=l4_eligibility_review`.

Generic `promote` without scope is ambiguous and should be rejected during
main-control intake because it can confuse research intake with live-order
eligibility.

Downshift or park should be normal, not exceptional:

- facts are unavailable or stale for the intended tier;
- classifier or disable state is wrong or missing;
- replay contradicts the edge thesis;
- costs remove the gross edge;
- real outcome review contradicts the strategy;
- the StrategyGroup no longer deserves Owner attention.

## Boundary

The registry does not authorize:

- runtime start;
- candidate creation;
- FinalGate;
- Operation Layer;
- exchange write;
- real order;
- live-profile mutation;
- order-sizing default mutation;
- withdrawal or transfer;
- credential mutation.

It defines strategy asset semantics so the Owner, Codex, and execution agents
can discuss the same object without turning research evidence into execution
authority.
