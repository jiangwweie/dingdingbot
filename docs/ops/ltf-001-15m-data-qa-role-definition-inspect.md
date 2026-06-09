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

# LTF-001 - 15m / Sub-1h Data QA + Role Definition Inspect

**Task ID:** LTF-001
**Date:** 2026-05-07
**Status:** Completed / Docs-only inspect
**Authorization Level:** Level 1/2 - docs-only
**Source:** SMA-001 lower-timeframe candidate map
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document inspects whether ETH/USDT:USDT 15m data is available enough for
future research planning, and defines the proper role of a 15m / sub-1h layer.

This is not:

- a 15m backtest;
- a 15m strategy experiment;
- a research script or adapter;
- parameter optimization;
- runtime/profile/risk/backtester-core work;
- small-live readiness review;
- strategy router, portfolio, or regime-engine design;
- new data pipeline work.

This task used only read-only database QA queries against existing local data.
No strategy logic was executed.

---

## 1. 15m Data Availability

### 1.1 Data Source

| Field | Value |
| --- | --- |
| Database | `data/v3_dev.db` |
| Table | `klines` |
| Symbol | `ETH/USDT:USDT` |
| Timeframe inspected | `15m` |
| Method | Read-only SQL QA |

### 1.2 Coverage

Existing 15m rows:

| Timeframe | Rows | Start UTC | End UTC |
| --- | ---: | --- | --- |
| 15m | 183,936 | 2021-01-01 00:00:00 | 2026-03-31 23:45:00 |

2021-2025 coverage:

| Year | Expected 15m rows | Actual 15m rows | Delta | First bar | Last bar |
| --- | ---: | ---: | ---: | --- | --- |
| 2021 | 35,040 | 35,040 | 0 | 2021-01-01 00:00:00 | 2021-12-31 23:45:00 |
| 2022 | 35,040 | 35,040 | 0 | 2022-01-01 00:00:00 | 2022-12-31 23:45:00 |
| 2023 | 35,040 | 35,040 | 0 | 2023-01-01 00:00:00 | 2023-12-31 23:45:00 |
| 2024 | 35,136 | 35,136 | 0 | 2024-01-01 00:00:00 | 2024-12-31 23:45:00 |
| 2025 | 35,040 | 35,040 | 0 | 2025-01-01 00:00:00 | 2025-12-31 23:45:00 |

Conclusion:

> Existing ETH/USDT:USDT 15m data covers the full 2021-2025 research window.

It does not cover pre-2021 in this table. Existing 1h / 4h data starts in
2020, but this task does not authorize importing older 15m data.

### 1.3 QA Checks

| Check | Full 15m dataset | 2021-2025 window | Result |
| --- | ---: | ---: | --- |
| Duplicate timestamps | 0 | 0 | PASS |
| Timestamp gaps vs 900,000 ms step | 0 | 0 | PASS |
| Misaligned 15m timestamps | 0 | 0 | PASS |
| `is_closed != 1` rows | 0 | 0 | PASS |
| Null OHLCV fields | 0 | 0 | PASS |
| Basic OHLC anomalies | 0 | 0 | PASS |
| Zero-volume 15m bars | 10 | 10 | CAVEAT |

Basic OHLC anomaly definition:

- non-positive open/high/low/close;
- negative volume;
- high below low/open/close;
- low above open/close.

The 10 zero-volume bars are flat OHLC bars. They do not create timestamp gaps,
but they must be treated as data-quality caveats before any Level 3 empirical
research.

### 1.4 1h / 4h Alignment

Coverage counts for 2021-2025:

| Year | Expected 1h | Actual 1h | Expected 4h | Actual 4h |
| --- | ---: | ---: | ---: | ---: |
| 2021 | 8,760 | 8,760 | 2,190 | 2,190 |
| 2022 | 8,760 | 8,760 | 2,190 | 2,190 |
| 2023 | 8,760 | 8,760 | 2,190 | 2,190 |
| 2024 | 8,784 | 8,784 | 2,196 | 2,196 |
| 2025 | 8,760 | 8,760 | 2,190 | 2,190 |

Alignment checks:

| Check | Result |
| --- | ---: |
| 1h anchor timestamps without matching 15m timestamp | 0 |
| 4h anchor timestamps without matching 15m timestamp | 0 |
| 1h buckets with not exactly four 15m bars | 0 |
| 4h buckets with not exactly sixteen 15m bars | 0 |

OHLCV re-aggregation caveat:

