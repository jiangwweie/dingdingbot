# PMR-001 Strategy Group Handoff Pack

Status: HANDOFF_READY_FOR_MAIN_CONTROL_REVIEW
Last updated: 2026-06-14
Version: 2026-06-14-r0

## Strategy

| Field | Value |
| --- | --- |
| strategy_group_id | `PMR-001` |
| Name | Precious Metal Regime Overlay |
| Runtime role | Experimental overlay / short-weakness StrategyGroup candidate |
| Execution status | Research-only handoff; no runtime registration or exchange action |

`PMR-001` observes metal futures and gold-token context. Current evidence is
stronger as XAG-led short/weakness or overlay context than as standalone broad
metal long momentum.

## Supported Scope

| Field | Value |
| --- | --- |
| supported_sides | `short`, `long_as_context_only` |
| primary_symbols | `XAGUSDT`, `XAUUSDT`, `XPTUSDT`, `XPDUSDT`, `COPPERUSDT`, `XAUTUSDT`, `PAXGUSDT` |
| default_observation_mode | `observe_only` |
| execution_readiness | Not execution-ready; main-control owns admission and execution boundary |

## Signal Ready Rule

Fresh signal means a closed-candle PMR role is explicit, preferably
regular-session XAG-led short/weakness, mark/funding facts are bounded, session
facts are present, and the packet is not mixing long trend, short weakness,
hedge, and overlay roles.

## RequiredFacts

| Fact | Purpose |
| --- | --- |
| `metal_role_split_state` | Separates long, short, hedge, and overlay roles. |
| `xag_dominance_state` | Required because evidence is XAG-led. |
| `pmr_regular_breakdown_state` | Current clean PMR short candidate state. |
| `commodity_session_gap_state` | Required for commodity-perp session interpretation. |
| `mark_deviation_bound_state` | Required before futures interpretation. |
| `real_margin_model_state` | Required before leverage promotion. |
| `gold_token_context_state` | Allows XAUT/PAXG as context, not promotion evidence. |

## Risk Defaults

| Field | Value |
| --- | --- |
| interpretation | Research proposal only, not live order-sizing default |
| risk_tier | `tiny` |
| max_notional_per_action_usdt | `8` research proposal |
| default_leverage | `1` |
| max_research_leverage | `2` |
| disabled_leverage | `3x/5x` for promotion; observation-only |
| requires_sl | `true` |
| requires_tp_or_exit_plan | `true` |

## Hard Stops

| Hard Stop | Reason |
| --- | --- |
| `role_conflict` | PMR must not mix long/short/overlay claims in one signal. |
| `xag_dominance_unbounded` | Broad metal-basket claim is unsupported. |
| `missing_commodity_session_policy` | Off-hours and weekend behavior are material. |
| `mark_deviation_spike` | Commodity futures mark risk is material. |
| `gold_token_product_risk_missing` | XAUT/PAXG are context only without product facts. |
| `high_leverage_requested` | 3x/5x are observation-only. |

## Evidence Summary

| Evidence | Result |
| --- | --- |
| Session-transfer lead | `pmr_regular_breakdown_short_72h` full 2x `31.047168%`, best-90d 2x `123.235308%`, `0` 2x liquidation-proxy events. |
| Classifier lead | `pmr_regular_volume_confirmed` best-90d 2x `141.806297%`, but DD 2x remains `-69.210756%`. |
| SOR support | PMR short SOR has positive full 2x and 100%+ best-window evidence, but second-half decay remains. |
| Main blocker | Role split, session, mark/funding, fill/gap, and real margin facts. |

## Sample Packets

Canonical sample packets are in `handoff.json`.

## Main-Control Handoff

`PMR-001` is ready for main-control review as an experimental PMR short/overlay
candidate. It should start as observe-only unless main-control explicitly
admits the regular-session short lane into armed observation.
