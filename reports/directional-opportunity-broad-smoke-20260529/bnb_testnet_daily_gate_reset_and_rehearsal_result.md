# BNB Testnet Daily Gate Reset and Protection Rehearsal Result

## 1. Starting State

- Task: resolve the `DAILY_TRADE_COUNT_LIMIT` blocker for the MI-001 BNB controlled testnet carrier and rerun the protected testnet rehearsal.
- Carrier: `MI-001-BNB-LONG`
- Symbol: `BNB/USDT:USDT`
- Runtime profile: `strategy_trial_bnb_testnet_runtime`
- Trading environment verified for the run: `TRADING_ENV=testnet`, `EXCHANGE_TESTNET=true`
- Previous blocker: daily trade count restored from `scope_key=runtime:default`, `trade_count=1`
- Required protection plan: `single_tp_plus_sl` for `0.01` BNB

This was a testnet/dev rehearsal task only. It was not a live trial, not real funds, not live execution permission, and not auto execution.

## 2. DAILY_TRADE_COUNT_LIMIT Source

| fact | result |
| --- | --- |
| gate source | `CapitalProtectionManager._check_daily_trade_count()` |
| persisted source | `daily_risk_stats_aggregates` / `daily_risk_stats_events` |
| old scope observed | `runtime:default` |
| old row state | `stats_date=2026-06-01`, `trade_count=1`, `realized_pnl=-0.009900000000000000` |
| cause | prior BNB testnet rehearsal close recorded one closed trade |
| initial classification | broad/default runtime counter, unsafe to reset directly |
| repair path | isolate confirmed testnet runtime profiles into `runtime_profile:<profile>` daily-risk scope |

The old `runtime:default` row was not reset.

## 3. Scope Classification

| counter | classification | action |
| --- | --- | --- |
| `runtime:default` | `global_live_or_unknown_counter` for reset purposes | left untouched |
| `runtime_profile:strategy_trial_bnb_testnet_runtime` | `strategy_trial_bnb_profile_counter` | allowed for testnet/profile-scoped reset |

The reset helper refuses:

- `TRADING_ENV=live`
- non-`testnet` trading env
- `EXCHANGE_TESTNET=false` or unknown
- missing runtime profile
- profile other than `strategy_trial_bnb_testnet_runtime`
- symbol other than `BNB/USDT:USDT`
- carrier other than `MI-001-BNB-LONG`
- broad/default `runtime:default` scope

## 4. Reset / Cleanup Performed

| item | before | after | action |
| --- | --- | --- | --- |
| daily risk `runtime:default` | `trade_count=1` | `trade_count=1` | no reset |
| daily risk profile scope | row absent | runtime restored/created `trade_count=0` | profile-scoped isolation |
| reset script result | no profile row found | no-op | `scripts/reset_bnb_testnet_daily_gate.py` completed with `row_found=false` |
| stale runtime campaign state | `armed`, carrier `MI-001-BNB-LONG` | cleaned to `closed`, then reset to `observe` | allowed only with same carrier and flat proof |
| stale empty BRC campaign | `observe`, attempt_count `0` | `ended_manual_stop` | finalized before retry |

No live/global daily risk counter was reset.

## 5. BNB Rehearsal Result

| check | result |
| --- | --- |
| runtime profile | `strategy_trial_bnb_testnet_runtime` |
| exchange mode | Binance testnet |
| GKS | clear, `active=false` |
| startup guard | runtime-owned guard armed by preflight |
| reconciliation before entry | clean |
| account facts | runtime cached snapshot fresh enough for testnet preflight |
| active BNB position before entry | 0 |
| BNB open orders before entry | 0 |
| protection plan before entry | `single_tp_plus_sl`, valid |
| entry | filled, `0.01` BNB, exchange order `1424453419` |
| TP | single TP placed for `0.01` BNB, exchange order `1424453440`, later terminalized/canceled during cleanup |
| SL | placed for `0.01` BNB, exchange order `1000000092441892`, canceled during cleanup |
| cleanup close | filled, reduce-only close order `1424454000` |
| final BNB position | flat, local active positions `0` |
| final local open orders | `0` |
| periodic reconciliation | consistent after close |
| latest campaign | `brc-0dfc16d54418`, `ended`, outcome `ended_manual_stop`, closed attempt |
| final state | `testnet_rehearsal_completed_with_valid_protection`, `not_live_ready` |

## 6. Files Changed

- `src/application/capital_protection.py`
- `src/application/testnet_daily_gate_reset.py`
- `src/infrastructure/pg_testnet_daily_gate_reset.py`
- `src/interfaces/api_console_runtime.py`
- `src/main.py`
- `scripts/reset_bnb_testnet_daily_gate.py`
- `tests/unit/test_bnb_testnet_daily_gate_reset.py`
- `tests/unit/test_brc_controlled_testnet_endpoints.py`
- `tests/unit/test_ls002b_daily_risk_stats_persistence.py`
- `reports/directional-opportunity-broad-smoke-20260529/bnb_testnet_daily_gate_reset_and_rehearsal_result.md`

## 7. Tests Run

- `python3 -m pytest -q tests/unit/test_bnb_testnet_daily_gate_reset.py tests/unit/test_ls002b_daily_risk_stats_persistence.py tests/unit/test_protection_order_planner.py`
- `python3 -m pytest -q tests/unit/test_brc_controlled_testnet_endpoints.py::test_strategy_trial_carrier_finalizes_stale_empty_campaign_before_retry tests/unit/test_brc_controlled_testnet_endpoints.py::test_strategy_trial_carrier_cleans_stale_armed_state_only_when_flat tests/unit/test_brc_controlled_testnet_endpoints.py::test_strategy_trial_carrier_bnb_controlled_route_executes_when_gates_pass`
- Additional final validation is recorded in the task summary.

## 8. Safety Proof

| item | result |
| --- | --- |
| live mode used | no |
| real funds used | no |
| live daily risk reset | no |
| live/global counter reset | no |
| credentials printed or committed | no |
| live order | no |
| testnet controlled order | yes |
| live execution permission granted | no |
| order permission changed | no |
| leverage changed | no |
| transfer / withdrawal | no |
| exchange_gateway modified | no |
| observation-to-live-order shortcut | no |
| Operation Layer bypass | no |

## 9. Final State

`testnet_rehearsal_completed_with_valid_protection`

The system remains:

- `not_live_ready`
- `not_auto_execution_ready`
- `no_real_funds`

## 10. Next Recommended Task

Prepare the Owner review packet for the completed BNB protected testnet rehearsal.
