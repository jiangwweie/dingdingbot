# Stage-2 Full Replay Report — Protocol V2

## Status

```text
research_status = STAGE2_FULL_REPLAY_COMPLETE
selector_design_authority = NONE
implementation_authority = NONE
production_authority = NONE
```

## Code facts

- Authority: `dev@2697f4b5943ed6a98f04a93e1b78d38e53780890`.
- CandidateUniverse is the exact sorted 24-member SOR Dynamic V0 panel.
- CPM/MPG/MI/BRF2 use direct current-dev Detector invocation and production
  `build_comparative_universe_projection()` for MPG/MI.
- Signal anchor is the trigger candle final close. Protection is the exact
  Detector `protection_reference` fact. Forward path starts strictly after the
  trigger close boundary.
- Signal-R is not production execution R. No Detector, threshold, ExitProfile,
  Capacity, leverage, Selection Authority, or production behavior changed.

## Replay facts

| Denominator | Count |
| --- | ---: |
| Candidate-hours | 17,856 |
| Valid Detector evaluations | 71,424 |
| Invalid Detector evaluations | 0 |
| Raw triggered evaluations | 2,188 |
| Rising-edge Replay Events | 1,476 |

| Strategy | Events |
| --- | ---: |
| BRF2 | 613 |
| CPM | 719 |
| MI | 74 |
| MPG | 70 |

| Path | Count |
| --- | ---: |
| SIGNAL_TP1_FIRST | 697 |
| SIGNAL_STOP_FIRST | 545 |
| NEITHER | 234 |
| AMBIGUOUS | 0 |

All 744 hourly market states contained all 24 candidates and all 276 pairwise
correlations. All Replay Events had valid Signal-R geometry. No observed Event
required a real 1m ambiguity drill-down; the 15m→1m and still-ambiguous branches
are covered by deterministic tests.

## Frozen classifications

| Classification | Count |
| --- | ---: |
| SUPPORTED_FOR_SHADOW | 4 |
| INCONCLUSIVE | 6 |
| REJECTED | 11 |

### Supported hypotheses

Effect is `HIGH net_path_rate - LOW net_path_rate`.

| Strategy | Feature | Discovery effect | Holdout effect | Holdout LOW N | Holdout HIGH N | LOSO same-sign |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| BRF2-001 | avg_cross_asset_corr_24h | 0.153 | 0.318 | 17 | 254 | 100.0% |
| BRF2-001 | market_rv_24h | 0.154 | 0.559 | 34 | 218 | 100.0% |
| CPM-RO-001 | avg_cross_asset_corr_24h | -0.331 | -0.386 | 28 | 244 | 100.0% |
| CPM-RO-001 | directional_efficiency_24h | 0.248 | 0.466 | 65 | 172 | 100.0% |

Interpretation:

- BRF2 Events had better Signal-R path quality in HIGH average cross-asset
  correlation and HIGH market realized-volatility states.
- CPM Events had better Signal-R path quality in LOW average cross-asset
  correlation states and HIGH candidate directional-efficiency states.
- MPG produced no supported Context feature under the frozen gates.
- MI produced no supported Context feature; its extreme Holdout buckets were
  generally below the required 15 resolved observations.

## Production parity and execution sensitivity

- Production historical signals: 420.
- Current-version direct Detector trigger matches: 290.
- Normalized Detector fact matches: 290.
- Protection-reference matches: 290.
- Legacy EventSpec v2 drift: 90.
- Fixed-24 ComparisonUniverse drift for MPG/MI: 40.
- Matched production Tickets: 30 / 41.
- Signal-basis vs actual-entry path classification: 28 same,
  2 changed.
- Absolute execution-anchor delta: P75 `0.076`
  Signal-R; P90 `0.123` Signal-R.

The requested immutable 2026-08-30 production snapshot was unavailable. These
checks use current Tokyo PostgreSQL retained historical lineage and therefore
are secondary sanity evidence only.

## Research inference

The four supported rows may enter a future Shadow Selection design as
univariate hypotheses. They do not authorize a composite score, threshold
optimization, ticker whitelist, production Selector, or strategy change.

## Not proven

This study does not prove profitability, causality, optimal thresholds,
execution-adjusted edge, fee/slippage-adjusted edge, production readiness, or
that a multi-feature Selector will outperform. Required next evidence remains:

```text
Shadow Selection -> Forward Evidence -> Execution Economics -> Owner Activation
```
