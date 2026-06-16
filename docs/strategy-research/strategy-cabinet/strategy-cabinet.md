# Strategy Cabinet

Status: ACTIVE_STRATEGY_CABINET
Version: 2026-06-16-r0
Last updated: 2026-06-16

## Scope

This cabinet is the human-readable semantic registry for Strategy Research v3.
It records research status, evidence links, blockers, handoff status, and
revival conditions.

This is research-only. It carries no runtime registration, order authority,
FinalGate input, Operation Layer input, deploy authority, credential authority,
live-profile authority, exchange-write authority, or order-sizing authority.

## Status Legend

| Status | Meaning |
| --- | --- |
| `handoff_ready` | Has a main-control StrategyGroup handoff pack. |
| `handoff_ready_facts_heavy` | Handoff exists, but required facts are heavy. |
| `handoff_ready_low_history_blocked` | Handoff exists, but short history and product facts block promotion. |
| `observe_only_overlay` | Useful as observer, overlay, or filter. |
| `conditional_observation` | Useful only under narrow branch or session conditions. |
| `next_handoff_candidate` | Best next candidate to convert into handoff-ready shape. |
| `research_candidate` | Active research candidate, not handoff-ready. |
| `parked_or_research_vocab` | Parked or vocabulary-only until semantics are redesigned. |
| `facts_pipeline_required` | Potentially valuable, but required fact capture is missing. |
| `observe_only_scorer` | Ranking or scoring lens, not an action group. |
| `overlay_candidate` | Context overlay, filter, or hedge candidate. |

## Cabinet Entries

