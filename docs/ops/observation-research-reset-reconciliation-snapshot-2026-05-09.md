# Observation + Research Methodology Reset Reconciliation Snapshot

**Date:** 2026-05-09  
**Status:** Docs-only Owner review snapshot  
**Current phase:** `Observation + Research Methodology Reset`  
**Only current mainline:** Direction A BTC+ETH Phase 1 observation design  
**Runtime impact:** None  

---

## 1. Stage Confirmation

Current mainline is now labeled:

`Observation + Research Methodology Reset`

BTC+ETH Phase 1 is the only current strategy-research mainline. It is an
observation-design and methodology-consolidation mainline only.

This snapshot does not authorize:

- strategy runtime;
- experiments or parameter optimization;
- paper, testnet, live, or small-live trading;
- portfolio/router or multi-strategy combination;
- SOL Phase 2;
- CPM reopening or rescue;
- short-side work;
- runtime/profile/risk changes.

Updated docs recognizing this phase:

| File | Update |
|---|---|
| `docs/ops/project-roadmap-v2.md` | Current stage renamed and BTC+ETH Phase 1 marked as only mainline |
| `docs/ops/live-safe-v1-program.md` | Live-safe reframed as preserved safety foundation, not activation path |
| `docs/ops/live-safe-v1-task-board.md` | Added current mainline confirmation |
| `docs/adr/0001-live-safe-v1-scope.md` | Added 2026-05-09 docs-only stage note |
| `docs/ops/live-safe-v1-progress.md` | Added session progress entry |
| `docs/ops/live-safe-v1-findings.md` | Added program-local findings |

---

## 2. SRR-002 Acceptance

SRR-002 is accepted as the guiding research methodology for all future
analysis.

Acceptance is docs-only. It does not itself satisfy SRR-002 for any module and
does not authorize any experiment, backtest, parameter optimization, runtime,
or small-live operation.

SRR-002 discipline applies to these current and future artifact classes:

| Artifact class | SRR-002 treatment |
|---|---|
| Direction A BTC+ETH Phase 1 observation docs | Must preserve pre-observable boundary caveats, sparse-trend fragility, and overlap/episode concentration disclosures |
| Future shadow/no-order rehearsal design, if Owner approves | Must define no-order logging, skipped signals, virtual exposure, and stop/review criteria without execution |
| Future Level 1/2 direction inspections | Must reference SRR-002 admission and failure-closure requirements before any Level 3 request |
| Future Level 3 requests | Must satisfy SRR-002 Section 7 before execution approval |
| Applicability-boundary hypotheses | Must be pre-observable, pre-registered, cost-aware, and invalid-state aware |
| Extra-data proposals | Must name the specific OHLCV ambiguity addressed; rescue narratives remain rejected |
| Direction maps and applicability maps | Must record whether classifications satisfy or fail SRR-002 standards |

Current binding state:

- No current module satisfies SRR-002 standards.
- Direction A BTC+ETH Phase 1 remains non-runtime and pause-fragile.
- Small-live readiness remains unmet.

---

## 3. Roadmap Reconciliation Snapshot

### 3.1 Commit-Log State

Recent commit log indicates a docs-heavy research consolidation sequence after
live-safe persistence work:

| Commit | Read |
|---|---|
| `12f261e` | Direction A capital-efficiency comparison and 1D spot robustness diagnostic |
| `db96d74` | Direction A cross-asset diagnostics |
| `c397ed8` | CPM-1 boundary attribution research archived |
| `fd07560` | Strategy research methodology baseline updated |
| `04938b5` | Live-safe task board status updated |
| `6a50708` | Strategy research reset and applicability maps |
| `d11b7ad` / `5c01625` | LS-003d reconciliation read model persistence tests and implementation |

Interpretation: the repo has moved from execution-hardening commits into
strategy-research evidence consolidation. The current docs now need to prevent
older small-live wording from being read as activation permission.

### 3.1a ADR State

Current ADR inventory:

| ADR | Current relevance |
|---|---|
| `0001-live-safe-v1-scope.md` | Updated with 2026-05-09 docs-only stage note; Live-safe remains safety foundation, not activation path |
| `0002-decision-trace-backbone-v0.md` | Historical execution-safety foundation; no current observation execution implication |
| `0003-post-merge-hardening-live-safe-v0.md` | Live-safe hardening backlog context only |
| `0004-daily-risk-limits-runtime-closure-v0.md` | Runtime-risk foundation context only; no profile/risk change authorized |
| `0005-reconciliation-read-model-v0.md` | Reconciliation read-model context only |
| `0006-runtime-periodic-reconciliation-report-only-loop.md` | Report-only runtime reconciliation context; no observation runtime authorization |
| `0007-reconciliation-read-model-persistence.md` | Persistence context for live-safe read models; no strategy implication |

ADR interpretation: no ADR authorizes Direction A runtime, paper/testnet/live
trading, small-live execution, strategy/risk/parameter changes,
portfolio/router work, SOL Phase 2, CPM reopening, or short-side work.

