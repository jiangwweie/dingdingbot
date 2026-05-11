# DIRA-HG-002 — Direction A Paper Admission & Human-Gated Process Spec

## 0. Boundary

This is a docs-only planning spec.

- No runtime control is authorized.
- No strategy change is authorized.
- No Direction A entry, exit, stop, sizing, or risk parameter change is authorized.
- No paper, testnet, live, small-live, or runtime activation is authorized.
- No LLM implementation is authorized.
- No automated decision-making is authorized.
- No backtest, adapter, or experiment was run for this spec.
- No Claude task card is created.
- No claim is made that Direction A is validated.

The purpose is to define what paper admission would look like for Direction A under human-gated process rehearsal, and to specify prerequisites, failure modes, and boundaries before any future paper-admission decision by the Owner.

## 1. What Is the Paper Object?

**Status: Unresolved.**

Direction A has two possible paper objects:

| Candidate | Description | Evidence readiness |
|---|---|---|
| **Baseline Direction A** | Donchian20 4h breakout, EMA60 lifecycle exit, fixed notional, no human gate. The exact same mechanism as the backtest/historical artifacts. | Mechanism is frozen. Evidence is `POSITIVE_CROSS_ASSET_SPARSE_TREND_EVIDENCE / PAUSE_FRAGILE / NON_RUNTIME`. No pre-observable applicability boundary. No runtime candidate status. |
| **Human-Gated Direction A Process** | Same Direction A signal mechanism, but new entries are only allowed when the Owner has completed the ON decision checklist (DIRA-HG-001) and classified the state as `ON_ALLOWED` or `ON_ALLOWED_SMALL`. Existing-position lifecycle (EMA60 exit) runs unchanged. | No process rehearsal logs exist yet. Human-gating plausibility is `WEAK`. The decision framework is a draft (DIRA-HG-001). No evidence that the Owner's ON/OFF judgment improves or preserves access to sparse payoff tails. |

The paper object is **not resolved** because:

- A1/A3 metric conflicts remain (Section 3).
- No manual no-order rehearsal logs exist to demonstrate that the Owner can execute the ON/OFF process with discipline.
- The choice between baseline and human-gated process is itself an Owner decision that requires prior evidence.

If the Owner chooses baseline Direction A as the paper object, then human gating is bypassed and the paper process tests whether baseline Direction A is tolerable to run. If the Owner chooses human-gated Direction A, then the paper process simultaneously tests Direction A execution and the Owner's decision discipline.

**This spec defines the framework for both options. The Owner must choose before paper admission.**

## 2. Paper Admission Prerequisites

No paper trading is approved by this spec. Before any future paper-admission note can even be drafted, ALL of the following must be satisfied:

| # | Prerequisite | Status |
|---|---|---|
| 1 | DIRA-HG-001 reviewed and accepted by Owner. | Pending Owner review. |
| 2 | Manual no-order decision logs created for at least 2-4 weeks across different market contexts. | Not started. |
| 3 | Decision logs created before decisions, not after outcomes. | Not started. |
| 4 | At least several ON/OFF/WAIT reviews completed across different market contexts. | Not started. |
| 5 | A1/A3 metric conflict resolved (Section 3). | Not resolved. |
| 6 | Paper object chosen explicitly by Owner: baseline Direction A or human-gated Direction A process. | Not chosen. |
| 7 | Decision log template accepted by Owner. | Template exists in DIRA-HG-001 Section 6; acceptance pending. |
| 8 | Kill / pause / review conditions drafted and accepted (Section 7 of this spec). | Drafted below. |
| 9 | Clear distinction maintained between process rehearsal, paper trading, testnet trading, and live trading. | Defined in Section 9 of this spec. |
| 10 | Owner accepts that human gating remains `WEAK` unless logged decision process demonstrates useful discipline. | Not yet accepted. |
| 11 | Paper-mode configuration, persistence, and isolation design approved by Owner (separate from this spec). | Not designed. |
| 12 | Direction A paper object does NOT modify strategy parameters, entry/exit rules, stop logic, or risk profile compared to the frozen backtest baseline. | Structural requirement. |

If any prerequisite is not met, the correct state remains docs-only review or no-order process rehearsal, not paper admission.

## 3. A1/A3 Conflicts That Remain

The A1/A3 risk-shaped Direction A diagnostics introduced metric inconsistencies that are unresolved:

