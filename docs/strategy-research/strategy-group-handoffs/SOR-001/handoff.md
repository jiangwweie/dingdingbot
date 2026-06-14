# SOR-001 Strategy Group Handoff Pack

Status: HANDOFF_READY_FOR_MAIN_CONTROL_REVIEW
Last updated: 2026-06-14
Version: 2026-06-14-r0

## Strategy

| Field | Value |
| --- | --- |
| strategy_group_id | `SOR-001` |
| Name | Session Opening-Range Breakout |
| Runtime role | Experimental session-structure StrategyGroup candidate |
| Execution status | Research-only handoff; no runtime registration or exchange action |

`SOR-001` adapts opening-range breakout semantics to Binance 2026 TradFi equity
and metal perpetuals. Current useful branches are PMR regular-session short and
a narrow TEQ decisive-breakdown 72h short lane. TEQ long remains revival-only.

## Supported Scope

| Field | Value |
| --- | --- |
| supported_sides | `short`, `long_revival_only` |
| primary_symbols | `XAGUSDT`, `XAUUSDT`, `XPTUSDT`, `XPDUSDT`, `INTCUSDT`, `SNDKUSDT`, `MUUSDT`, `CRCLUSDT`, `MSTRUSDT` |
| default_observation_mode | `armed_observation` |
| execution_readiness | Not execution-ready; main-control owns runtime admission and execution boundary |

## Signal Ready Rule

Fresh signal means the opening range is built from closed 13:00/14:00 UTC 1h
bars, the trigger is a closed 15:00 UTC bar, entry would be next-open 16:00 UTC
only after main-control review, and the selected branch has explicit horizon
and session facts.

## RequiredFacts

| Fact | Purpose |
| --- | --- |
| `session_open_range_state` | Required for ORB construction. |
| `session_breakout_trigger_state` | Required for trigger interpretation. |
| `tradfi_session_mapping_state` | Required for 24/7 Binance to U.S./metal session mapping. |
| `post_open_decay_disable_state` | Required because long and short branches decay differently. |
| `time_stop_exit_horizon_state` | Required because the TEQ short lead is 72h-specific. |
| `exit_horizon_reslot_state` | Required for capacity and turnover interpretation. |
| `mark_funding_session_review_state` | Required for futures interpretation. |
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
| `missing_closed_open_range` | ORB cannot be formed. |
| `missing_closed_trigger` | Trigger cannot be evaluated. |
| `session_mapping_missing` | Binance 24/7 bars cannot be interpreted. |
| `missing_exit_horizon` | SOR evidence is horizon-specific. |
| `post_open_decay_detected` | Known failure mode. |
| `high_leverage_requested` | 3x/5x are stress-only. |

## Evidence Summary

| Evidence | Result |
| --- | --- |
| PMR short base | `sor_pmr_us_open_short_72h` full 2x `33.825028%`, best-90d 2x `126.853890%`, `0` 2x/5x liquidation proxy. |
| PMR classifier | `sorcls_pmr_short_prior_weakness` full 2x `77.200972%`, best-90d 2x `117.597324%`, but second-half 2x is negative. |
| TEQ short reslot | `sorcls_teq_short_decisive_breakdown` 72h best-90d 2x `119.963254%`, `0` 2x liquidation proxy, but only full 2x `1.999826%`. |
| Main blocker | Session mapping, post-open decay, fill/gap, mark/funding, margin, and high-leverage risk. |

## Sample Packets

Canonical sample packets are in `handoff.json`.

## Main-Control Handoff

`SOR-001` is ready for main-control review as an experimental session-structure
candidate. It should be observed branch-by-branch rather than as a broad
opening-range strategy.
