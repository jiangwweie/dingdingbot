---
title: STRATEGY_ENGINEERING_INTAKE_CONTRACT
status: CURRENT
authority: docs/current/STRATEGY_ENGINEERING_INTAKE_CONTRACT.md
last_verified: 2026-07-13
---

# Strategy Engineering Intake Contract

## Current Production Boundary

The strategy-intake labels in this document govern research and engineering
priority. They do not redefine the current production registry. The current
production candidate set is exactly **5 admitted StrategyGroups**, **22 active
candidate lanes**, and **6 Event Specs** defined by PG/current registry rows.

For a current admitted lane, the decision is not "observe for an unspecified
period." It is:

```text
admitted Event-Spec scope
-> non-executing runtime scan
-> exact fresh event
-> official Ticket path when action-time gates pass
```

An unadmitted strategy variant remains research, `future_option`,
`support_filter`, or `parked`. It may not create an active production lane only
to collect observe-only signals. The engineering intake work must preserve the
same registered StrategyGroup, symbol, side, Event Spec, and timeframe at every
runtime boundary; an evaluator output may not infer a new direction. Source:
`PRE_TRADE_RUNTIME_CONTRACT.md` and `STRATEGYGROUP_REGISTRY_CONTRACT.md`.

## Purpose

This contract defines what a StrategyGroup must prove before it consumes
engineering capacity.

It exists to keep strategy work from becoming:

```text
more strategies
more replay rows
more artifacts
more explanations
```

The accepted shape is:

```text
regime-specific strategy option
-> one-page engineering brief
-> WIP-limited blocker removal
-> replay/live parity or admission decision
-> tiny-live outcome only through official gates
-> promote / revise / park / kill
```

This contract does not replace:

- `docs/current/TRADEABILITY_DECISION_CONTRACT.md`;
- `docs/current/WIP_AND_STOP_RULE_CONTRACT.md`;
- `docs/current/BLOCKER_CLASSIFICATION_CONTRACT.md`;
- `docs/current/STRATEGY_OPPORTUNITY_REVIEW_LEDGER.md`.

It is the pre-engineering intake filter before a StrategyGroup is allowed to
claim mainline implementation attention.

## Core Rule

A StrategyGroup may exist in the registry as a future option, but it must not
enter active engineering unless it has:

1. a clear regime thesis;
2. a bounded risk envelope;
3. one first blocker;
4. one next engineering action;
5. a downgrade or kill condition.

Past replay evidence can show where edge may have appeared. It cannot, by
itself, prove that a strategy is the best future engineering option.

Use this priority frame:

```text
Engineering Priority =
Regime option value
* Evidence strength
* Runtime readiness
* Risk envelope clarity
/ WIP cost
```

Do not use this frame:

```text
Strategy had the most historical replay rows
-> therefore engineer it first
```

## Strategy Engineering Brief

Before a StrategyGroup enters engineering work, it must have one concise brief.
The brief should fit on one page and contain no more than the fields below.

```text
StrategyGroup:
Asset class:
Side:
Regime fit:
Regime avoid:
Edge thesis:
Primary symbols / baskets:
Required facts:
Entry condition:
Invalidation:
Disable condition:
Expected trade frequency:
Main false positive:
Cost sensitivity:
Replay evidence:
Live parity status:
Risk envelope:
Upgrade condition:
Downgrade condition:
Kill condition:
Next engineering action:
```

If the brief cannot name a kill condition, the strategy must stay
`future_option`, `support_filter`, or `parked`.

If the brief cannot name one next engineering action, the first task is brief
repair, not detector implementation.

## Intake States

Each StrategyGroup must be assigned exactly one intake state before planning
work starts.

| Intake state | Meaning | May consume mainline engineering WIP |
| --- | --- | --- |
| `current_active` | Current regime and runtime path justify active blocker removal | Yes, only inside `WIP_AND_STOP_RULE_CONTRACT.md` |
| `future_option` | Future regime value exists, but current work should stay lightweight | No |
| `support_filter` | Provides facts or filters for other strategies, not standalone live lane | No, unless it is already an admitted WIP lane |
| `conditional_trigger` | Becomes relevant only after named market or blocker conditions appear | No |
| `parked` | Not worth current engineering capacity | No |

These states are strategy-intake labels. They do not grant runtime observation,
trial eligibility, live-submit readiness, or real-order authority.