| Conflict | Description | Impact |
|---|---|---|
| **Trade count** | Phase 1 aggregate docs show 490 BTC+ETH trades; risk-shape diagnostic JSON shows 373. The discrepancy is unexplained. | Paper-mode trade-level metrics may be unreliable if the baseline trade count is not fixed. |
| **Time-in-market** | Phase 1 docs show ~38% time-in-market; risk-shape frontier shows 52.26%. Different derivation methods. | Paper-mode exposure and capital-efficiency metrics depend on which definition is used. |
| **Metric definitions** | Gross PnL, net PnL, PF, payoff ratio, and drawdown definitions vary across docs, diagnostic reports, and frozen-baseline summaries. | Paper-mode performance evaluation needs a single ground-truth metric definition set. |
| **Evidence source consistency** | Some metrics come from frozen-baseline trades.jsonl, others from risk-shape diagnostic, others from summary.json. The chain of custody is unclear. | Paper-mode results must be traceable to a single authoritative source. |

**Required resolution before paper admission:** The Owner must choose one canonical metric definition set and one canonical trade-artifact source. Until then, paper-mode performance numbers are not comparable to historical evidence.

## 4. How Owner Classification Affects Paper Process

The Owner classifications from DIRA-HG-001 map to paper-process behavior as follows:

| Classification | Paper-process meaning | Action on new entries | Action on existing positions |
|---|---|---|---|
| `ON_ALLOWED` | Paper allows new Direction A entries per frozen rules. | Normal entry. | Lifecycle (EMA60 exit) continues unchanged. |
| `ON_ALLOWED_SMALL` | Paper allows new Direction A entries, but this is a label only; it is NOT sizing approval. In paper mode with fixed notional, `ON_ALLOWED_SMALL` behaves identically to `ON_ALLOWED` unless the Owner separately authorizes a paper-mode sizing variant. | Normal entry (no sizing change unless separately authorized). | Lifecycle continues unchanged. |
| `WAIT` | No new entries until next scheduled review. | Denied. | Lifecycle continues unchanged. |
| `DO_NOT_TURN_ON` | No new entries. Broad hostile regime or unresolved risk. | Denied. | Lifecycle continues unchanged. |
| `KEEP_ON` | Normal paper-mode behavior continues. | Normal entry. | Lifecycle continues unchanged. |
| `REDUCE` | Label only; no sizing change unless separately authorized. Behaves as `KEEP_ON` in paper mode with fixed notional. | Normal entry (no sizing change unless separately authorized). | Lifecycle continues unchanged. |
| `PAUSE_NEW_ENTRIES` | No new Direction A entries until a defined review condition is met. | Denied. | Lifecycle continues unchanged. |
| `TURN_OFF` | No new Direction A entries. Process inactive until Owner re-activates. | Denied. | Lifecycle continues unchanged. |

**Critical invariant:** Owner classification affects ONLY new-entry permission. It never modifies exit behavior, stop logic, sizing, or any existing-position lifecycle rule.

## 5. Does Human Gate Control Only New Entries?

**Yes.**

The human gate is a new-entry permission layer, period. It answers one question: "Is Direction A allowed to take new entries right now?"

It does NOT:

- Control exits (EMA60 lifecycle exit is unconditional and untouched).
- Control stop-losses (initial stop is frozen and untouched).
- Control position sizing (fixed notional unless a separate sizing spec is approved).
- Control partial exits (TP1, TP2, trailing stops are untouched).
- Allow the Owner to manually close positions (no manual intervention in lifecycle).
- Allow the Owner to override signal direction or timing.

If the Owner wants to turn Direction A OFF after already being in a position, the existing position continues through its normal EMA60 lifecycle exit. The OFF decision only prevents new entries from appearing.

This asymmetry is intentional. Exiting existing positions based on the same emotional state that triggered OFF would amplify the failure mode of loss-panic → premature exit → missed sparse winner.

## 6. Are Existing Positions Still Managed by Unchanged EMA60 Lifecycle Exit?

**Yes.**

All existing Direction A positions follow the frozen exit rule: `ema60_close_break_next_open`. This rule is unchanged by human gating.

Rationale:

- The EMA60 exit is classified as `PAYOFF_ENGINE` (DIRA-FORENSIC-001). It preserves sparse multi-week payoff tails.
- NSC-018 / E-A showed that naive early-exit overlays damaged total net, PF, drawdown, and top-N fragility.
- Human gating must not become a backdoor exit override. If the Owner wants to change the exit, that is a separate strategy-change decision with its own evidence requirements.

