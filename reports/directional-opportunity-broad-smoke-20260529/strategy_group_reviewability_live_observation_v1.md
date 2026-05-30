# Strategy Group Reviewability + Live Read-only Observation v1

## 1. Summary

This task moved the MI / CPM strategy-group shelf from display-only review into an Owner-reviewable read-only aggregate plus live read-only observation v1 wiring.

Completed closure:

- MI-001 SOL and MI-001 BNB have Owner-reviewable candidate evidence, including repaired BNB coverage, BNB/SOL comparison, cost/baseline/top-tail/dedup/year-split fields, and representative 72h cases.
- CPM-RO-001 remains `owner_special_observation` with explicit 2021/2022 OOS negative disclosure, not proven alpha, and not runtime eligible by default.
- Added strategy-specific read-only signal evaluator glue for MI and CPM using the existing `StrategyFamilySignalOutput` contract: `no_action`, `would_enter`, and `invalid`.
- Added a read-only API surface for observation v1 status and exposed it to the Owner Console.

No trial was started. No runtime execution was started. No execution intent or order was created. No execution permission was granted.

## 2. Path Chosen

Path chosen: implement a safe read-only v1 layer rather than starting observation.

Implementation path:

- Pure application service for MI / CPM evaluator glue and observation status.
- Read-only API endpoint for strategy-group live observation v1.
- Strategy group reviewability aggregate updated to reflect evaluator glue is now wired but live runner binding / scheduled observation sink remain blocked.
- Owner Console consumes the new observation status and shows candidate-level read-only observation readiness.
- Report artifacts updated for Owner review.

## 3. MI Evidence Review

| candidate | coverage | signal_count | dedup_signal_count | 24h mean / positive | 72h mean / positive | 7d mean / positive | 72h MFE / MAE | status |
| --- | --- | ---: | ---: | --- | --- | --- | --- | --- |
| MI-001 BNB long | 2021-01-01 -> 2026-05-20; 47184 bars; missing 0 | 4166 | 714 | 0.8087 / 0.4851 | 2.4074 / 0.5470 | 5.4482 / 0.5552 | 8.7626 / -5.9467 | strong_smoke_candidate / reviewable_with_repaired_coverage |
| MI-001 SOL long | 2021-01-01 -> 2026-05-20; 47064 bars; missing 120 | 8135 | 1271 | 0.6373 / 0.5019 | 1.9531 / 0.5175 | 4.7372 / 0.5398 | 10.2580 / -7.8922 | chain_sample / reviewable_with_risk_tags |

Representative 72h cases:

| candidate | positive case | adverse case | typical case |
| --- | --- | --- | --- |
| BNB | 2021-02-17 09:00, 72h return 121.5050, MFE 161.6275, MAE -0.1458 | 2021-05-16 12:00, 72h return -43.2491, MFE 0.6458, MAE -56.0425 | 2022-01-23 12:00, 72h return 0.7324, MFE 1.6081, MAE -12.4293 |
| SOL | 2021-01-07 07:00, 72h return 82.7927, MFE 88.2675, MAE -8.8263 | 2021-05-20 17:00, 72h return -53.7714, MFE 0.0290, MAE -60.4307 | 2021-11-06 07:00, 72h return 0.3554, MFE 5.7626, MAE -3.4007 |

Review interpretation:

- BNB coverage repair is complete for the current local review span and BNB remains in MI.
- BNB still needs Owner review for 2025 weakness, top-tail dependence, cost/funding sensitivity, and campaign replay gaps.
- SOL remains the operational chain sample because PG registration and readiness work are already complete.
- SOL and BNB are not mutually exclusive and neither is proven alpha.

Owner decision options:

- Keep SOL as bounded-trial chain sample and continue reviewing BNB as a strong observation candidate.
- Promote BNB only to live read-only observation after Owner reviews repaired evidence.
- Keep both blocked from runtime execution and order permission until a separate explicit Owner start decision.

## 4. CPM Special Observation Review

CPM-RO-001 status:

- `owner_special_observation`
- historical OOS 2021/2022: negative
- not proven alpha
- not runtime eligible by default
- suitable only for current-market validation and review evidence collection

Observation hypothesis:

