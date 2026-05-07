# NSC-004 — CPM-2 Research-only Adapter Design Plan

**Date:** 2026-05-06
**Status:** Proposed / Research-only Adapter Design Plan
**Scope:** Docs-only design plan
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document designs the minimum research-only adapter scope needed after NSC-003 stopped at `HARNESS_INFEASIBLE`.

This document does not authorize:

- writing adapter code;
- running experiments;
- changing runtime profiles;
- changing risk rules;
- registering production strategies;
- modifying backtester / research engine core;
- making any promotion, small-live, or live deployment decision.

CPM-1 remains paused. CPM-2 has no Candidate A/B evidence yet and is not pass/pause/reject on strategy evidence. Small-live readiness gate remains unmet.

---

## 1. Background

Prior state:

- NSC-001 selected CPM-2 direction: ETH 1h pullback-continuation with a different entry confirmation mechanism.
- NSC-002 defined Candidate A/B frozen experiment rules.
- NSC-003 stopped before execution because the current harness cannot express the frozen rules without implementation work.

NSC-003 findings:

| Candidate | NSC-003 Finding |
| --- | --- |
| Candidate A — One-Bar Continuation Reclaim | Current immediate-bar trigger harness cannot express delayed one-bar reclaim and delayed fill convention. |
| Candidate B — Donchian-Location Pullback Confirmation | `-0.016809` provenance is confirmed, but current `donchian_distance` filter semantics are inverse to NSC-002 and would revive old E4 hard-filter behavior. |

NSC-004 therefore designs a research-only adapter, not a runtime strategy implementation.

---

## 2. Adapter Goal

The adapter's only goal is to make Candidate A and Candidate B executable under NSC-002 frozen rules for research evidence generation.

The adapter must:

- remain research-only;
- avoid production strategy registration;
- avoid runtime/profile/risk changes;
- avoid backtester/research engine core changes;
- preserve NSC-002 frozen rule semantics;
- generate enough trace data to support evidence review and anti-lookahead audit.

The adapter must not:

- become a reusable live strategy implementation;
- introduce parameter search;
- introduce Candidate C;
- combine Candidate A and B unless a later Owner-approved plan explicitly allows it;
- imply promotion or small-live readiness.

---

## 3. Preferred Architecture

Preferred path: standalone research script / report generator under a later Owner-approved NSC-005 task.

The adapter should operate outside production runtime and outside backtester core:

1. Load historical 1h/4h data through read-only existing repositories or already available report artifacts.
2. Reproduce CPM-1 setup marker detection for research purposes.
3. Apply Candidate A or Candidate B frozen acceptance rules.
4. Produce candidate signal/event ledgers with full timestamps and rejection reasons.
5. Either:
   - call existing matching/cost logic read-only if it can accept externally generated candidate entries without modifying core semantics; or
   - run a clearly labeled proxy matching layer inside the standalone script with explicit caveats.
6. Write outputs only under `reports/nsc-005-cpm2-research-only-adapter/` or equivalent `reports/` subdirectory.

If a faithful implementation requires modifying `src/application/backtester.py`, `src/domain/strategy_engine.py`, `src/domain/filter_factory.py`, runtime strategy models, or any production code path, NSC-005 must not execute. It must return to Owner for an explicit architecture decision.

---

## 4. Candidate A Adapter Design

### 4.1 Objective

Implement the NSC-002 Candidate A frozen rule in research-only form:

> CPM-1 Pinbar setup marker appears, no immediate entry; inspect only the next fully closed 1h candle; accept only if the confirmation candle close reclaims setup high.

### 4.2 Minimal Inputs

Required inputs:

- ETH/USDT:USDT 1h candles for 2021, 2022, 2023, 2024, 2025.
- ETH/USDT:USDT 4h candles or existing 4h EMA60 trend data for the same windows.
- CPM-1 frozen Pinbar setup definition:
  - `min_wick_ratio=0.6`
  - `max_body_ratio=0.3`
  - `body_position_tolerance=0.1`
