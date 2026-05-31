# CPM Special Observation v1 Result

Generated: 2026-05-31 16:43 CST

## 1. Summary

Completed CPM-RO-001 Owner Special Observation reviewability work.

This task:

- reviewed CPM evaluator and historical evidence paths;
- generated a current live read-only CPM observation snapshot;
- persisted that snapshot to PG;
- created Owner review packet and CPM vs MI comparison;
- checked API / Console readiness for CPM special observation status.

It did not start a trial, start runtime execution, create an execution intent, create or cancel orders, grant execution permission, modify leverage, transfer, withdraw, or modify `exchange_gateway`.

## 2. Path Chosen

Path chosen: read-only observation and report packet, no API change.

Reason:

- CPM evaluator glue already exists and is wired to `CPMRO001HistoricalEvaluator`.
- PG-backed observation persistence already exists through `brc_strategy_group_observations`.
- `GET /api/brc/strategy-groups/reviewability` already exposes CPM as `owner_special_observation`, OOS negative, not proven alpha, and not runtime eligible by default.
- `GET/POST /api/brc/strategy-groups/live-readonly-observation/v1` already exposes current signal/history and non-permissions.
- Owner Console can consume those fields; the missing artifact was the Owner review packet and comparison framing.

## 3. CPM Review Packet

Created:

`reports/directional-opportunity-broad-smoke-20260529/cpm_owner_special_observation_review_packet.md`

Packet covers:

- CPM strategy description;
- market regimes it eats and hates;
- 2021/2022 OOS negative warning;
- Owner rationale for special observation;
- current live observation snapshot;
- review metrics;
- invalidation conditions;
- Owner decision options;
- non-permissions.

Historical evidence summary:

| item | status |
| --- | --- |
| signal definition / evaluator contract | available in `src/domain/cpm_historical_evaluator.py` |
| 2021 OOS warning | available; negative, `-21.54%`, 74 positions |
| 2022 OOS warning | available; negative, `-9.72%`, 51 positions |
| feature-context extraction | available; 329 positions; 2021/2023 failure modes identifiable |
| mildness evidence | partial; 2024 winners show lower-volatility and slower continuation, but not alpha proof |
| runtime eligibility | not eligible by default |

## 4. CPM Live Observation Snapshot

Command run:

`python3 scripts/run_strategy_group_readonly_observation_once.py --source live_market --json`

Current CPM row:

| field | value |
| --- | --- |
| candidate_id | `CPM-RO-001` |
| record_id | `CPM-RO-001:cpm-fb9e296ef9beebce7ba18cea:1780210800000` |
| signal_type | `no_action` |
| side | `none` |
| market_bar_timestamp | `2026-05-31T07:00:00Z` |
| market_bar_close | `2023.14` |
| source_type | `live_market_read_only` |
| market_source | `binance_usdm_public_klines_read_only` |
| sink_status | `recorded_pg` |
| reason_codes | `cpm_no_action_trend_ambiguous` |
| human_summary | `4h trend is ambiguous under CPM v0.` |

Evidence payload summary:

| field | value |
| --- | --- |
| htf_trend | `neutral` |
| primary_trend | `down` |
| trend_alignment | `unknown` |
| regime | `transition` |
| entry_pattern | `bounce_loss` |
| pullback_depth_pct | `1.1372` |
| bounce_depth_pct | `1.1502` |
| long_reclaim_confirmed | `false` |
| short_loss_confirmed | `true` |

Interpretation:

- The snapshot is live read-only, persisted, and Owner-reviewable.
- It is `no_action`, not a missed trade.
- Condition missing: 4h trend alignment. The evaluator saw transition/ambiguous trend, so it refused a would-enter observation despite some structure-loss markers.
- No forward review is required for this `no_action` row.

## 5. CPM vs MI Comparison

Created:

`reports/directional-opportunity-broad-smoke-20260529/cpm_vs_mi_observation_comparison.md`

Core comparison:

| topic | MI | CPM |
| --- | --- | --- |
| style | aggressive momentum impulse | calmer pullback-continuation observation |
| current live review | BNB case #001 under forward review | current snapshot `no_action` |
| risk path | local exhaustion, high MAE, right-tail dependence | ambiguous trend, slow adverse continuation, OOS negative recurrence |
| Owner role | review strong signals and adverse path quickly | evaluate whether no-action/would-enter selectivity is useful |
| trial posture | design discussion exists for BNB; no authorization | observation only; bounded review discussion only after evidence |

## 6. API / Console Impact

Checked:

- `build_strategy_group_reviewability_snapshot()`
- `GET /api/brc/strategy-groups/reviewability` model path
- `GET/POST /api/brc/strategy-groups/live-readonly-observation/v1` model path

Result: no API change was needed for this task.

Existing fields already cover:

- CPM special observation status;
- historical OOS negative warning;
- not proven alpha;
- not runtime eligible by default;
- live read-only observation readiness;
- current signal / history;
- non-permissions.

Report-only additions provide the missing Owner narrative and review rules without expanding runtime/API scope.

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
| 是否把 CPM 标成 proven alpha？ | no |
| 是否自动提升 CPM runtime eligibility？ | no |

## 8. Tests / Validation

Commands run:

- `git status --short`
- `git log --oneline -12`
- `git diff --stat`
- `rg` over CPM / MI / forbidden execution paths
- `python3 scripts/run_strategy_group_readonly_observation_once.py --source live_market --json`
- PG readback for `CPM-RO-001` current row via `PgStrategyGroupObservationRepository`
- `python3` check of `build_strategy_group_reviewability_snapshot()` CPM fields

Final validation commands are recorded in the assistant final response for this task.

## 9. Remaining Work

- Accumulate enough CPM live read-only observations to compute no-action ratio, would-enter count, invalid count, and forward outcomes.
- Add CPM-specific forward review case packet if a future `would_enter` row appears.
- Decide later whether Owner wants CPM to remain observation-only, revise, park, or become an owner-special bounded review candidate.

## 10. Next Recommended Task

Continue CPM live read-only observation until the first `would_enter` CPM case appears, then create CPM live case #001 review.
