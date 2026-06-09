> [!NOTE]
> **HISTORICAL_EVIDENCE** — This document is a historical operational, governance, sprint, product, or live-trial artifact from an earlier project phase.
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

# Strategy Family Map v0

Date: 2026-05-26
Status: DESIGN_BASELINE

## Purpose

The project should not pursue a universal strategy that works in every market
state. The better model is:

```text
multiple bounded playbook candidates
-> selected by market context and Owner judgment
-> wrapped by BRC risk controls
-> tested in simulation/testnet first
-> reviewed with evidence.
```

This document defines the first strategy-family map. It is a design and
governance asset, not an automatic strategy pool or runtime router.

## Core Principle

Do not frame the system as:

```text
find one universal strategy -> auto execute forever.
```

Frame it as:

```text
identify market state -> choose a suitable playbook -> run a bounded BRC
campaign -> protect profit or lock loss -> review -> decide the next attempt.
```

BRC does not create market edge. It creates risk boundaries, behavior
discipline, traceability, and review.

## Strategy Family vs Playbook

| Object | Meaning |
| --- | --- |
| Strategy Family | A broad market mechanism family, such as trend following or pullback continuation. |
| Playbook | A concrete operating candidate inside a strategy family, such as `TF-001` or `CPM-1`. |
| Monitor Profile | A non-trading observation configuration for a playbook. |
| BRC Campaign Binding | The BRC wrapper: risk envelope, max attempts, loss lock, profit protect, and evidence packet. |

## Status Model

| Status | Meaning |
| --- | --- |
| `Idea` | Only an idea. |
| `Intake` | One-page brief is being written or reviewed. |
| `Research Candidate` | Worth a minimum research task. |
| `Backtest Candidate` | Owner may approve an isolated script backtest. |
| `Conditional Candidate` | Can be considered only under specific market states. |
| `BRC Rehearsal Candidate` | Can enter simulation/testnet BRC rehearsal after Owner approval. |
| `Active Playbook` | Currently allowed for a bounded campaign. |
| `Paused` | Temporarily not allowed. |
| `Rejected` | Not pursued now. |
| `Archived Evidence` | Preserved as historical evidence. |
| `Reserve` | Not active now, but kept as a future candidate. |
| `Filter Candidate` | Used as a filter/helper, not a standalone strategy. |
| `Watchlist` | Worth watching, not ready for intake. |

## Initial Strategy Families

| Priority | Family | Playbook | Status | Role |
| ---: | --- | --- | --- | --- |
| 1 | Trend Following | `TF-001` | `Intake` / `Carrier Validation` | First BRC-R5 carrier; validates full chain, not alpha. |
| 2 | Pullback Continuation | `CPM-1` | `Conditional Candidate` | Reframed as market-sensitive pullback playbook. |
| 3 | Volatility Contraction Breakout | `VB-001` | `Reserve` | Second candidate; not current work. |
| 4 | Multi-Timeframe Momentum | `MTF-001` | `Filter Candidate` | Filter/helper for trend, CPM, or breakout. |
| 5 | Funding / OI / Event | TBD | `Watchlist` | Future observation candidate. |
| - | ML Strategy | none | `Rejected for Now` | Too complex and low explainability for current stage. |
| - | HFT / Orderbook | none | `Rejected for Now` | Infrastructure and data requirements do not fit current stage. |

## Trend Following / TF-001

Plain meaning:

```text
Do not guess top or bottom. Follow the middle part of an already visible move.
```

Why it is the first carrier:

- simple logic;
- explainable failure modes;
- compatible with low-frequency BTC/ETH;
- easy to monitor;
- suitable for BRC max-attempt and loss-lock validation.

R5 use:

```text
TF-001 is a carrier validation playbook, not a profitability claim.
```

R5 should verify whether TF-001 can be selected, monitored, switched into
simulation/testnet trade, paused, stopped, flattened, audited, and reviewed.

R5 should not optimize TF-001 parameters or claim live readiness.

## Pullback Continuation / CPM-1

CPM is no longer treated as simply failed or permanently archived.

The updated classification is:

```text
Family: Pullback Continuation
Playbook: CPM-1
Status: Conditional Candidate
```

Interpretation:

- weak years provide disable-boundary evidence;
- strong periods, including the Owner-noted 2024 behavior, may provide
  applicability clues;
- CPM should not be run year-round or directly promoted to live;
- CPM may be considered later as a conditional playbook with explicit
  enable/disable gates.

Possible enable conditions:

- higher-timeframe trend is not broken;
- BTC/ETH show relative strength or repair structure;
- pullback depth is within a normal range;
- volatility is not extreme;
- previous CPM campaign is not loss-locked;
- latest relevant campaign is reviewed;
- Owner explicitly chooses CPM.

Possible disable conditions:

- deep bear market;
- trend break;
- repeated false bounces;
- extreme volatility;
- prior unresolved review;
- current BRC loss lock;
- attempt to reset losses by switching playbooks.

## Volatility Contraction Breakout / VB-001

Plain meaning:

```text
Market quiets down, volatility contracts, and a later breakout may release
directional movement.
```

Current status: `Reserve`.

Reason:

- promising for bounded attempts;
- failure mode is understandable as false breakout;
- but requires clearer definitions for contraction, breakout validity,
  re-entry timing, and volume/body confirmation.

Do not start this before TF-001 carrier validation.

## Multi-Timeframe Momentum / MTF-001

Plain meaning:

```text
Large timeframe decides direction; smaller timeframe only refines observation
or entry context.
```

Current status: `Filter Candidate`.

It should support other families rather than become a standalone strategy in
the current stage.

Risk:

- too many timeframes;
- too many indicators;
- failed tests triggering endless new filters;
- parameter puzzle behavior.

## Rejected For Now

### ML Strategy

Rejected for now because it requires larger datasets, feature engineering,
overfit controls, and explainability that does not match the current BRC
delivery goal.

### HFT / Orderbook

Rejected for now because it requires latency, market microstructure data,
execution sophistication, and infrastructure that do not fit the current
personal low-frequency BRC system.

## Strategy Family To BRC Admission Questions

Before any family/playbook enters BRC rehearsal, it must answer:

Strategy questions:

1. What market behavior does it try to capture?
2. Which market structure does it depend on?
3. In which market states does it fail?
4. What are the entry and exit conditions?
5. What does a single failure look like?
6. Can it fail repeatedly?

BRC questions:

1. Maximum campaign loss?
2. Maximum attempts?
3. Loss-lock trigger?
4. Profit-protect trigger?
5. Cooldown rule?
6. Is playbook switching allowed?
7. Does switching preserve accumulated loss state?

Owner questions:

1. Does Owner understand the playbook?
2. Does Owner accept the failure mode?
3. Is it research-only, monitor-only, simulation/testnet, or live?
4. Has Owner explicitly authorized the next stage?

## Current R5 Usage

R5 should not build a full strategy pool.

R5 should use `TF-001` as the existing trend-strategy carrier to validate:

- Owner natural-language request;
- LLM status query and risk advice;
- action card;
- monitor-state switch;
- simulation/testnet trade flow;
- pause/stop/flatten controls;
- audit trace;
- review packet.

All other strategy families remain design/governance records until separately
approved.