In paper mode, if the Owner classifies as `TURN_OFF` or `PAUSE_NEW_ENTRIES`, the existing position continues to trail via EMA60. The Owner may observe the position but must not intervene to close it outside the frozen exit rule.

## 7. Paper Pause / Kill / Review Conditions

### Pause conditions (paper entries halted, existing positions continue):

| # | Condition | Trigger |
|---|---|---|
| P1 | Owner classifies `PAUSE_NEW_ENTRIES` or `TURN_OFF`. | Owner decision via checklist. |
| P2 | Three consecutive paper-mode failed breakouts (stopped out within 48 hours of entry). | Automatic observation flag; Owner decides whether to continue or pause. |
| P3 | Paper-mode cumulative realized loss exceeds a threshold to be defined by Owner before paper admission. | Automatic observation flag. |
| P4 | Owner fails to produce a decision log for 7+ consecutive days while paper is active. | Automatic flag; entries paused until next logged decision. |
| P5 | External event: major macro shock, exchange incident, or regulatory event. | Owner decision to pause or continue. |

### Kill conditions (paper mode stops entirely):

| # | Condition | Trigger |
|---|---|---|
| K1 | Paper-mode cumulative realized loss exceeds Owner-defined kill threshold. | Automatic observation; Owner confirms kill. |
| K2 | Owner acknowledges paper mode is not producing useful decision discipline after 4+ weeks. | Owner decision. |
| K3 | A decision-process failure (Section 8 of DIRA-HG-001) is identified and not corrected. | Owner decision. |
| K4 | Direction A frozen rules are changed during paper mode (a violation of this spec). | Automatic kill; evidence from this paper period is discarded. |

### Review conditions (periodic reassessment):

| # | Condition | Frequency |
|---|---|---|
| R1 | Full decision-log audit: ON/OFF classification accuracy vs subsequent market behavior. | Monthly. |
| R2 | Paper-mode PnL vs baseline Direction A historical PnL for same period. | Monthly. |
| R3 | Decision-process discipline check: were all decisions pre-logged, or were there overrides? | Monthly. |
| R4 | Re-entry accuracy: after `TURN_OFF` or `PAUSE_NEW_ENTRIES`, was the re-entry timely or was the sparse winner missed? | After each re-entry event. |

## 8. Paper-Process Failure Modes

Paper-process failure occurs when the Owner's manual decision process degrades the quality of Direction A participation, or when the paper-mode boundaries are violated.

| # | Failure mode | Description | Severity |
|---|---|---|---|
| F1 | Emotional shutdown after losses | Owner turns OFF or PAUSE immediately after a loss cluster, not because market evidence changed, but because of discomfort. This is the highest-probability failure mode identified in DIRA-FORENSIC-001. | HIGH |
| F2 | FOMO ON after large move | Owner turns ON after a large bullish candle or multi-day trend leg, driven by fear of missing the move rather than by the ON checklist. | HIGH |
| F3 | Missing re-entry after OFF | Owner turns OFF with no concrete re-entry condition, then fails to re-enable before the next sparse multi-week winner. This is the tail-kill failure mode. | HIGH |
| F4 | Undocumented override | Owner changes a decision without writing a log entry, or overrides the checklist without recorded rationale. This destroys the audit trail. | HIGH |
| F5 | LLM overreach | The LLM briefing is treated as the decision rather than as input. The Owner stops writing independent judgment. | MODERATE |
| F6 | Treating paper as validation too early | After a few profitable weeks of paper, the Owner concludes Direction A is validated and moves toward live or small-live without sufficient process evidence. Paper-mode profit does not equal strategy validation. | HIGH |
| F7 | Changing Direction A rules during paper | Owner modifies entry conditions, exit logic, stop levels, or risk parameters while paper is running, then attributes paper results to the original Direction A. This invalidates any comparison to historical evidence. | BLOCKER (for evidence integrity) |
| F8 | Asymmetric review discipline | Owner reviews decisions after losses but not after wins, creating hindsight bias and inaccurate process assessment. | MODERATE |
| F9 | Classification drift | The meaning of `ON_ALLOWED_SMALL` or `REDUCE` silently evolves into actual sizing behavior without a separate Owner-approved paper/risk specification. | MODERATE |

### Paper-process failure severity mapping:

| Severity | Treatment |
|---|---|
| BLOCKER | Paper evidence from this period is discarded. Process must restart. |
| HIGH | Paper mode is paused. Owner must identify root cause and correct before resuming. |
| MODERATE | Logged as a finding. Reviewed at next periodic review (R1). |
| LOW | Noted for awareness. No immediate action required. |

