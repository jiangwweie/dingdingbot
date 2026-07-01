---
title: STRATEGY_EXPERIMENT_EVALUATION_CONTRACT
status: CURRENT
authority: docs/current/STRATEGY_EXPERIMENT_EVALUATION_CONTRACT.md
last_verified: 2026-06-23
---

# Strategy Experiment Evaluation Contract

## Purpose

This file defines how agents, strategy-research workers, and main-control
reviewers should evaluate StrategyGroup candidates during the small-capital
right-tail experiment.

It exists to prevent strategy review from drifting into either:

```text
perfect-strategy proof before experimentation
```

or:

```text
unbounded execution authority from research evidence
```

The correct middle layer is:

```text
experiment-worthy strategy asset
-> risk envelope
-> replay / paper observation / review
-> main-control absorption
-> later runtime eligibility only through official gates
```

After main-control absorption, strategy progress should be evaluated through
`docs/current/TRADEABILITY_DECISION_CONTRACT.md`. The strategy question becomes:

```text
Is the asset tradeable now?
If not, what first blocker prevents trading?
```

Evaluation decides whether a strategy deserves the path. Tradeability decides
where it currently sits on that path.

## Core Rule

Strategy advancement is based on experiment value, not perfect return proof.

Use this evaluation frame:

```text
Does the strategy have a meaningful right-tail or portfolio-role thesis?
Can the known failure modes be expressed?
Can the loss envelope be bounded?
Can replay, paper observation, or tiny-live intake teach the system something?
Can final main-control absorb the artifact without creating execution authority?
```

Do not use this frame:

```text
Did the strategy prove a fixed return target?
Did the strategy stay below an arbitrary leverage number?
Did the strategy avoid every path-risk warning?
Did the strategy look like stable year-round alpha?
```

## Terminology

| Term | Meaning | Not |
| --- | --- | --- |
| `right_tail_aspiration_anchor` | A target used to ask whether the strategy has enough upside imagination | A hard pass/fail return threshold |
| `leverage_scenario` | A research or runtime scenario used to inspect path, liquidation, and loss-envelope behavior | Automatic live leverage authorization or automatic disqualification |
| `experiment_worthy` | Worth continued replay, paper observation, or main-control intake because the thesis and risk envelope are useful | Proof of profitability |
| `path_risk_known` | Path and stop-hit risks are measured and reviewable | Path is safe or execution-ready |
| `risk_envelope_defined` | Attempt cap, loss cap, pause condition, or equivalent review boundary exists | Risk is eliminated |
| `absorption_ready_research_asset` | Research artifact can be read by final main-control for review | Runtime admission or order authority |
| `tiny_live_intake_candidate` | Main control may ingest it as a small-capital experimental asset for review | Tiny-live ready, actionable now, or real-order authorized |
| `trial_asset_admission_candidate` | Main control is preparing registry, policy, facts, runtime scope, and risk-envelope admission | Runtime admission or order authority |
| `admitted_trial_asset` | Strategy exists as a final-owned experimental asset under scoped governance | Action-time submit authority |
| `armed_observation` | Runtime may observe the scoped asset and assemble non-executing evidence | Real-order authority |
| `tiny_live_ready` | A downstream state after main-control review, facts, risk envelope, and runtime scope are closed | Automatic exchange write |
| `live_submit_ready` | Action-time runtime state says a real submit may proceed through FinalGate and Operation Layer | Research or markdown conclusion |

## Signal Grade Semantics

Signal grade must be explicit. A strategy such as `BRF2-001` may be suitable
for a bounded small-capital trial before it has enough evidence for production
expansion. Do not hide that distinction inside a generic `fresh_signal` label.

| Signal type | May place order | Use |
| --- | --- | --- |
| `observe_only_signal` | No | Record, replay, repair classifier, and improve RequiredFacts |
| `trial_grade_signal` | Yes, only inside scoped small-capital trial boundaries | Enter a bounded trial such as the 30 USDT BRF2 trial after hard safety gates still pass |
| `production_grade_signal` | Yes, at higher or normalized production grade after later promotion | Support future scale-up or regularized runtime operation |
| `invalid_signal` | No | Attribution, replay, and rule repair |

