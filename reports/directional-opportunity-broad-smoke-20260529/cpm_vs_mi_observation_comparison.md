# CPM vs MI Observation Comparison

Generated: 2026-05-31 16:43 CST

## 1. Summary

This comparison is for Owner review of live read-only observation styles. It does not start a trial, create execution intents, place orders, grant execution permission, or make CPM runtime eligible.

## 2. Style Comparison

| 项 | MI Momentum Impulse | CPM Owner Special Observation |
|---|---|---|
| strategy style | momentum impulse / right-tail continuation | pullback-continuation / calmer-market validation |
| 行情类型 | 强动量 / 右尾 | 温和趋势回调 |
| market it eats | strong trend, high-beta follow-through, willing chase environment | low-slope, lower-volatility trend continuation after controlled pullback |
| market it hates | momentum exhaustion, sharp reversal after crowded impulse, fake breakout | trend failure, ambiguous 4h trend, continuation failure, aggressive volatility |
| 风险路径 | MAE 大 / 追高衰竭 | 趋势失效 / 慢性回撤 |
| Owner experience | 激进；can produce fast large MFE and fast adverse moves | 温和 when valid, but can be frustrating if continuation fails slowly |
| 当前状态 | BNB/SOL live observation; BNB case #001 under forward review | Owner special observation; current live snapshot is `no_action` |
| evidence warning | high MAE, top-tail dependence, 2025 weakness for BNB, signal density/dedup | 2021/2022 OOS negative, not proven alpha, not runtime eligible by default |
| trial 方向 | BNB/SOL 后续讨论; SOL has readiness chain, BNB design-only draft | 先观察和复盘; bounded review only after live evidence |
| not allowed now | no automatic BNB promotion, no order, no trial start | no alpha claim, no runtime eligibility by default, no order |

## 3. Current Evidence Snapshot

| candidate | current evidence state | live observation state | main risk |
| --- | --- | --- | --- |
| `MI-001-SOL-LONG` | chain sample with PG readiness work and high-MAE disclosure | latest live observation command produced `no_action` at `2026-05-31T07:00:00Z` | high MAE / density / dedup |
| `MI-001-BNB-LONG` | repaired coverage, strong 72h/7d historical means, BNB live case #001 under review | latest live observation command produced `no_action`; earlier case #001 remains 1h/4h adverse | local exhaustion / top-tail / 2025 weakness |
| `CPM-RO-001` | Owner special observation despite negative 2021/2022 OOS | latest live observation command produced `no_action`; PG row recorded | ambiguous trend / OOS failure recurrence |

## 4. Current CPM Snapshot vs MI Case Context

CPM current snapshot:

- `signal_type = no_action`
- reason: `cpm_no_action_trend_ambiguous`
- `htf_trend = neutral`
- `primary_trend = down`
- `entry_pattern = bounce_loss`
- PG row: `CPM-RO-001:cpm-fb9e296ef9beebce7ba18cea:1780210800000`

MI BNB live case #001:

- initial signal: `would_enter`
- 1h forward return: `-0.7593%`
- 4h forward return: `-2.7020%`
- interpretation: adverse continuation; no-chase and wait-for-confirmation remain appropriate.

Owner-readable contrast:

- MI currently gives faster, more aggressive observation cases, including adverse early paths that must be reviewed quickly.
- CPM currently refuses action under ambiguous trend, which is exactly the behavior to observe if Owner wants a calmer validation line.
- CPM no-action is evidence too: it shows the evaluator is not forcing a setup while trend alignment is unclear.

## 5. Observation Review Rules

| review dimension | MI | CPM |
| --- | --- | --- |
| signal frequency | watch clustering and dedup | watch selectivity and no_action ratio |
| would_enter review | forward path 1h/4h/12h/24h/72h | forward path 24h/72h/7d when would_enter appears |
| key path metrics | MFE / MAE / local exhaustion / top-tail | MFE / MAE / continuation failure / slow adverse path |
| invalidation focus | crowded impulse reversal and high MAE | ambiguous trend entries and weak continuation |
| Owner verdicts | continue observation, revise trigger, design-only bounded review | continue_observation, revise, park, owner_special_bounded_review_candidate |

## 6. Key Blockers

| family | blocker |
| --- | --- |
| MI | observation is not execution readiness; BNB case #001 has adverse 1h/4h path; BNB-specific trial metadata not complete |
| CPM | negative OOS warning; no `would_enter` live case yet; not proven alpha; not runtime eligible by default |

## 7. Non-permissions

- no trial start
- no execution intent
- no order
- no order permission
- no execution permission
- no runtime start
- no automatic strategy routing
- no automatic promotion from observation to bounded trial
