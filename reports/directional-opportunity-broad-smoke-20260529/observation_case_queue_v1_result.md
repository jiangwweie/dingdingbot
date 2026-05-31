# Observation Case Queue v1 Result

Generated: 2026-05-31

## 1. Summary

Built Observation Case Queue v1 for MI / CPM live read-only signals.

The queue promotes persisted `would_enter` observation rows into Owner-review cases, attaches persisted forward review windows, excludes `no_action` and `invalid` rows from the case queue, and preserves explicit non-permissions.

This is not trial start, order creation, execution intent creation, execution permission, runtime start, or trade advice.

## 2. Path Chosen

Path: backend read-only aggregate + API + Owner Console panel.

Reason:

- Existing `brc_strategy_group_observations` and `brc_strategy_group_forward_reviews` already separate observation evidence from execution/order concepts.
- A queue read model can be derived without schema changes, without touching runtime/execution/order files, and without starting any runner.
- Owner Console already renders MI / CPM observation status, so the lowest-risk UI path is to add a case queue section to that existing panel.

## 3. Queue Model

| item | value |
| --- | --- |
| service | `src/application/strategy_group_observation_case_queue.py` |
| API | `GET /api/brc/strategy-groups/observation-cases/v1` |
| observation source | `pg_brc_strategy_group_observations` |
| forward review source | `pg_brc_strategy_group_forward_reviews` |
| included signal types | `would_enter` |
| excluded signal types | `no_action`, `invalid` |
| runtime effect | none |
| order/execution effect | none |

Per case, the read model exposes:

- `case_id`
- `observation_id`
- `candidate_id`
- `signal_type`
- `case_status`
- `owner_review_status`
- market timestamp / source
- completed and pending review windows
- forward review rows
- risk tags
- human summary / Owner interpretation
- non-permission flags

## 4. BNB Case #001

The queue maps the known BNB live observation row to:

| field | value |
| --- | --- |
| case_id | `MI-001-BNB-LONG-live-case-001` |
| observation_id | `MI-001-BNB-LONG:mi001-5bb8b1c1b14437d7bddbacab:1780196400000` |
| candidate_id | `MI-001-BNB-LONG` |
| signal_type | `would_enter` |
| expected status | `pending_forward_review` while 12h / 24h / 72h remain pending |
| completed windows | `1h`, `4h` |
| pending windows | `12h`, `24h`, `72h` |
| risk tags | `bnb_live_case_001`, `local_exhaustion_watch`, `adverse_path_watch`, `no_chase_required`, `wait_for_confirmation_required` |

The queue preserves the prior interpretation: BNB case #001 is valid as a live observation case, not validated as a trade case.

## 5. CPM Case Readiness

Current CPM `no_action` records are excluded from the case queue.

The queue explicitly supports future CPM `would_enter` records. Those future records will enter Owner review with CPM-specific risk tags:

- `owner_special_observation`
- `historical_oos_negative_warning`
- `not_proven_alpha`
- `not_runtime_eligible_by_default`

CPM remains an Owner special observation family and is not runtime eligible by default.

## 6. API / Console Impact

API:

- Added `GET /api/brc/strategy-groups/observation-cases/v1`.
- The endpoint reads PG observation and forward review tables only.
- It returns a blocked response if PG is unavailable rather than starting any runner or using execution paths.

Console:

- `/strategy-groups` now requests the case queue API.
- The Live Read-only Observation Readiness panel now shows Observation Case Queue v1.
- BNB case #001 appears with completed/pending review windows and risk tags when the API returns PG queue data.
- CPM no-action observations remain excluded from case review.
- The panel keeps non-permission language visible.

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
| 是否把 case queue 当 trade recommendation？ | no |

## 8. Tests / Validation

Commands run:

- `python3 -m compileall -q src scripts`
- `python3 -m pytest -q tests/unit/test_strategy_group_live_readonly_observation.py tests/unit/test_brc_console_api_surface.py tests/unit/test_execution_permission.py`
- `cd gemimi-web-front && npx vitest run src/pages/brc/OwnerConsoleV2.test.tsx`

Additional PG verification attempt:

- A direct read-only queue probe was run against the configured local PG.
- Result: `probe_pg_connectivity()` returned `false` in this shell, so the live local PG rows were not directly readable from this session.
- The API is designed to return `blocked_pg_unavailable` in that condition.
- Unit tests cover the BNB case #001 mapping and CPM future `would_enter` mapping using the same application read model.

## 9. Remaining Work

- Run the case queue endpoint in the dev environment where PG is available to visually confirm the real BNB case row appears in Owner Console.
- Continue BNB case #001 forward review after the pending windows reach due time.

## 10. Next Recommended Task

Owner Console case queue visual verification with dev PG available.
