# BNB Testnet Rehearsal Preflight Fact Collector Result

## 1. Summary

Implemented a generic read-only preflight fact collector for the `StrategyTrialReadiness` framework, using MI-001 BNB long as the first carrier.

This is not a trial start, not an order task, not execution intent creation, and not execution permission. The collector only reads injected/runtime/PG read paths where available; unavailable facts remain explicit rehearsal blockers.

## 2. Path Chosen

Path A/B hybrid:

- Added an injectable generic collector in application code.
- Wired the Owner Console API to try existing read-only runtime/PG paths for active positions, open orders, GKS, startup guard, and reconciliation.
- Account facts freshness remains unavailable unless a safe account-facts reader is injected, so it is an explicit blocker.
- No exchange gateway, execution orchestrator, order lifecycle, live runner, leverage, transfer, or withdrawal path was touched.

## 3. Fact Collection Coverage

| fact | status behavior | read path | blocker when unavailable/blocked |
| --- | --- | --- | --- |
| active position for `BNBUSDT` | clear if no active positions; blocked if any active position exists | injected `_position_repo.list_active` or PG `PgPositionRepository.list_active` | `active_position_check_required_before_rehearsal` / `conflicting_position_exists` |
| open orders for `BNBUSDT` | clear if no open orders; blocked if any open order exists | injected `_order_repo.get_open_orders` or PG `PgOrderRepository.get_open_orders` | `open_order_check_required_before_rehearsal` / `conflicting_open_order_exists` |
| GKS | clear when `active=False`; blocked when `active=True` | runtime GKS service or PG GKS repository | `gks_status_required_before_rehearsal` / `gks_blocked` |
| startup guard | clear when `armed=True`; blocked when `armed=False` | runtime-owned startup guard service only | `startup_guard_status_required_before_rehearsal` / `startup_guard_blocked` |
| reconciliation | clean when summary is clean; blocked on mismatch/failure | bound startup reconciliation summary | `reconciliation_status_required_before_rehearsal` / `reconciliation_not_clean` |
| account facts freshness | clear only when injected fresh account facts are available | injected account facts reader only | `account_facts_required_before_rehearsal` |

## 4. API / Console Impact

- `GET /api/brc/strategy-trial-readiness/v1` now includes `fact_checks`.
- The API response keeps `live_ready=false` and `auto_execution_ready=false`.
- Owner Console `Strategy Trial Readiness Framework` panel now renders a `Preflight facts` block showing each fact status and blocker.
- Missing facts are no longer represented only by generic `*_not_checked` labels; they are concrete rehearsal blockers.

## 5. Readiness Semantics

Possible terminal states remain:

- `testnet_rehearsal_ready_pending_owner_authorization`
- `testnet_rehearsal_not_ready_with_explicit_blockers`

Owner testnet authorization missing is tracked as `owner_testnet_authorization_missing` warning while otherwise-clear facts can still return `testnet_rehearsal_ready_pending_owner_authorization`.

## 6. Safety Check

| item | result |
| --- | --- |
| trial started | no |
| runtime execution started | no |
| order created | no |
| order cancelled | no |
| ExecutionIntent created | no |
| execution permission granted | no |
| leverage modified | no |
| `set_leverage` called | no |
| transfer/withdrawal | no |
| exchange gateway modified | no |
| execution/order/live runner modified | no |
| signal treated as order | no |
| testnet readiness treated as execution authorization | no |

## 7. Tests / Validation

- `python3 -m compileall -q src scripts` passed.
- `python3 -m pytest -q tests/unit/test_strategy_trial_readiness.py tests/unit/test_brc_console_api_surface.py tests/unit/test_execution_permission.py` passed: 47 passed, 2 existing SQLAlchemy resource warnings.
- `cd gemimi-web-front && npm run lint` passed.
- `cd gemimi-web-front && npx vitest run` passed: 7 files, 12 tests.
- `cd gemimi-web-front && npm run build` passed.

## 8. Remaining Work

- Inject a safe account facts freshness source for BNB rehearsal readiness.
- Bind runtime startup guard/reconciliation summaries when running an actual testnet-control process.
- Resolve any concrete fact blockers before Owner can authorize same-path testnet rehearsal.

## 9. Next Recommended Task

Inject safe BNB account facts freshness into the testnet rehearsal preflight collector.
