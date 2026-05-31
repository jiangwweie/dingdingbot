# Live Observation Forward Review v1 Result

Generated: 2026-05-31 15:28 CST

## 1. Summary

Built forward review tracking v1 for `MI-001-BNB-LONG-live-case-001`.

The implementation persists forward review windows for the source observation signal in PG, calculates completed windows from Binance public USD-M closed 1h klines, marks not-yet-due windows pending, and exposes review records through the existing read-only observation API payload.

This task did not start trial, start runtime execution, create execution intents, create or cancel orders, grant execution permission, modify leverage, transfer, withdraw, modify API keys, or modify `exchange_gateway`.

## 2. Path Chosen

Path: dedicated PG forward review evidence table.

Reason:

- Existing historical forward outcome tables are scoped to historical experiment runs.
- Reusing them for a live read-only observation case would blur historical research evidence with current observation evidence.
- A dedicated `brc_strategy_group_forward_reviews` table keeps the scope explicit and enforces non-permission flags.

## 3. Forward Review Persistence

| item | value |
| --- | --- |
| table | `brc_strategy_group_forward_reviews` |
| ORM | `PGBrcStrategyGroupForwardReviewORM` |
| repository | `PgStrategyGroupForwardReviewRepository` |
| migration | `2026-05-31-029_create_strategy_group_forward_reviews.py` |
| calculator | `calculate_forward_reviews_for_observation` |
| command | `python3 scripts/run_bnb_live_case_forward_review_once.py` |
| source | Binance public USD-M 1h klines |
| runtime effect | none |
| order/execution effect | none |

Persisted fields include:

- `observation_id`
- `candidate_id`
- `symbol`
- `side`
- `signal_type`
- `market_bar_timestamp_ms`
- `review_window`
- `review_due_at_ms`
- `review_status`
- `forward_return_pct`
- `mfe_pct`
- `mae_pct`
- `source`
- `calculated_at_ms`
- `notes`

Non-permission flags are persisted as true:

- `not_order`
- `not_execution_intent`
- `no_execution_permission`
- `no_order_permission`
- `no_runtime_start`

## 4. BNB Case #001 Review Table

Source observation:

`MI-001-BNB-LONG:mi001-5bb8b1c1b14437d7bddbacab:1780196400000`

| window | status | due_at_utc | forward_return | MFE | MAE | calculated_at_utc |
| --- | --- | --- | ---: | ---: | ---: | --- |
| 1h | `completed` | `2026-05-31T05:00:00Z` | `-0.7593%` | `0.3121%` | `-1.1483%` | `2026-05-31T07:28:58.745Z` |
| 4h | `pending` | `2026-05-31T08:00:00Z` | n/a | n/a | n/a | n/a |
| 12h | `pending` | `2026-05-31T16:00:00Z` | n/a | n/a | n/a | n/a |
| 24h | `pending` | `2026-06-01T04:00:00Z` | n/a | n/a | n/a | n/a |
| 72h | `pending` | `2026-06-03T04:00:00Z` | n/a | n/a | n/a | n/a |

The pending windows were persisted with due times. They were not calculated or fabricated before the relevant closed bars exist.

## 5. API / Console Impact

API:

- `GET /api/brc/strategy-groups/live-readonly-observation/v1` now includes `forward_review_summary`.
- The summary contains `review_count`, `by_observation_id`, `writes_execution_or_order_tables=false`, and `runtime_effect=none`.
- The API remains read-only and falls back safely if PG review data is unavailable.

Console:

- No frontend code was changed in this task.
- Owner Console can consume `forward_review_summary` from the existing observation API. A dedicated UI rendering refinement can be added separately if needed.

## 6. Readiness Interpretation

Does the 1h adverse move change trial design?

- It does not invalidate the BNB design by itself.
- It should add a stronger local-exhaustion / no-chase note.

Does it suggest local exhaustion risk?

- Yes. A `-0.7593%` 1h return with only `0.3121%` MFE after a `6.5051%` 12h impulse is consistent with short-term exhaustion risk.

Should it change exit draft?

- It supports keeping short-window review gates and an invalidation stop in the design.
- It argues against immediate signal-to-order conversion, which is already forbidden.

Should it require wait-for-confirmation?

- Yes for any future design iteration. The current evidence supports Owner review plus wait-for-confirmation, not chase execution.

Should it affect Owner decision options?

- Yes. Owner options should remain: continue observation, wait for 4h/12h follow-through, or keep BNB parked. It should not become a start/order option.

## 7. Safety Check

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
| 是否把 forward review 当 trade recommendation？ | no |

## 8. Tests / Validation

Commands run for implementation evidence:

- `python3 -m pytest -q tests/unit/test_strategy_group_live_readonly_observation.py`
- `python3 scripts/run_bnb_live_case_forward_review_once.py`

Final validation commands are recorded in the assistant final response for this task.

## 9. Remaining Work

- Re-run the forward review command after 4h / 12h / 24h / 72h due times.
- Add a focused Owner Console visual treatment for forward review windows if desired.
- Add broader multi-case forward review scheduling after more live cases accumulate.

## 10. Next Recommended Task

Re-run BNB case #001 forward review after the 4h window due time.
