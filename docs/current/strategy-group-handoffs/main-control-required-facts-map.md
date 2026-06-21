# Main-Control RequiredFacts Map

Status: CURRENT_PILOT_SUPPLEMENT
Last updated: 2026-06-19

## Purpose

This supplement maps StrategyGroup handoff facts into main-control readiness
classes. It does not fetch facts, place orders, change risk settings, or bypass
FinalGate.

## Readiness Classes

| Class | Meaning | Missing Behavior |
| --- | --- | --- |
| `market` | Price, closed candles, mark, funding, and volume context. | Block signal or downshift to observe-only. |
| `strategy` | StrategyGroup evaluator state and disable classifiers. | Emit no-signal or conflict. |
| `derivatives` | Funding, basis, crowding, and OI context. | Block FBS candidate prepare; may allow observe-only. |
| `risk` | Protection, exit, mark/fill, and leverage boundary. | Block candidate prepare. |
| `account` | Balance, same-symbol position, and open orders. | Block candidate prepare. |
| `exchange` | Symbol availability, min notional, step, tick, leverage limit. | Block candidate prepare for the affected symbol. |

## BTPC-001 L2 Shadow-Candidate Facts

`BTPC-001` is imported for L2 non-executing shadow-candidate observation.
These facts do not authorize `FinalGate`, `Operation Layer`, or real orders.
They define the minimum facts required before a BTPC shadow-candidate packet can
be prepared for review.

| RequiredFact | Class | Current Main-Control Meaning | Missing Behavior |
| --- | --- | --- | --- |
| `bear_trend_context` | `strategy` | Confirms the short-side regime context. | Keep observe-only and block L2 shadow candidate. |
| `weak_rally_or_pullback_depth` | `strategy` | Confirms a rally failure instead of chasing a fresh breakdown. | Keep observe-only and block L2 shadow candidate. |
| `pullback_structure_loss` | `strategy` | Requires closed-candle structure loss before a would-enter signal is reviewable. | Keep observe-only and block L2 shadow candidate. |
| `strong_uptrend_disable_state` | `strategy` | Disables BTPC when the market is in a strong upside reclaim regime. | Block L2 shadow candidate. |
| `short_squeeze_risk` | `derivatives` | Prevents short-side continuation from being promoted during unbounded squeeze risk. | Block L2 shadow candidate. |
| `funding_72h` | `derivatives` | Carries short-side funding context. | Keep observe-only until attached. |
| `perp_spot_premium` | `derivatives` | Carries futures/spot premium context. | Keep observe-only until attached. |
| `historical_open_interest_window` | `derivatives` | Needed for historical promotion claims. | Block promotion beyond L2 review. |
| `historical_global_long_short_ratio_window` | `derivatives` | Needed for account-side crowding review. | Block promotion beyond L2 review. |
| `top_trader_position_ratio_window` | `derivatives` | Needed for high-margin positioning review. | Block promotion beyond L2 review. |
| `real_exchange_margin_liquidation_model` | `risk` | Converts research leverage scores into exchange-margin terms. | Block any real-order eligibility. |
