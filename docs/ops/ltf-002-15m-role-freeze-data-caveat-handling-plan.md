# LTF-002 - 15m Role Freeze + Data Caveat Handling Plan

**Task ID:** LTF-002
**Date:** 2026-05-07
**Status:** Completed / Docs-only role freeze and caveat plan
**Authorization Level:** Level 1/2 - docs-only
**Source:** LTF-001 data QA; SMA-002 applicability-map update
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document freezes the current research role for the ETH/USDT:USDT 15m /
sub-1h auxiliary layer and defines how known data caveats must be handled
before any future empirical work.

It is not:

- a 15m backtest;
- a 15m strategy experiment;
- a 15m strategy script;
- parameter optimization;
- database repair;
- data deletion or patching;
- backtester/runtime/profile/risk work;
- strategy router, portfolio, or regime-engine design;
- small-live or runtime-candidate review.

No data is modified by this document. No Level 3 experiment is authorized.

---

## 1. 15m Role Freeze

### 1.1 Recommended Role Ranking

| Rank | Candidate role | Current judgment | Reason |
| --- | --- | --- | --- |
| 1 | Execution timing under frozen 4h thesis | **Default frozen role** | Most bounded use of 15m; can test timing/fill improvement without letting 15m define strategy thesis |
| 2 | 4h main trend + 15m precision entry | Candidate later role | Plausible, but higher risk of turning 15m into an entry-filter strategy |
| 3 | Risk compression / smaller-stop entry | Later role only | Potentially useful, but high churn, stop-out, cost, and same-bar sensitivity |
| 4 | Independent 15m strategy main timeframe | Not allowed in current stage | Too much noise/cost/overfit risk; conflicts with SMA-002 classification |

### 1.2 Default Frozen Role

Default frozen role:

> **15m is an execution-timing layer under a frozen 4h parent thesis.**

Under this role:

- 15m may only help choose timing inside a pre-defined parent 4h entry window.
- 15m must serve the parent 4h thesis.
- 15m cannot create a standalone trade thesis.
- 15m cannot change the parent direction, trend state, stop logic, or exit lifecycle.

### 1.3 Default Prohibitions

By default, 15m is not allowed to:

- independently produce direction judgment;
- independently define the main trend;
- independently decide whether a 4h thesis exists;
- independently define exit lifecycle;
- open trades from standalone 15m signals;
- flip or override the parent 4h direction;
- become a hidden CPM-2, Direction D, or lower-timeframe pullback strategy.

Changing the 15m role requires a new Owner approval before any empirical work.

---

## 2. Parent Thesis Requirements

Before any future 15m Level 3 request, the parent 4h thesis must be frozen
first. LTF-002 does not choose a specific parent strategy; it defines the
minimum parent-thesis contract.

### 2.1 Required Parent Contract

| Parent element | Must be frozen before Level 3 |
| --- | --- |
| Parent direction source | Which 4h source owns LONG/SHORT permission; 15m cannot infer or reverse it |
| Parent trend condition | What makes the parent 4h thesis active; must be defined before 15m inspection |
| Parent invalidation condition | What cancels the parent thesis before or during the 15m timing window |
| Parent exit / lifecycle authority | Which higher-timeframe rule owns exit; 15m does not own lifecycle by default |
| Parent entry window | When 15m is allowed to evaluate timing after parent activation |
| Parent baseline comparator | The fixed 4h behavior against which 15m timing is compared |
| Conflict rule | What happens if 15m conflicts with parent thesis |

### 2.2 15m Authority Under Parent Thesis

Default authority:

- 15m only controls execution timing.
- 15m may defer or time an entry inside the frozen parent window.
- 15m may not reject the parent thesis after results are known.
- 15m may not create additional directional exposure.
- 15m may not define exit or stop lifecycle unless separately approved.

### 2.3 Conflict Handling

Default conflict rule:

