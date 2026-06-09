> [!NOTE]
> **HISTORICAL_EVIDENCE** — This document is a historical research artifact from an earlier project phase.
>
> It may be useful for context, auditing, or traceability, but it does **not** represent current project state, constraints, product direction, or agent instructions.
>
> Current authoritative sources:
> - `docs/canon/PROJECT_BASELINE_CURRENT.md`
> - `docs/canon/BRC_TARGET_SEMANTICS.md`
> - `docs/canon/AGENT_WORKSPACE_RULES.md`
> - `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
> - `docs/canon/TECH_DEBT_BASELINE.md`
> - `docs/canon/DOCUMENT_GOVERNANCE.md`

# Direction A BTC+ETH Phase 1 Owner Review

**Date:** 2026-05-09  
**Status:** Docs-only decision brief  
**Current phase:** `Observation + Research Methodology Reset`  
**Mainline:** Direction A BTC+ETH Phase 1 only  
**Runtime impact:** None  

---

## 1. Confirmation

The current stage is `Observation + Research Methodology Reset`.

BTC+ETH Phase 1 is the only current strategy-research mainline. It is a
shadow/no-order observation design candidate only.

Not authorized:

- strategy runtime;
- experiments or parameter optimization;
- paper/testnet/live trading;
- small-live execution;
- portfolio/router or multi-strategy logic;
- SOL Phase 2;
- CPM reopening;
- short-side work;
- strategy rules, risk profile, or parameter changes.

---

## 2. Artifact Reconciliation

Current Owner-review documents:

| Artifact | Role |
|---|---|
| `docs/ops/observation-research-reset-reconciliation-snapshot-2026-05-09.md` | Roadmap, artifact, SRR-002, and untracked-doc reconciliation snapshot |
| `docs/ops/direction-a-btc-eth-phase1-observation-design-consolidation.md` | BTC+ETH Phase 1 evidence and no-order observation design consolidation |
| `docs/ops/direction-a-btc-eth-phase1-owner-review-2026-05-09.md` | Concise Owner decision brief |
| `docs/ops/project-roadmap-v2.md` | High-level SSOT; current phase and mainline confirmation |
| `docs/ops/live-safe-v1-task-board.md` | Task-board confirmation; SRR-002 baseline and no-runtime constraints |

Visible untracked docs in this worktree:

| Path | Proposed handling |
|---|---|
| `docs/ops/direction-a-btc-eth-phase1-observation-design-consolidation.md` | Accept as Group A current mainline consolidation if Owner approves |
| `docs/ops/observation-research-reset-reconciliation-snapshot-2026-05-09.md` | Accept as Group A current mainline reconciliation snapshot if Owner approves |
| `docs/ops/direction-a-btc-eth-phase1-owner-review-2026-05-09.md` | Accept as Group A concise Owner decision brief if Owner approves |

The requested 21 untracked research docs are not visible in this local
worktree. Current local count is three visible untracked docs. Owner should
confirm whether the 21-doc inventory belongs to another branch, another
machine, ignored files, or a planned submission batch.

Proposed handling:

| Set | Recommendation |
|---|---|
| 3 visible docs | Approve as Group A current mainline Owner-review package, after any requested edits |
| 21-doc batch | Owner should provide inventory before any grouping, archival, staging, or tracking |
| 21-doc current BTC+ETH consolidation items | Group A if they directly support current mainline |
| 21-doc no-order observation templates | Group B; docs-only only |
| 21-doc SOL/CPM/short-side/future diagnostics | Group C or D; preserve as future pool or archive, no promotion |
| 21-doc generated/raw artifacts | Group E; read-only preservation, never execution |

---

## 3. SRR-002 Methodology

SRR-002 is reaffirmed as the governing methodology for future strategy
research. This adoption is docs-only.

Current SRR-002 state:

- No current module satisfies SRR-002 standards.
- Direction A BTC+ETH Phase 1 lacks a validated pre-observable applicability
  boundary.
- Sparse-trend fragility remains material.
- Same-risk comparison and risk shaping are decision inputs, not promotion or
  runtime evidence.

Artifacts needing Owner review under SRR-002:

| Artifact / issue | Owner-review need |
|---|---|
| BTC+ETH no-order observation | Decide whether observation value justifies a docs-only shadow plan despite SRR-002 unmet |
| Historical small-live design wording | Decide whether to normalize older docs or keep current SSOT as override |
| A1/A3 trade-count mismatch | Decide whether to require a docs-only reconciliation before shadow metric definitions |
| A1/A3 time-in-market mismatch | Decide which exposure definition should govern observation reporting |
| BTC+ETH baseline MaxDD | Decide whether exact portfolio-level baseline MaxDD is required for no-order observation |
| MTM drawdown inclusion | Decide whether no-order observation should track MTM drawdown in addition to realized/virtual drawdown |

---

## 4. Shadow/No-Order Observation Scope

Allowed:

- record BTC and ETH 4h observation events;
- track rule-match status;
- track skipped signals and invalidated signals;
- track virtual open/flat state;
- track virtual initial risk and virtual aggregate exposure;
- track anomaly and data-quality notes;
- track fragility markers, including top-winner dependence and year-specific
  vulnerabilities.

Required fragility notes:

- unshaped BTC+ETH top-3 removal is negative;
- unshaped BTC+ETH top-5 removal is negative;
- 2023 and 2024 carry more than 100% of total BTC+ETH net;
- 2022 and 2025 are negative vulnerability years;
- P0 evidence strength is inconclusive and winner episodes are partially
  shared;
- conservative A1/A3 risk shaping improves tolerability but does not validate
  a deployable boundary.

Forbidden:

- order submission;
- exchange/API activation;
- paper/testnet/live trading;
- simulated execution as a runtime module;
- portfolio/router logic;
- SOL, CPM, short-side, or other strategy inclusion;
- parameter, strategy-rule, or risk-profile changes.

---

## 5. Recommended Owner Decisions

1. Approve or decline a docs-only BTC+ETH Phase 1 shadow/no-order observation
   design plan.
2. Approve Group A handling for the three visible untracked docs, or provide the
   missing 21-doc inventory source.
3. Confirm SRR-002 as the methodology baseline for future analysis.
4. Decide whether historical docs with `small-live design` wording should be
   normalized now, or left as history with roadmap/task-board/ADR as current
   SSOT.
5. Decide whether A1/A3 trade count, time-in-market, BTC+ETH portfolio MaxDD,
   and MTM drawdown gaps must be reconciled before any observation log template
   is finalized.