### 3.2 Mainline Consistency

| Topic | Current reconciled state |
|---|---|
| Phase name | `Observation + Research Methodology Reset` |
| Mainline strategy object | Direction A BTC+ETH Phase 1 only |
| SOL | Phase 2 optional/future only; not current mainline |
| CPM | Paused; no reopening or rescue |
| Short-side | Rejected/closed for current short-side breakdown evidence; no current work |
| Portfolio/router | Forbidden under current stage |
| Live-safe | Preserved safety foundation; does not imply activation |
| Runtime | No strategy runtime, paper/testnet/live, or small-live execution |

### 3.3 Gaps And Inconsistencies

| ID | Gap / inconsistency | Owner relevance | Proposed handling |
|---|---|---|---|
| R-001 | Some older docs still use phrases like `small-live design`, `small-live candidate`, or `full-auto small-live candidate safety` from earlier phase context | Agents may over-read docs as execution path | Treat updated roadmap/task-board/ADR as current SSOT; avoid bulk rewriting historical docs unless Owner requests archival normalization |
| R-002 | User request references 21 untracked research docs, but local git shows three visible untracked docs under `docs/ops/` | Submission/grouping decision depends on correct inventory | Owner should confirm whether 21 refers to another machine, ignored files, prior branch, or a desired future batch |
| R-003 | Existing untracked consolidation doc identifies A1/A3 trade-count and time-in-market mismatches | Rehearsal metrics cannot be finalized until definitions are reconciled | Keep as Owner-review reconciliation gap; no recomputation authorized |
| R-004 | Reports include generated research artifacts, adapters, CSV/JSONL outputs, and old run artifacts | Artifact pool is broad and mixed between evidence, code-like adapters, and generated outputs | Preserve as read-only evidence pool; do not execute adapters or rerun reports |
| R-005 | Live-safe task board still has implementation TODOs | Could be misread as next active implementation | Keep as backlog; current task is docs-only consolidation and observation logging |
| R-006 | Direction A P2 text mentions `ELIGIBLE_FOR_SMALL_LIVE_DESIGN_PLAN` | Could be mistaken for approval | Interpret as historical docs-only eligibility for design discussion, superseded by current no-execution constraints |

### 3.4 Duplicate / Overlapping Artifacts

| Area | Overlap | Recommendation |
|---|---|---|
| Direction A observation | Observation value memo, Phase 1 aggregate diagnostic, small-live design plan, risk frontier, same-risk comparison, untracked consolidation doc | Keep all. Treat the untracked consolidation doc as the Owner-facing summary/index once approved |
| CPM-1 | Scope note, OOS reports, failure classification, boundary attribution chain, closeout | Keep as archived evidence; do not reopen |
| Research methodology | SRR-001, SRR-002, SMA-001, SRD-001/SRD-002 | SRR-002 is current methodology baseline; older docs remain evidence history |
| Live-safe | Program, task board, findings, progress, ADRs | Keep as execution-safety foundation backlog; not current activation path |

---

## 4. Untracked Research Documents

Local commands run docs-only:

- `git status --short`
- `git ls-files --others --exclude-standard docs`
- `git status --short --ignored docs`

Visible untracked docs in this worktree:

| Path | Proposed classification | Proposed submission group |
|---|---|---|
| `docs/ops/direction-a-btc-eth-phase1-observation-design-consolidation.md` | Docs-only / BTC+ETH Phase 1 observation candidate / Owner-review summary | Group A: current mainline consolidation |
| `docs/ops/observation-research-reset-reconciliation-snapshot-2026-05-09.md` | Docs-only / reconciliation snapshot / Owner-review summary | Group A: current mainline consolidation |
| `docs/ops/direction-a-btc-eth-phase1-owner-review-2026-05-09.md` | Docs-only / concise Owner decision brief | Group A: current mainline consolidation |

Ignored visible docs artifact:

| Path | Proposed classification |
|---|---|
| `docs/.DS_Store` | Local OS metadata; not a research doc |

The requested "21 untracked research docs" were not present in this local
worktree state. The current local visible count is three docs, one of which is
this snapshot and one of which is the concise Owner decision brief. Do not group, stage, move, or submit a 21-doc batch until the
Owner confirms the missing inventory source.

Proposed grouping scheme if the full 21-doc set appears later:

| Group | Contents | Handling |
|---|---|---|
| A. Current mainline consolidation | BTC+ETH Phase 1 observation summaries, reconciliation notes, SRR-002 acceptance notes | Owner-review priority |
| B. Observation candidates | No-order logging specs, skipped-signal templates, virtual exposure review docs | Docs-only; no runtime |
| C. Future research pool | Direction A future diagnostics, benchmark notes, non-mainline hypotheses | Preserve; no execution |
| D. Archived/closed evidence | CPM, SOL Phase 2, short-side, rejected or paused direction docs | Preserve as historical evidence; no reopening |
| E. Generated/raw artifacts | JSON/CSV/JSONL summaries, adapter files, report outputs | Preserve read-only; never execute as part of submission |

