# Main-Control Runtime Tier Policy

Status: CURRENT_PILOT_SUPPLEMENT
Last updated: 2026-06-23

## Purpose

This supplement separates StrategyGroup visibility from real-order eligibility.
It is not order authority, FinalGate input, Operation Layer input, a credential
change, a live-profile change, or an order-sizing default.

Strategy evaluation follows
`docs/current/STRATEGY_EXPERIMENT_EVALUATION_CONTRACT.md`: `100%`-style return
targets are aspiration anchors, and `5x`-style leverage values are scenarios for
review. Neither creates tier promotion authority by itself, and neither blocks a
bounded experiment-worthy candidate by itself.

Tradeability evaluation follows
`docs/current/TRADEABILITY_VERDICT_CONTRACT.md`: a candidate that is not yet in
the registry or runtime tier policy is blocked by asset admission, not by the
market. `waiting_for_market` is only accurate after final-owned admission,
scoped policy, armed observation, and non-live readiness are closed.

## Tier Definitions

| Tier | Name | Meaning | Real order |
| --- | --- | --- | --- |
| `L0` | `catalog_only` | Visible in the StrategyGroup catalog only | No |
| `L1` | `observe_only` | May record read-only observations and no-action packets | No |
| `L2` | `shadow_candidate` | May prepare non-executing shadow candidate and authorization evidence after fresh signal and facts pass | No |
| `L3` | `armed_observation` | May run armed observation and action-time rehearsal, but cannot place a real order unless separately promoted to `L4` | No |
| `L4` | `tiny_real_order_eligible` | May place an allocated-subaccount bounded-aggressive real order only after the full official runtime chain passes. The mode name is a legacy compatibility label, not a de-risking instruction. | Yes, bounded |

## Current Pilot Mapping

| StrategyGroup | Tier | Mode | Main-Control Meaning |
| --- | --- | --- | --- |
| `MPG-001` | `L4` | `tiny_real_order_eligible` | First bounded-aggressive live-order pilot lane; use Owner-allocated subaccount profile |
| `TEQ-001` | `L2` | `shadow_candidate` | May prepare candidate evidence, but should not compete with first MPG real-order closure |
| `FBS-001` | `L3` | `armed_observation` | Observable with stricter derivatives facts before promotion |
| `SOR-001` | `L3` | `conditional_armed_observation` | Armed only inside its session/structure conditions |
| `PMR-001` | `L1` | `observe_only` | Observe-only until role/session/mark facts are consistently ready |
| `BTPC-001` | `L2` | `shadow_candidate` | Passed main-control L2 intake dry-run; may prepare non-executing shadow-candidate evidence only and remains outside `L4` real-order scope |

## New StrategyGroup Default

New or newly reviewed StrategyGroups such as `BRF`, `VCB`, `LSR`, and `RBR`
default to `L1 observe_only`.

Research-side candidates such as `BRF2-001` or `RBR2-001` are not automatically
covered by existing `BRF` or `RBR` rows. They must first pass a final-owned
trial asset admission step:

```text
tiny_live_intake_candidate
-> trial_asset_admission_candidate
-> admitted_trial_asset
-> L1/L2/L3/L4 tier review as scoped by Owner policy
```

They may move to `L2 shadow_candidate` only after reviewed handoff intake,
final-owned admission, and dry-run audit. They must not enter `L4
tiny_real_order_eligible` until either the first selected live lane has closed
or the Owner explicitly changes the selected live lane and all runtime scope,
facts, protection, and official gates pass.

## Boundary

`L4 tiny_real_order_eligible` is still not direct order authority. A real order
requires every item in this runtime chain:

| Requirement | Meaning |
| --- | --- |
| `selected_strategygroup_scope` | The active selected StrategyGroup scope matches the live lane |
| `allocated_subaccount_profile_boundary` | Symbol, side, notional, leverage, and max exposure stay inside the Owner-selected subaccount/profile boundary |
| `fresh_signal` | The signal is fresh at action time |
| `required_facts_readiness` | RequiredFacts are present and fresh |
| `candidate_authorization_evidence` | Candidate and authorization evidence are bound to the fresh signal |
| `action_time_finalgate` | The official action-time FinalGate passes |
| `official_operation_layer` | The official Operation Layer path is ready and used |
| `exchange_native_protection` | Exchange-native protection is required after entry |
| `post_submit_finalize` | Post-submit finalize records the submit outcome |
| `reconciliation` | Account/order/position facts are reconciled |
| `budget_settlement` | Runtime budget is settled or held according to position state |
| `review_capture` | Review evidence is recorded |

StrategyGroup tiers do not bypass:

- selected StrategyGroup scope;
- allocated subaccount/profile boundary;
- fresh signal;
- RequiredFacts readiness;
- candidate and authorization evidence;
- action-time FinalGate;
- official Operation Layer;
- protection, reconciliation, budget settlement, and review.

## StrategyGroup Decision Review

StrategyGroup tier movement should now be driven by the minimal StrategyGroup
Decision Ledger plus replay-to-review evidence, not by isolated reports.

| Tier decision | Required pre-live evidence |
| --- | --- |
| Keep `L1 observe_only` | High-priority no-action / would-enter evidence exists but replay or facts are insufficient |
| Prepare `L2 shadow_candidate` | Replay coverage, RequiredFacts mapping, and classifier state support non-executing shadow review |
| Keep `L2 shadow_candidate` | Shadow quality is useful but facts/classifier/cost gaps remain |
| Park | Evidence is weak, negative, low-priority, or not tied to right-tail opportunity |
| Future `L4` review | Requires explicit Owner lane change or post-MPG first live closure, plus the full official runtime chain |

For newly absorbed research candidates, add the admission step before tier
movement:

| Admission decision | Required pre-tier evidence |
| --- | --- |
| `intake_only` | Research handoff is useful but remains outside final-owned registry and policy |
| `trial_admission` | Thesis, risk envelope, facts draft, and review path justify final-owned admission preparation |
| `admitted_trial_asset` | Registry, policy, fact, risk, and non-authority fields are present and testable |
| `armed_observation` | Watcher scope, signal definition, disable facts, and no-submit boundary are ready |

Return anchors and leverage scenarios may prioritize review, but they do not
replace the tier evidence path. A `tiny_live_intake_candidate` is an intake
asset, not `tiny_live_ready` and not `actionable_now`.

The decision ledger is not a promotion authority by itself. It records why a
StrategyGroup should be kept, revised, promoted, parked, killed, reviewed for
go-live, rejected for go-live, or blocked for safety. Routine observations and
raw replay samples stay as lower-level evidence.