Trial-grade does not mean relaxed authority. It means the strategy-quality
standard may accept known path risk when that risk is expressed as a bounded
experiment envelope. The action-time runtime path still requires fresh facts,
candidate/authorization evidence, FinalGate, Operation Layer, protection,
account state, and exchange facts.

Known strategy risk should enter the experiment envelope instead of becoming a
generic trade blocker:

```text
path risk known
-> max attempts limited
-> loss unit fixed
-> stop/protection required
-> pause after configured failures
-> review required
```

Hard safety and authority gates cannot be weakened by trial-grade status.
Examples include wrong account or profile, stale action-time facts, missing
protection, duplicate-submit risk, conflicting exposure, FinalGate bypass,
Operation Layer bypass, exchange-write bypass, withdrawal or transfer,
credential mutation, and order-sizing expansion.

## Return Target Semantics

Numbers such as `100%`, `90d 100%`, or similar high-return anchors are aspiration
and comparison tools. They are not hard gates for intake, replay, paper
observation, or StrategyGroup revision.

Correct use:

```text
This candidate has enough right-tail asymmetry to justify deeper experiment.
```

Incorrect use:

```text
This candidate failed the 100% target, so it cannot be absorbed.
```

Return targets may influence priority, but they must not erase an otherwise
useful experiment-worthy asset with clear semantics, known risks, and a bounded
review path.

## Leverage Semantics

Leverage values such as `1x`, `2x`, `3x`, `4x`, or `5x` are scenarios. They are
not quality labels by themselves.

Agents must not treat:

```text
<=3x = formal
4x / 5x = stress-only or invalid
```

as the project rule.

The correct question is:

```text
Does this leverage scenario have a clear liquidation buffer, path-risk profile,
loss unit, attempt cap, protection requirement, and pause rule?
```

A higher-leverage scenario can be better than a lower-leverage scenario when the
event selection, loss envelope, and path behavior make it cleaner. A higher
leverage scenario also does not authorize runtime leverage expansion. Runtime
leverage remains bounded by the Owner-selected profile and action-time exchange
facts.

## Evaluation Stages

| Stage | Meaning | Required evidence | Authority boundary |
| --- | --- | --- | --- |
| `research_candidate` | A plausible strategy idea or vocabulary item | Strategy thesis and rough regime fit | Research only |
| `replay_candidate` | Worth replay or event extraction | Event definition, sample source, rough outcome question | No runtime authority |
| `paper_observation_candidate` | Worth live read-only observation | RequiredFacts draft, disable/review facts, paper observation evidence shape | No submit authority |
| `tiny_live_intake_candidate` | Worth main-control review as a small-capital experimental asset | Thesis, risk envelope, path-risk evidence, replay/paper evidence, boundary-clean handoff | Not tiny-live ready |
| `trial_asset_admission_candidate` | Worth formal final-owned admission preparation | Registry proposal, policy-scope draft, RequiredFacts draft, risk envelope, hard-stop summary | No runtime authority |
| `admitted_trial_asset` | Accepted into final-owned strategy asset layer | Registry/tier/policy representation and explicit non-authority boundary | No action-time authority |
| `armed_observation` | Worth runtime observation under scoped rules | Watcher scope, signal definition, fact mapping, disable/downshift facts | No direct submit authority |
| `tiny_live_ready` | Main control has closed non-executing readiness for a scoped experiment | Runtime scope, facts, risk envelope, protection plan, review path | Still requires action-time gates |
| `live_submit_ready` | Runtime says the current signal may submit through official path | Fresh signal, RequiredFacts, candidate/auth, FinalGate, Operation Layer, protection, account/exchange facts | Action-time only |

## Strategy Review Questions

Every promising strategy direction should answer:

