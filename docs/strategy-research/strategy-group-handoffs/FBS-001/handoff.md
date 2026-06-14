# FBS-001 Strategy Group Handoff Pack

Status: HANDOFF_READY_FOR_MAIN_CONTROL_REVIEW
Last updated: 2026-06-14
Version: 2026-06-14-r0

## Strategy

| Field | Value |
| --- | --- |
| strategy_group_id | `FBS-001` |
| Name | Funding Basis Stress |
| Runtime role | Experimental StrategyGroup candidate and derivatives stress overlay |
| Execution status | Research-only handoff; no runtime registration or exchange action |

`FBS-001` observes funding, basis/premium, open-interest, mark/last, and
crowding states. Its strongest current branch is a TEQ negative-funding squeeze
long candidate. Its broader role is to downshift or disable levered candidates
when derivatives stress facts are unsafe.

## Supported Scope

| Field | Value |
| --- | --- |
| supported_sides | `long`, `short_as_disable_or_redesign_only` |
| primary_symbols | `INTCUSDT`, `COINUSDT`, `HOODUSDT`, `CRCLUSDT`, `MSTRUSDT`, `SNDKUSDT`, `MUUSDT`, `XAGUSDT`, `XAUUSDT` |
| default_observation_mode | `armed_observation` |
| execution_readiness | Not execution-ready; main-control owns admission, watcher, FinalGate, and execution boundary |

## Signal Ready Rule

Fresh signal means a closed-candle funding-stress state is present, funding is
deep enough to be a signal rather than noise, mark/last deviation is bounded,
quote-volume participation is present, and the packet declares whether it is a
direct TEQ long squeeze candidate or a downshift/disable overlay.

## RequiredFacts

| Fact | Purpose |
| --- | --- |
| `funding_rate_window` | Primary stress source. |
| `basis_or_premium_window` | Perp dislocation check. |
| `open_interest_value_change` | Separates crowding from normal trend. |
| `global_long_short_ratio` | Broad account-side crowding proxy. |
| `top_trader_position_ratio` | Higher-margin account positioning proxy. |
| `mark_deviation_state` | Blocks mark/last dislocation. |
| `negative_funding_crowding_state` | Required for current TEQ long squeeze lead. |
| `funding_settlement_timing_state` | Required before carry and timing assumptions are trusted. |
| `real_exchange_margin_liquidation_model` | Required before leverage promotion. |
| `funding_squeeze_concentration_state` | Blocks symbol/month concentration surprises. |

## Risk Defaults

| Field | Value |
| --- | --- |
| interpretation | Research proposal only, not live order-sizing default |
| risk_tier | `tiny` |
| max_notional_per_action_usdt | `8` research proposal |
| default_leverage | `1` |
| max_research_leverage | `2` |
| disabled_leverage | `5` until real margin model exists |
| requires_sl | `true` |
| requires_tp_or_exit_plan | `true` |

## Hard Stops

| Hard Stop | Reason |
| --- | --- |
| `missing_funding_rate_window` | No primary signal source. |
| `missing_mark_price_window` | Futures replay cannot be interpreted. |
| `missing_historical_oi_or_longs_short` | Promotion review blocked. |
| `mark_deviation_spike` | Mark/last stress can invalidate signal interpretation. |
| `positive_funding_short_failure_state` | Current positive-funding short rows are negative/redesign evidence. |
| `low_history_funding_sample_state` | Direct lead is 2026 low-history discovery evidence. |
| `missing_real_margin_model_for_leverage` | Leverage promotion blocked. |

## Evidence Summary

| Evidence | Result |
| --- | --- |
| Direct lead | `fbs_teq_extreme_negative_funding_long_72h` full 2x `1703.596239%`, best-90d 2x `1813.121179%`, DD 2x `-53.515312%`, `0` 2x/5x proxy liquidation events. |
| Robustness | Six stricter signal-time filters preserve P1 support, but 2026-06 is negative and concentration remains a blocker. |
| Negative evidence | Positive-funding short reversal rows are mostly negative or redesign evidence. |

## Sample Packets

Canonical sample packets are in `handoff.json`.

## Main-Control Handoff

`FBS-001` is ready for main-control review as an experimental direct TEQ
negative-funding long candidate and derivatives stress overlay. It should enter
observation only; main-control owns all runtime, watcher, FinalGate, and
execution boundaries.
