# BTC+ETH Phase 1 Docs-Only Confirmation Report

**Date:** 2026-05-09  
**Status:** Owner review-ready validation report  
**Scope:** 4h Direction A BTC+ETH Phase 1 docs-only consolidation  
**Runtime impact:** None  

---

## 1. Validation Result

Confirmed.

The current phase is:

`Observation + Research Methodology Reset`

The only current mainline strategy-research object is:

`Direction A BTC+ETH Phase 1 observation design`

The current mode is shadow/no-order observation planning only. The reviewed
docs consistently prohibit paper/testnet/live trading, small-live execution,
strategy runtime, exchange/API activation, portfolio/router logic, SOL Phase 2,
CPM reopening, short-side work, and strategy/risk/parameter changes.

SRR-002 remains the governing docs-only methodology for future strategy
research. No current module satisfies SRR-002 standards.

---

## 2. Files Verified

| File | Validation read |
|---|---|
| `docs/ops/direction-a-btc-eth-phase1-observation-design-consolidation.md` | Contains BTC+ETH evidence summary, shadow/no-order scope, sleeve projections, fragility notes, and gap list |
| `docs/ops/direction-a-btc-eth-phase1-owner-review-2026-05-09.md` | Contains concise Owner decision frame and recommendations |
| `docs/ops/observation-research-reset-reconciliation-snapshot-2026-05-09.md` | Contains phase/mainline confirmation, ADR state, artifact reconciliation, SRR-002 flags, and untracked-doc grouping frame |
| `docs/adr/0001-live-safe-v1-scope.md` | Contains 2026-05-09 docs-only stage note |
| `docs/ops/live-safe-v1-findings.md` | Records phase, BTC+ETH mainline, and SRR-002 finding |
| `docs/ops/live-safe-v1-program.md` | Reframes live-safe as preserved safety foundation, not activation path |
| `docs/ops/live-safe-v1-progress.md` | Records 2026-05-09 consolidation progress and no-execution status |
| `docs/ops/live-safe-v1-task-board.md` | Contains current mainline confirmation and SRR-002 baseline |
| `docs/ops/project-roadmap-v2.md` | Names current stage and BTC+ETH Phase 1 as only current mainline |

---

## 3. Reconciliation Gaps Confirmed

| Gap | Confirmed status |
|---|---|
| A1/A3 trade count mismatch | Recorded: Phase 1 doc says 490; frontier JSON says 373 |
| A1/A3 time-in-market mismatch | Recorded: Phase 1 doc says ~38%; frontier JSON says 52.26% |
| BTC+ETH portfolio MaxDD baseline | Recorded as not exactly computable from standalone docs |
| MTM drawdown inclusion | Recorded as Owner decision: whether no-order observation should track MTM drawdown in addition to realized/virtual drawdown |

These gaps do not authorize recomputation, reruns, experiments, or runtime work.

---

## 4. Fragility Notes Confirmed

| Fragility item | Confirmed status |
|---|---|
| Top-winner dependence | Recorded in BTC+ETH consolidation and Owner brief |
| Top-3 removal failure | Recorded: unshaped BTC+ETH net after top-3 removal is negative |
| Top-5 removal failure | Recorded: unshaped BTC+ETH net after top-5 removal is negative |
| 2022 vulnerability | Recorded as BTC+ETH negative year / bear-chop damage |
| 2025 vulnerability | Recorded as BTC+ETH negative year / cost-chop drag |
| Shared episode dependence | Recorded through P0 `WINNER_EVIDENCE_PARTIALLY_SHARED` and effective observation caveat |

---

## 5. Untracked Document Handling

Current visible untracked docs in this worktree:

| Path | Proposed handling |
|---|---|
| `docs/ops/direction-a-btc-eth-phase1-observation-design-consolidation.md` | Group A current mainline consolidation |
| `docs/ops/direction-a-btc-eth-phase1-owner-review-2026-05-09.md` | Group A concise Owner decision brief |
| `docs/ops/observation-research-reset-reconciliation-snapshot-2026-05-09.md` | Group A reconciliation snapshot |

The referenced 21-doc batch is not visible in the current local worktree. It
should not be grouped, archived, staged, or tracked until the Owner provides
the actual inventory source.

---

## 6. Recommendation

Recommended Owner decisions:

1. Approve BTC+ETH Phase 1 shadow/no-order observation design planning if the
   Owner accepts the recorded SRR-002 caveats and fragility.
2. Approve the three visible docs as Group A current mainline Owner-review
   artifacts, or request edits before tracking.
3. Confirm SRR-002 as the governing docs-only methodology.
4. Decide whether the A1/A3 trade count, time-in-market, BTC+ETH portfolio
   MaxDD, and MTM drawdown gaps must be resolved before finalizing any
   observation log template.

This report does not authorize runtime, experiments, paper/testnet/live
trading, small-live execution, strategy/risk/parameter changes, SOL Phase 2,
CPM, short-side work, or portfolio/router logic.