| Question | Purpose |
| --- | --- |
| What does it eat? | Identify regime, session, product, crowding, or volatility source |
| How does it trade? | Explain side, entry, exit, invalidation, and protection idea |
| Why is it experiment-worthy? | Separate right-tail or portfolio-role value from noise |
| What can go wrong? | Make left-tail, squeeze, stop-hit, overfit, liquidity, and fact risks visible |
| What is the loss envelope? | Define attempt cap, loss cap, pause rule, or review trigger |
| What facts are required? | Draft market, strategy, derivatives, risk, account, and exchange facts |
| What should disable or downshift it? | Convert known failures into reviewable facts |
| What should happen next? | Replay, paper observation, tiny-live intake, revise, park, or reject |

## Decision Language

Preferred labels:

```text
experiment_worthy
path_risk_known
risk_envelope_defined
paper_observation_candidate
tiny_live_intake_candidate
trial_asset_admission_candidate
admitted_trial_asset
armed_observation
role_only_intake_candidate
classifier_enhancement
StrategyGroup_revision_evidence
watchlist
reject
```

Avoid labels that imply a fixed return qualification gate:

```text
return_qualified
not_return_qualified
formal_only_under_3x
stress_only_invalid
failed_100_percent_target
```

Existing historical reports may still contain older labels. New planning and
main-control intake should translate them through this contract.

Promotion language must be scoped:

| Scope | Meaning |
| --- | --- |
| `intake_only` | Promote only into main-control intake review |
| `trial_admission` | Promote into formal trial asset admission preparation |
| `armed_observation` | Promote into scoped runtime observation without real-order authority |
| `tiny_live_ready_review` | Promote into non-executing tiny-live readiness closure |
| `l4_eligibility_review` | Promote into Owner-scoped L4 eligibility review |

Generic `promote` is too broad for new artifacts because it can confuse
research intake, observation, tiny-live readiness, and real-order eligibility.

## Replay And Paper Observation

Replay and paper observation may improve strategy governance by showing:

- event quality;
- path-risk shape;
- stop-hit behavior;
- cost sensitivity;
- funding or mark-risk exposure;
- session concentration;
- hidden BTC or ETH beta;
- symbol concentration;
- false positives and false negatives;
- review, revise, park, or promote evidence.

Replay and paper observation must not become:

- live market signals;
- live RequiredFacts;
- FinalGate inputs;
- Operation Layer evidence;
- exchange-write authority;
- proof of stable profitability.

## Main-Control Absorption

Final main-control may absorb strategy-research output only as one of:

| Absorption route | Meaning |
| --- | --- |
| `paper_observation_candidate` | Observe and record future cases without submit authority |
| `tiny_live_intake_candidate` | Review as small-capital experimental asset, still not live-ready |
| `trial_asset_admission_candidate` | Prepare final-owned registry, policy, facts, tier, and risk envelope |
| `admitted_trial_asset` | Represent the strategy as a final-owned trial asset, still non-executing until runtime gates pass |
| `armed_observation` | Observe under scoped runtime rules without real-order authority |
| `role_only_intake_candidate` | Useful as portfolio role, detector, or classifier input |
| `classifier_enhancement` | Improves another StrategyGroup without independent trial status |
| `StrategyGroup_revision_evidence` | Changes keep, revise, promote, park, or kill logic |
| `watchlist` | Interesting but not ready for active observation |
| `reject` | Negative evidence says it should not consume more near-term work |

Absorption must preserve:

```text
research artifacts remain research_only=true
main-control reviewed artifacts remain non-executing unless runtime scope changes
Tradeability Decision remains the only can-trade read model
Runtime Safety State remains the only live-submit safety read model
```

## Hard Boundaries

This contract does not authorize:

- FinalGate bypass;
- Operation Layer bypass;
- live profile mutation;
- order-sizing default mutation;
- symbol, side, notional, leverage, or profile expansion;
- stale-fact execution;
- missing-protection execution;
- duplicate submit risk;
- conflicting active position or open-order execution;
- exchange write from research evidence.

The Owner may accept scoped strategy quality risk. The Owner cannot make
research evidence itself become action-time runtime authority.
