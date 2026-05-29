# Account Equity Readiness Result

Date: 2026-05-29

Scope: MI-001 SOL/USDT:USDT long bounded trial account-equity blocker.

## 1. Summary

This task implemented the minimum read-only account equity mapping needed for bounded trial budgeting readiness. The Owner Console account facts path can now expose `wallet_equity` / `account_equity` from an already cached `AccountSnapshot.total_balance`, and `available_margin` from `AccountSnapshot.available_balance`.

No trial was started. No runtime was started. No exchange was connected by this task. No real account API was called by this task. No order or execution intent was created.

## 2. Path Chosen

Path A: only mapping was needed.

Reason:

- `AccountSnapshot` already defines `total_balance`, `available_balance`, `unrealized_pnl`, `positions`, and `timestamp`.
- `ExchangeGateway.get_account_snapshot()` is a cache reader and does not initiate a balance fetch.
- Owner Console `_account_facts()` already had an account facts response structure, but hardcoded `wallet_equity` and `available_margin` to `not_available`.
- The safe change was to map the cached snapshot only, not to call `fetch_account_balance()` or modify `exchange_gateway.py`.

## 3. AccountSnapshot Interpretation

- `AccountSnapshot.total_balance` is interpreted as `account_equity` / `wallet_equity`.
- `AccountSnapshot.available_balance` is interpreted as `available_margin`.
- `AccountSnapshot.timestamp` is exposed as `account_equity_timestamp_ms`.
- Freshness is classified from the cached snapshot timestamp:
  - `fresh` when the cached snapshot is not older than 5 minutes.
  - `stale` when older than 5 minutes.
  - `unknown` when timestamp is missing or future-skewed.
- Source is `runtime_cached_account_snapshot`.
- Truth level is `cached_exchange_read`.
- Reconciliation still comes from the existing local/exchange account facts reconciliation path. This mapping does not claim complete exchange account truth by itself.

## 4. Mapping / Implementation

Modified files:

- `src/interfaces/api_brc_console.py`
- `tests/unit/test_brc_console_api_surface.py`

Mapping:

- `wallet_equity = str(AccountSnapshot.total_balance)`
- `account_equity = str(AccountSnapshot.total_balance)`
- `available_margin = str(AccountSnapshot.available_balance)` when present
- unavailable fields remain `not_available`

Read-only reason:

- The endpoint uses only `exchange_gateway.get_account_snapshot()`.
- It does not call `fetch_account_balance()`.
- It does not call `place_order()`, `cancel_order()`, close, flatten, transfer, or withdrawal methods.
- `exchange_gateway.py` was not modified.

Tests added:

- Owner Console account facts maps cached `AccountSnapshot` equity without calling balance fetch.
- Existing account facts no-trading endpoint checks remain in place.

## 5. Ratio-based Budget Readiness

The bounded trial must still use Owner-confirmed ratios. No fixed USDT amount is authorized by this report.

```text
effective_max_notional =
min(
  account_equity * owner_confirmed_notional_pct,
  available_margin * available_margin_safety_pct if available,
  strategy_family_notional_cap if exists,
  symbol_notional_cap if exists,
  operation_layer_notional_cap if exists
)

effective_max_realized_loss =
min(
  account_equity * owner_confirmed_loss_pct,
  strategy_family_loss_cap if exists,
  daily_loss_cap_remaining if exists,
  operation_layer_loss_cap if exists
)
```

Owner still needs to provide the ratio values. Operation Layer cap enforcement still needs to be checked before any trial-start checklist is treated as executable.

## 6. Boundary Check

- 是否连接交易所？no
- 是否调用真实账户 API？no
- 是否创建 order？no
- 是否创建 execution intent？no
- 是否修改 execution permission？no
- 是否触碰 exchange_gateway？no
- 是否暴露 place_order / cancel_order 给 account equity path？no
- 是否触碰 api_research_jobs.py？no
- 是否启动 runtime？no
- 是否执行 trial？no

## 7. Readiness Verdict

needs_owner_ratio_values

Reason:

- The hardcoded `wallet_equity` / `available_margin` blocker in Owner Console account facts is removed when a cached `AccountSnapshot` exists.
- The path remains read-only and cache-only.
- MI-001 SOL long still needs Owner-confirmed notional and loss ratios.
- Trial start still needs a checklist that verifies Operation Layer caps, kill switch state, available-margin safety percentage, and fresh cached account facts.

## 8. Next Recommended Task

generate trial_start_checklist_mi001_sol_long
