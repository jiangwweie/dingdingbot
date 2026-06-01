# BNB Protection Order Planning and Min-size Safety Result

## 1. Summary

This sprint fixed the BNB controlled testnet rehearsal defect where `0.01` BNB was split into two `0.005` BNB TP orders that Binance futures rejected.

Final outcome:

```text
testnet_rehearsal_blocked_with_explicit_reasons
not_live_ready
not_auto_execution_ready
no_real_funds
```

The protection planner worked as intended: for `0.01` BNB, it rejected the invalid 50/50 TP split and produced a valid `single_tp_plus_sl` plan. The rerun did not place a new entry order because runtime `DAILY_TRADE_COUNT_LIMIT` blocked before order submission. This is an explicit runtime safety blocker, not a protection planner failure.

## 2. Starting State

Previous BNB testnet rehearsal:

- Entry order filled: `0.01` BNB at `705.43`.
- TP1/TP2 split into `0.005` BNB each.
- Binance rejected TP1/TP2 due to min-size / precision constraints.
- SL was created and later terminalized during cleanup.
- Cleanup close succeeded; final PG position is closed and quantity is `0`.
- BRC attempt remained `blocked`, correctly reflecting protection attach failure.

## 3. Root Cause

The controlled carrier entry path generated a fixed two-TP strategy:

```text
entry_quantity = 0.01 BNB
tp_ratios = [0.5, 0.5]
planned_tp_quantities = [0.005, 0.005]
```

For BNB futures, `0.005` BNB is below the valid minimum amount / amount precision requirement. The previous code only discovered this after the entry filled, while submitting protection orders.

## 4. What Changed

Added a pure precision-aware protection planner:

- file: `src/application/protection_order_planner.py`
- no exchange calls
- no execution intent creation
- no order creation
- no runtime start

Planner inputs:

- entry quantity
- entry price
- min amount
- amount step / precision
- min notional
- desired TP ratios / targets

Planner outcomes:

- `multi_tp_plus_sl`
- `single_tp_plus_sl`
- `sl_only`
- `entry_without_protection_forbidden`
- `blocked_unprotectable_size`

The BNB carrier path now builds the protection plan before campaign/attempt/order execution. If the plan is blocked, it returns:

```text
testnet_rehearsal_blocked_before_entry_due_to_unprotectable_size
```

without creating a campaign or calling the orchestrator.

## 5. Protection Planner Behavior

For current BNB testnet carrier:

| field | value |
|---|---|
| symbol | `BNB/USDT:USDT` |
| entry quantity | `0.01` |
| min amount | `0.01` |
| amount step | `0.01` |
| amount precision | `2` |
| intended TP ratios | `[0.5, 0.5]` |
| invalid split quantities | `[0.005, 0.005]` |
| fallback plan | `single_tp_plus_sl` |
| planned TP quantity | `0.01` |
| planned SL quantity | `0.01` |
| degraded protection | `false` |
| fallback reason | `split_tp_quantity_below_min_amount` |

This avoids placing entry first and discovering the invalid split afterward.

## 6. Runtime Rerun Result

Runtime verification:

| check | result |
|---|---:|
| profile | `strategy_trial_bnb_testnet_runtime` |
| exchange mode | `EXCHANGE_TESTNET=true` |
| trading env | `testnet` |
| symbol scope | `BNB/USDT:USDT` only |
| GKS | clear |
| startup guard | armed through runtime-owned preflight |
| startup reconciliation | clean |
| account facts | fresh |
| inventory before entry | flat |
| protection plan | valid `single_tp_plus_sl` |

Rerun entry result:

| item | value |
|---|---|
| endpoint | `POST /api/dev/testnet/brc/carriers/MI-001-BNB-LONG/execute-controlled-entry` |
| intent id | `intent_e7aebbadce17` |
| signal id | `sig_a3c3adcd3388` |
| entry status | `blocked` |
| blocked reason | `DAILY_TRADE_COUNT_LIMIT` |
| order created | no |
| active BNB position after rerun | no |
| BNB open orders after rerun | no |
| cleanup needed | no active position; campaign metadata ended after flat blocked rehearsal |

Because daily trade count was already `1` for `2026-06-01`, the runtime safety gate blocked before order submission. I did not reset or weaken the daily risk gate.

## 7. Files Changed

- `src/application/protection_order_planner.py`
- `src/application/strategy_trial_controlled_testnet_carrier.py`
- `src/interfaces/api_console_runtime.py`
- `tests/unit/test_protection_order_planner.py`
- `tests/unit/test_brc_controlled_testnet_endpoints.py`
- this report

## 8. Tests / Validation

Executed:

- `python3 -m compileall -q src scripts`
- `python3 -m pytest -q tests/unit/test_protection_order_planner.py tests/unit/test_brc_controlled_testnet_endpoints.py tests/unit/test_brc_execution_bypass_hardening.py tests/unit/test_strategy_trial_bnb_profile_seed.py tests/unit/test_execution_permission.py`
  - result: `50 passed`

Runtime validation:

- Started local testnet runtime.
- Armed runtime-owned startup guard.
- Called BNB carrier entry endpoint.
- Verified protection plan in response:
  - `plan_type=single_tp_plus_sl`
  - `planned_tp_quantities=["0.01"]`
  - `planned_sl_quantity="0.01"`
- Verified runtime blocked entry with `DAILY_TRADE_COUNT_LIMIT` before order submission.
- Verified final PG state:
  - no active BRC campaign
  - no active BNB position
  - no BNB open order

## 9. Safety Proof

| safety item | result |
|---|---:|
| live mode used | no |
| real funds used | no |
| live order placed | no |
| new testnet order placed during rerun | no, blocked before order |
| credential changed | no |
| secret printed | no |
| secret committed | no |
| withdrawal/transfer called | no |
| leverage changed | no |
| arbitrary symbol/side allowed | no |
| Operation Layer bypassed | no |
| live execution permission granted | no |
| naked exchange order script used | no |
| invalid TP protection marked as success | no |

## 10. Remaining Work

The protection planner defect is fixed and covered by tests. The next testnet rehearsal is blocked only by the existing daily risk trade-count gate for the current day.

## 11. Next Recommended Task

Run the next BNB controlled testnet rehearsal after the daily trade-count window resets, or create a separate dev/testnet-only risk-counter reset procedure with explicit audit metadata.
