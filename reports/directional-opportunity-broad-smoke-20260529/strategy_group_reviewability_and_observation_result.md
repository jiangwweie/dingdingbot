# Strategy Group Reviewability and Observation Result

## 1. Summary

This task moved the `/strategy-groups` shelf from a frontend-only display model to a read-only Owner-reviewable backend aggregate plus console view.

The implementation does not start trial, does not start runtime, does not create execution intents, does not place orders, and does not grant execution or order permission. The new surface is reviewability/readiness only.

## 2. Path Chosen

Path B/C hybrid:

- Backend aggregate API was missing, so a new read-only endpoint was added: `GET /api/brc/strategy-groups/reviewability`.
- The existing `/strategy-groups` UI now consumes the API and keeps a clearly labeled `display_model_only / api_unavailable` fallback.
- No PG schema migration was needed.
- No execution, order, live runner, `exchange_gateway`, or `src/main.py` files were touched.

## 3. Strategy Group Status

| strategy_group_id | group | status | evidence_reviewability | live_readonly_observation_readiness | bounded_trial_readiness | main_blockers |
| --- | --- | --- | --- | --- | --- | --- |
| MI-001 | Momentum Impulse | primary_chain_candidate / strong_smoke_candidate | reviewable_with_known_risks | live_readonly_candidate_requires_signal_glue | SOL chain sample has bounded-trial metadata; BNB remains coverage-repair candidate | MI signal evaluator glue missing; SOL dedup/MAE review; BNB 2023-2025 coverage gap |
| VI-001 | Volume Impulse | backup_observation_candidate | reviewable_but_cost_sensitive | live_readonly_candidate_requires_signal_glue | not_first_trial_line | VI signal evaluator glue missing; cost-sensitive edge |
| CPM-RO-001 | Owner Special Observation | owner_special_observation | reviewable_with_negative_oos_disclosure | live_readonly_candidate_requires_signal_glue | not_runtime_eligible_by_default | historical OOS 2021/2022 negative; CPM signal glue missing |
| TB | Trend Breakout | research_pool / keep_for_later | coarse_review_only | live_readonly_candidate_requires_signal_glue | not_current_trial_candidate | frozen evaluator missing; not admitted |
| PC | Pullback Continuation | research_pool | coarse_review_only | research_pool_requires_frozen_evaluator | not_current_trial_candidate | independent hypothesis missing |
| VB | Volatility Breakout | research_pool | coarse_review_only | research_pool_requires_evidence | not_current_trial_candidate | quality filter and Tier 1 context missing |
| MR/RB | Mean Reversion / Range Boundary | weak_or_secondary / needs better variant | secondary_review_only | not_observation_ready | not_current_trial_candidate | variant hypothesis missing |
| Tier 1 Data Families | Funding/OI/taker flow/etc. | data_request_ready / not_downloaded / not_admitted | request_ready_not_observed | not_observation_ready | not_strategy_family_admitted | data not downloaded; semantics not validated |

## 4. Candidate Evidence Reviewability

| candidate | status | key evidence | confidence flags |
| --- | --- | --- | --- |
| MI-001-SOL-LONG | current_chain_sample_with_known_risks | 8,135 signals; 72h mean 1.9531; 72h positive rate 0.5175; 7d mean 4.7372; 72h net baseline 1.5831 | chain sample, not the only primary strategy; high MAE; signal density/dedup blocker |
| MI-001-BNB-LONG | strong_smoke_candidate_with_coverage_gap | 2,683 signals; 72h mean 3.5342; 72h positive rate 0.5617; 7d mean 7.9309; 72h net baseline 3.1642 | severe 2023-2025 coverage gap is a confidence flag, not elimination |
| VI-001-ETH-LONG | backup_observation_candidate | 1,277 signals; 72h mean 1.1164; 72h positive rate 0.5348; 7d mean 2.2386; 72h net baseline 0.7464 | positive but thin and cost-sensitive, not auto-parked |
| CPM-RO-001 | owner_special_observation_not_proven_alpha | historical OOS 2021/2022 negative | Owner special observation; not proven alpha; not runtime eligible by default |

## 5. Live Read-only Observation Readiness

The existing `brc_live_read_only_detection_runner.py` can record metadata and evidence without creating orders, but strategy-specific live observation is not active. The missing glue remains:

- frozen signal evaluator per strategy group/candidate
- strategy-specific signal-to-observation sink
- admission/campaign binding for observation events
- evidence writing path for observation iterations

MI/VI/CPM/TB are therefore marked `live_readonly_candidate_requires_signal_glue`; PC/VB/MR/RB/Tier 1 remain research or data-readiness surfaces.

## 6. Implementation Summary

Changed:

- `src/application/strategy_group_reviewability.py`
  - Added pure read-only Pydantic reviewability aggregate.
  - Encoded the six primary strategy groups and two secondary groups.
  - Encoded SOL/BNB/ETH/CPM candidate evidence reviewability.
  - Explicitly included non-permissions and observation blockers.
- `src/interfaces/api_brc_console.py`
  - Added `GET /api/brc/strategy-groups/reviewability`.
- `tests/unit/test_brc_console_api_surface.py`
  - Added API test for primary/secondary group count, SOL+BNB coexistence, BNB coverage flag, CPM special observation, and non-permissions.
- `gemimi-web-front/src/services/api.ts`
  - Added types and client method for the new endpoint.
- `gemimi-web-front/src/pages/brc/OwnerConsoleV2.tsx`
  - `/strategy-groups` now consumes backend reviewability data.
  - Added primary/secondary shelf sections, detail readiness fields, candidate evidence comparison, live read-only observation readiness, and fallback labeling.
- `gemimi-web-front/src/pages/brc/OwnerConsoleV2.test.tsx`
  - Added mock reviewability payload and assertions for the new Owner Console display.

No runtime source of truth was moved into Markdown. The report is an audit/review artifact only.

## 7. Safety Check

- push: no
- trial started: no
- runtime started: no
- execution intent created: no
- order created: no
- execution permission granted: no
- order permission granted: no
- exchange write method called: no
- leverage changed: no
- transfer/withdrawal: no
- strategy runner touched: no
- execution/order/live runner files touched: no
- `exchange_gateway` touched: no
- PG migration run: no

## 8. Tests / Validation

Passed:

- `python3 -m compileall -q src scripts`
- `python3 -m pytest -q tests/unit/test_brc_console_api_surface.py tests/unit/test_execution_permission.py`
  - 34 passed, 1 existing SQLAlchemy resource warning.
- `cd gemimi-web-front && npm run lint`
- `cd gemimi-web-front && npx vitest run`
  - 7 files passed, 12 tests passed.
- `cd gemimi-web-front && npm run build`
- `git diff --check`
- `git diff --cached --check`

## 9. Remaining Work

- BNB 2023-2025 data coverage repair remains the main confidence repair task.
- Strategy-specific live read-only observation glue is not wired.
- Tier 1 data families remain request-ready only; no download or admission occurred.

## 10. Next Recommended Task

BNB data coverage repair plan