> If a 15m signal conflicts with the frozen 4h parent thesis, the 15m signal is
> ignored. Parent thesis authority wins.

Future Level 3 specs must define:

- whether 15m can only confirm timing or can also abstain inside a window;
- whether missed timing means no trade or parent fallback entry;
- whether 15m timing may delay entry beyond the parent window;
- how many 15m attempts are allowed per parent thesis;
- how signal clustering is counted.

These are preconditions, not strategy rules selected by LTF-002.

---

## 3. Data Caveat Handling Options

LTF-001 classified ETH/USDT:USDT 15m data as:

> **DATA_AVAILABLE_WITH_CAVEATS**

Known caveats:

- 10 zero-volume flat 15m bars;
- 3 15m -> 1h OHLCV re-aggregation mismatches;
- 4 15m -> 4h OHLCV re-aggregation mismatches;
- one 2024-10-28 20:00 UTC 4h block where flat zero-volume 15m bars create an
  OHLC mismatch versus stored 4h;
- no pre-2021 15m coverage in current `klines`.

LTF-002 does not repair or modify data. It only defines future handling choices.

### 3.1 Caveat Option Matrix

| Caveat | Exclude | Patch | Mark-as-caveat | Leave-as-is with sensitivity note | Block Level 3 until resolved |
| --- | --- | --- | --- | --- | --- |
| 10 zero-volume flat 15m bars | Possible: exclude affected bars/windows from empirical claims | Possible only with separate data-repair approval | Required minimum | Possible for inspect-only; risky for Level 3 | Required if trade entries/exits can touch affected bars |
| 15m -> 1h OHLCV mismatch | Possible for affected parent windows | Possible only with separate data-repair approval | Required minimum | Possible if volume-only and not used by rule | Required if 1h alignment is used in metrics/rules |
| 15m -> 4h OHLCV mismatch | Possible for affected parent windows | Possible only with separate data-repair approval | Required minimum | Risky because parent thesis is 4h | Required if mismatch touches parent thesis bars |
| 2024-10-28 20:00 UTC 4h block mismatch | Recommended exclusion for any future Level 3 window using that block | Possible only with separate Owner-approved data task | Required | Not recommended for Level 3 | Required unless excluded |
| No pre-2021 15m coverage | Exclude pre-2021 from 15m claims | Import/patch only through separate data task | Required | Acceptable if research window is 2021-2025 only | Blocks any pre-2021 15m claim |

### 3.2 Option Meanings

`exclude` means the future empirical task explicitly removes affected bars,
parent windows, or trades from eligibility before execution.

`patch` means the source data is repaired or re-imported. This requires a
separate Owner-approved data task and must not be hidden inside strategy
research.

`mark-as-caveat` means the report discloses the issue and shows affected
timestamps, but does not change data.

`leave-as-is with explicit sensitivity note` means the issue is accepted as
non-material for a particular role, with a written explanation. This is not
acceptable if the affected bars can determine entries, exits, stops, or parent
thesis state.

`block Level 3 until resolved` means a future empirical task cannot proceed
until it either excludes affected data or completes a separate approved repair.

---

## 4. Recommended Caveat Policy

### 4.1 Required Before Future Level 3

Before any 15m Level 3 request, the task must:

- list exact affected timestamps / parent blocks from LTF-001 or a read-only QA
  refresh;
- define whether affected bars are excluded or handled by a separate data task;
- state whether 15m is used only for execution timing or for any price/volume
  condition;
- state whether parent 4h bars are sourced from stored 4h data or 15m
  aggregation;
- define how any mismatch can affect entries, exits, stops, MFE/MAE, and
  same-bar calculations.

### 4.2 Recommended Handling By Caveat

