# Strategy Group Live Facts Readiness Checkpoint

Status: OBSERVE_READY_ARMED_BLOCKED
Last updated: 2026-06-14

## Source Inputs

| Input | Value |
| --- | --- |
| Strategy handoff source commit | `05f616b0` |
| Main-control intake commit | `6d70fa13` |
| Exchange rules validation commit | `ecf661a2` |
| Public exchange metadata | Binance USD-M Futures `GET /fapi/v1/exchangeInfo` |
| Live account / position / open-order access | Not used in this checkpoint |

## Readiness Summary

| Metric | Count |
| --- | ---: |
| Strategy groups evaluated | `5` |
| Observe-ready strategy groups | `5` |
| Armed candidate-prepare ready groups | `0` |
| Candidate-prepare blocked groups | `5` |

## Current Interpretation

The first StrategyGroup batch can continue as observation scope because all
handoff symbols passed public exchange-rule availability validation.

Candidate preparation remains blocked because current main-control live facts
are not yet attached to the StrategyGroup readiness packet:

1. `account`
2. `active_position`
3. `open_orders`
4. `protection`
5. `budget`
6. `next_attempt_gate`

This is the intended safety state:

```text
observation can continue
fresh candidate preparation cannot start yet
FinalGate is not reached
Operation Layer is not reached
real submit is not authorized by this packet
```

## Implemented Artifacts

| Artifact | Purpose |
| --- | --- |
| `scripts/build_strategy_group_live_facts_readiness_packet.py` | Builds read-only StrategyGroup live-facts readiness from intake and facts. |
| `GET /api/trading-console/strategy-group-live-facts-readiness` | Exposes observe vs armed readiness to Owner Console. |
| `trading-console/src/pages/StrategyGroupIntake.tsx` | Shows live facts readiness counts on the StrategyGroup intake page. |
| `tests/unit/test_strategy_group_live_facts_readiness_packet.py` | Verifies observe-ready / candidate-blocked separation. |

## Safety Boundary

The readiness packet explicitly keeps these invariants false:

```text
registers_runtime: false
creates_candidate: false
authorizes_execution: false
places_order: false
mutates_pg: false
```

The next safety checkpoint is to feed current read-only live account facts into
this packet without creating candidates or touching execution paths.