- CPM-1 frozen context:
  - EMA50 primary context
  - 4h EMA60 confirmation
  - LONG-only

### 4.3 Event Flow

For each 1h candle `bar_i`:

1. Compute CPM-1 Pinbar setup marker on `bar_i`.
2. Apply CPM-1 context filters using only data available by `bar_i` close:
   - primary EMA context;
   - 4h EMA60 confirmation using only fully closed 4h candles.
3. If setup is not valid, record `NO_SETUP` or `FILTERED_CONTEXT` as appropriate.
4. If setup is valid, do not create an entry on `bar_i`.
5. Read only `bar_i+1` after it is fully closed.
6. Accept if `bar_i+1.close > bar_i.high`.
7. Reject if `bar_i+1.close <= bar_i.high`.
8. If accepted, create a research entry event using the explicitly defined entry convention.

### 4.4 Entry Convention

NSC-005 must choose and freeze one entry convention before execution. Recommended convention:

- Confirmation candle: `bar_i+1`.
- Entry bar: `bar_i+2`.
- Entry timestamp: `bar_i+2.open_time`.
- Entry price convention: `bar_i+2.open` adjusted by the official OOS entry slippage model.

If `bar_i+2` is unavailable because the setup is near the end of a data window, record `REJECT_NO_ENTRY_BAR` and do not infer prices from future windows.

### 4.5 Required Audit Fields

Each Candidate A setup row must record:

| Field | Description |
| --- | --- |
| `setup_timestamp` | `bar_i` timestamp |
| `setup_open/high/low/close` | setup candle OHLC |
| `confirmation_timestamp` | `bar_i+1` timestamp |
| `confirmation_open/high/low/close` | confirmation candle OHLC |
| `confirmation_rule` | `confirmation_close > setup_high` |
| `confirmation_result` | accepted / rejected |
| `entry_timestamp` | `bar_i+2.open_time`, if accepted |
| `entry_bar` | explicit bar index or timestamp |
| `entry_price_convention` | e.g. next-bar open plus entry slippage |
| `entry_price` | computed entry price, if accepted |
| `reject_reason` | no setup / context fail / reclaim fail / no entry bar |
| `lookahead_proof` | fields used: setup bar, confirmation bar, entry bar only |

### 4.6 Future-candle Access Proof

The adapter must prove:

- setup decision uses data through `bar_i` close only;
- 4h MTF context uses only 4h candles whose close time is `<= bar_i` close time;
- confirmation decision uses `bar_i+1` only after it is fully closed;
- entry fill uses only `bar_i+2.open` and the frozen slippage convention;
- no MFE/MAE, exit, or future price data is consulted before entry decision is finalized.

The final report must include an anti-lookahead section and at least one row-level example showing the timestamps used.

### 4.7 Non-goals

Candidate A adapter must not:

- test multiple reclaim rules;
- optimize wait length;
- use EMA/pivot/range reclaim variants;
- change Pinbar geometry;
- change exits, risk sizing, MTF, direction, or costs;
- combine with Candidate B.

---

## 5. Candidate B Adapter Design

### 5.1 Objective

Implement the NSC-002 Candidate B frozen rule in research-only form:

```text
distance_to_donchian_high = (setup_close - previous_20_bar_donchian_high) / previous_20_bar_donchian_high
accept if distance_to_donchian_high >= -0.016809
reject if distance_to_donchian_high < -0.016809
```

This is structural confirmation for pullback-continuation. It is not Donchian breakout and not the old E4 hard filter.

### 5.2 Threshold Provenance

The threshold must be recorded as:

- value: `-0.016809`
- source: NSC-001 historical evidence chain;
- historical provenance:
  - `archive/2026-04-29-pre-live-safe-replan/docs/planning/2026-04-28-pinbar-toxic-state-avoidance-m1.md`
  - `archive/2026-04-29-pre-live-safe-replan/docs/planning/2026-04-28-m1c-donchian-distance-official-check.md`
  - `archive/2026-04-29-pre-live-safe-replan/docs/planning/2026-04-28-m1d-donchian-distance-implementation-design.md`

