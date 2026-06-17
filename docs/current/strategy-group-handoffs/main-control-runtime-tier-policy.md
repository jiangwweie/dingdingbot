# Main-Control Runtime Tier Policy

Status: CURRENT_PILOT_SUPPLEMENT
Last updated: 2026-06-17

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
| `L4` | `tiny_real_order_eligible` | May place a bounded tiny real order only after the full official runtime chain passes | Yes, bounded |

## Current Pilot Mapping

| StrategyGroup | Tier | Mode | Main-Control Meaning |
| --- | --- | --- | --- |
| `MPG-001` | `L4` | `tiny_real_order_eligible` | First bounded live-order pilot lane; tiny risk only |
| `TEQ-001` | `L2` | `shadow_candidate` | May prepare candidate evidence, but should not compete with first MPG real-order closure |
| `FBS-001` | `L3` | `armed_observation` | Observable with stricter derivatives facts before promotion |
| `SOR-001` | `L3` | `conditional_armed_observation` | Armed only inside its session/structure conditions |
| `PMR-001` | `L1` | `observe_only` | Observe-only until role/session/mark facts are consistently ready |

## New StrategyGroup Default

New or newly reviewed StrategyGroups such as `BRF`, `BTPC`, `VCB`, `LSR`, and
`RBR` default to `L1 observe_only`.

They may move to `L2 shadow_candidate` only after reviewed handoff intake and
dry-run audit. They must not enter `L4 tiny_real_order_eligible` until the
first `MPG-001` tiny real-order loop has closed or the Owner explicitly changes
the selected live lane.

## Boundary

StrategyGroup tiers do not bypass:

- selected StrategyGroup scope;
- tiny risk boundary;
- fresh signal;
- RequiredFacts readiness;
- candidate and authorization evidence;
- action-time FinalGate;
- official Operation Layer;
- protection, reconciliation, budget settlement, and review.
