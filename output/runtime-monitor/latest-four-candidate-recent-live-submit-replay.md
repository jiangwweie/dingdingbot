## Four-Candidate Recent Counterfactual Live-Submit Replay

- Status: `recent_counterfactual_replay_ready`
- Scope: `strategygroup_recent_counterfactual_live_submit_replay_non_authority`
- Unique review signals: `335`
- Unique missed-opportunity review count: `245`
- Window-cumulative signals: `543`
- Window-cumulative missed opportunities: `418`
- Would reach action-time boundary: `129`
- Counterfactual live-submit allowed: `0`
- Venue basis: `coinbase_spot_proxy`
- Execution venue match: `false`
- Absorbability grade: `review_only_proxy`
- Output JSON: `output/runtime-monitor/latest-four-candidate-recent-live-submit-replay.json`

## Data Source Boundary

| Field | Value |
| --- | --- |
| Provider | `coinbase_exchange_public_candles_fallback` |
| Venue basis | `coinbase_spot_proxy` |
| Execution venue basis | `binance_usdm_usdt_perps` |
| Execution venue match | `false` |
| Absorbability grade | `review_only_proxy` |
| Primary source error | `HTTPError:HTTP Error 451: ` |

## Current Tradeability

| Strategy | Stage | Decision | First blocker | Owner |
| --- | --- | --- | --- | --- |
| `MPG-001` | `armed_observation` | `not_tradable_market_wait` | `fresh_executable_signal_absent` | `market` |
| `BRF2-001` | `armed_observation` | `not_tradable_market_wait` | `short_squeeze_risk_state_disable_active` | `market` |
| `SOR-001` | `armed_observation` | `not_tradable_market_wait` | `fresh_session_range_signal_absent` | `market` |
| `CPM-RO-001` | `armed_observation` | `not_tradable_market_wait` | `fresh_cpm_long_signal_absent` | `market` |

## Replay Summary

| Strategy | 3d signals/review/boundary | 7d signals/review/boundary | 14d signals/review/boundary | Next action |
| --- | ---: | ---: | ---: | --- |
| `MPG-001` | `30/30/6` | `57/57/6` | `93/93/12` | `review_symbol_scope_and_fact_classifier_for_recent_counterfactual_signals` |
| `BRF2-001` | `8/2/2` | `76/47/47` | `192/102/102` | `keep_brf2_armed_but_respect_short_squeeze_disable` |
| `SOR-001` | `3/3/1` | `6/6/2` | `14/14/6` | `review_symbol_scope_and_fact_classifier_for_recent_counterfactual_signals` |
| `CPM-RO-001` | `10/10/3` | `18/18/3` | `36/36/9` | `review_symbol_scope_and_fact_classifier_for_recent_counterfactual_signals` |

## Per-Symbol Replay

| Strategy | Symbol | Primary scope | 3d signals/review/boundary | 7d signals/review/boundary | 14d signals/review/boundary |
| --- | --- | ---: | ---: | ---: | ---: |
| `MPG-001` | `BTCUSDT` | `true` | `0/0/0` | `0/0/0` | `1/1/1` |
| `MPG-001` | `ETHUSDT` | `true` | `6/6/6` | `6/6/6` | `11/11/11` |
| `MPG-001` | `SOLUSDT` | `false` | `11/11/0` | `18/18/0` | `34/34/0` |
| `MPG-001` | `AVAXUSDT` | `false` | `6/6/0` | `12/12/0` | `19/19/0` |
| `MPG-001` | `SUIUSDT` | `false` | `7/7/0` | `12/12/0` | `18/18/0` |
| `MPG-001` | `OPUSDT` | `false` | `0/0/0` | `9/9/0` | `10/10/0` |
| `BRF2-001` | `BTCUSDT` | `true` | `2/0/0` | `22/9/9` | `44/13/13` |
| `BRF2-001` | `ETHUSDT` | `true` | `0/0/0` | `25/18/18` | `51/25/25` |
| `BRF2-001` | `SOLUSDT` | `false` | `0/0/0` | `17/13/13` | `49/29/29` |
| `BRF2-001` | `AVAXUSDT` | `false` | `6/2/2` | `12/7/7` | `48/35/35` |
| `SOR-001` | `BTCUSDT` | `true` | `0/0/0` | `0/0/0` | `2/2/2` |
| `SOR-001` | `ETHUSDT` | `true` | `1/1/1` | `2/2/2` | `4/4/4` |
| `SOR-001` | `SOLUSDT` | `false` | `1/1/0` | `2/2/0` | `5/5/0` |
| `SOR-001` | `AVAXUSDT` | `false` | `1/1/0` | `2/2/0` | `3/3/0` |
| `CPM-RO-001` | `ETHUSDT` | `true` | `3/3/3` | `3/3/3` | `9/9/9` |
| `CPM-RO-001` | `SOLUSDT` | `false` | `3/3/0` | `5/5/0` | `10/10/0` |
| `CPM-RO-001` | `AVAXUSDT` | `false` | `2/2/0` | `6/6/0` | `12/12/0` |
| `CPM-RO-001` | `SUIUSDT` | `false` | `2/2/0` | `4/4/0` | `5/5/0` |