| Aggregation check | Mismatch count |
| --- | ---: |
| 15m -> 1h OHLCV mismatch | 3 |
| 15m -> 4h OHLCV mismatch | 4 |

The 1h mismatches are volume-only. The 4h mismatches are mostly volume-only,
with one 2024-10-28 20:00 UTC block where 15m flat zero-volume bars create an
OHLC mismatch versus the stored 4h bar. This is small relative to the full
window, but any future Level 3 task must explicitly decide whether to exclude,
patch, or caveat those bars. LTF-001 does not authorize fixing or importing
data.

### 1.5 Data Availability Verdict

15m data is available for 2021-2025 and is broadly aligned with 1h / 4h.

Classification:

> **DATA_AVAILABLE_WITH_CAVEATS**

The caveats are:

- no pre-2021 15m coverage in current `klines`;
- 10 zero-volume flat 15m bars;
- 3 1h and 4 4h OHLCV re-aggregation mismatches from 15m.

These caveats do not block docs-only role definition. They do block any clean
Level 3 empirical claim until explicitly handled in a future Owner-approved
task.

---

## 2. 15m Role Definition

### 2.1 Role Comparison

| Role | Fit | Information value | Risk | Current judgment |
| --- | --- | --- | --- | --- |
| Execution timing under 4h thesis | Highest | Tests whether lower timeframe can reduce chase / improve fill timing without changing thesis | Can quietly become entry logic if not bounded | Recommended first role |
| 4h main trend + 15m precision entry | Medium-High | Tests whether 15m can refine entry after a frozen 4h parent signal | Overfit local structure; may delete payoff tail | Candidate role after strict parent rules |
| Risk compression / smaller-stop entry | Medium | Tests whether lower timeframe can reduce initial risk | More stop-outs, churn, cost sensitivity | Later role, not first |
| Independent 15m strategy main timeframe | Low | Tests a new primary strategy family | Noise, cost, false breakout, CPM-1 15m warning | Not current-stage fit |

### 2.2 Recommended Role Order

Recommended order:

1. **Execution timing under 4h thesis**
2. **4h main trend + 15m precision entry**
3. **Risk compression / smaller-stop entry**
4. **Independent 15m strategy main timeframe**

The first legitimate 15m research role should be an auxiliary layer under a
frozen 4h parent thesis. 15m should not begin as an independent strategy.

---

## 3. Boundary With Higher Timeframes

### 3.1 Parent Thesis Requirement

For current-stage research, 15m should only be active when a frozen 4h parent
thesis is already active.

Acceptable parent-thesis examples:

- a frozen Direction A-style 4h trend permission;
- a future Owner-approved 4h MTC parent signal;
- a docs-only specified 4h context used only for role definition.

Not acceptable:

- 15m independently deciding trend direction;
- 15m replacing the parent thesis after seeing results;
- 15m selecting which 4h signals are valid through post-hoc filters.

### 3.2 Direction Judgment

15m should not independently produce directional bias in the current stage.

Allowed:

- timing an already-approved long entry window;
- measuring local entry quality;
- reducing execution chase if the 4h thesis remains intact.

Not allowed:

- opening trades from standalone 15m signals;
- flipping direction;
- declaring a 15m trend regime;
- overriding the 4h thesis.

### 3.3 Exit Lifecycle

15m should not define exit lifecycle by default.

For an execution-timing layer, exit should remain owned by the parent 4h
strategy. A 15m exit rule would be a new strategy module or overlay and must be
separately inspected.

### 3.4 Preventing Execution Layer Drift

If 15m is only an execution layer, future specs must enforce:

- parent 4h signal must exist before any 15m condition is evaluated;
- 15m can only choose timing inside a pre-defined window;
- 15m cannot skip trades using post-hoc no-trade gates unless that skip rule is
  pre-registered;
- 15m cannot define stop, exit, lifecycle, or direction unless separately
  authorized;
- every result must compare against the same parent 4h baseline and report
  whether the parent payoff tail was preserved.

---

## 4. 15m Risk Register