If NSC-005 cannot verify this provenance before execution, Candidate B must pause. It may not replace, round, sweep, or temporarily tune the threshold.

### 5.3 Minimal Inputs

Required inputs:

- ETH/USDT:USDT 1h candles for 2021, 2022, 2023, 2024, 2025.
- ETH/USDT:USDT 4h candles or existing 4h EMA60 trend data for the same windows.
- CPM-1 frozen Pinbar setup marker and context filters.
- Previous 20 fully closed 1h candles before each setup candle.

### 5.4 Event Flow

For each 1h setup candle `bar_i`:

1. Compute CPM-1 Pinbar setup marker on `bar_i`.
2. Apply CPM-1 context filters using only data available by `bar_i` close.
3. If setup is not valid, record `NO_SETUP` or `FILTERED_CONTEXT`.
4. Build Donchian high using exactly `bar_i-20` through `bar_i-1`.
5. Exclude `bar_i` from Donchian calculation.
6. If fewer than 20 prior candles are available, record `REJECT_INSUFFICIENT_HISTORY`.
7. Compute:

```text
distance_to_donchian_high = (bar_i.close - max(high[bar_i-20:bar_i-1])) / max(high[bar_i-20:bar_i-1])
```

8. Accept if `distance_to_donchian_high >= -0.016809`.
9. Reject if `distance_to_donchian_high < -0.016809`.
10. If accepted, use the same CPM-1 entry timing convention unless NSC-005 explicitly freezes a research-only equivalent.

### 5.5 Required Audit Fields

Each Candidate B setup row must record:

| Field | Description |
| --- | --- |
| `setup_timestamp` | setup candle timestamp |
| `setup_open/high/low/close` | setup candle OHLC |
| `donchian_lookback` | `20` |
| `donchian_window_start` | timestamp of `bar_i-20` |
| `donchian_window_end` | timestamp of `bar_i-1` |
| `donchian_high` | previous-20-bar high |
| `distance_to_donchian_high` | exact Decimal/string value |
| `threshold` | `-0.016809` |
| `threshold_provenance` | NSC-001 / M1 / M1c / M1d references |
| `confirmation_result` | accepted / rejected |
| `reject_reason` | no setup / context fail / insufficient history / structural fail |
| `lookahead_proof` | Donchian window excludes setup/current candle |

### 5.6 Future-candle Access Proof

The adapter must prove:

- Donchian high uses only the previous 20 fully closed 1h candles;
- setup/current candle is excluded from Donchian high;
- no future candle is used in structural confirmation;
- MTF context uses only closed 4h candles available at setup time.

The final report must include at least one row-level example showing the 20-bar window boundaries.

### 5.7 Non-goals

Candidate B adapter must not:

- call or configure the current inverse-semantics `donchian_distance` filter as the candidate rule;
- run the old E4 hard-filter semantics;
- sweep threshold;
- round threshold;
- replace threshold;
- add EMA slope / volatility / recent-return toxic filters;
- become Donchian breakout or trend-following;
- combine with Candidate A.

---

## 6. Matching and Cost Handling

The adapter should prefer reuse by read/call where safe, but must not change core semantics.

Acceptable options for NSC-005:

| Option | Allowed? | Notes |
| --- | --- | --- |
| Standalone research proxy matcher inside `scripts/` | Allowed if Owner approves NSC-005 | Must label proxy caveats and preserve official cost values. |
| Read/call existing matching/cost code without modifications | Allowed if technically possible | Must not alter `src/**`; must record exact fee/slippage/funding values. |
| Modify backtester core to accept external signals | Not allowed under NSC-005 as currently envisioned | Must return to Owner for separate architecture decision. |
| Modify production strategy/filter classes | Not allowed | Would cross into runtime strategy implementation. |

