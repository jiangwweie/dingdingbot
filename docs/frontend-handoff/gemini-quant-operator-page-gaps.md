# Quant Operator Page Gaps

This document lists the additional pages that are worth adding from the perspective of
an actual low-frequency quant operator using the console for Sim-1, simulated trading,
and later live observation.

The goal is not to turn the frontend into a configuration workbench yet. The goal is to
close the gap between "the system runs" and "a human can monitor and understand it".

---

## 1. Recommendation Summary

If the current scaffold already includes:

- Runtime / Overview
- Runtime / Signals
- Runtime / Execution
- Runtime / Health
- Research / Candidates
- Research / Candidate Detail
- Research / Replay
- Research / Backtests
- Research / Compare

Then the next pages worth adding are:

1. `Runtime / Portfolio`
2. `Runtime / Events`
3. `Config / Snapshot` (read-only preview only)

Priority from operator value:

1. `Runtime / Portfolio`
2. `Runtime / Events`
3. `Config / Snapshot`

---

## 2. Why These Pages Matter

### 2.1 Runtime / Portfolio

This is the missing page with the highest real operator value.

From a quant operator perspective, people do not only care about:

- signals
- attempts
- intents

They also immediately care about:

- current account equity
- available balance
- unrealized PnL
- open positions
- total exposure
- daily loss usage
- leverage usage
- margin safety

Without a portfolio/risk page, the operator still needs to jump to exchange UI or logs
to understand whether the system is currently safe.

This page should stay read-only.

Suggested sections:

- equity summary
- available balance
- unrealized PnL
- current open positions
- exposure usage
- daily max loss usage
- single-trade risk usage
- leverage / margin summary

---

### 2.2 Runtime / Events

The system already has warnings, startup markers, recovery, breaker, reconciliation,
and execution transitions.

A quant operator usually wants a unified "what happened recently" view.

This page should function as a read-only event/journal timeline.

Suggested event categories:

- startup markers
- reconciliation events
- breaker events
- recovery task events
- warning/error summaries
- signal accepted/rejected summaries
- execution lifecycle events

Why it matters:

- much faster than reading raw logs
- improves incident understanding
- helps answer "when did the system start drifting?"

---

### 2.3 Config / Snapshot (Read-only Preview)

Yes, this page is worth adding, but only as a **preview / snapshot** page.

Do **not** turn it into a config editor.

From a quant user's perspective, this page answers:

- what profile is running now?
- what exact strategy/risk/execution settings are active?
- what market scope is active?
- which values are frozen?
- what is runtime vs baseline vs candidate-derived?

This is especially important because the project already has:

- runtime profile
- backtest baseline
- candidate-only outputs
- explicit "no hot change during Sim-1" rules

Suggested sections:

- runtime profile identity
  - profile / version / hash
- market config preview
  - symbols / timeframes / MTF
- strategy preview
  - strategy name / direction / key parameters
- risk preview
  - max_loss_percent / daily_max_loss_percent / max_total_exposure / leverage
- execution preview
  - TP targets / TP ratios / stop behavior / same-bar policy
- backend summary
  - execution intent backend / order backend / position backend
- source-of-truth hints
  - environment vs runtime profile vs code defaults

This page must be:

- read-only
- clearly labeled "snapshot"
- explicit that changes are not supported from UI

---

## 3. Why Not Build a Config Editor Yet

A real quant operator definitely wants to know the current config.

But at the current stage, editing from UI would be dangerous because:

- Sim-1 runtime is frozen
- strategy/risk hot changes are intentionally forbidden
- config truth is still carefully controlled

Therefore:

- **build preview**
- **do not build editing**

That is the right middle ground.

---

## 4. Suggested Navigation Expansion

Recommended navigation once these pages are added:

```text
Trading Console
├── Runtime
│   ├── Overview
│   ├── Portfolio
│   ├── Signals
│   ├── Execution
│   ├── Events
│   └── Health
├── Research
│   ├── Candidates
│   ├── Candidate Detail
│   ├── Replay
│   ├── Backtests
│   └── Compare
└── Config
    └── Snapshot
```

---

## 5. Interface Suggestions

### P0.5 / P1-level additional APIs

#### `GET /api/runtime/portfolio`

Returns:

- total_equity
- available_balance
- unrealized_pnl
- total_exposure
- daily_loss_used
- daily_loss_limit
- max_total_exposure
- positions[]

#### `GET /api/runtime/events`

Returns:

- recent event timeline items
- category
- severity
- message
- timestamp
- related entity ids

#### `GET /api/config/snapshot`

Returns:

- profile identity
- market snapshot
- strategy snapshot
- risk snapshot
- execution snapshot
- backend snapshot
- source-of-truth hints
- frozen flags

---

## 6. Build Order Recommendation

If Gemini is continuing page expansion, recommend this order:

1. `Runtime / Portfolio`
2. `Runtime / Events`
3. `Config / Snapshot`

Reason:

- Portfolio has the highest real operator value
- Events most directly reduces log-reading pain
- Config Snapshot is very useful, but less urgent than risk/portfolio awareness

---

## 7. Final Recommendation

Yes, the console should add a configuration-related page, but it should be:

- `Config / Snapshot`
- read-only
- clearly positioned as preview / frozen runtime snapshot

Not:

- config editor
- strategy builder
- runtime mutation panel

From a quant operator perspective, that is the right next step.
