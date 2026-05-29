# Account Facts Read Model Result

Generated: 2026-05-29

Scope: `MI-001 SOL/USDT:USDT long` trial readiness account facts read model.

This report is a review artifact only. It is not runtime source of truth and does not authorize trial start.

## 1. Summary

Implemented a minimal read-only account facts model for trial readiness.

The model is injectable and can consume pre-collected PG/local cached facts without touching runtime, exchange gateway, execution, orders, or live runner code.

No real account facts were read in this task because no independent PG/local account facts source currently exists. The checklist therefore remains blocked.

## 2. Path Chosen

Path B: injectable read-only interface + fake tests.

Reason:

- No dedicated PG account facts / account snapshot table was found that can provide timestamped equity, available margin, freshness, and reconciliation status for trial readiness.
- The visible runtime cache helper reads through `_exchange_gateway.get_account_snapshot`; this task must not use that path.
- A minimal interface lets future PG/local cached sources plug in safely without changing checklist logic.

## 3. Account Facts Source

| source | status | notes |
| --- | --- | --- |
| PG account facts table | not_found | No dedicated table with the required readiness fields was found. |
| legacy `accounts` table | not_sufficient | It has balance fields but no timestamped freshness, available margin source, or reconciliation status suitable for trial readiness. |
| runtime cached account snapshot | unsafe_for_this_task | Visible helper reads through `_exchange_gateway.get_account_snapshot`; not invoked. |
| injected read-only source | implemented | Tests use `StaticTrialReadinessAccountFactsSource`; production/local source remains future work. |

## 4. Implementation Summary

Added:

- `src/application/trial_readiness_account_facts.py`

Updated:

- `src/application/mi001_sol_trial_start_checklist.py`
- `tests/unit/test_mi001_sol_trial_start_checklist.py`
- `reports/directional-opportunity-broad-smoke-20260529/trial_start_checklist_mi001_sol_long.md`

The read model expresses:

- `account_id`
- `source_id`
- `source_type`
- `account_equity`
- `available_margin`
- `timestamp_ms`
- `freshness_status`
- `reconciliation_status`
- `read_only_guarantee`
- `external_call_performed`
- `notes`

Readiness blockers include:

- external account call performed;
- read-only guarantee missing;
- account equity missing;
- available margin missing;
- timestamp missing;
- stale/missing/unknown freshness;
- reconciliation mismatch.

## 5. Checklist Impact

The checklist logic can now consume an injected read-only account facts source.

Test-only fake facts prove the capital calculation:

`computed_max_notional_candidate = min(account_equity * 5, available_margin * 5, operation_layer_notional_cap_if_exists)`

Real checklist verdict did not change because no real safe source is wired:

`blocked_fresh_account_facts_required`

No fake/test account facts were written into the report as real readiness.

## 6. Safety Check

| check | answer |
| --- | --- |
| 是否连接交易所？ | no |
| 是否调用真实账户 API？ | no |
| 是否触碰 exchange_gateway？ | no |
| 是否触碰 execution/order/live runner？ | no |
| 是否创建 execution intent？ | no |
| 是否创建 order？ | no |
| 是否启动 trial？ | no |
| 是否使用 fake account facts 写入 report？ | no |
| 是否把 fake/test facts 当真实 readiness？ | no |

## 7. Next Recommended Task

Implement a PG-backed account facts snapshot repository for trial readiness.
