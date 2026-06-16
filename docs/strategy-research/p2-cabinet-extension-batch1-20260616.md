# P2 Cabinet Extension Batch 1

Status: ACTIVE_P2_CABINET_EXTENSION
Last updated: 2026-06-16

## Scope

This file expands the Strategy Cabinet with a first batch of additional
right-tail review and revival semantics from existing candidate packets.

It is research-only. It is not a StrategyGroup handoff, not runtime
registration, not FinalGate input, not Operation Layer input, not exchange-write
authority, not live-profile authority, not leverage authority, and not an
order-sizing default.

## Selection Rule

Batch 1 selects candidates that already have:

1. a stable strategy id and semantic name;
2. reproducible candidate packet or replay evidence;
3. a named market structure;
4. explicit blockers;
5. a clear reason to preserve the candidate even when promotion is blocked.

## Batch 1 Entries

| Strategy | Cabinet Status | Market Structure | Preserve Because | Main Blocker |
| --- | --- | --- | --- | --- |
| `SCF-001` | `observe_only handoff draft` | Session confluence / TEQ structure confirmation. | 12h TEQ confluence row has positive full 2x, lower drawdown than 72h, and no 2x/5x proxy liquidation; converted to `strategy-group-handoffs/SCF-001/`. | Fill/gap, product-risk, real margin, and time-stop tradeoff facts. |
| `DMI-001` | `observe_only handoff draft` | ADX / DMI directional ignition. | Equity ADX-rising 24h row has strong full 2x, best-90d 2x, and positive second-half behavior; converted to `strategy-group-handoffs/DMI-001/`. | Cost sensitivity, product/session/fill, metal drag, and real margin facts. |
| `MASS-001` | `right_tail_candidate` | Mass Index range-expansion reversal / continuation. | Mass bulge reversal long has a cleaner drawdown profile than most right-tail review rows. | Direction context, decay, concentration, session/fill, product-risk, and real margin facts. |
| `EFI-001` | `right_tail_candidate` | Price-volume negative-force exhaustion reversal. | Negative-force exhaustion reversal has very large right-tail windows and positive full 2x. | Candidate-level drawdown, short-side failure, high-leverage breakdown, session/fill, product-risk, and real margin facts. |
| `HAT-001` | `research_candidate` | Heikin-Ashi smoothed trend / stop-reslot revival. | Clean-combo and stop-reslot rows preserve large right-tail windows. | Drawdown, stop-fill/gap, exit/disable quality, session/product transferability, and real margin facts. |
| `LSR-001` | `research_candidate` | Liquidity sweep upper-range rejection. | Unbiased rewrite and signal-time classifier preserve a short-side upper-range right-tail window. | Full-sequence collapse, cost/fill, slot/M2M, classifier quality, and real margin facts. |

## Not Handoff-Ready

None of the Batch 1 entries should be handed to main control as executable
StrategyGroups yet. `DMI-001` and `SCF-001` now have observe-only handoff
drafts, but they are still not armed observation or execution intake. Their
current use is:

1. preserve strategy vocabulary;
2. preserve right-tail evidence and negative evidence;
3. create revival conditions;
4. give future P1 handoff work a clear starting queue;
5. keep RequiredFacts visible before any Strategy Picker or runtime intake work.

## RequiredFacts Themes

| Theme | Applies To | Reason |
| --- | --- | --- |
| `fill_gap_slippage_state` | `SCF-001`, `DMI-001`, `MASS-001`, `EFI-001`, `HAT-001`, `LSR-001` | Every entry depends on next-open or stop/fill assumptions. |
| `real_margin_liquidation_model_state` | All Batch 1 entries | Levered outputs remain research stress labels. |
| `session_product_risk_state` | `SCF-001`, `DMI-001`, `MASS-001`, `EFI-001`, `HAT-001` | Binance 2026 equity-like and metal products need session and product handling. |
| `decay_disable_state` | All Batch 1 entries | Full-sequence, monthly, or second-half decay is the common promotion blocker. |
| `asset_role_state` | `DMI-001`, `MASS-001`, `EFI-001`, `HAT-001` | Equity, precious-metal, and industrial-metal roles differ materially. |
| `range_context_state` | `MASS-001`, `LSR-001` | Range-expansion and sweep/rejection facts must not be confused with trend continuation. |

## Next Work

1. Treat `DMI-001` and `SCF-001` as converted Batch 1 observe-only handoff
   drafts; their current use is Strategy Picker vocabulary, watcher exploration,
   and future P1 follow-up, not armed observation.
2. Keep `MASS-001` and `EFI-001` in right-tail review, but do not handoff until
   concentration, decay, fill, and real margin facts improve.
3. Keep `HAT-001` and `LSR-001` as revival candidates until their drawdown and
   full-sequence problems have materially stronger disable or exit facts.
4. Do not compare these rows as a return leaderboard; their evidence models are
   event replay, raw-pool reslot, exit-horizon reslot, fixed-stop reslot, and
   classifier replay.
