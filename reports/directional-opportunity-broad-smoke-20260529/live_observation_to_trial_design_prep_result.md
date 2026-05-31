# Live Observation to BNB Trial Design Prep Result

Generated: 2026-05-31 15:13 CST

## 1. Summary

Completed the transition from live read-only observation run-once toward scheduled observation and BNB bounded-trial design preparation.

This task did not start a trial, start runtime execution, create execution intents, create or cancel orders, grant execution permission, change leverage, transfer, withdraw, modify API keys, modify `exchange_gateway`, or touch execution/order/live runner files.

## 2. Scheduled Observation v0

Implemented and ran:

`python3 scripts/run_strategy_group_readonly_observation_once.py --source live_market`

Result:

- public Binance USD-M klines only
- latest closed 1h bars only
- candidates: SOL, BNB, CPM
- sink: `brc_strategy_group_observations`
- first run inserted 3 rows
- second run skipped the same 3 rows as duplicates

Idempotency key:

- `candidate_id`
- `symbol`
- `side`
- `market_bar_timestamp_ms`

## 3. BNB Live Case #001

Created:

`reports/directional-opportunity-broad-smoke-20260529/mi001_bnb_live_case_001.md`

Source PG observation row:

`MI-001-BNB-LONG:mi001-5bb8b1c1b14437d7bddbacab:1780196400000`

Signal:

- `signal_type = would_enter`
- `source_type = live_market_read_only`
- `market_bar_close = 740.200`
- `impulse_return_pct = 6.5051`

Forward tracking:

- 1h available: close return `-0.7593%`, MFE `0.3121%`, MAE `-1.1483%`
- 4h / 12h / 24h / 72h pending

Interpretation: valid live observation case, still pending as a trade-quality case. The first 1h outcome highlights local exhaustion risk.

## 4. BNB Bounded Trial Design v0

Created:

`reports/directional-opportunity-broad-smoke-20260529/mi001_bnb_bounded_trial_design_v0.md`

Status:

- `design_only`
- `not_trial_ready`
- `not_execution_ready`

Design boundary:

- Owner confirms each entry.
- `would_enter` means Owner review, not order.
- dedicated subaccount equity as capital model.
- max leverage `5x`.
- no auto top-up, transfer, withdrawal, symbol expansion, side expansion, or leverage expansion.
- max simultaneous position draft: `1`.
- max attempts draft: `3`.
- review windows: `1h`, `4h`, `12h`, `24h`, `72h`, `7d`.

## 5. Readiness Gap Check

Created:

`reports/directional-opportunity-broad-smoke-20260529/bnb_trial_readiness_gap_check.md`

Current BNB gaps:

- BNB-specific Operation Layer cap missing.
- BNB-specific trial/admission registration missing.
- Owner BNB trial approval missing.
- Startup guard remains runtime-coupled.
- No execution/order path is enabled.

Current available facts:

- GKS PG state is `active=False`.
- Active BNB position count is `0`.
- Open BNB order count is `0`.
- Durable PG observation history exists.

## 6. Safety Check

| check | answer |
| --- | --- |
| 是否启动 trial？ | no |
| 是否启动 runtime execution？ | no |
| 是否下单？ | no |
| 是否取消订单？ | no |
| 是否创建 execution intent？ | no |
| 是否授予 execution permission？ | no |
| 是否修改杠杆？ | no |
| 是否 set_leverage？ | no |
| 是否转账/提现？ | no |
| 是否修改 exchange_gateway？ | no |
| 是否修改 execution/order/live runner？ | no |
| 是否把 signal 当 order？ | no |
| 是否把 observation 当 execution readiness？ | no |

## 7. Tests / Validation

Commands run for implementation and evidence:

- `python3 -m pytest -q tests/unit/test_strategy_group_live_readonly_observation.py`
- `python3 scripts/run_strategy_group_readonly_observation_once.py --source live_market --json`
- repeated the same CLI command to verify duplicate skipping
- PG read-only query for BNB live observation rows
- public Binance USD-M kline read for BNB case OHLCV and 1h forward outcome
- PG read-only query for GKS, BNB active positions, and BNB open orders

Final validation commands are recorded in the assistant final response for this task.

## 8. Remaining Work

- Add BNB-specific trial/admission registration if Owner wants to move from review to rehearsal.
- Add BNB Operation Layer notional/loss cap metadata.
- Implement forward outcome persistence for 1h/4h/12h/24h/72h windows.
- Resolve runtime-owned startup guard blocker before any start-like action.

## 9. Next Recommended Task

Implement forward outcome persistence for BNB live signal case windows.
