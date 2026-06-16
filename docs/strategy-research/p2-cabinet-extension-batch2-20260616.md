# P2 Cabinet Extension Batch 2

Status: ACTIVE_P2_CABINET_EXTENSION
Last updated: 2026-06-16

## Scope

This file expands the Strategy Cabinet with a second batch of indicator-derived
right-tail review, window-revival, and support/negative vocabulary candidates.

It is research-only. It is not a StrategyGroup handoff, runtime registration,
FinalGate input, Operation Layer input, exchange-write authority, deploy
authority, credential authority, live-profile authority, leverage authority, or
order-sizing authority.

## Selection Rule

Batch 2 selects candidates that already have:

1. a stable candidate packet;
2. closed-candle replay evidence;
3. a narrow interpretable market structure;
4. explicit negative branches;
5. a reason to preserve the semantic even without handoff.

## Batch 2 Entries

| Strategy | Cabinet Status | Market Structure | Preserve Because | Main Blocker |
| --- | --- | --- | --- | --- |
| `UO-001` | `observe_only handoff draft` | Ultimate Oscillator bullish divergence after prior weakness. | `uo_bullish_divergence_long_72h` has full 2x `77.534009%`, best-90d 2x `197.155957%`, DD 2x `-44.564941%`, and `0/0` 2x/5x proxy liquidation events; converted to `strategy-group-handoffs/UO-001/`. | Generic midline persistence, short-side symmetry, product/session/fill, and real margin facts. |
| `TRIX-001` | `right_tail_candidate` | TRIX triple-EMA zero-cross long, thin sample. | `trix_zero_cross_long_72h` has `8` events, full 2x `117.088679%`, best-90d 2x `121.251707%`, DD 2x `-1.881580%`, and `0/0` proxy liquidation events; boundary fixed in `trix-thin-sample-concentration-boundary-20260616.md`. | Thin sample, symbol contribution concentration, broad TRIX persistence failure, product/session/fill, and real margin facts. |
| `PSAR-001` | `right_tail_candidate` | Parabolic SAR bullish flip burst. | `psar_flip_long_48h` has full 2x `33.292646%`, best-90d 2x `124.602670%`, and `0/0` 2x/5x proxy liquidation events; boundary fixed in `psar-whipsaw-stop-reverse-boundary-20260616.md`. | DD 2x `-57.821226%`, whipsaw, stop-reverse decay, product/session/fill, and real margin facts. |
| `ICH-001` | `research_candidate` | Ichimoku cloud breakout with no-future-cloud policy. | `ich_cloud_breakout_long_48h` has best-90d 2x `296.354715%` and a clear leakage-safe cloud-breakout vocabulary; boundary fixed in `ich-no-future-cloud-decay-boundary-20260616.md`. | Full 2x `-78.421778%`, DD 2x `-85.398509%`, category decay, no-future-cloud enforcement, product/session/fill, and margin facts. |
| `CCI-001` | `research_candidate` | CCI trend escape / failure and precious-metal +100 failure short. | `cci_failure_short_precious_metal_only` has full 2x `72.496535%`, best-90d 2x `105.400734%`, and `0` 2x proxy liquidation events. | DD 2x `-74.614868%`, generic CCI failure, equity reclaim decay, off-hour mark/index, fill/gap, and real margin facts. |
| `AEB-001` | `research_candidate` | ATR / True Range expansion breakout, short-window equity branch. | `aeb_atr24_equity_expansion_long_48h` has best-30d 2x `218.708454%` and positive full 2x `2.502514%`. | Best-90d 2x only `31.950523%`, false-breakout risk, 90d decay, product/session/fill, and margin facts. |
| `STOCH-001` | `parked_or_research_vocab` | Stochastic bullish range persistence and whipsaw vocabulary. | `stoch_bullish_range_persistence_long_72h` preserves short-window 30d/60d 2x evidence. | No 100%+ best-90d 2x row, full 2x `-90.790585%`, DD 2x `-95.696757%`, and 5x proxy risk. |

## Semantic Split

| Group | Strategies | Meaning |
| --- | --- | --- |
| Right-tail review | `TRIX-001`, `PSAR-001` | Worth preserving as narrow review candidates, but not handoff-ready. |
| Converted observe-only | `UO-001` | Converted to an observe-only handoff draft; not armed observation or execution intake. |
| Window-revival | `ICH-001`, `CCI-001`, `AEB-001` | Useful windows or branches exist, but full-sequence and drawdown block promotion. |
| Support / negative vocabulary | `STOCH-001` | Useful as oscillator whipsaw / decay vocabulary, not as an active candidate. |

## RequiredFacts Themes

| Theme | Applies To | Reason |
| --- | --- | --- |
| `divergence_quality_state` | `UO-001` | Only bullish divergence has current right-tail evidence. |
| `thin_sample_state` | `TRIX-001` | The useful zero-cross row has only `8` accepted events. |
| `whipsaw_disable_state` | `PSAR-001`, `STOCH-001` | Stop-reverse and stochastic signals are vulnerable to chop and continuation failure. |
| `no_future_cloud_policy` | `ICH-001` | Ichimoku forward-shifted cloud / Chikou facts must not become entry facts. |
| `asset_role_state` | `CCI-001`, `AEB-001`, `STOCH-001` | Equity, precious-metal, and industrial-metal rows behave differently. |
| `window_decay_state` | All Batch 2 entries | Best-window evidence must not be confused with full-sample alpha. |
| `fill_gap_slippage_state` | All Batch 2 entries | All replay entries use next-open 1h assumptions. |
| `real_margin_liquidation_model_state` | All Batch 2 entries | Leverage remains research stress without real margin facts. |

## Current Decisions

1. `UO-001` now has an observe-only handoff draft under `strategy-group-handoffs/UO-001/`.
2. Keep `TRIX-001` and `PSAR-001` as right-tail review candidates; `TRIX-001`
   has a thin-sample / concentration boundary and `PSAR-001` has a whipsaw /
   stop-reverse boundary, but neither has a handoff.
3. Keep `ICH-001`, `CCI-001`, and `AEB-001` as research candidates with
   explicit window-revival semantics; `ICH-001` now has a no-future-cloud /
   decay boundary but no handoff.
4. Keep `STOCH-001` as parked / research vocabulary because the best 90d gate
   fails and the full sequence is deeply negative.
5. Do not compare Batch 2 returns as a leaderboard; evidence types include
   thin sample, window-revival, broad negative attribution, and branch-specific
   support.

## Next Work

1. Build signal-time hardening for `UO-001` before any armed-observation
   discussion, build PSAR bullish-flip quality and whipsaw-disable facts after
   `psar-whipsaw-stop-reverse-boundary-20260616.md`, enforce ICH no-future-cloud
   and cloud-breakout disable facts after
   `ich-no-future-cloud-decay-boundary-20260616.md`, and build a disable
   classifier for `CCI-001` before any handoff discussion.
2. Expand sample, concentration, and signal-time zero-cross quality checks for
   `TRIX-001` after `trix-thin-sample-concentration-boundary-20260616.md`.
3. Treat `AEB-001` as a short-window volatility-expansion revival handle until
   60d/90d persistence improves.
4. Use `STOCH-001` primarily as stochastic whipsaw / decay RequiredFacts
   vocabulary for other oscillator or range-persistence candidates.
