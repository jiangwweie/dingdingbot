# Strategy Trial Controlled Testnet Carrier Path - BNB Result

Generated: 2026-06-01

## 1. Summary

Built a finite generic Strategy Trial Controlled Testnet Carrier path and wired `MI-001-BNB-LONG` as the first allowlisted carrier.

This replaces the previous blocker where BNB readiness existed but the controlled testnet same-path carrier route was missing. The implementation remains testnet-only and bounded:

- no live readiness
- no auto execution readiness
- no real funds
- no arbitrary symbol / side / leverage
- no credential changes
- no observation-to-live-order shortcut

The real BNB testnet rehearsal was not run in this shell because testnet runtime/profile credentials were not safely injected through the runtime environment. The pasted testnet credentials were not echoed, persisted, committed, or passed as command-line arguments.

Final state:

`testnet_rehearsal_blocked_with_explicit_reasons`

The remaining blocker is now environment/profile setup, not a missing BNB carrier path.

## 2. What Changed

| area | change |
| --- | --- |
| carrier allowlist | Added `StrategyTrialControlledTestnetCarrier` with `MI-001-BNB-LONG` as the first finite carrier. |
| runtime API | Added `GET /api/runtime/test/brc/carriers` and `POST /api/runtime/test/brc/carriers/{carrier_id}/execute-controlled-entry`. |
| BRC campaign envelope | Extended campaign creation to accept explicit max attempts, allowed runtime profile, and allowed symbol sequence. |
| attempt sequencing | Generalized BRC attempt sequencing to use the campaign risk envelope allowed-symbol sequence, preserving ETH/BTC behavior while enabling a single-symbol BNB carrier. |
| preflight gates | Added BNB carrier checks for testnet profile, non-live trading env, runtime flags, GKS, startup guard, reconciliation, fresh cached account facts, flat inventory, and cap/min-notional feasibility. |
| tests | Added targeted tests proving allowlist behavior, blocking gates, and successful mocked BNB carrier execution when gates pass. |

## 3. Why Finite Generic Carrier Path

A BNB-only naked endpoint would have created a second special-case order surface. Instead, the new path is a finite allowlisted carrier route:

`Strategy Trial Controlled Testnet Carrier -> allowlisted profile -> runtime/testnet gates -> BRC campaign envelope -> controlled entry`

Only `MI-001-BNB-LONG` is enabled in this sprint. Unsupported carriers, symbol overrides, side overrides, arbitrary amount, arbitrary leverage, and live profiles are rejected before the orchestrator can be called.

## 4. Files Changed

- `src/application/strategy_trial_controlled_testnet_carrier.py`
- `src/application/bounded_risk_campaign_service.py`
- `src/interfaces/api_console_runtime.py`
- `tests/unit/test_brc_controlled_testnet_endpoints.py`
- `reports/directional-opportunity-broad-smoke-20260529/strategy_trial_controlled_testnet_carrier_bnb_result.md`

## 5. Testnet Profile / Config Status

Required runtime config for a real BNB testnet rehearsal:

- `RUNTIME_PROFILE` resolved to one of:
  - `strategy_trial_bnb_testnet_runtime`
  - `brc_strategy_trial_bnb_testnet_runtime`
- runtime market symbols exactly:
  - `BNB/USDT:USDT`
- `EXCHANGE_TESTNET=true`
- `TRADING_ENV` not live/prod/production/mainnet/real
- `RUNTIME_CONTROL_API_ENABLED=true`
- `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=true`
- testnet credentials available through runtime environment / secret manager
- runtime cached account snapshot fresh enough
- GKS inactive
- startup guard armed
- reconciliation clean
- no BNB position
- no BNB open orders

This shell did not execute a real BNB testnet order because credentials were provided in chat, not through a safe runtime secret channel, and the runtime profile was not confirmed as a bound BNB testnet runtime process.

## 6. Rehearsal Result

Rehearsal was not run against Binance testnet in this task.

The BNB carrier route is no longer missing. In tests with a properly configured fake testnet runtime context, the route:

- resolves `MI-001-BNB-LONG`;
- rejects unsupported carriers;
- rejects wrong symbol and wrong side;
- rejects non-testnet runtime;
- rejects missing runtime control flags;
- rejects stale account facts;
- rejects conflicting position/open order;
- rejects GKS/startup/reconciliation blockers;
- executes a mocked BNB controlled entry when all gates pass;
- returns `testnet_rehearsal_completed` in the successful mocked path;
- keeps `live_ready=false` and `auto_execution_ready=false`.

Concrete current real-runtime blocker:

`testnet_runtime_profile_not_safely_bound_with_secret-backed_credentials`

## 7. Safety Proof

| check | result |
| --- | --- |
| live mode used | no |
| real funds used | no |
| live order placed | no |
| testnet order placed in this shell | no |
| credentials committed | no |
| credentials written to report | no |
| credentials echoed in commands | no |
| `exchange_gateway` modified | no |
| execution orchestrator modified | no |
| order lifecycle modified | no |
| execution permission granted | no |
| live auto execution enabled | no |
| withdrawal / transfer | no |
| arbitrary symbol / side / leverage | no |
| Operation Layer bypass | no |
| observation-to-live-order shortcut | no |

## 8. Tests / Validation

Validation commands:

- `python3 -m pytest -q tests/unit/test_brc_controlled_testnet_endpoints.py` passed: 23 passed.
- `python3 -m compileall -q src scripts` passed.
- `python3 -m pytest -q tests/unit/test_brc_controlled_testnet_endpoints.py tests/unit/test_strategy_trial_readiness.py tests/unit/test_brc_console_api_surface.py tests/unit/test_execution_permission.py` passed: 73 passed, with an existing SQLAlchemy async resource warning.

Full final validation is recorded in the assistant final response.

## 9. Final State

Final state:

`testnet_rehearsal_blocked_with_explicit_reasons`

Always:

- `not_live_ready`
- `not_auto_execution_ready`
- `no_real_funds`

## 10. Next Recommended Task

Bind a confirmed BNB testnet runtime profile with credentials supplied through a safe secret channel, then rerun `POST /api/runtime/test/brc/carriers/MI-001-BNB-LONG/execute-controlled-entry`.