Cost requirements:

- Use CPM-1 official OOS report SSOT.
- Record exact fee, entry slippage, TP slippage, funding enabled/disabled state, and funding approximation.
- Separate gross expectancy from net PnL.
- Classify any improvement without gross expectancy improvement as trade deletion / cost compression.

Same-bar requirements:

- Use pessimistic same-bar policy if matching is performed.
- Record same-bar conflict counts.
- If standalone proxy cannot faithfully represent same-bar behavior, report must mark the evidence as proxy-only and not comparable to official backtester evidence.

---

## 7. Output Requirements for NSC-005

If Owner approves NSC-005 and the adapter is implemented, it must output under `reports/nsc-005-cpm2-research-only-adapter/`:

- `candidate_a_events.jsonl` or equivalent event ledger.
- `candidate_b_events.jsonl` or equivalent event ledger.
- candidate-level summary JSON.
- human-readable Markdown experiment report.
- anti-lookahead audit section.
- failure / evidence classification block from NSC-002.

The report must explicitly state:

- CPM-1 remains paused.
- CPM-2 result is only evidence review input.
- No promotion conclusion.
- No small-live candidate conclusion.
- No live deployment recommendation.
- No runtime/profile/risk change.

---

## 8. NSC-005 Candidate Execution Path

NSC-005 may proceed only if the adapter can be implemented as standalone research-only code or read/call-only use of existing components.

Decision gate:

| Condition | NSC-005 Action |
| --- | --- |
| Candidate A/B adapters can be standalone under allowed files | Proceed with Owner-approved research-only implementation + experiment. |
| Matching/cost can be reused read-only without changing core semantics | Proceed, record exact reused semantics. |
| Matching/cost cannot be reused and proxy is acceptable to Owner | Proceed only if NSC-005 explicitly labels proxy caveats. |
| Any required work modifies backtester core, runtime strategy classes, production filters, runtime profiles, risk rules, or migrations | Stop; return to Owner for architecture decision. |

---

## 9. NSC-005 Draft Allowed / Forbidden Files

### Allowed Files Draft

For a later Owner-approved NSC-005:

- `scripts/nsc_005_cpm2_research_adapter.py` or equivalent standalone research script.
- `reports/nsc-005-cpm2-research-only-adapter/**`.
- `docs/ops/**` for report links, progress notes, or review notes.
- `archive/**` inspect-only.
- `reports/**` inspect/read plus NSC-005 output write under its own subdirectory.

Optional only if Owner explicitly approves tests for the standalone script:

- `tests/research/**` or another non-runtime research-test location, if such a location already exists or is approved.

### Forbidden Files Draft

For NSC-005 by default:

- `src/**`
- `configs/**`
- `migrations/**`
- runtime profiles
- production strategy implementation
- production filter implementation
- risk rules
- backtester / research engine core
- portfolio engine
- regime system
- multi-strategy runtime
- multi-asset runtime
- feature store
- complex ML components

Forbidden behaviors:

- parameter search;
- Candidate A reclaim-rule sweep;
- Candidate B threshold sweep;
- threshold rounding/replacement;
- Candidate A/B combination;
- Candidate C execution;
- promotion conclusion;
- live deployment advice.

---

## 10. Review Recommendation

NSC-005 is worth entering Owner approval only if it is explicitly scoped as:

> research-only standalone adapter implementation + frozen Candidate A/B experiment execution.

The valuable next step is to create auditable research evidence, not production strategy code.

If implementation discovery shows that a faithful experiment requires changing backtester core or production strategy/filter semantics, NSC-005 should stop and return to Owner decision rather than widening scope.

---

## 11. Readiness Statement

This design plan does not make CPM-2 a strategy candidate.

Any later NSC-005 result can only enter evidence review. It cannot by itself imply:

- promotion;
- small-live candidacy;
- live deployment;
- runtime profile changes;
- risk rule changes.

Small-live readiness gate remains unmet.