Owner grouping/archival decision frame:

| Set | Proposed action |
|---|---|
| 3 visible docs in current worktree | Approve as Group A current mainline Owner-review package, or request edits before tracking |
| Referenced 21-doc batch | Do not infer, stage, or archive until Owner provides the actual inventory source |
| Any 21-doc items that are current BTC+ETH Phase 1 consolidation | Group A, after Owner review |
| Any 21-doc items that are no-order observation templates | Group B, docs-only; no runtime |
| Any 21-doc items involving SOL, CPM, short-side, variants, or extra diagnostics | Group C or D by status; preserve but do not promote |
| Generated/raw report artifacts in the 21-doc batch | Group E; preserve read-only and do not execute |

---

## 5. SRR-002 Compliance / Owner-Review Flags

| Artifact / area | Current read | SRR-002 state | Owner-review flag |
|---|---|---|---|
| Direction A BTC+ETH Phase 1 consolidation | Positive sparse trend evidence, smart-beta timing, non-runtime | Does not satisfy pre-observable applicability-boundary standard | Owner must decide whether observation value justifies no-order shadow planning despite SRR-002 unmet |
| Direction A risk frontier | Conservative A1/A3 improves drawdown and top-5 residual | Risk shaping does not remove shared-episode dependence | Treat only as observation envelope; no risk-module or runtime interpretation |
| Same-risk comparison | Supports capital-efficiency case versus benchmarks at matched MaxDD | Benchmark comparison is not a validation boundary | Keep as decision input, not promotion evidence |
| Historical small-live design plan | Contains sizing/exposure references and older rehearsal language | Superseded by current no-paper/no-execution constraint | Read only as historical sizing reference until normalized |
| Reports under `reports/direction-a-*` | Existing generated evidence artifacts | May be referenced read-only | Do not execute adapters, rerun scripts, or recompute outputs under this task |
| SOL evidence | Strengthens cross-asset mechanism history | Not current mainline | Exclude from Phase 1 observation planning |
| CPM / short-side artifacts | Archived, paused, rejected, or future pool | Not current mainline | Preserve only; do not reopen |

---

## 6. Mac Mini Observation Log Snapshot

This section defines the docs-only logging frame for BTC+ETH Phase 1
observation. No runtime, order placement, paper/testnet/live trading, or
exchange execution is authorized.

### 6.1 Observation Scope

| Dimension | Value |
|---|---|
| Assets | BTC + ETH only |
| Strategy object | Direction A Phase 1 observation design |
| Mode | Docs-only / no-order observation |
| SOL | Excluded |
| CPM | Excluded |
| Short-side | Excluded |
| Portfolio/router | Excluded |
| Execution | Forbidden |

### 6.2 Log Template

Future observation entries should use this shape:

| Field | Meaning |
|---|---|
| `timestamp_local` | Mac mini local timestamp |
| `timestamp_utc` | UTC timestamp |
| `asset` | BTC or ETH |
| `bar_timeframe` | Expected 4h observation bar |
| `environment_state` | Data available / data delayed / process paused / manual review |
| `signal_state` | No signal / candidate signal / skipped signal / invalidated signal |
| `skip_reason` | Missing data, stale bar, duplicate bar, manual pause, rule mismatch, other |
| `virtual_position_state` | Flat / virtual open / virtual exit pending |
| `virtual_initial_risk` | Hypothetical initial risk only; no order |
| `virtual_total_open_risk` | Hypothetical aggregate risk only; no order |
| `anomaly` | None or anomaly code |
| `notes` | Short evidence note |

### 6.3 Current Snapshot

| Category | Current docs-only state |
|---|---|
| Environment data logging | Template defined; no new Mac mini data ingested by this pass |
| Signal logging | Template defined; no signal scan or strategy runtime was run |
| Skipped signals | No new skipped-signal records created by this pass |
| Anomalies | No new anomalies observed by this pass |
| Virtual risk exposure | No virtual exposure computed by this pass |

This is intentionally a zero-execution snapshot. The next valid action, if the
Owner approves, is to fill this log manually or through a separately approved
no-order observation process that cannot place, simulate, or route orders.

---

## 7. Owner Review Questions

1. Should `docs/ops/direction-a-btc-eth-phase1-observation-design-consolidation.md` be accepted as Group A current mainline consolidation?
2. Where are the referenced 21 untracked research docs, or should this repo state supersede that count?
3. Should older historical docs that mention small-live design be normalized, or should the updated roadmap/task-board/ADR remain the SSOT without broad historical rewrites?
4. Should a separate docs-only Mac mini no-order observation log file be created, or should observation entries live in this snapshot family?

---

## 8. Done State

- Current phase naming confirmed.
- BTC+ETH Phase 1 marked as only current mainline in active SSOT docs.
- SRR-002 accepted as docs-only methodology baseline.
- Reconciliation gaps and artifact overlaps listed for Owner review.
- Visible untracked research-doc inventory recorded.
- Mac mini observation logging frame defined without execution.
