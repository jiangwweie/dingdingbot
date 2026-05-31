# Scheduled Read-only Observation v0 Result

Generated: 2026-05-31 15:13 CST

## 1. Summary

Implemented a cron-ready read-only observation v0 command for MI/CPM candidates:

`python3 scripts/run_strategy_group_readonly_observation_once.py --source live_market`

The command evaluates latest closed Binance USD-M public 1h bars for:

- `MI-001-SOL-LONG`
- `MI-001-BNB-LONG`
- `CPM-RO-001`

It writes observe-only evidence to PG table `brc_strategy_group_observations`. It does not start trial, start runtime, create execution intents, create or cancel orders, grant execution permission, modify leverage, transfer, withdraw, or call `exchange_gateway`.

## 2. Implementation

| component | status | notes |
| --- | --- | --- |
| CLI entrypoint | implemented | `scripts/run_strategy_group_readonly_observation_once.py` |
| scheduler service | implemented | `src/application/strategy_group_readonly_observation_scheduler.py` |
| market source | live public read-only | `binance_usdm_public_klines_read_only` |
| sink | PG durable observation table | `brc_strategy_group_observations` |
| candidates | 3 | SOL, BNB, CPM |
| runtime effect | none | no runtime/trial/order path |

## 3. First Run Result

Command:

`python3 scripts/run_strategy_group_readonly_observation_once.py --source live_market --json`

| candidate | signal_type | market_bar_timestamp_ms | close | action | record_id |
| --- | --- | ---: | ---: | --- | --- |
| MI-001-SOL-LONG | `no_action` | `1780207200000` | `82.9200` | `inserted` | `MI-001-SOL-LONG:mi001-9342cd877d28f8cb41360850:1780207200000` |
| MI-001-BNB-LONG | `no_action` | `1780207200000` | `736.310` | `inserted` | `MI-001-BNB-LONG:mi001-0736cdbfbcaf274e0b6a2c3f:1780207200000` |
| CPM-RO-001 | `no_action` | `1780207200000` | `2028.99` | `inserted` | `CPM-RO-001:cpm-914f90c8c1c094bf30452314:1780207200000` |

Run summary:

- candidates evaluated: `3`
- inserted: `3`
- skipped_duplicate: `0`
- failed: `0`
- market source: `binance_usdm_public_klines_read_only`
- source type: `live_market_read_only`
- sink: `pg_brc_strategy_group_observations`

## 4. Second Run / Idempotency Result

Command:

`python3 scripts/run_strategy_group_readonly_observation_once.py --source live_market --json`

| candidate | signal_type | market_bar_timestamp_ms | action | duplicate reason |
| --- | --- | ---: | --- | --- |
| MI-001-SOL-LONG | `no_action` | `1780207200000` | `skipped_duplicate` | `same_candidate_symbol_side_closed_bar_already_recorded` |
| MI-001-BNB-LONG | `no_action` | `1780207200000` | `skipped_duplicate` | `same_candidate_symbol_side_closed_bar_already_recorded` |
| CPM-RO-001 | `no_action` | `1780207200000` | `skipped_duplicate` | `same_candidate_symbol_side_closed_bar_already_recorded` |

Second run summary:

- candidates evaluated: `3`
- inserted: `0`
- skipped_duplicate: `3`
- failed: `0`

Duplicate prevention is application-level through PG lookup by:

- `candidate_id`
- `symbol`
- `side`
- `market_bar_timestamp_ms`

## 5. Safety Check

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
| 是否把 signal 当 order？ | no |
| 是否把 observation 当 execution readiness？ | no |

## 6. Next

Use this CLI from cron or an operator scheduler only in read-only observation mode.
