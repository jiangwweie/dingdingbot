## Four-Candidate Recent Counterfactual Live-Submit Replay

- Status: `recent_counterfactual_replay_ready`
- Scope: `strategygroup_recent_counterfactual_live_submit_replay_non_authority`
- Review signals: `543`
- Missed-opportunity review count: `79`
- Counterfactual live-submit allowed: `0`
- Output JSON: `output/runtime-monitor/latest-four-candidate-recent-live-submit-replay.json`

## Current Tradeability

| Strategy | Stage | Decision | First blocker | Owner |
| --- | --- | --- | --- | --- |
| `MPG-001` | `armed_observation` | `not_tradable_market_wait` | `fresh_executable_signal_absent` | `market` |
| `BRF2-001` | `armed_observation` | `not_tradable_market_wait` | `short_squeeze_risk_state_disable_active` | `market` |
| `SOR-001` | `armed_observation` | `not_tradable_market_wait` | `fresh_session_range_signal_absent` | `market` |
| `CPM-RO-001` | `armed_observation` | `not_tradable_market_wait` | `fresh_cpm_long_signal_absent` | `market` |

## Replay Summary

| Strategy | 3d signals/review | 7d signals/review | 14d signals/review | Next action |
| --- | ---: | ---: | ---: | --- |
| `MPG-001` | `30/30` | `57/57` | `93/93` | `review_symbol_scope_and_fact_classifier_for_recent_counterfactual_signals` |
| `BRF2-001` | `8/0` | `76/0` | `192/0` | `keep_brf2_armed_but_respect_short_squeeze_disable` |
| `SOR-001` | `3/3` | `6/6` | `14/14` | `review_symbol_scope_and_fact_classifier_for_recent_counterfactual_signals` |
| `CPM-RO-001` | `10/10` | `18/18` | `36/36` | `review_symbol_scope_and_fact_classifier_for_recent_counterfactual_signals` |

## Per-Symbol Replay

| Strategy | Symbol | Primary scope | 3d signals/review | 7d signals/review | 14d signals/review |
| --- | --- | ---: | ---: | ---: | ---: |
| `MPG-001` | `BTCUSDT` | `true` | `0/0` | `0/0` | `1/1` |
| `MPG-001` | `ETHUSDT` | `true` | `6/6` | `6/6` | `11/11` |
| `MPG-001` | `SOLUSDT` | `false` | `11/11` | `18/18` | `34/34` |
| `MPG-001` | `AVAXUSDT` | `false` | `6/6` | `12/12` | `19/19` |
| `MPG-001` | `SUIUSDT` | `false` | `7/7` | `12/12` | `18/18` |
| `MPG-001` | `OPUSDT` | `false` | `0/0` | `9/9` | `10/10` |
| `BRF2-001` | `BTCUSDT` | `true` | `2/0` | `22/0` | `44/0` |
| `BRF2-001` | `ETHUSDT` | `true` | `0/0` | `25/0` | `51/0` |
| `BRF2-001` | `SOLUSDT` | `false` | `0/0` | `17/0` | `49/0` |
| `BRF2-001` | `AVAXUSDT` | `false` | `6/0` | `12/0` | `48/0` |
| `SOR-001` | `BTCUSDT` | `true` | `0/0` | `0/0` | `2/2` |
| `SOR-001` | `ETHUSDT` | `true` | `1/1` | `2/2` | `4/4` |
| `SOR-001` | `SOLUSDT` | `false` | `1/1` | `2/2` | `5/5` |
| `SOR-001` | `AVAXUSDT` | `false` | `1/1` | `2/2` | `3/3` |
| `CPM-RO-001` | `ETHUSDT` | `true` | `3/3` | `3/3` | `9/9` |
| `CPM-RO-001` | `SOLUSDT` | `false` | `3/3` | `5/5` | `10/10` |
| `CPM-RO-001` | `AVAXUSDT` | `false` | `2/2` | `6/6` | `12/12` |
| `CPM-RO-001` | `SUIUSDT` | `false` | `2/2` | `4/4` | `5/5` |

## Fifth Candidate Review

- Candidate: `MI-001`
- Recommendation: `open_formal_candidate_replay_review`
- Recent impulse events: `20`

## Safety

- Replay/public market data is not a live signal.
- No FinalGate, Operation Layer, exchange write, order creation, live profile change, or order-sizing change.
