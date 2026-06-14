# TEQ-001 Strategy Group Handoff Pack

Status: HANDOFF_READY_FOR_MAIN_CONTROL_REVIEW
Last updated: 2026-06-14
Version: 2026-06-14-r0

## Strategy

| Field | Value |
| --- | --- |
| strategy_group_id | `TEQ-001` |
| Name | Tokenized Equity Momentum |
| Runtime role | Experimental StrategyGroup candidate for Binance 2026 equity-like perps |
| Execution status | Research-only handoff; no runtime registration or exchange action |

`TEQ-001` observes Binance-listed U.S. equity-like perpetual momentum. The
current lead is long-side, single-name cluster momentum, not a broad equity
basket. Short-side TEQ is disabled except for narrow SOR-linked research.

## Supported Scope

| Field | Value |
| --- | --- |
| supported_sides | `long` |
| primary_symbols | `INTCUSDT`, `SNDKUSDT`, `MUUSDT`, `CRCLUSDT`, `MRVLUSDT`, `MSTRUSDT`, `HOODUSDT`, `COINUSDT`, `NVDAUSDT`, `TSLAUSDT` |
| default_observation_mode | `armed_observation` |
| execution_readiness | Not execution-ready; main-control owns runtime admission and execution boundary |

## Signal Ready Rule

Fresh signal means a closed-candle equity-like momentum state exists, the
symbol is inside the current TEQ observation set, mark/funding/liquidity facts
are available, the signal is not a low-history bStocks-only event, and no
session-gap or concentration hard stop is active.

## RequiredFacts

| Fact | Purpose |
| --- | --- |
| `theme_momentum_state` | Primary long-side momentum state. |
| `relative_volume_or_quote_volume_floor` | Liquidity participation filter. |
| `product_eligibility_state` | Required for Binance equity-like products. |
| `basket_breadth_state` | Prevents broad-basket claims from single-name evidence. |
| `symbol_concentration_state` | Required because top windows are concentrated. |
| `session_gap_context` | Required for 24/7 Binance versus U.S. equity session mapping. |
| `mark_funding_review_state` | Required for perpetual interpretation. |
| `exchange_margin_liquidation_state` | Required before leverage promotion. |

## Risk Defaults

| Field | Value |
| --- | --- |
| interpretation | Research proposal only, not live order-sizing default |
| risk_tier | `tiny` |
| max_notional_per_action_usdt | `8` research proposal |
| default_leverage | `1` |
| max_research_leverage | `2` |
| disabled_leverage | `3x/5x` for promotion; stress-only |
| requires_sl | `true` |
| requires_tp_or_exit_plan | `true` |

## Hard Stops

| Hard Stop | Reason |
| --- | --- |
| `low_history_symbol` | bStocks and recent symbols cannot support promotion. |
| `single_symbol_concentration_unbounded` | Top-window concentration is a known risk. |
| `missing_mark_funding_review` | Futures interpretation incomplete. |
| `weekend_or_offhour_policy_missing` | Session transfer is not neutral. |
| `teq_short_requested` | Short-side TEQ is not generally supported. |
| `high_leverage_requested` | 3x/5x are stress-only. |

## Evidence Summary

| Evidence | Result |
| --- | --- |
| Universe | `87` TradFi equity/ETF perps and `6` bStocks spot rows in current expanded scope. |
| Clean 2x lead | `INTCUSDT` best allowed 2x envelope row at `309.267800%`. |
| Session-transfer lead | `teq_regular_stronger_momentum` full 2x `120.920956%`, best-90d 2x `719.609726%`, but DD 2x `-79.986654%`. |
| Main blocker | Concentration, session-gap, mark/funding, low-history, fill/gap, and real margin facts. |

## Sample Packets

Canonical sample packets are in `handoff.json`.

## Main-Control Handoff

`TEQ-001` is ready for main-control review as an experimental long-side
strategy-group candidate for observation. It is not a broad always-on equity
basket strategy and should not promote without concentration and session facts.