| Caveat | Recommended policy | Why |
| --- | --- | --- |
| 10 zero-volume flat 15m bars | Exclude affected 15m bars and any 15m entry/exit decision that would depend on them in Level 3; mark in report | They can distort local range, intrabar assumptions, and stop/entry timing |
| 15m -> 1h volume-only mismatches | Mark-as-caveat if volume is not used; exclude if any volume feature or 1h aggregation is used | Volume mismatch is low impact only if volume is not part of the rule or metric |
| 15m -> 4h mismatches | Exclude affected parent 4h windows unless a separate data task resolves them | Parent thesis is 4h; mismatch can undermine parent/child alignment |
| 2024-10-28 20:00 UTC 4h block | Mandatory exclusion from Level 3 eligibility unless separately repaired | It includes OHLC mismatch tied to zero-volume flat 15m bars |
| No pre-2021 15m coverage | Restrict all 15m claims to 2021-2025; do not compare to pre-2021 1h/4h evidence | Missing lower-timeframe history blocks pre-2021 15m conclusions |

### 4.3 When Separate Owner Approval Is Required

Separate Owner approval is required for:

- any DB patch;
- any data deletion;
- any data import or new data pipeline;
- any generated data-repair script;
- any decision to treat repaired data as canonical;
- any empirical 15m Level 3 using patched data.

### 4.4 Validity Impact If Unhandled

Unhandled caveats can invalidate future backtest claims if:

- a trade enters, exits, stops, or measures MFE/MAE on a zero-volume flat bar;
- 15m aggregation is used to validate 4h parent state and the affected 4h block
  is mismatched;
- volume is part of any 15m condition while volume-only mismatches are ignored;
- pre-2021 comparisons imply lower-timeframe evidence that does not exist.

---

## 5. 15m-Specific Evaluation Gates

Future 15m Level 3, if separately authorized, must satisfy stricter gates than
4h-only research because lower-timeframe evidence is more cost-sensitive and
more correlated.

| Gate | Minimum requirement |
| --- | --- |
| Stricter cost model | Use costs at least as conservative as current backtests and explicitly report total fee/slippage drag |
| Slippage sensitivity | Include pre-registered adverse slippage sensitivity; no threshold tuning after results |
| Same-bar / intrabar policy | Pre-register execution ordering, ambiguity handling, and conflict counts |
| Trade count floor | Set a higher floor than 4h research because 15m samples are more correlated |
| Winner count floor | Set a higher winner floor and report independent winner clusters |
| Top-1 / top-3 / top-5 removal | Required; add top-10 if trade count is high |
| Signal churn | Report signals per parent thesis, per day/week, and clustered repeated attempts |
| Average holding time | Report distribution; very short holds require stronger cost and same-bar scrutiny |
| Fee drag | Report fees as percentage of gross profit and gross loss |
| Parent-thesis alignment | Every 15m action must link to a parent 4h thesis id/window |
| Signal independence | Count independent parent opportunities, not just 15m bars or repeated local signals |
| False breakout / whipsaw diagnostics | Report rapid invalidations, immediate reversals, and repeated stop-outs |
| MFE / MAE / giveback | Required at trade level and by parent-thesis cluster |
| MTM drawdown | Required; not just realized closed-trade drawdown |
| Year-by-year | Required for 2021-2025; no aggregate-only conclusion |
| Failure closure condition | Predefine what failure closes, e.g. "15m execution timing does not improve parent entry after costs" |

Any 15m result that improves only by suppressing bad parent trades after the
fact should be treated as post-hoc filtering, not execution timing.

---

## 6. Relationship To Pullback-Continuation Family

15m has two possible family relationships:

| 15m usage | Family treatment |
| --- | --- |
| Execution timing under frozen 4h thesis | Lower-timeframe auxiliary; not automatically pullback-continuation |
| 4h parent + 15m pullback-entry | Pullback-continuation family |
| 15m risk compression via local pullback stop | Pullback-continuation risk until proven otherwise |
| Independent 15m pullback strategy | Not allowed now; if ever proposed, manage under pullback-continuation |

Rules:

- 15m pullback-entry, if ever researched, must be managed with CPM-1 and
  Direction D under the pullback-continuation family.