CPM may be useful as a calmer pullback-continuation observation line in less violent regimes. It should be observed for structure quality, not treated as an alpha claim.

What to observe:

- HTF trend direction and ambiguity.
- Pullback/bounce depth.
- Reclaim or structure-loss confirmation.
- Whether no-action states correctly avoid low-quality setups.
- 4h / 24h / 72h / 7d forward review outcomes.

Invalidation / caution:

- Repeated would-enter observations in ambiguous trend.
- Pullback depth outside CPM bounds.
- Negative follow-through despite clean-looking reclaim.
- Any attempt to treat CPM as runtime eligible by default.

Useful validation:

- Clean no-action / would-enter samples with reviewable forward outcomes.
- Evidence that current-market observation differs meaningfully from the historical OOS failure class.

## 5. Live Read-only Observation v1

Implemented:

- `src/application/strategy_group_live_readonly_observation.py`
- `MI001MomentumImpulseReadOnlyEvaluator`
- `CPMRO001LiveReadOnlyEvaluator`
- `GET /api/brc/strategy-groups/live-readonly-observation/v1`
- Owner Console display of candidate-level observation readiness.

Signal contract:

- `no_action`
- `would_enter`
- `invalid`

Current candidate observation readiness:

| candidate | evaluator glue | latest preview | evidence mapping | readiness | blockers |
| --- | --- | --- | --- | --- | --- |
| MI-001-SOL-LONG | wired_read_only_v1 | would_enter preview over sample closed candles | metadata_only_observation_record_ready | evaluator_ready_requires_runner_binding | live observation runner is not started; observation sink is not bound to scheduler |
| MI-001-BNB-LONG | wired_read_only_v1 | would_enter preview over MI evaluator contract | metadata_only_observation_record_ready | evaluator_ready_requires_runner_binding | live observation runner is not started; Owner review of repaired BNB evidence remains pending |
| CPM-RO-001 | wired_read_only_v1 | CPM no_action / would_enter / invalid capable | metadata_only_observation_record_ready | evaluator_ready_requires_runner_binding | live observation runner is not started; CPM is not proven alpha and not runtime eligible by default |

Still blocked:

- Live observation runner is not started by this task.
- Scheduled observation sink binding is not active.
- No live read-only observation is claimed active.

## 6. API / Console Changes

Backend:

- Added read-only observation v1 response model and evaluator glue.
- Added `GET /api/brc/strategy-groups/live-readonly-observation/v1`.
- Updated strategy group reviewability aggregate to report MI/CPM evaluator glue as wired and runner/sink binding as remaining blocker.

Frontend:

- Owner Console now calls the observation v1 endpoint.
- `/strategy-groups` displays candidate-level observation contract, evaluator glue status, latest signal preview type, readiness status, and blockers.
- Dangerous trading actions remain absent.

## 7. Safety Check

- 是否启动 trial？no
- 是否启动 runtime execution？no
- 是否下单？no
- 是否取消订单？no
- 是否创建 execution intent？no
- 是否授予 execution permission？no
- 是否修改杠杆？no
- 是否 set_leverage？no
- 是否转账/提现？no
- 是否修改 exchange_gateway？no
- 是否把任何策略标成 proven alpha？no
- 是否自动选择策略？no

## 8. Tests / Validation

Validation commands:

- `python3 scripts/analyze_mi001_bnb_sol_evidence_reviewability.py --sqlite-db data/v3_dev.db`
- `python3 -m compileall -q src scripts`
- `python3 -m pytest -q tests/unit/test_brc_console_api_surface.py tests/unit/test_execution_permission.py tests/unit/test_strategy_group_live_readonly_observation.py`
- `cd gemimi-web-front && npm run lint && npx vitest run && npm run build`
- `git diff --check`
- `git diff --cached --check`

## 9. Remaining Work

- Bind the read-only evaluator glue into a scheduled observation sink without starting trial execution.
- Decide whether BNB repaired evidence is accepted for live read-only observation.
- If CPM stays as Owner special observation, define a small Owner review cadence for current-market validation.
- Keep Operation Layer / startup guard / execution permission boundaries separate from observation evidence.

## 10. Next Recommended Task

BNB live read-only observation sink wiring.
