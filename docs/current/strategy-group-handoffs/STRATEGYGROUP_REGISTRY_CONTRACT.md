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
Can it trade now, and if not, what first blocker remains?
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
| Decision Ledger | Records current keep, revise, promote, park, kill, go-live, do-not-go-live, or safety-block decisions |
| Tradeability Verdict | Records whether the strategy can trade now and the first blocker when it cannot |
| Review Ledger | Records real action outcomes and post-trial learning |

The registry should summarize handoff and research evidence. It must not copy
large replay corpora or raw packet details into the main-control layer.

## Governance Authority

The registry supports this authority split:

```text
Owner controls policy.
System executes process.
Runtime decides actionability.
Review updates strategy governance.
```

The Owner may use the registry to decide whether a StrategyGroup should be
enabled, paused, promoted, downshifted, parked, killed, or accepted for a scoped
risk tier. The registry must not require the Owner to manually assemble
RequiredFacts, validate fresh signals, inspect candidate/auth evidence, judge
FinalGate, or operate the Operation Layer.

Registry and Owner policy may make a StrategyGroup `trial_eligible`.
Only runtime state may make it `actionable_now`.

The registry may support a Tradeability Verdict, but it must not compute live
actionability by itself. Registry rows explain asset admission, policy scope,
risk envelope, and hard blocks. Runtime state decides whether the current
market moment can actually trade.

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
| `actionable_now` | Whether it can submit now; usually generated at runtime, not hand-authored |
| `risk_gaps` | Strategy risks the Owner may accept or reject |
| `hard_blocks` | Mechanical or authority issues the Owner cannot override |
| `required_facts_summary` | Human-readable RequiredFacts summary by market, strategy, derivatives, risk, account, exchange |
| `promotion_gate` | Evidence needed to move to a higher tier |
| `downshift_rule` | Conditions that downgrade tier or disable candidate preparation |
| `park_rule` | Conditions that keep it inactive without deleting the idea |
| `kill_condition` | Conditions that remove it from active strategy allocation |
| `evidence_refs` | Links to handoff packs, replay summaries, Decision Ledger rows, or Review Ledger rows |
| `authority_boundary` | Explicit statement that the row does not authorize real orders |

## Trial Eligibility And Actionability

The registry must separate strategy eligibility from action-time execution:

| Field | Meaning | Source |
| --- | --- | --- |
| `trial_eligible` | This StrategyGroup is allowed to enter the small-capital trial candidate pool under scoped Owner policy | Registry plus Owner policy |
| `actionable_now` | A real action is currently allowed because fresh signal, RequiredFacts, candidate/auth, FinalGate, Operation Layer, protection, and account/exchange facts all pass | Runtime state only |

No fresh signal means `actionable_now=false`. It does not necessarily mean
`trial_eligible=false`.

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
to attempt the official real-order path when `actionable_now=true`.

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
- which are `actionable_now`;
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
-> Decision Ledger row
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