## Top Missed Events

| Strategy | Symbol | Time | Strength | Next blocker | Review reason |
| --- | --- | --- | ---: | --- | --- |
| `MPG-001` | `AVAXUSDT` | `2026-06-27T02:00:00+00:00` | `10.8514` | `symbol_scope_review_required` | `fresh_like_signal_on_non_primary_replay_symbol` |
| `MPG-001` | `OPUSDT` | `2026-06-24T23:00:00+00:00` | `10.5263` | `symbol_scope_review_required` | `fresh_like_signal_on_non_primary_replay_symbol` |
| `MPG-001` | `SOLUSDT` | `2026-06-26T19:00:00+00:00` | `10.2556` | `symbol_scope_review_required` | `fresh_like_signal_on_non_primary_replay_symbol` |
| `MPG-001` | `SOLUSDT` | `2026-06-26T16:00:00+00:00` | `9.8816` | `symbol_scope_review_required` | `fresh_like_signal_on_non_primary_replay_symbol` |
| `CPM-RO-001` | `SOLUSDT` | `2026-06-26T16:00:00+00:00` | `9.8816` | `symbol_scope_review_required` | `fresh_like_signal_on_non_primary_replay_symbol` |
| `MPG-001` | `SOLUSDT` | `2026-06-26T18:00:00+00:00` | `9.6838` | `symbol_scope_review_required` | `fresh_like_signal_on_non_primary_replay_symbol` |
| `MPG-001` | `SOLUSDT` | `2026-06-26T20:00:00+00:00` | `8.9013` | `symbol_scope_review_required` | `fresh_like_signal_on_non_primary_replay_symbol` |
| `MPG-001` | `SOLUSDT` | `2026-06-26T15:00:00+00:00` | `8.6681` | `symbol_scope_review_required` | `fresh_like_signal_on_non_primary_replay_symbol` |
| `CPM-RO-001` | `SOLUSDT` | `2026-06-26T15:00:00+00:00` | `8.6681` | `symbol_scope_review_required` | `fresh_like_signal_on_non_primary_replay_symbol` |
| `MPG-001` | `SOLUSDT` | `2026-06-26T17:00:00+00:00` | `8.148` | `symbol_scope_review_required` | `fresh_like_signal_on_non_primary_replay_symbol` |

## Scope Change Review

| Strategy | Recommendation | Candidate symbols | Boundary |
| --- | --- | --- | --- |
| `MPG-001` | `review_primary_symbol_scope_expansion` | `SOLUSDT`, `AVAXUSDT`, `SUIUSDT`, `OPUSDT` | `review_only_no_policy_or_live_scope_change` |
| `SOR-001` | `review_primary_symbol_scope_expansion` | `SOLUSDT`, `AVAXUSDT` | `review_only_no_policy_or_live_scope_change` |
| `CPM-RO-001` | `review_primary_symbol_scope_expansion` | `SOLUSDT`, `AVAXUSDT`, `SUIUSDT` | `review_only_no_policy_or_live_scope_change` |
| `MI-001` | `open_formal_candidate_replay_review` | `AVAXUSDT`, `ETHUSDT`, `SOLUSDT`, `SUIUSDT` | `review_only_no_registry_admission_or_live_authority` |

## Fifth Candidate Review

- Candidate: `MI-001`
- Recommendation: `open_formal_candidate_replay_review`
- Recent impulse events: `20`

## Safety

- Replay/public market data is not a live signal.
- No FinalGate, Operation Layer, exchange write, order creation, live profile change, or order-sizing change.
