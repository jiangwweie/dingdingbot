---
title: STRATEGY_EXPERIMENT_EVALUATION_CONTRACT
status: CURRENT
last_verified: 2026-08-17
---

# Strategy Experiment Evaluation Contract

## Objective

Evaluate whether a StrategyGroup is worth bounded real-capital experimentation,
not whether it can promise a fixed return or smooth equity curve.

The portfolio hypothesis is asymmetric: repeated bounded losses are acceptable
only when the strategy preserves a credible path for less frequent winners to
contribute materially more than one initial unit of risk.

## Required Evaluation

| Dimension | Required answer |
| --- | --- |
| Edge thesis | What market behavior creates the opportunity |
| Event identity | Which versioned event means the opportunity exists |
| Regime fit | Where the event is expected to work or fail |
| Side and instrument | Explicit supported scope |
| Downside envelope | Stop, invalidation, path, liquidation, fee, and funding risk |
| Right-tail path | How the strategy preserves materially larger winners |
| Evidence | Replay, paper, observation, or real outcome evidence with source boundary |
| Kill rule | Evidence that ends further experimentation |

High-return and leverage numbers are scenarios and aspiration anchors, not
automatic authorization or rejection. Runtime authority still comes from
current Owner policy, current facts, an immutable Ticket, and the official
kernel chain.

## Required Economic Evidence

| Measure | Required interpretation |
| --- | --- |
| Net R | Realized PnL after fee, funding, and slippage divided by frozen initial stop risk |
| Payoff distribution | Win rate, median loss, median win, large-winner frequency, and concentration of gains |
| MFE and MAE | Maximum favorable and adverse excursion measured on one explicit price and fee basis |
| Runner contribution | Net R contributed after TP1 or the strategy's first risk-reduction event |
| Execution cost | Fee, funding, spread, slippage, and rejected or flattened execution cost |
| Tail dependence | How much total result depends on the largest winners and whether that dependence matches the thesis |
| Survival evidence | Observation count, losing streak, drawdown, incident count, and remaining experiment-capital capacity |
| Owner Regime attribution | When an effective Owner Regime Gate exists, separate Gate-inside realized Tickets, Gate-excluded opportunity evidence, and explicitly hypothetical counterfactual estimates |

No single metric establishes an edge. Review must preserve per-Ticket facts and
show both the aggregate result and the contribution of tail outcomes. Missing
funding or execution evidence remains explicit rather than being treated as
zero.

## Offline Attribution And Prospective Research

Research outputs are display-only evidence; they do not replace canonical
Review economics, create a second ledger, or authorize runtime changes.

- Freeze the source code commit, database snapshot identity/time, analysis
  revision, inclusion rules and effective Review revision. A moving branch
  name alone is insufficient provenance.
- Attribute Tickets by StrategyGroup/version, position side, frozen
  ExitProfile, Policy and birth Selection authority/mode. Missing lineage stays
  unknown; current controls must not retrospectively classify old Tickets.
- Report all eligible Tickets, economically complete Tickets and missing-data
  counts by group. Complete-case results are a subset, not total performance.
  Missing funding/fills are never zero-filled. Use frozen initial stop risk as
  the Net R denominator and disclose unavailable denominators.
- Actual execution prices already reflect realized execution slippage. Report
  benchmark slippage separately; do not deduct it twice from realized PnL.
- TP1 quantity sensitivity at the historical Runner exit price is a conditional
  estimate, not replay or a new strategy's realized return. Disclose changed
  fees/funding, path dependence and execution assumptions that cannot be proved.
- Report largest-winner concentration and leave-largest-winners-out sensitivity.
  Tail dependence alone does not invalidate a right-tail hypothesis; prospective
  evidence, bounded downside and a plausible repeatable mechanism still matter.
- Compare rejected Signal-owned Shadow Outcomes separately by Policy and exact
  Signal identity. Excursion is opportunity-path evidence, not executable profit.
  Static/Dynamic cohort comparisons are descriptive unless a prospective
  comparison design addresses regime, time and version confounding.
- Freeze prospective metrics, observation windows and stop rules before tuning.
  An elapsed window may end in insufficient evidence. Closed candles that touch
  both stop and profit thresholds cannot establish intrabar first-touch order.

Additional price-path persistence requires its own bounded design and engineering
acceptance. It must reuse the kernel's identities, preserve read-only research
semantics, bound query/storage cost and never create execution authority. An
offline research delivery does not close deferred runtime or projector gates.

## Exit And Closure Attribution

Lifecycle completeness and exit attribution are separate facts. A Ticket may
be terminal, reconciled, settled, and economically complete while its Owner
projection still lacks a classified exit mechanism. The product must not label
that condition as a generic technical failure.

Use exact persisted evidence in this precedence order:

1. an explicit `ExitRequested.reason` for strategy exit, Owner controlled
   flatten, deployment drain, or another commanded exit;
2. an exit fill attributed to the Ticket's `initial_stop` command;
3. a `TakeProfitFilled` event followed by an exit fill attributed to the active
   `replace_protection` command for the Runner;
4. an exit fill attributed to the Ticket's `take_profit` command;
5. external flatness without attributable fill evidence, reported explicitly
   as `external_flat_reason_unavailable`.

