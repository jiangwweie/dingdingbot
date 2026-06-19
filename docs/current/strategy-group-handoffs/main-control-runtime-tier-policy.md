# Main-Control Runtime Tier Policy

Status: CURRENT_PILOT_SUPPLEMENT
Last updated: 2026-06-19

## Purpose

This supplement separates StrategyGroup visibility from real-order eligibility.
It is not order authority, FinalGate input, Operation Layer input, a credential
change, a live-profile change, or an order-sizing default.

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

They may move to `L2 shadow_candidate` only after reviewed handoff intake and
dry-run audit. They must not enter `L4 tiny_real_order_eligible` until the
first `MPG-001` allocated-subaccount real-order loop has closed or the Owner
explicitly changes the selected live lane.

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