| Strategy | Status | Default Mode | Research Role | Main Blockers | Evidence | Handoff |
| --- | --- | --- | --- | --- | --- | --- |
| `MPG-001` | `handoff_ready` | `armed_observation` | Core momentum-persistence StrategyGroup over WPR/MFI/PPO/TSI/MHI/DMI with prefix-safe member-disable requirements. | Drawdown, late-cycle disable, forensic attribution not yet prefix-safe, fill/session/product-risk, real margin. | `mpg-member-drawdown-disable-addendum-20260616.md`; `strategy-groups/MPG-001-momentum-persistence-group.md`; `candidate-packets/WPR-001-williams-percent-range-packet.md`; `candidate-packets/DMI-001-adx-directional-ignition-packet.md` | `strategy-group-handoffs/MPG-001/handoff.md`; `strategy-group-handoffs/MPG-001/handoff.json` |
| `FBS-001` | `handoff_ready_facts_heavy` | `armed_observation` | Funding and crowding stress observer; TEQ negative-funding squeeze lead. | Funding settlement, historical OI/long-short/top-trader facts, fill/gap, real margin, concentration. | `fbs-derivatives-facts-readiness-split-20260616.md`; `candidate-packets/FBS-001-funding-basis-stress-packet.md`; `fbs-funding-stress-reversal/fbs-funding-stress-reversal-summary.md`; `fbs-funding-stress-robustness/fbs-funding-stress-robustness-summary.md` | `strategy-group-handoffs/FBS-001/handoff.md`; `strategy-group-handoffs/FBS-001/handoff.json` |
| `TEQ-001` | `handoff_ready_low_history_blocked` | `armed_observation` | Binance equity-like / bStocks / TradFi-perp momentum lane. | Low history, current product availability, session gap, concentration, fill, real margin. | `teq-current-product-availability-refresh-20260616.md`; `candidate-packets/TEQ-001-tokenized-equity-momentum-packet.md`; `extended-universe-us-equity-metals-refresh-20260613.md`; `teq-relative-strength-rotation/teq-relative-strength-rotation-summary.md` | `strategy-group-handoffs/TEQ-001/handoff.md`; `strategy-group-handoffs/TEQ-001/handoff.json` |
| `PMR-001` | `observe_only_overlay` | `observe_only` | Precious-metal short/weakness overlay, XAG-led metal context, and target-specific PMR filter. | Target-specific overlay policy, XAG concentration, standalone short blocked, session/fill, mark/funding, real margin. | `pmr-overlay-role-split-20260616.md`; `candidate-packets/PMR-001-precious-metal-regime-overlay-packet.md`; `pmr-metal-dislocation-refresh/pmr-metal-dislocation-refresh-summary.md`; `pmr-metal-relative-spread-replay/pmr-metal-relative-spread-summary.md` | `strategy-group-handoffs/PMR-001/handoff.md`; `strategy-group-handoffs/PMR-001/handoff.json` |
| `SOR-001` | `conditional_observation` | `armed_observation` | Branch-specific session opening-range and 72h time-stop semantics. | Narrow TEQ short 72h branch, PMR short decay, TEQ long revival-only, broad ORB blocked, session/fill, mark/funding, real margin. | `sor-branch-eligibility-time-stop-20260616.md`; `candidate-packets/SOR-001-session-opening-range-breakout-packet.md`; `sor-session-classifier-sweep/sor-session-classifier-sweep-summary.md`; `sor-exit-reslot-replay/sor-exit-reslot-replay-summary.md` | `strategy-group-handoffs/SOR-001/handoff.md`; `strategy-group-handoffs/SOR-001/handoff.json` |
| `VCB-001` | `observe_only` | `observe_only` | Volatility compression / breakout observe-only true-breakout classifier lane. | False breakout, full-curve weakness, pre-entry classifier weakness, spread/depth, mark/index, real margin. | `candidate-packets/VCB-001-volatility-breakout-packet.md`; `oss-vcb-true-false-breakout/oss-vcb-true-false-breakout-summary.md`; `oss-vcb-volume-compression-cost-m2m/oss-vcb-volume-compression-cost-m2m-summary.md` | `strategy-group-handoffs/VCB-001/handoff.md`; `strategy-group-handoffs/VCB-001/handoff.json` |
| `NLPD-001` | `observe_only` | `observe_only` | New listing / contract event and low-history price-discovery observer. | Low history, listing survivorship, spread/liquidity, product-risk, executable side. | `candidate-packets/NLPD-001-new-listing-price-discovery-packet.md`; `nlpd-new-listing-event-study/nlpd-new-listing-event-study-summary.md`; `bstocks-event-study-refresh/bstocks-event-study-refresh-summary.md` | `strategy-group-handoffs/NLPD-001/handoff.md`; `strategy-group-handoffs/NLPD-001/handoff.json` |
| `RBR-001` | `parked_or_research_vocab` | `observe_only` | Range-boundary / calm-range vocabulary and anti-pattern evidence. | Current calm-range replay fails; needs materially different reclaim/range classifier. | `candidate-packets/RBR-001-range-boundary-reversion-packet.md`; `oss-rbr-calm-range/oss-rbr-calm-range-summary.md`; `negative-evidence.md` | None yet. |
| `LCF-001` | `facts_pipeline_required` | `observe_only` | Liquidation cascade follow-through thesis; high-potential but fact-heavy. | ForceOrder, liquidation cluster, OI, funding, top-trader ratio, ADL, depth, fill/slippage, real margin capture. | `lcf-liquidation-cascade-requiredfacts-design-20260616.md`; `derivatives-leverage-requiredfacts-data-plan.md`; `btpc-derivatives-reviewability/btpc-derivatives-reviewability-summary.md`; `external-data/binance-futures-context-20260613/futures-context-summary.md` | None yet. |
| `RSR-001` | `observe_only_scorer` | `observe_only` | Relative-strength rotation scorer for TEQ and cross-basket interpretation. | Second-half decay, session/fill, product-risk, mark/funding, real margin. | `candidate-packets/RSR-001-relative-strength-rotation-packet.md`; `rsr-decay-disable-classifier/rsr-decay-disable-classifier-summary.md`; `teq-relative-strength-rotation/teq-relative-strength-rotation-summary.md` | `strategy-group-handoffs/RSR-001/handoff.md`; `strategy-group-handoffs/RSR-001/handoff.json` |
| `MDS-001` | `overlay_candidate` | `observe_only` | Metals dislocation / session mismatch concept for PMR-adjacent research. | External session mapping, settlement windows, product availability, spread/fill, target-specific overlay coverage, real margin. | `mds-metals-dislocation-overlay-note-20260616.md`; `pmr-metal-dislocation-refresh/pmr-metal-dislocation-refresh-summary.md`; `pmr-metal-relative-spread-replay/pmr-metal-relative-spread-summary.md`; `extended-universe-us-equity-metals-refresh-20260613.md` | None yet. |

## Main-Control Rule

Only handoff packs under `strategy-group-handoffs/` are main-control intake
artifacts. Cabinet entries without handoff paths are research semantics only.

## Revival Rule

Parked or blocked strategies should not be deleted. They should be revived
only when their listed blocker changes, a stronger activation/disable
classifier appears, or current exchange/product/fact coverage improves.
