# P2 Strategy Pool Expansion Queue

Status: ACTIVE_P2_QUEUE
Last updated: 2026-06-16

## Scope

This queue keeps the strategy pool expanding while preserving the project
boundary: simple, interpretable, non-deep-learning, reproducible, closed-candle
research that can become StrategyGroup semantics, overlay facts, disable facts,
or parked vocabulary.

## Expansion Rules

1. Do not discard a strategy only because it is weak across the full sample.
2. Preserve high-return local windows when the market state is explainable,
   detectable, and bounded.
3. Preserve negative evidence as disable facts, parking rules, or revival
   conditions.
4. Treat leverage as a stress boundary, not as a way to manufacture a strategy.
5. Separate crypto, Binance 2026 equity-like instruments, precious metals, and
   event/listing instruments.
6. Do not use post-entry labels as entry facts.
7. Do not turn retrospective attribution into a signal without a separate
   signal-time classifier.

## Active Expansion Lanes

| Lane | Candidate Families | Current Role | Next Work |
| --- | --- | --- | --- |
| Momentum persistence | `MPG-001`, WPR, MFI, PPO, TSI, MHI, DMI | Core right-tail family. | Mine disable facts and member-level drawdown boundaries. |
| Breakout / compression | `VCB-001`, AEB, DCB, KSB, IBB | Candidate and vocabulary pool. | Separate true breakout, false breakout, and cost/M2M states. |
| Funding / crowding | `FBS-001`, LCF-like derivatives facts | Facts-heavy right-tail lane. | Improve derivatives fact capture and stale-fact behavior. |
| Equity-like rotation | `TEQ-001`, `RSR-001`, NLPD-adjacent event windows | Low-history but important 2026 lane. | Refresh product availability and split scorer versus action semantics. |
| Precious-metal overlay | `PMR-001`, `MDS-001`, RVI metal rows | Overlay and possible conditional short lane. | Expand target-specific overlay coverage after `MDS-001` split NLPD disable, TEQ support, and standalone-blocked roles. |
| Session structure | `SOR-001`, session transfer, opening range | Conditional branch lane. | Build branch eligibility and time-stop tables. |
| New listing / event | `NLPD-001`, bStocks event studies | Low-history event observer. | Broaden event cohort and survivorship controls. |
| Parked vocabulary | `RBR-001`, failed calm-range variants | Negative evidence and future redesign vocabulary. | Revive only with materially different reclaim/range classifier. |

## Cabinet Extension Batch 1

The first P2 cabinet extension is recorded in
`p2-cabinet-extension-batch1-20260616.md`.

| Strategy | Added Role | Current Boundary |
| --- | --- | --- |
| `SCF-001` | Session-confluence observe-only handoff draft. | Converted to `strategy-group-handoffs/SCF-001/`; armed observation remains blocked until fill/gap, product-risk, time-stop, and margin facts improve. |
| `DMI-001` | ADX/DMI directional ignition observe-only handoff draft. | Converted to `strategy-group-handoffs/DMI-001/`; generic DMI, short-side, and metals branches stay blocked. |
| `MASS-001` | Mass Index range-expansion reversal observe-only handoff draft. | Converted to `strategy-group-handoffs/MASS-001/`; armed observation remains blocked until direction-context, decay, concentration, fill/product-risk, and margin facts improve. |
| `EFI-001` | Elder Force Index exhaustion-reversal right-tail candidate. | Boundary fixed in `efi-drawdown-disable-boundary-20260616.md`; review only until drawdown, short-side failure, high-leverage, fill/product-risk, and margin blockers improve. |
| `HAT-001` | Heikin-Ashi stop-reslot revival candidate. | Revival only until drawdown, stop-fill/gap, exit/disable, session/product, and margin facts improve. |
| `LSR-001` | Liquidity-sweep upper-range revival candidate. | Revival only until full-sequence collapse, cost/fill, slot/M2M, classifier, and margin blockers improve. |

## Candidate Intake Criteria

| Criterion | Required Interpretation |
| --- | --- |
| Market structure | Must name the state: trend persistence, squeeze, liquidation cascade, event discovery, session break, range reclaim, or overlay. |
| Data discipline | Closed-candle signal and next-open entry unless explicitly marked analysis-only. |
| Right-tail evidence | Best 30d / 60d / 90d windows are discovery evidence, not promotion proof. |
| Negative evidence | Must be written as disable, parking, or revival facts. |
| Leverage | `1x` default; `2x` research lane; `3x` stress-only; `5x` disabled by default. |
| Main-control shape | Candidate must eventually produce RequiredFacts, hard stops, sample packets, and non-execution flags. |

## Revival Backlog

| Candidate | Current State | Revival Condition |
| --- | --- | --- |
| `RBR-001` | Parked or research vocabulary. | Revive only if a materially different reclaim/range classifier avoids trend-break tail risk. |
| Broad `VCB-001` breakout | Negative as broad rule. | Revive only if signal-time classifier separates true follow-through from false breakout with full-sequence improvement. |
| `NLPD-001` spot fade labels | Analysis-only. | Revive only with executable venue facts and survivorship/liquidity controls. |
| `PMR-001` standalone short | Observe-only overlay. | Revive only after role split, session mapping, fill, mark/funding, and margin facts improve. |
| `MDS-001` universal metal overlay | Overlay candidate. | Revive only with target-specific coverage, PMR-state freshness, session/fill/margin facts, and a stable activation/disable pair. |
| `EFI-001` broad Force Index | Right-tail candidate, not handoff. | Revive only through negative-force exhaustion isolation, signal-time drawdown disable, product/session/fill facts, and real margin evidence. |
| `SOR-001` broad branch | Conditional. | Revive only through named branch eligibility and time-stop evidence. |

## P2 Next Actions

1. Keep the strategy cabinet as the living semantic registry.
2. Add new candidates only when they have evidence paths and blockers.
3. Turn recurring failures into `negative-evidence.md` entries and cabinet
   revival conditions.
4. Keep community and open-source sources as hypothesis vocabulary only.
5. Promote no candidate from P2 to P1 without a stable semantic name,
   reproducible evidence path, RequiredFacts sketch, hard stops, and sample
   signal/no-signal packets.
