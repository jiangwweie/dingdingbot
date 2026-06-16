# NLPD-001 Low-History Event Boundary

Status: P1_HANDOFF_SUPPLEMENT_READY
Last updated: 2026-06-16

## Scope

This document hardens `NLPD-001` by separating low-history event observation
from executable listing-strategy activation.

It is research-only. It does not register runtime behavior, authorize orders,
change risk sizing, modify FinalGate, touch Operation Layer, or request deploy.

## Known Objective

`NLPD-001` should remain observe-only until listing event time, first-window
OHLCV, survivorship, product-risk, spread/liquidity, and executable-side facts
are reproducible.

The useful shape is not "trade every new listing." The useful shape is:

1. Preserve auditable event timestamps.
2. Record first-session continuation and delayed fade labels.
3. Separate bStocks spot labels from TradFi futures labels.
4. Keep spot short/fade labels analysis-only.
5. Use PMR disable context when it historically blocks continuation.

## Evidence Boundary

| Evidence | Result | Allowed Use | Forbidden Use |
| --- | ---: | --- | --- |
| Listing-hint universe | `31` symbols. | Event-observation universe. | Broad listing-strategy allowlist. |
| bStocks spot cohort | `6` symbols, `31` to `55` refreshed 1h bars. | Low-history event-study cohort. | Promotion or robust right-tail claim. |
| Delayed labels | `575` rows. | Research labels using closed candles and next-open entry. | Runtime signal without current event facts. |
| bStocks delayed labels | `135` rows. | Low-history continuation/fade vocabulary. | Executable short/fade strategy. |
| Best bStocks first window | `SNDKBUSDT` 24h `17.207059%`. | Event-window discovery evidence. | General new-listing alpha claim. |
| Best delayed continuation | `SNDKBUSDT` 12h delay / 36h hold `6.846788%` net. | Continuation label candidate. | Armed observation. |
| Best delayed fade | `CRCLBUSDT` 3h delay / 24h hold `5.620422%` net. | Analysis-only fade label. | Spot short execution signal. |
| PMR target-specific overlay | PMR-state continuation events: `213`; 2x result `-99.992487%`. No-PMR allowed events: `64`; 2x result `113.983438%`. | NLPD disable/downshift context. | PMR standalone signal. |

## Event Observer Versus Candidate Split

| NLPD Role | Meaning | Main-Control Behavior |
| --- | --- | --- |
| `nlpd_event_observer` | Auditable event time plus first closed 1h windows exist. | Allow observe-only packet. |
| `nlpd_first_session_continuation_label` | Early continuation label exists after 1h/3h/12h delay. | Research label only until cohort and liquidity facts improve. |
| `nlpd_post_burst_fade_label` | Delayed fade label exists after initial burst. | Analysis-only unless executable-side facts exist. |
| `nlpd_bstocks_low_history_cohort` | bStocks spot cohort has short but useful histories. | Keep low-history warning and block promotion. |
| `nlpd_spot_short_analysis_only` | Short/fade label appears on spot-only product. | Block executable short interpretation. |
| `nlpd_pmr_disable_overlay` | PMR-state continuation labels are historically toxic. | Allow disable/downshift annotation only. |
| `nlpd_armed_observation_blocked` | Product, survivorship, liquidity, and executable-side facts remain incomplete. | Block candidate prepare and armed observation. |

## RequiredFacts Deltas

| RequiredFact | Meaning | Missing Behavior |
| --- | --- | --- |
| `nlpd_event_source_state` | Official listing, exchangeInfo first-seen time, or auditable event source. | `no_event_signal` |
| `nlpd_first_window_completeness_state` | Required closed 1h candles exist after listing. | `no_event_signal` |
| `nlpd_low_history_block_state` | Dataset is short-history and not promotion-grade. | `observe_only` |
| `nlpd_survivorship_control_state` | Failed, missing, renamed, or unavailable symbols are accounted for. | `block_cohort_claim` |
| `nlpd_product_class_state` | Separates bStocks spot, TradFi perps, metal tokens, and normal crypto. | `block_promotion` |
| `nlpd_spread_liquidity_state` | Spread, volume, and liquidity proxies are reproducible. | `block_promotion` |
| `nlpd_short_executable_state` | Short/fade labels are executable or analysis-only. | `block_short_candidate` |
| `nlpd_post_entry_label_boundary_state` | Labels are research targets, not runtime entry facts. | `block_candidate_prepare` |
| `nlpd_pmr_disable_overlay_state` | PMR downshift/disable context for NLPD continuation labels. | `no_disable_annotation` |

## Sample Event Packet

```json
{
  "strategy_group_id": "NLPD-001",
  "version": "2026-06-16-low-history-boundary-r0",
  "status": "observe_only_listing_event_state_ready",
  "symbol": "SNDKBUSDT",
  "direction": "long",
  "candidate_prepare_allowed_by_research": false,
  "execution_allowed_by_research": false,
  "role": "nlpd_event_observer",
  "required_facts_state": {
    "nlpd_event_source_state": "present",
    "nlpd_first_window_completeness_state": "present",
    "nlpd_low_history_block_state": "blocking",
    "nlpd_survivorship_control_state": "missing",
    "nlpd_product_class_state": "bstocks_spot",
    "nlpd_spread_liquidity_state": "missing",
    "nlpd_short_executable_state": "not_applicable_for_long",
    "nlpd_post_entry_label_boundary_state": "labels_research_only",
    "nlpd_pmr_disable_overlay_state": "not_triggered"
  },
  "main_control_hint": "observe_only_no_candidate_prepare",
  "reason": "Listing event and first-window candles are observable, but low-history, survivorship, product, spread/liquidity, and executable-side facts block promotion."
}
```

## Research Conclusion

`NLPD-001` remains useful because it gives the system an event-observation lane
for new listings and short-history products. It is not yet an executable
listing strategy.

The correct handoff posture is:

```text
observe listing events
record first-window behavior
keep labels research-only
separate bStocks from futures
block spot short execution labels
attach PMR disable context when present
block armed observation until cohort and product facts improve
```

This preserves the event-study value while keeping low-history evidence inside
its proper boundary.
