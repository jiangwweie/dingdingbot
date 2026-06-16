# SCF-001 Strategy Group Handoff Pack

Status: OBSERVE_ONLY_HANDOFF_DRAFT_FOR_MAIN_CONTROL_REVIEW
Last updated: 2026-06-16

## Strategy

| Field | Value |
| --- | --- |
| Strategy Group | `SCF-001` |
| Name | Session Confluence Classifier |
| Family | Session confluence / structure-confirmed momentum |
| Default Mode | `observe_only` |
| Execution Status | Research-only draft; no runtime registration or order authority. |

`SCF-001` is a confluence observer, not a standalone session strategy. It starts
from the existing session-transfer raw pool and only counts same-symbol,
same-direction SOR/VWAP/session-gap/FVG structure that was already visible at
or before the base signal. The current useful semantic is TEQ-specific:
`teq_regular_strong_any_structure` with a `12h` time-stop.

## Supported Scope

| Field | Value |
| --- | --- |
| Timeframe | `1h` |
| Primary Side | `long` |
| Support Side | `short_support_only` for PMR / XAG confluence context. |
| Lead Mode | `teq_regular_strong_any_structure_12h` |
| Research Symbols | `INTCUSDT`, `SNDKUSDT`, `MUUSDT`, `CRCLUSDT`, `MRVLUSDT`, `MSTRUSDT`, `HOODUSDT`, `COINUSDT`, `NVDAUSDT`, `TSLAUSDT`, `XAGUSDT`, `XAUUSDT`, `XPTUSDT`, `XPDUSDT` |
| Unsupported Scope | Standalone SCF execution, PMR right-tail promotion, non-prefix-safe confluence, and high-leverage promotion. |

## Signal Ready Rule

The observe-only signal is fresh only when a closed 1h base session-transfer
signal and at least one same-symbol, same-direction confluence structure are
known at signal time. Confluence must be no more than `24h` older than the base
signal, and no confluence fact can be added after the base signal timestamp.

The current research recommendation is observe-only. A fresh SCF packet may
support Strategy Picker context and watcher exploration, but the research
window does not allow candidate preparation or execution authority.

## RequiredFacts

| RequiredFact | Why |
| --- | --- |
| `base_session_transfer_state` | Required because SCF is built on session-transfer raw-pool signals. |
| `session_confluence_state` | Required for any confluence score. |
| `session_vwap_or_opening_range_state` | Required for TEQ structure confirmation. |
| `session_imbalance_gap_state` | Required for FVG / session-gap confirmation. |
| `pmr_session_breakdown_structure_state` | Required before using PMR short context. |
| `session_multi_structure_state` | Required when multiple structure sources are claimed. |
| `structure_confluence_count_state` | Required because at least one prior structure is needed. |
| `confluence_prefix_state` | Required to prove no post-entry or post-signal structure was used. |
| `teq_strong_momentum_state` | Required for the current TEQ lead. |
| `session_confluence_drawdown_state` | Required because the 72h row is high-drawdown. |
| `scf_exit_horizon_state` | Required because the current lead moved to the `12h` time-stop. |
| `scf_time_stop_tradeoff_state` | Required before comparing 12h cleaner behavior with 72h right-tail behavior. |
| `scf_fill_gap_slippage_state` | Required before runtime or armed-observation discussion. |
| `real_exchange_margin_liquidation_model` | Required before leverage promotion. |

## Risk Defaults

| Field | Value |
| --- | --- |
| Interpretation | Research proposal only, not live order-sizing defaults. |
| Risk Tier | `tiny` |
| Default Leverage | `1x` |
| Max Research Leverage | `2x` |
| Stress Only | `3x` |
| Disabled | `5x` |
| Exit Horizon | `12h` observe-only review lane. |
| Protection | Requires stop-loss and explicit exit plan before any future armed review. |

## Hard Stops

| Hard Stop | Reason |
| --- | --- |
| `base_session_transfer_missing` | SCF cannot exist without the base session-transfer state. |
| `session_confluence_missing` | No structure confirmation exists. |
| `confluence_not_prefix_safe` | Post-signal structure would be lookahead. |
| `confluence_older_than_24h` | Confluence exceeds the allowed lookback. |
| `structure_confluence_count_zero` | No SOR/VWAP/session-gap/FVG confirmation exists. |
| `teq_strong_momentum_missing` | Current lead depends on strong TEQ momentum. |
| `pmr_support_promoted_as_right_tail` | PMR confluence is support-only in current evidence. |
| `scf_exit_horizon_missing` | Current lead depends on the 12h time-stop. |
| `fill_gap_slippage_missing` | Next-open and session fill risk remain unresolved. |
| `product_session_policy_missing` | Binance 2026 equity-like and metal products need session/product handling. |
| `real_margin_model_missing` | Leverage promotion is blocked. |
| `high_leverage_requested` | 3x is stress-only and 5x is disabled. |
| `same_symbol_active_position_or_open_order` | Prevents duplicate same-symbol exposure. |
| `stale_market_facts` | Blocks signal interpretation. |
| `missing_exchange_rules` | Blocks runtime consumption. |
| `no_stop_loss_plan` | Blocks any future candidate preparation. |

## Evidence Summary

| Evidence | Result |
| --- | --- |
| Original lead | `teq_regular_strong_any_structure` 72h classifier full 2x `259.729043%`; best 90d 2x `774.340784%`; DD 2x `-69.451868%`. |
| Current lead | `teq_regular_strong_any_structure` at `12h`. |
| Current lead performance | Events `71`; full 2x `318.065867%`; full 3x `649.103170%`; full 5x `1835.326912%`; best 90d 2x `216.167925%`; DD 2x `-22.978941%`; 2x/5x proxy liquidation `0/0`. |
| 72h contrast | Full 2x `280.727766%`; best 90d 2x `853.468427%`; DD 2x `-68.722679%`; 5x proxy liquidation `1`. |
| PMR support | `pmr_regular_xag_confluence` at `12h` full 2x `36.181618%`; best 90d 2x `24.605620%`; support-only. |
| Negative scope | PMR confluence does not clear the right-tail gate; broad confluence rows remain drawdown or full-curve blocked. |

## Sample Packets

Canonical sample packets are in `handoff.json`.

## Main-Control Handoff

Recommendation: consume `SCF-001` as an observe-only handoff draft. It is useful
for Strategy Picker vocabulary, signal watcher exploration, and TEQ structure
confirmation review. It should not be treated as armed observation until
fill/gap/session/product and real exchange-margin facts are available.