- 15m cannot bypass CPM-1 / Direction D historical failures by claiming that
  lower timeframe data is available.
- `DATA_AVAILABLE_WITH_CAVEATS` means research infrastructure may be possible;
  it does not mean a 15m strategy is worth experimenting.
- If 15m is only execution timing, specs must prevent drift into CPM-2,
  Direction D, or a hidden pullback-continuation variant.
- If 15m shows CPM-like churn, poor signal quality, or top-winner fragility, it
  should reinforce family caution rather than spawn a new trigger branch.

---

## 7. Level 3 Readiness Classification

| Dimension | Current classification | Reason |
| --- | --- | --- |
| Data | `DATA_AVAILABLE_WITH_CAVEATS` | Full 2021-2025 coverage and clean timestamps, but zero-volume bars and aggregation mismatches remain |
| Role | `ROLE_FROZEN` for default execution-timing role; other roles not frozen | LTF-002 freezes the default role but does not authorize precision-entry/risk-compression/independent roles |
| Level 3 | `NOT_LEVEL_3_READY` | Parent 4h thesis, caveat execution policy, cost/same-bar gates, and failure closure are not yet frozen in a Level 3 task card |
| Runtime readiness | Not applicable / not ready | No runtime candidate, no small-live strategy |

Recommended current path:

1. Continue docs-only.
2. If needed, prepare a future Level 1/2 parent-thesis selection note.
3. If Owner later wants Level 3, write a separate task card that freezes parent
   thesis, 15m authority, caveat exclusion/repair policy, evaluation gates, and
   failure closure.

No immediate 15m Level 3 is recommended.

---

## 8. Owner Summary

### 8.1 Default Frozen Role

15m default role is frozen as:

> **Execution timing under a frozen 4h parent thesis.**

15m does not independently produce direction, define main trend, decide exit
lifecycle, or create standalone strategy authority.

### 8.2 Data Caveat Policy

Recommended policy:

- zero-volume flat 15m bars: exclude affected 15m decision bars in any future
  Level 3 and mark them in the report;
- 15m -> 1h volume-only mismatches: mark-as-caveat if volume is unused; exclude
  if volume or 1h aggregation is used;
- 15m -> 4h mismatches: exclude affected parent windows unless separately
  repaired;
- 2024-10-28 20:00 UTC 4h block: mandatory exclusion from future Level 3
  eligibility unless separately repaired;
- no pre-2021 15m coverage: restrict 15m claims to 2021-2025.

### 8.3 Data Repair Task

A separate data repair task is not required for docs-only planning.

It is required only if Owner wants to patch/delete/import data or treat repaired
data as canonical. Any such task needs separate Owner approval.

### 8.4 Recommend Level 3?

Not now.

Reason:

- parent 4h thesis is not selected and frozen;
- future caveat exclusion/repair policy is not yet encoded in a Level 3 task;
- 15m-specific cost, slippage, same-bar, churn, and top-N gates are not yet tied
  to a specific experiment;
- 15m remains an auxiliary candidate, not an immediate mainline.

If Level 3 is later requested, preconditions are:

- frozen parent 4h thesis;
- frozen 15m execution-timing authority;
- explicit caveat handling policy;
- stricter cost/slippage and same-bar policy;
- trade/winner count floors;
- top-N removal;
- parent-thesis alignment and signal-independence reporting;
- failure closure condition;
- no parameter sweep.

### 8.5 Non-Authorization

LTF-002 does not authorize:

- 15m backtests;
- 15m strategy scripts;
- data patching, deletion, import, or DB modification;
- backtester/runtime/profile/risk changes;
- 15m Level 3;
- independent 15m main strategy;
- strategy router, portfolio, or regime engine;
- runtime candidate or small-live conclusion.

Small-live readiness remains unmet.

---

## 9. Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-05-07 | Initial LTF-002 role freeze and data caveat handling plan | Codex |