K-line shape, candle high/low, or approximate price proximity cannot invent an
exit reason. Unknown codes remain visible for audit and use an Owner-readable
"未归类退出原因" label rather than "技术原因待查看". Programmatic review and
strategy/version statistics consume the same canonical attribution so the
list, Ticket detail, Review, and aggregate strategy page cannot disagree.

## Signal-Owned Observation Evidence

One Signal may own at most one read-only `Shadow Outcome`. An eligible
portfolio-rejected Signal uses `fixed_horizon_excursion_v1` and preserves its
immutable rejected AdmissionDecision. An Entry-disabled TradFi strategy
observation uses `sor_path_observation_v1` directly from the Signal and has no
AdmissionDecision. Both freeze explicit price and time facts and record bounded
closed-candle path evidence.

The independently enabled `generic_signal_path_v1` observes valid CPM, MPG, MI,
BRF2 and SOR-1H Signals on their frozen hourly Signal-close price and original
Registry stop. It covers the Registry's 24-bar horizon, stores full-horizon
MFE/MAE, +1R/+3R/+5R and initial-stop first-touch bars, and labels same-bar order
as ambiguous. Stop-then-rally evidence is retained as opportunity evidence.
One Signal still owns at most one Outcome, whether admitted or rejected. Existing
older Outcomes are retained in their original version and price basis.

The PostgreSQL research switch starts disabled with zero quota. Enabled sampling
uses a persisted UTC-day limit and strategy/hour coverage counts; skipped samples
must remain disclosed. Retries are bounded and persisted. Price-path R0, Ticket
frozen stop risk and effective Review economics are distinct fields. Readonly
association follows the exact AdmissionDecision/Ticket and effective Review
pointer; absent execution evidence stays unknown. Owner Regime attribution is
outside this MVP.

Optional research at Signal creation and Admission rejection runs within a
PostgreSQL savepoint. A recoverable builder or SQL failure rolls back all research
writes and quota changes, then verifies that the outer trading transaction is
usable before continuing. Research SQL has a 100ms lock wait and a 500ms per
statement limit; the outer settings are restored. Connection loss or failed
rollback remains an outer transaction failure and cannot be treated as success.
`research_collection_failed` logs identify each missing Signal, stage, error type
and SQLSTATE without logging SQL values. These failures are not budget skips.
The readonly collection report labels the population `quota_limited_prospective`
and explicitly discloses `skipped_budget`; it must not represent its samples as
the complete Signal population. Disabled research retains successful legacy
rejection sampling and creates no generic samples or quota counts.

This evidence is not a fill, not simulated PnL, not realized PnL, and not a
fee, funding, or real slippage estimate. It never creates CapacityClaim,
Reservation, Ticket, Exchange Command, or venue mutation. If real Entry is
later authorized, the formal Ticket lifecycle remains the only source of
execution economics and may coexist with the Signal-owned observation.

## Owner Regime Attribution Boundary

An Owner Regime Gate is a prospective scope or risk-budget restriction on new
ENTRY, not a source of strategy signals or a substitute execution path. When that product
capability is active, its Journal freezes the effective direction and
StrategyGroup range before an AdmissionDecision is made. Existing Tickets keep
their frozen lifecycle and are not reclassified when the Gate later changes.

Performance review must keep the following evidence classes separate:

| Evidence class | Permitted conclusion | Forbidden conclusion |
| --- | --- | --- |
| Natural Ticket admitted inside the Gate | Actual net economics and actual strategy/Owner-scope outcome | That the same result would occur under another Gate |
| Gate-excluded Signal-owned observation | Bounded market-path evidence such as MFE/MAE | Realized PnL, exact fees/funding/slippage, or a simulated fill |
| Counterfactual model | A conditional estimate with frozen disclosed assumptions | Historical fact or Owner alpha proved by an unfilled opportunity |

No Gate is equivalent to no additional scope overlay; it is not evidence that
the Owner selected `BOTH`. Review must label absent Gate, effective Gate and
expired Gate states explicitly. Owner attribution never changes Review
economics, Exit Attribution, StrategyVersion identity or the underlying
immutable Ticket lineage.

The approved, not-yet-implemented Owner Directional Risk V1 baseline is in the
[design record](../superpowers/specs/2026-10-25-owner-directional-risk-v1-design.md).
Its exact numerical matrix belongs only to the experiment profile. A risk
overlay may reduce a candidate's size as well as reject it; attribution must
record the effective rule/choice, relevant usage, actual admission outcome and
dispatch authority without rewriting the original Decision or frozen Ticket.
A first-blocker label does not prove that removing the overlay would result
in an executable trade. Minimal authority/admission evidence is mandatory;
optional market-path samples retain their existing quota and failure disclosure.

The first eight-week review checks operation, coverage and opportunity costs,
not statistical sufficiency or guaranteed profit. Owner-view prediction,
excluded opportunity paths and actual portfolio economics remain distinct.
Capacity-constrained counterfactuals require chronological replay with explicit
execution assumptions; summing every excluded path is not a feasible baseline
portfolio. New evidence work remains bounded and does not create a second
execution chain, expand research quota or defer engineering acceptance until
profitability is demonstrated.

## Outcomes

Use one of:

```text
experiment_worthy
observe_only
revise
park
kill
```

Strategy evaluation never creates a Ticket or Exchange Command.