## 9. What Paper Does NOT Authorize

Paper trading, if eventually approved by the Owner after all prerequisites are met, does NOT authorize:

| # | Non-authorization | Explanation |
|---|---|---|
| 1 | Live trading | Paper is not live. Paper results do not justify live activation. |
| 2 | Small-live execution | Paper is not small-live. Paper results do not justify small-live execution. |
| 3 | Testnet unless separately approved | Paper mode and testnet mode are separate decisions with separate governance. |
| 4 | Strategy validation claim | Paper-mode profit does not prove Direction A is validated. The sparse-trend fragility, top-winner dependence, and lack of pre-observable applicability boundary remain unresolved. |
| 5 | LLM automation | Paper mode does not authorize LLM-driven ON/OFF decisions, order submission, or any automated runtime control. |
| 6 | Entry/exit/parameter/risk-profile change | Direction A frozen rules remain unchanged during paper. |
| 7 | Parameter sweep or optimization | No parameter changes are tested during paper mode. |
| 8 | Paper results as live-ready evidence | Paper results may inform future Owner decisions, but they are not a live-readiness gate. |
| 9 | Reopening CPM-1 or promoting other directions | Paper mode is scoped to Direction A only. |
| 10 | Portfolio or router work | Paper mode does not introduce multi-strategy, portfolio allocation, or regime routing. |

## 10. Risk Triage

| Item | Severity | Treatment |
|---|---|---|
| Paper object unresolved | HIGH | Owner must choose baseline Direction A or human-gated Direction A before paper admission. Cannot proceed without this choice. |
| A1/A3 metric conflict unresolved | HIGH | Canonical metric set and trade-artifact source must be chosen before paper admission. |
| No manual rehearsal logs exist | HIGH | At least 2-4 weeks of no-order decision logs are required before paper admission. |
| Direction A evidence strength remains WEAK | MODERATE | Paper mode does not resolve Direction A fragility; it only tests the Owner's decision process. |
| Human-gating plausibility remains WEAK | MODERATE | The ON/OFF decision framework may not improve access to sparse payoff tails. Paper mode is the test for this. |
| Top-winner dependence | MODERATE | Paper mode cannot remove top-winner dependence. This is a structural property of Direction A. |
| Emotional shutdown (F1) and FOMO ON (F2) | MODERATE | Mitigated by checklists (DIRA-HG-001 Sections 3-4), devil's-advocate LLM briefing, and review discipline (R1-R4). |
| Re-entry miss after OFF (F3) | MODERATE | Mitigated by requiring explicit re-entry conditions before any OFF/PAUSE decision. |
| Rule mutation during paper (F7) | LOW (with governance) | Mitigated by this spec's explicit prohibition and kill condition K4. |
| Paper-mode configuration/persistence | MODERATE | Not yet designed. Requires a separate design note before paper admission. |
| LLM overreach (F5) | LOW (with governance) | Mitigated by DIRA-HG-001 Sections 5 and the explicit prohibition in this spec Section 9. |

No `BLOCKER` is identified for this spec as a docs-only artifact.

DIRA-HG-002 is sufficient for Owner review.

## 11. Minimum Next Step

1. Owner reviews DIRA-HG-002 as a docs-only planning spec.
2. Owner resolves paper object choice: baseline Direction A or human-gated Direction A process.
3. Owner resolves A1/A3 metric conflict by choosing canonical metric set and trade-artifact source.
4. Owner begins no-order manual rehearsal (DIRA-HG-001 Section 6 decision log template).
5. After 2-4 weeks of rehearsal logs, Owner re-evaluates whether paper admission is warranted.
6. If paper admission is warranted, a separate paper-mode configuration/isolation design note is drafted.

## 12. What Not To Do

- Do not create a Claude task card.
- Do not implement runtime paper-mode logic.
- Do not implement LLM automation.
- Do not run backtests, adapters, parameter sweeps, or mechanical filter searches.
- Do not reopen CPM-1.
- Do not rewrite Direction A exit logic.
- Do not change Direction A entry, stop, sizing, or risk parameters.
- Do not treat this spec as paper admission approval.
- Do not convert `ON_ALLOWED_SMALL` or `REDUCE` into actual sizing without a separate Owner-approved paper/risk specification.
- Do not use paper-mode results to claim Direction A validation.
- Do not skip prerequisites because the spec looks comprehensive.