| Risk | Why it matters for 15m | Required future control |
| --- | --- | --- |
| Fee sensitivity | Higher frequency can turn gross edge into net loss | Stricter cost model; cost as % of gross; turnover report |
| Slippage sensitivity | 15m entries/stops are closer to microstructure noise | Adverse slippage scenarios required |
| Same-bar / intrabar ambiguity | Smaller bars reduce duration but do not solve order ambiguity | Explicit ordering, conflict counts, pessimistic rules |
| False breakout | Local structure breaks are frequent and noisy | Parent 4h constraint; no standalone breakout search |
| Signal churn | Many signals can cluster in the same move/chop | Signal independence report by day/week/regime |
| Overfitting | More windows, buffers, and timing rules become tempting | One frozen role/rule; no sweep |
| Top-N fragility | More trades can still depend on few winners | Stricter top-N, likely top-5/top-10 review |
| Trade count quality | High trade count may mean lower quality, not stronger evidence | Winner count, independent opportunity count, net-after-cost focus |

The key 15m danger is false confidence: trade count can rise while evidence
quality falls.

---

## 5. CPM-1 15m Old Evidence Interpretation

The CPM-1 scope note records ETH 15m as:

> Too many trades with poor signal quality.

Interpretation:

- It rejects direct CPM-1 migration to 15m.
- It rejects treating Pinbar-style 15m pullback continuation as a ready path.
- It lowers the priority of any 15m pullback-entry concept.
- It does not permanently invalidate all 15m research.

The distinction is important:

| 15m concept | Impact of CPM-1 15m evidence |
| --- | --- |
| CPM-1 Pinbar directly moved to 15m | Rejected |
| 15m pullback-entry as a new primary strategy | Priority lowered materially |
| 15m precision entry under frozen 4h parent thesis | Still possible, but strict boundaries required |
| 15m execution timing under frozen 4h parent thesis | Still the best candidate role |

Any future 15m pullback-entry should be managed under the broader
pullback-continuation family. If it repeats CPM-like churn and poor quality,
it should reinforce family pause rather than generate another trigger branch.

---

## 6. Future Level 3 Preconditions

15m is not currently Level 3 admissible. It becomes admissible only if all
preconditions below are satisfied in a future Owner-approved task:

| Precondition | Requirement |
| --- | --- |
| Role frozen | State whether 15m is execution timing, precision entry, risk compression, or independent strategy |
| Parent 4h thesis frozen | Define the parent signal before any 15m condition is evaluated |
| Cost/slippage model stricter | Use harsher cost/slippage assumptions than sparse 4h research |
| Same-bar/intrabar policy | Pre-register ordering, conflict handling, and reporting |
| Trade count / winner count gates | Define higher floors than 4h because 15m samples are more correlated |
| Top-N removal | Require stricter top-N review, likely top-5/top-10 |
| Signal independence | Report clustering so churn does not masquerade as evidence |
| Failure closure condition | State what failure closes, e.g. "15m does not improve entry timing after realistic costs" |
| No parameter sweep | One frozen role/rule; no buffers, windows, or variants after result |
| Data caveat handling | Decide how to treat zero-volume bars and 15m->1h/4h re-aggregation mismatches |

If these are not satisfied, 15m remains inspect-only.

---

## 7. Owner Summary

### 7.1 Is 15m Data Available?

Yes, for 2021-2025.

Classification:

> **DATA_AVAILABLE_WITH_CAVEATS**

The data fully covers 2021-2025 with no timestamp gaps, no duplicates,
complete `is_closed`, and no basic OHLC anomalies. Caveats are 10 zero-volume
flat bars and a small number of 15m-to-1h/4h re-aggregation mismatches.

### 7.2 Recommended 15m Role

Recommended role:

1. Execution timing under a frozen 4h thesis.
2. Then, only if justified, 4h main trend + 15m precision entry.
3. Risk compression later.
4. Independent 15m main strategy is not recommended for the current stage.

### 7.3 Recommend Level 3 Now?

No.

Reason:

- Role is not frozen yet.
- Parent 4h thesis is not selected/frozen for 15m use.
- 15m-specific cost, slippage, same-bar, top-N, and signal-independence gates
  are not yet specified.
- Data caveats need explicit handling before empirical claims.

### 7.4 If Level 3 Is Later Recommended

Required preconditions:

- freeze 15m role;
- freeze parent 4h thesis;
- define stricter cost/slippage model;
- define same-bar/intrabar policy;
- define trade/winner count gates;
- define top-N removal gates;
- define failure closure condition;
- explicitly prohibit parameter sweep.

### 7.5 Non-Authorization

LTF-001 does not authorize:

- 15m backtests;
- 15m strategy scripts;
- backtester changes;
- runtime/profile/risk changes;
- 15m experiments;
- small-live;
- treating 15m as an immediate mainline.

---

## 8. Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-05-07 | Initial LTF-001 15m data QA and role definition inspect | Codex |