## Current Strategic Buckets

These buckets express strategy-engineering focus. They do not replace the active
live-enablement WIP list in `docs/current/WIP_AND_STOP_RULE_CONTRACT.md`.

| Bucket | StrategyGroups | Current interpretation |
| --- | --- | --- |
| `active_engineering_focus` | `CPM-RO-001`, `MI-001` | Highest value for immediate blocker reduction |
| `lightweight_enablement` | `TEQ-001`, `PMR-001`, selective `MPG-001` | Keep future regime option value without claiming new WIP slots |
| `support_filter_or_infrastructure` | `FBS-001`, `SOR-001` | Use as facts, session, crowding, or context support; `SOR-001` still follows its existing WIP row when active |
| `conditional_short_lane` | `BRF-001`, `BRF2-001`, `BTPC-001` | Advance only under explicit short-side trigger, disable-state, or admission evidence |
| `parked_or_future_option` | `VCB-001`, `RBR-001`, `LSR-001` | Keep only as future regime vocabulary unless new evidence changes the decision |

`TEQ-001`, `PMR-001`, `FBS-001`, or any other support-only StrategyGroup may
replace an active WIP lane only through the replacement rule in
`docs/current/WIP_AND_STOP_RULE_CONTRACT.md`.

## Current Three Intake Blockers

The current strategic intake focus is limited to three blocker-removal themes:
This section does not admit a new active WIP lane. `TEQ-001` remains
support-only / lightweight intake unless it explicitly replaces one active lane
through `docs/current/WIP_AND_STOP_RULE_CONTRACT.md`.

| Priority | StrategyGroup | Blocker theme | Required next result |
| --- | --- | --- | --- |
| `1` | `MI-001` | Identity and trial admission closure | Decide whether `MI-001` is independent, an `MPG-001` member role, or a smoke lane |
| `2` | `CPM-RO-001` | Replay/live parity matrix | Classify `ETHUSDT`, `SOLUSDT`, `SUIUSDT`, and `AVAXUSDT` facts as missing, computed false, satisfied, or action-time pending |
| `3` | `TEQ-001` | Lightweight product/session/breadth facts | Decide whether `TEQ-001` is a standalone lane or cross-asset overlay, without creating live authority |

`FBS-001` and `SOR-001` may support these blockers with filter or session facts,
but they must not create extra P0 engineering slots.

## Seven-Day Downgrade Rule

Every seven calendar days, and after every major parity or admission checkpoint,
strategy engineering work must answer:

| Question | Required decision use |
| --- | --- |
| Which blocker moved | Count as progress only if the first blocker was removed or reclassified |
| Which artifact changed no decision | Mark `no_progress`; do not count as completion |
| Which regime option value fell | Downgrade, park, or keep support-only |
| Which replay/live parity failed | Record `replay_live_rule_mismatch` or revise strategy rules |
| Which strategy should exit mainline | Apply `WIP_AND_STOP_RULE_CONTRACT.md` |
| Which strategy deserves promotion | Require explicit `promotion_scope` and no authority leakage |

If seven days pass with artifact growth but no blocker movement, the lane must
exit mainline or be reduced to a smaller blocker-removal task.

## Outcome Review

After a live, paper-parity, or missed-trade event, the review must capture the
fields needed to change StrategyGroup state:

```text
Strategy:
Asset:
Signal time:
Entry:
Exit:
Fee:
Slippage:
Funding:
MFE:
MAE:
Stop:
Net:
Expected vs actual:
Decision: promote / keep / revise / park / kill
```

Losses may be acceptable inside an experiment envelope. They must still update
one of:

- risk envelope;
- scope;
- disable rule;
- RequiredFacts;
- cost sensitivity;
- promotion, revision, park, or kill decision.

An explanation that preserves every prior assumption is not an accepted outcome
review.

## Authority Boundary

This contract does not authorize:

- real-order submission;
- live profile expansion;
- sizing-default expansion;
- symbol or side expansion;
- FinalGate bypass;
- Operation Layer bypass;
- exchange writes from replay, paper, or read-only evidence;
- stale-fact execution;
- missing-protection execution;
- duplicate submit;
- conflicting active exposure;
- withdrawal or transfer;
- credential mutation.

It only defines how a strategy earns engineering attention before the official
Tradeability Decision and runtime safety path decide actionability.
