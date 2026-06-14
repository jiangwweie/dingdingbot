# Strategy Group Live Facts Read-Only Collector

Status: PARTIAL_READ_ONLY_FACTS
Last updated: 2026-06-14

## Scope

This checkpoint adds and runs a local read-only live-facts collector for the
first StrategyGroup batch.

The collector uses only Binance USD-M Futures `GET` endpoints:

| Endpoint | Signed | Purpose |
| --- | --- | --- |
| `/fapi/v1/exchangeInfo` | No | Public exchange symbol rules. |
| `/fapi/v2/account` | Yes | Account trade/account summary. |
| `/fapi/v2/positionRisk` | Yes | Position exposure summary. |
| `/fapi/v1/openOrders` | Yes | Open order summary. |

## Result

| Fact Area | Result |
| --- | --- |
| Exchange rules | `ready` |
| StrategyGroup symbols | `26/26 TRADING` |
| Account facts | `missing` |
| Position facts | `missing` |
| Open-order facts | `missing` |
| Protection facts | `missing` |
| Budget facts | `missing` |
| Next-attempt gate facts | `missing` |

Signed account/position/open-order endpoints returned:

```text
http_401: Invalid API-key, IP, or permissions for action
```

This means the current local machine/IP/key permission set cannot provide
signed live account facts. It does not indicate that an exchange write was
attempted.

## StrategyGroup Readiness After Partial Facts

| Metric | Count |
| --- | ---: |
| Strategy groups evaluated | `5` |
| Observe-ready groups | `5` |
| Armed candidate-prepare ready groups | `0` |
| Candidate-prepare blocked groups | `5` |

Current operator path:

```text
can_continue_observation: true
can_prepare_fresh_candidate: false
next_gate: wait_for_or_generate_fresh_strategy_signal
requires_action_time_final_gate_before_submit: true
requires_official_operation_layer: true
```

## Safety Boundary

The collector and readiness packet keep these invariants:

```text
signed_get_only: true
post_delete_put_used: false
exchange_write_called: false
order_created: false
order_lifecycle_called: false
execution_intent_created: false
runtime_budget_mutated: false
withdrawal_or_transfer_created: false
secrets_printed: false
```

## Interpretation

Observation can continue because public exchange-rule facts are available for
all StrategyGroup handoff symbols.

Fresh candidate preparation remains blocked until account, position,
open-order, protection, budget, and next-attempt gate facts are supplied by a
trusted live read source, most likely the Tokyo runtime environment where the
live API key/IP permission is valid.
